"""Identifica o tipo de cada ativo e monta a série de preços em reais, com rastreio.

Como escrever os ativos no site:
  Ações, FIIs, ETFs e BDRs da B3 ...  PETR4, HGLG11, BOVA11, IVVB11
  Cripto ..........................  BTC, ETH, SOL (ou BTC-USD)
  Ouro ............................  OURO (contrato futuro COMEX, GC=F)
  Dólar ...........................  USD (PTAX do Banco Central)
  Tesouro Direto ..................  TD-IPCA-20350515 (escolha pela lista do site)
"""
import re

import numpy as np
import pandas as pd

from indicadores_b3.data import tesouro
from indicadores_b3.data.fontes import SERIE_PTAX, comp, historico_yf, rastro, sgs, url_yahoo

B3 = re.compile(r"^[A-Z]{4}\d{1,2}$")
CRIPTOS = {"BTC", "ETH", "SOL"}
ESPECIAIS = {
    "OURO": {"simbolo": "GC=F", "moeda": "USD", "classe": "commodity",
             "nome": "Ouro — contrato futuro COMEX (US$ por onça troy)"},
    "GC=F": {"simbolo": "GC=F", "moeda": "USD", "classe": "commodity",
             "nome": "Ouro — contrato futuro COMEX (US$ por onça troy)"},
    "USD": {"simbolo": None, "moeda": "BRL", "classe": "moeda",
            "nome": "Dólar americano — PTAX venda (Banco Central)"},
}


def identificar(ticker: str) -> dict:
    """Só pelo formato: de onde vem o preço e em que moeda. (Ação x FII x ETF é decidido em indicadores.py.)"""
    t = ticker.strip().upper()
    if tesouro.eh_tesouro(t):
        return {"ticker": t, "simbolo": None, "moeda": "BRL", "classe": "tesouro", "nome": tesouro.nome(t)}
    if t in ESPECIAIS:
        return {"ticker": t, **ESPECIAIS[t]}
    base = t.removesuffix("-USD")
    if base in CRIPTOS:
        return {"ticker": base, "simbolo": f"{base}-USD", "moeda": "USD", "classe": "cripto",
                "nome": f"{base} (cotação em US$ no Yahoo, convertida pela PTAX)"}
    if B3.match(t):
        return {"ticker": t, "simbolo": f"{t}.SA", "moeda": "BRL", "classe": "b3", "nome": f"{t} (B3)"}
    raise ValueError(f"Não reconheci '{t}'. Use um código da B3 (PETR4, HGLG11, BOVA11), "
                     f"uma cripto ({', '.join(sorted(CRIPTOS))}), OURO, USD ou um título do Tesouro (TD-...).")


def serie_brl(ticker: str, periodo: str) -> tuple[pd.Series, dict]:
    """Preço diário em R$ + rastreio de como ele foi obtido."""
    a = identificar(ticker)
    fim = pd.Timestamp.now().normalize()
    inicio = fim - pd.DateOffset(years=int(periodo.rstrip("y")))

    if a["classe"] == "tesouro":  # preço de mercado publicado pelo Tesouro Nacional
        s, fonte = tesouro.serie_pu(a["ticker"], inicio)
        return s, {**a, "fontes": [fonte]}

    if a["classe"] == "moeda":  # dólar: a própria PTAX
        s, url = sgs(SERIE_PTAX, inicio, fim)
        return s, {**a, "fontes": [{"fonte": "Banco Central", "documento": f"SGS · série {SERIE_PTAX}",
                                    "descricao": "PTAX venda (R$ por US$)", "url": url}]}

    s = historico_yf(a["simbolo"], periodo)
    if s.empty:
        raise ValueError(f"yfinance não retornou histórico para {a['simbolo']}.")
    fontes = [{"fonte": "yfinance", "documento": f"download('{a['simbolo']}', auto_adjust=True)",
               "descricao": "Fechamento ajustado por proventos e desdobramentos", "url": url_yahoo(a["simbolo"])}]

    if a["moeda"] == "USD":
        ptax, url = sgs(SERIE_PTAX, s.index[0] - pd.Timedelta(days=10), fim)
        # cripto negocia todo dia; nos fins de semana/feriados usa a última PTAX publicada
        ptax_dia = ptax.reindex(s.index.union(ptax.index)).ffill().reindex(s.index)
        s = (s * ptax_dia).dropna()
        fontes.append({"fonte": "Banco Central", "documento": f"SGS · série {SERIE_PTAX}",
                       "descricao": "PTAX venda (R$ por US$) — preço em US$ × PTAX do mesmo dia "
                                    "(ou a última publicada, em fins de semana e feriados)", "url": url})
    return s, {**a, "fontes": fontes}


def metricas_mercado(ticker: str) -> dict:
    """Base para o catálogo de mercado: preço, preço há 12 meses e volatilidade, com rastreio."""
    s, info = serie_brl(ticker, "2y")
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=1, days=7)]
    if len(s) < 30:
        raise LookupError(f"{ticker}: histórico insuficiente (menos de 30 preços no último ano).")

    hoje, v_hoje = s.index[-1], float(s.iloc[-1])
    alvo = hoje - pd.DateOffset(years=1)
    antes = s[s.index <= alvo]
    d_ant, v_ant = (antes.index[-1], float(antes.iloc[-1])) if not antes.empty else (s.index[0], float(s.iloc[0]))

    ret = s.pct_change().dropna()
    ret = ret[ret.index > hoje - pd.DateOffset(years=1)]
    obs_ano = len(ret)  # ~252 para B3, ~365 para cripto (convertida: dias com PTAX válida)

    fonte_txt = " + ".join(f["documento"] for f in info["fontes"])
    url = info["fontes"][0]["url"]

    def linha(dia, valor, papel):
        return comp("+", papel, {"fonte": " + ".join(f["fonte"] for f in info["fontes"]), "documento": fonte_txt,
                                 "url": url, "data_ref": dia.strftime("%Y-%m-%d"),
                                 "periodo": f"fechamento de {dia:%Y-%m-%d}", "conta": "Close (R$)",
                                 "descricao": info["nome"], "valor": valor})

    nota_moeda = (" Convertido para reais pela PTAX do Banco Central." if info["moeda"] == "USD" else "")
    return {
        "info": info,
        "rastreio": {
            "preco": rastro(v_hoje, [linha(hoje, v_hoje, "Fechamento mais recente")],
                            "Último preço de fechamento disponível." + nota_moeda),
            "preco_12m": rastro(v_ant, [linha(d_ant, v_ant, "Fechamento de ~12 meses atrás")],
                                "Último fechamento até a mesma data do ano passado." + nota_moeda),
            "desvio_diario": rastro(float(ret.std()), [comp("+", f"{len(ret)} retornos diários", {
                "fonte": "cálculo", "documento": fonte_txt, "url": url,
                "data_ref": hoje.strftime("%Y-%m-%d"),
                "periodo": f"{ret.index[0]:%Y-%m-%d} a {hoje:%Y-%m-%d}", "conta": "std(pct_change)",
                "descricao": "Desvio-padrão dos retornos diários em R$", "valor": float(ret.std())})],
                "Desvio-padrão da variação percentual de um dia para o outro."),
            "obs_ano": rastro(obs_ano, [], "Quantos retornos diários existem em 1 ano para este ativo "
                                           "(~252 na B3, ~365 em cripto). Usado para anualizar a volatilidade."),
        },
    }


def anualizar(desvio: float, obs: float) -> float:
    return desvio * np.sqrt(obs)
