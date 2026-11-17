"""Gráfico de preço de um ativo da B3 ao longo dos anos, com proventos e comparação com o Ibovespa.

Duas séries do Yahoo Finance (yfinance), as duas ajustadas por desdobramentos e grupamentos:
- fechamento: o preço como apareceu na tela da corretora (sem somar proventos);
- retorno total: o fechamento ajustado por proventos ("Adj Close"), como se cada dividendo e JCP
  tivesse sido reinvestido na própria ação. É o que se compara com o Ibovespa, que também é um índice de retorno total.
Estatísticas do período: variação do preço, retorno total, retorno anualizado, volatilidade anual,
maior queda (drawdown máximo), máxima e mínima.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from indicadores_b3.data.ativos import identificar
from indicadores_b3.data.fontes import url_yahoo, yf

PERIODOS = {"1y": "1 ano", "5y": "5 anos", "10y": "10 anos", "max": "desde o início"}
MAX_PONTOS = 1300  # acima disso o gráfico usa o último preço de cada semana


def _baixar(simbolo: str, periodo: str) -> pd.DataFrame:
    df = yf.download(simbolo, period=periodo, auto_adjust=False, actions=True, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


@lru_cache(maxsize=64)
def _cache(simbolo: str, periodo: str, chave: str) -> pd.DataFrame:
    return _baixar(simbolo, periodo)


def baixar(simbolo: str, periodo: str) -> pd.DataFrame:
    """Um download a cada 15 minutos durante o pregão; fora dele, um por dia (fontes.chave_preco)."""
    from indicadores_b3.data.fontes import chave_preco
    return _cache(simbolo, periodo, chave_preco())


def estatisticas(fech: pd.Series, total: pd.Series) -> dict:
    """Números do período a partir das séries diárias (antes de reduzir para semanal)."""
    anos = max((total.index[-1] - total.index[0]).days / 365.25, 1e-9)
    ret = total.pct_change().dropna()
    pico = total.cummax()
    queda = total / pico - 1
    fundo = queda.idxmin()
    return {
        "inicio": total.index[0].strftime("%Y-%m-%d"), "fim": total.index[-1].strftime("%Y-%m-%d"),
        "variacao_preco": (fech.iloc[-1] / fech.iloc[0] - 1) * 100,
        "retorno_total": (total.iloc[-1] / total.iloc[0] - 1) * 100,
        "retorno_anual": ((total.iloc[-1] / total.iloc[0]) ** (1 / anos) - 1) * 100 if anos >= 0.9 else None,
        "vol_anual": float(ret.std() * np.sqrt(252) * 100) if len(ret) > 20 else None,
        "drawdown_max": float(queda.min() * 100),
        "drawdown_data": fundo.strftime("%Y-%m-%d"),
        "drawdown_pico": total.loc[:fundo].idxmax().strftime("%Y-%m-%d"),
        "maxima": float(fech.max()), "maxima_data": fech.idxmax().strftime("%Y-%m-%d"),
        "minima": float(fech.min()), "minima_data": fech.idxmin().strftime("%Y-%m-%d"),
    }


def reduzir(df: pd.DataFrame) -> pd.DataFrame:
    """Último pregão de cada semana quando há pontos demais para o gráfico (o último dia é sempre mantido)."""
    if len(df) <= MAX_PONTOS:
        return df
    sem = df.groupby(df.index.to_period("W")).tail(1)
    if sem.index[-1] != df.index[-1]:
        sem = pd.concat([sem, df.iloc[[-1]]])
    return sem


def historico(ticker: str, periodo: str = "5y", baixar_fn=None) -> dict:
    if periodo not in PERIODOS:
        raise ValueError(f"Período inválido: use {', '.join(PERIODOS)}.")
    a = identificar(ticker)
    if a["classe"] != "b3":
        raise ValueError("O gráfico de preço é para ativos da B3 (ações, FIIs, ETFs).")
    pegar = baixar_fn or baixar
    df = pegar(a["simbolo"], periodo)
    if df.empty or "Close" not in df:
        raise LookupError(f"O yfinance não retornou o histórico de {a['simbolo']}. Tente de novo em alguns minutos.")
    df = df.dropna(subset=["Close"])
    fech = df["Close"].astype(float)
    total = df["Adj Close"].astype(float) if "Adj Close" in df else fech
    stats = estatisticas(fech, total)

    prov = df["Dividends"] if "Dividends" in df else pd.Series(dtype=float)
    prov = prov[prov > 0]
    proventos = [{"data": d.strftime("%Y-%m-%d"), "valor": float(v)} for d, v in prov.items()]
    por_ano: dict[str, float] = {}
    for p in proventos:
        por_ano[p["data"][:4]] = por_ano.get(p["data"][:4], 0.0) + p["valor"]

    ibov_df = pegar("^BVSP", periodo)
    ibov = None
    if not ibov_df.empty and "Close" in ibov_df:
        s = ibov_df["Close"].astype(float).reindex(df.index).ffill()
        s = s.dropna()
        if len(s) > 1:
            ibov = s
            stats["ibov_retorno"] = (s.iloc[-1] / s.iloc[0] - 1) * 100

    curto = reduzir(pd.DataFrame({"fech": fech, "total": total}))
    base_total = curto["total"].iloc[0]
    out = {
        "ticker": a["ticker"], "simbolo": a["simbolo"], "periodo": periodo, "periodo_nome": PERIODOS[periodo],
        "datas": [d.strftime("%Y-%m-%d") for d in curto.index],
        "fechamento": [round(float(v), 4) for v in curto["fech"]],
        "total_base100": [round(float(v / base_total * 100), 3) for v in curto["total"]],
        "ibov_base100": None,
        "proventos": proventos, "proventos_por_ano": por_ano,
        "estatisticas": stats,
        "semanal": len(curto) < len(df),
        "fontes": [{"fonte": "yfinance", "documento": f"download('{a['simbolo']}', auto_adjust=False, actions=True)",
                    "descricao": "Close (ajustado só por desdobramentos), Adj Close (também por proventos) e Dividends",
                    "url": url_yahoo(a["simbolo"])},
                   {"fonte": "yfinance", "documento": "download('^BVSP')", "descricao": "Ibovespa (pontos)",
                    "url": url_yahoo("^BVSP")}],
    }
    if ibov is not None:
        ib = ibov.reindex(curto.index).ffill().bfill()
        out["ibov_base100"] = [round(float(v / ib.iloc[0] * 100), 3) for v in ib]
    return out
