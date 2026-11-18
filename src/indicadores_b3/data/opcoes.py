"""Opções de ações: arquivo oficial de cotações históricas da B3 (COTAHIST, diário).

Layout oficial: https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf
Página: https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/

Registro 01 (posições do layout, base 1):
  DATA 3-10 · CODNEG 13-24 · TPMERC 25-27 (010 à vista, 070 call, 080 put) · ESPECI 40-49
  PREABE..PREULT 57-121 (2 casas implícitas) · PREOFC 122-134 · PREOFV 135-147 · TOTNEG 148-152
  QUATOT 153-170 · VOLTOT 171-188 · PREEXE 189-201 · DATVEN 203-210 · FATCOT 211-217

O Black-Scholes, a volatilidade implícita e as estratégias são calculados na página (static/opcoes.js),
para você ver cada passo e mudar as premissas.
"""
import time
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from indicadores_b3 import config
from indicadores_b3.data.fontes import cdi_atual, historico_yf, url_yahoo

SERHIST = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
LAYOUT = "https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf"
CACHE = config.CACHE_DIR
CACHE.mkdir(parents=True, exist_ok=True)

# (nome, início, fim) em posições base 1 do layout
CAMPOS = [("TIPREG", 1, 2), ("DATA", 3, 10), ("CODNEG", 13, 24), ("TPMERC", 25, 27), ("NOMRES", 28, 39),
          ("ESPECI", 40, 49), ("PREABE", 57, 69), ("PREMAX", 70, 82), ("PREMIN", 83, 95), ("PREULT", 109, 121),
          ("PREOFC", 122, 134), ("PREOFV", 135, 147), ("TOTNEG", 148, 152), ("QUATOT", 153, 170),
          ("VOLTOT", 171, 188), ("PREEXE", 189, 201), ("DATVEN", 203, 210), ("FATCOT", 211, 217)]
PRECOS = ["PREABE", "PREMAX", "PREMIN", "PREULT", "PREOFC", "PREOFV", "PREEXE", "VOLTOT"]


def url_dia(dia: pd.Timestamp) -> str:
    return f"{SERHIST}/COTAHIST_D{dia:%d%m%Y}.ZIP"


def baixar_dia(dia: pd.Timestamp) -> Path | None:
    arq = CACHE / f"cotahist_{dia:%Y%m%d}.zip"
    if arq.exists():
        return arq
    try:
        r = requests.get(url_dia(dia), timeout=120)
    except requests.RequestException:
        return None
    if not r.ok or not r.content.startswith(b"PK"):  # não é zip = sem pregão nesse dia
        return None
    arq.write_bytes(r.content)
    return arq


@lru_cache(maxsize=4)
def _ultimo_pregao(hora: int) -> tuple[pd.Timestamp, Path]:
    dia = pd.Timestamp.now().normalize()
    for _ in range(10):
        if dia.dayofweek < 5:
            arq = baixar_dia(dia)
            if arq:
                return dia, arq
        dia -= pd.Timedelta(days=1)
    raise LookupError("Não consegui baixar o arquivo COTAHIST da B3 dos últimos 10 dias.")


def ultimo_pregao():
    return _ultimo_pregao(int(time.time() // 3600))


@lru_cache(maxsize=4)
def ler(arq: Path) -> pd.DataFrame:
    with zipfile.ZipFile(arq) as zf:
        texto = zf.read(zf.namelist()[0]).decode("latin-1")
    linhas = [l for l in texto.splitlines() if l.startswith("01")]
    df = pd.DataFrame({n: [l[i - 1:f] for l in linhas] for n, i, f in CAMPOS})
    df["LINHA"] = linhas  # a linha original, para conferência
    for c in df.columns:
        if c != "LINHA":
            df[c] = df[c].str.strip()
    for c in PRECOS:
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100
    for c in ["TOTNEG", "QUATOT", "FATCOT"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["PREULT", "PREOFC", "PREOFV", "PREEXE"]:
        df[c] = df[c] / df["FATCOT"].replace(0, 1)
    return df


def vol_historica(ticker: str) -> dict:
    s = historico_yf(f"{ticker}.SA", "1y")
    ret = np.log(s).diff().dropna()
    def v(n):
        r = ret.tail(n)
        return float(r.std() * np.sqrt(252) * 100) if len(r) > 10 else None
    return {"21d": v(21), "63d": v(63), "252d": v(252), "fonte": url_yahoo(f"{ticker}.SA"),
            "nota": "Desvio-padrão dos retornos logarítmicos diários × √252, com preços do yfinance."}


def grade(ticker: str) -> dict:
    t = ticker.strip().upper()
    dia, arq = ultimo_pregao()
    df = ler(arq)
    spot = df[(df.CODNEG == t) & (df.TPMERC == "010")]
    if spot.empty:
        raise LookupError(f"{t} não foi negociado no mercado à vista no pregão de {dia:%d/%m/%Y}.")
    s = spot.iloc[0]
    classe = s.ESPECI.split()[0] if s.ESPECI else ""  # ON, PN, UNT...
    op = df[df.TPMERC.isin(["070", "080"]) & df.CODNEG.str.startswith(t[:4])].copy()
    op = op[op.ESPECI.str.split().str[0] == classe]  # opções sobre a mesma classe da ação
    if op.empty:
        raise LookupError(f"Nenhuma opção de {t} negociada no pregão de {dia:%d/%m/%Y}.")

    hoje = dia.date()
    itens = []
    for _, r in op.sort_values(["DATVEN", "TPMERC", "PREEXE"]).iterrows():
        venc = pd.Timestamp(r.DATVEN)
        itens.append({
            "codigo": r.CODNEG, "tipo": "call" if r.TPMERC == "070" else "put",
            "strike": float(r.PREEXE), "vencimento": venc.strftime("%Y-%m-%d"),
            "dias_uteis": int(np.busday_count(hoje, venc.date())), "dias_corridos": (venc.date() - hoje).days,
            "ultimo": float(r.PREULT), "abertura": float(r.PREABE), "maximo": float(r.PREMAX), "minimo": float(r.PREMIN),
            "oferta_compra": float(r.PREOFC), "oferta_venda": float(r.PREOFV),
            "negocios": int(r.TOTNEG), "quantidade": int(r.QUATOT), "volume": float(r.VOLTOT),
            "linha": r.LINHA,
        })
    try:
        cdi = cdi_atual()
    except Exception:
        cdi = None
    return {
        "ticker": t, "empresa": s.NOMRES, "pregao": dia.strftime("%Y-%m-%d"),
        "spot": {"preco": float(s.PREULT), "linha": s.LINHA},
        "fonte": {"arquivo": arq.name.replace("cotahist_", "COTAHIST_D"), "url": url_dia(dia), "layout": LAYOUT},
        "opcoes": itens,
        "vol_hist": vol_historica(t),
        "cdi": cdi,
        "nota": "Dias úteis contados sem feriados (aproximação). Opções de compra na B3 costumam ser do tipo americano "
                "e as de venda, europeu; o Black-Scholes é um modelo para opções europeias.",
    }
