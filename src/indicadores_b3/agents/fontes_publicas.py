"""Fontes públicas e gratuitas usadas pelos agentes (sem chave, sem cadastro):

  Banco Central · SGS        https://api.bcb.gov.br/dados/serie/bcdata.sgs.{n}/dados
  Banco Central · Focus      https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/
  FRED (St. Louis Fed)       https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}  (CSV, sem chave)
  Tesouro Nacional           curva prefixada/IPCA+ (premissas.py, arquivo já usado no site)
  CVM · IPE                  fatos relevantes e comunicados (comunicados.py)

Cada função devolve {"valor", "data_ref", "fonte", "documento", "url", "descricao"} ou levanta erro;
quem chama registra o erro como dado ausente.
"""
from __future__ import annotations

import io
from functools import lru_cache

import pandas as pd
import requests

UA = {"User-Agent": "indicadores-b3/1.0 (uso pessoal, estudo)"}
OLINDA = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

SGS_SERIES = {  # número: (nome, unidade, descrição)
    432: ("Selic (meta)", "% a.a.", "Meta da taxa Selic definida pelo Copom"),
    13522: ("IPCA acumulado em 12 meses", "%", "IPCA, variação acumulada em 12 meses (IBGE, via SGS)"),
    1: ("Dólar (PTAX venda)", "R$/US$", "Taxa de câmbio PTAX de venda"),
    24369: ("Taxa de desocupação", "%", "PNAD Contínua, IBGE (via SGS)"),
    24363: ("IBC-Br (dessazonalizado)", "índice", "Índice de Atividade Econômica do Banco Central"),
}
FRED_SERIES = {
    "DGS10": ("Juro do Tesouro americano de 10 anos", "% a.a."),
    "FEDFUNDS": ("Fed Funds (juro básico dos EUA)", "% a.a."),
    "CPIAUCSL": ("Índice de preços ao consumidor dos EUA (CPI)", "índice"),
    "DCOILBRENTEU": ("Petróleo Brent", "US$/barril"),
    "T10YIE": ("Inflação implícita dos EUA em 10 anos (breakeven)", "% a.a."),
}
TIMEOUT = 12  # s; fontes complementares não podem travar a página
IPEA = "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{}')"


def _hoje():
    return pd.Timestamp.now().strftime("%Y-%m-%d")


@lru_cache(maxsize=64)
def sgs_ultimo(n: int, dia: str = "") -> dict:
    from indicadores_b3.data.fontes import sgs
    fim = pd.Timestamp.now()
    s, url = sgs(n, fim - pd.DateOffset(years=2), fim)
    if s.empty:
        raise LookupError(f"SGS {n} sem dados")
    nome, un, desc = SGS_SERIES.get(n, (f"SGS {n}", "", ""))
    out = {"valor": float(s.iloc[-1]), "data_ref": s.index[-1].strftime("%Y-%m-%d"), "fonte": "Banco Central",
           "documento": f"SGS · série {n}", "url": url, "descricao": desc, "conta": str(n), "periodo": f"dado de {s.index[-1]:%m/%Y}"}
    if len(s) > 12:  # valor de 12 observações antes, para tendência
        out["anterior"] = {"valor": float(s.iloc[-13]), "data_ref": s.index[-13].strftime("%Y-%m-%d")}
    return out


@lru_cache(maxsize=32)
def focus(indicador: str, ano: int, dia: str = "") -> dict:
    """Mediana da expectativa de mercado (relatório Focus) para o ano."""
    v, r = [], None
    for filtro in (f"Indicador eq '{indicador}' and DataReferencia eq '{ano}' and baseCalculo eq 0",
                   f"Indicador eq '{indicador}' and DataReferencia eq '{ano}'"):
        params = {"$top": "1", "$format": "json", "$orderby": "Data desc", "$filter": filtro}
        r = requests.get(OLINDA, params=params, headers=UA, timeout=TIMEOUT)
        if r.ok:
            v = r.json().get("value", [])
            if v:
                break
    if not v:
        raise LookupError(f"Focus sem {indicador} {ano}")
    x = v[0]
    return {"valor": float(x["Mediana"]), "data_ref": x["Data"], "fonte": "Banco Central", "documento": f"Focus · {indicador} {ano}",
            "url": r.url, "descricao": f"Mediana das expectativas de mercado para {indicador} em {ano}", "conta": "Mediana",
            "periodo": f"pesquisa de {x['Data']}"}


@lru_cache(maxsize=16)
def fred(serie: str, dia: str = "") -> dict:
    r = requests.get(FRED.format(serie), headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["data", "valor"]
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna()
    if df.empty:
        raise LookupError(f"FRED {serie} sem dados")
    nome, un = FRED_SERIES.get(serie, (serie, ""))
    out = {"valor": float(df.valor.iloc[-1]), "data_ref": str(df.data.iloc[-1])[:10], "fonte": "FRED (Federal Reserve Bank of St. Louis)",
           "documento": serie, "url": f"https://fred.stlouisfed.org/series/{serie}", "descricao": nome, "conta": serie,
           "periodo": f"dado de {str(df.data.iloc[-1])[:10]}"}
    if serie == "CPIAUCSL" and len(df) > 12:  # inflação anual = índice ÷ índice de 12 meses antes − 1
        out.update({"valor": (df.valor.iloc[-1] / df.valor.iloc[-13] - 1) * 100,
                    "descricao": "Inflação ao consumidor dos EUA em 12 meses (CPI)", "conta": "CPIAUCSL (variação 12m)"})
    return out


@lru_cache(maxsize=8)
def ipea_ultimo(serie: str, dia: str = "") -> dict:
    """Último valor de uma série do Ipeadata (API pública, sem chave). Ex.: JPM366_EMBI366 = risco-país (EMBI+ Brasil, pontos-base)."""
    r = requests.get(IPEA.format(serie), headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    v = [x for x in r.json().get("value", []) if x.get("VALVALOR") is not None]
    if not v:
        raise LookupError(f"Ipeadata {serie} sem dados")
    x = max(v, key=lambda y: y["VALDATA"])
    return {"valor": float(x["VALVALOR"]), "data_ref": x["VALDATA"][:10], "fonte": "Ipeadata", "documento": serie,
            "url": f"http://www.ipeadata.gov.br/ExibeSerie.aspx?serid={serie}", "conta": serie,
            "descricao": "Risco-país: EMBI+ Brasil (JP Morgan), em pontos-base", "periodo": f"dado de {x['VALDATA'][:10]}"}
