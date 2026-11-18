"""Fontes de mercado e o formato do rastreio.

Regra do projeto: todo número mostrado no site vem com o caminho até a fonte.
  rastro = {"valor", "componentes": [comp...], "nota"}
  comp   = {"sinal", "papel", "fonte", "documento", "url", "data_ref", "periodo",
            "conta", "descricao", "valor", ...}

Fontes:
- Banco Central (SGS): PTAX (série 1) e CDI anualizado (série 4389) — oficiais
- yfinance (Yahoo Finance): preços históricos e proventos
- CoinGecko: preço atual de cripto, usado só como conferência
"""
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np
import pandas as pd
import requests
import yfinance as yf

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
SGS_PAGINA = "https://www3.bcb.gov.br/sgspub/consultarvalores/telaCvsSelecionarSeries.paint"
SERIE_PTAX = 1      # Dólar americano (venda), PTAX, diário — R$ por US$
SERIE_CDI = 4389    # CDI anualizado base 252, % a.a., diário


# ---------- rastreio ----------
def comp(sinal: str, papel: str, linha: dict) -> dict:
    return {"sinal": sinal, "papel": papel, **linha}


def rastro(valor, componentes, nota="") -> dict:
    v = None if valor is None or (isinstance(valor, float) and np.isnan(valor)) else float(valor)
    return {"valor": v, "componentes": componentes, "nota": nota}


def url_yahoo(simbolo: str) -> str:
    return f"https://finance.yahoo.com/quote/{simbolo}/history/"


def br(data) -> str:
    return pd.Timestamp(data).strftime("%d/%m/%Y")


# ---------- Banco Central ----------
def sgs(serie: int, inicio, fim) -> tuple[pd.Series, str]:
    """Série do SGS entre duas datas. Retorna (série, url exata consultada)."""
    url = f"{SGS.format(serie=serie)}?formato=json&dataInicial={br(inicio)}&dataFinal={br(fim)}"
    # A API do BC oscila (502/503/504 ou demora) por alguns segundos: tenta de novo antes de desistir.
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code < 500:
                break
        except (requests.ConnectionError, requests.Timeout):
            if tentativa == 2:
                raise
        time.sleep(1 + 2 * tentativa)  # 1 s, depois 3 s
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.Series(dtype=float), url
    s = pd.Series(df["valor"].astype(float).values, index=pd.to_datetime(df["data"], dayfirst=True))
    return s.sort_index(), url


def chave_preco(agora: datetime | None = None) -> str:
    """Chave de cache para preços: muda a cada 15 minutos com a B3 aberta e uma vez por dia fora do pregão.

    Pregão regular: segunda a sexta, das 10h às 18h de Brasília (UTC−3; o Brasil não tem horário de verão desde 2019,
    então o fuso fixo evita depender do banco de fusos horários, que falta em muitas instalações do Windows).
    """
    agora = agora or datetime.now(timezone(timedelta(hours=-3)))
    dia = agora.strftime("%Y-%m-%d")
    if agora.weekday() < 5 and 10 <= agora.hour < 18:
        return f"{dia} {agora.hour:02d}:{agora.minute // 15 * 15:02d}"
    return dia


@lru_cache(maxsize=1)
def _cdi_cache(dia: str) -> dict:
    fim = pd.Timestamp(dia)
    s, url = sgs(SERIE_CDI, fim - pd.Timedelta(days=15), fim)
    if s.empty:
        raise LookupError("O Banco Central não retornou o CDI.")
    data, v = s.index[-1], float(s.iloc[-1])
    return rastro(v, [comp("+", "Último CDI publicado", {
        "fonte": "Banco Central", "documento": f"SGS · série {SERIE_CDI}", "url": url,
        "data_ref": data.strftime("%Y-%m-%d"), "periodo": f"dia {data:%Y-%m-%d}",
        "conta": str(SERIE_CDI), "descricao": "Taxa de juros — CDI anualizada base 252 (% a.a.)", "valor": v})],
        "Taxa oficial publicada pelo Banco Central. É a referência de 'renda fixa sem risco' usada no Sharpe.")


def cdi_atual() -> dict:
    return _cdi_cache(pd.Timestamp.now().strftime("%Y-%m-%d"))


# ---------- yfinance ----------
def historico_yf(simbolo: str, periodo: str) -> pd.Series:
    df = yf.download(simbolo, period=periodo, auto_adjust=True, progress=False)
    if df.empty:
        return pd.Series(dtype=float)
    s = df["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.dropna()


def proventos_12m(simbolo: str) -> dict:
    dvd = yf.Ticker(simbolo).dividends
    comps = []
    if not dvd.empty:
        dvd.index = dvd.index.tz_localize(None)
        for dt, v in dvd[dvd.index >= pd.Timestamp.now() - pd.DateOffset(years=1)].items():
            d = dt.strftime("%Y-%m-%d")
            comps.append(comp("+", "Provento", {
                "fonte": "yfinance", "documento": "Ticker.dividends", "url": url_yahoo(simbolo),
                "data_ref": d, "periodo": f"data-ex {d}", "conta": "Dividends",
                "descricao": "Provento por cota/ação", "valor": float(v)}))
    return rastro(sum(c["valor"] for c in comps), comps,
                  "Soma dos proventos com data-ex nos últimos 12 meses (yfinance)." if comps else
                  "Nenhum provento com data-ex nos últimos 12 meses no yfinance.")


# ---------- CoinGecko (conferência) ----------
COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}


def coingecko_brl(cripto: str) -> dict | None:
    cid = COINGECKO_IDS.get(cripto)
    if not cid:
        return None
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=brl&include_last_updated_at=true"
    try:
        j = requests.get(url, timeout=20).json()[cid]
    except Exception:
        return None
    return {"valor": float(j["brl"]), "url": url,
            "data": pd.Timestamp(j["last_updated_at"], unit="s").strftime("%Y-%m-%d %H:%M UTC")}


def erro_amigavel(e: Exception) -> str:
    """Mensagem curta para a tela, sem stack trace nem detalhes de proxy."""
    import requests as _rq

    if isinstance(e, _rq.exceptions.Timeout):
        return "a fonte demorou demais para responder"
    if isinstance(e, _rq.exceptions.ConnectionError | _rq.exceptions.ProxyError):
        return "sem conexão com a fonte (internet, firewall ou site fora do ar)"
    if isinstance(e, _rq.exceptions.HTTPError) and e.response is not None:
        return f"a fonte respondeu com erro {e.response.status_code}"
    msg = str(e).strip()
    return msg if msg and len(msg) < 160 and "http" not in msg.lower() else type(e).__name__
