
"""Carteira eficiente (Markowitz), antes e depois dos impostos.

Passo a passo:
1. Monta a série de preços em R$ de cada ativo (ativos.serie_brl): B3 direto do yfinance;
   cripto e ouro em US$ do yfinance × PTAX do Banco Central.
2. Mantém só os dias em que todos têm preço, calcula os retornos diários e anualiza
   (média × 252, covariância × 252).
3. Otimiza os pesos (sem venda a descoberto, soma = 100%, respeitando o peso máximo).
4. CAPM (opcional): β de cada ativo contra o Ibovespa e retorno esperado
   rf + β × (E[Rm] − rf) no lugar da média histórica; alfa de Jensen e Security Market Line.
5. Versão com impostos: aplica a alíquota de cada classe sobre o ganho e a tabela
   regressiva sobre o CDI, e otimiza de novo.
"""
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from indicadores_b3.analytics.impostos import BASE_LEGAL_RF, aliquota_renda_fixa, regra, regra_tesouro
from indicadores_b3.data import fii, fundamentos
from indicadores_b3.data.ativos import identificar, serie_brl
from indicadores_b3.data.fontes import cdi_atual, erro_amigavel, historico_yf, proventos_12m, url_yahoo

DIAS_UTEIS = 252
PERIODOS = {"1y": "1 ano", "2y": "2 anos", "3y": "3 anos", "5y": "5 anos"}


@lru_cache(maxsize=64)
def _serie(ticker: str, periodo: str, dia: str):
    return serie_brl(ticker, periodo)  # cache por dia


@lru_cache(maxsize=16)
def _ibov(periodo: str, dia: str) -> pd.Series:
    return historico_yf("^BVSP", periodo)  # cache por dia


# ---------- CAPM ----------
MODELOS = {"historico": "Média histórica", "capm": "CAPM", "blocos": "Premissas de mercado (blocos)",
           "bl": "Premissas de mercado (blocos)"}  # na fronteira, sem as visões do Black-Litterman


def capm(ret: pd.DataFrame, periodo: str, hoje: str, rf: float, mercado_pct: float | None) -> dict:
    """β, retorno pelo CAPM e alfa de Jensen de cada ativo, contra o Ibovespa."""
    ibov = _ibov(periodo, hoje)
    if ibov.empty:
        raise LookupError("O yfinance não retornou o Ibovespa (^BVSP).")
    rm = ibov.pct_change().dropna().rename("_m")
    df = ret.join(rm, how="inner").dropna()  # só dias em que todos e o Ibovespa têm retorno
    if len(df) < 60:
        raise LookupError("Poucos dias em comum entre os ativos e o Ibovespa (menos de 60).")
    var_m = df["_m"].var()
    rm_hist = df["_m"].mean() * DIAS_UTEIS
    rm_esp = rm_hist if mercado_pct is None else mercado_pct / 100
    ativos = []
    for t in ret.columns:
        cov_im = df[t].cov(df["_m"])
        beta = cov_im / var_m
        r_hist = df[t].mean() * DIAS_UTEIS
        ativos.append({
            "ticker": t, "beta": beta, "r2": df[t].corr(df["_m"]) ** 2,
            "cov_mercado": cov_im * DIAS_UTEIS, "retorno_hist": r_hist * 100,
            "retorno_capm": (rf + beta * (rm_esp - rf)) * 100,
            # Jensen usa o retorno REALIZADO do mercado no mesmo período
            "alfa": (r_hist - (rf + beta * (rm_hist - rf))) * 100,
        })
    return {
        "mercado": {"ticker": "^BVSP", "nome": "Ibovespa", "url": url_yahoo("^BVSP"),
                    "var_anual": var_m * DIAS_UTEIS, "retorno_hist": rm_hist * 100,
                    "esperado": rm_esp * 100, "esperado_origem": "historico" if mercado_pct is None else "informado"},
        "rf": rf * 100, "dias": int(len(df)),
        "inicio": df.index[0].strftime("%Y-%m-%d"), "fim": df.index[-1].strftime("%Y-%m-%d"),
        "ativos": ativos,
    }


# ---------- Otimização ----------
def estatisticas(w, mu, cov, rf):
    ret = float(w @ mu)
    vol = float(np.sqrt(max(w @ cov @ w, 0)))
    return {"retorno": ret * 100, "volatilidade": vol * 100,
            "sharpe": (ret - rf) / vol if vol > 0 else None}


def _min(objetivo, n, peso_max, extra=()):
    r = minimize(objetivo, np.full(n, 1 / n), method="SLSQP", bounds=[(0.0, peso_max)] * n,
                 constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}, *extra],
                 options={"maxiter": 500, "ftol": 1e-10})
    return r.x if r.success else None


def otimizar(tickers, mu, cov, rf, peso_max) -> dict:
    n = len(tickers)
    pesos = lambda w: {t: float(v) for t, v in zip(tickers, (w * 100).round(2))}
    var = lambda w: w @ cov @ w
    w_min = _min(var, n, peso_max)
    w_sharpe = _min(lambda w: -(w @ mu - rf) / np.sqrt(w @ cov @ w), n, peso_max)
    w_max_ret = _min(lambda w: -(w @ mu), n, peso_max)

    fronteira = []
    if w_min is not None and w_max_ret is not None:
        for alvo in np.linspace(w_min @ mu, w_max_ret @ mu, 30):
            w = _min(var, n, peso_max, [{"type": "eq", "fun": lambda w, a=alvo: w @ mu - a}])
            if w is not None:
                fronteira.append({**estatisticas(w, mu, cov, rf), "pesos": pesos(w)})

    rng = np.random.default_rng(42)
    aleatorias = [[round(s["volatilidade"], 3), round(s["retorno"], 3)]
                  for w in rng.dirichlet(np.ones(n), 1500) if w.max() <= peso_max + 1e-9
                  for s in [estatisticas(w, mu, cov, rf)]]

    def pacote(w, nome, explicacao):
        return None if w is None else {"nome": nome, "explicacao": explicacao,
                                       **estatisticas(w, mu, cov, rf), "pesos": pesos(w)}

    return {
        "min_var": pacote(w_min, "Mínima variância", "A combinação com o menor risco possível, sem olhar para o retorno."),
        "max_sharpe": pacote(w_sharpe, "Máximo Sharpe", "A combinação com o maior retorno extra (acima da taxa "
                                                        "livre de risco) por unidade de risco."),
        "fronteira": fronteira,
        "aleatorias": aleatorias,
        "ativos": [{"ticker": t, **estatisticas(np.eye(n)[i], mu, cov, rf)} for i, t in enumerate(tickers)],
        "rf": rf * 100,
    }


# ---------- Impostos ----------
def classe_fiscal(ticker: str) -> str:
    a = identificar(ticker)
    if a["classe"] != "b3":
        return a["classe"]
    if a["ticker"] in fundamentos.mapa_tickers():
        return "acao"
    if fii.buscar(a["ticker"]):
        return "fii"
    return "etf"


def com_impostos(tickers, info, px, mu, cov, rf, peso_max, horizonte_anos, dentro_isencao) -> dict:
    linhas, t_ganho, mu_liq = [], [], []
    for i, t in enumerate(tickers):
        cf = classe_fiscal(t)
        r = regra_tesouro(int(horizonte_anos * 365)) if cf == "tesouro" else regra(cf, dentro_isencao)
        dy = 0.0
        if info[t]["classe"] == "b3":
            prov = proventos_12m(info[t]["simbolo"])["valor"] or 0.0
            dy = prov / float(px[t].iloc[-1])  # aproximação: rendimento corrente
        ganho = mu[i] - dy
        liq = dy * (1 - r["proventos"] / 100) + ganho * (1 - r["ganho_aplicado"] / 100)
        t_ganho.append(r["ganho_aplicado"] / 100)
        mu_liq.append(liq)
        linhas.append({"ticker": t, "classe": r["nome"], "aliquota_ganho": r["ganho_aplicado"],
                       "aliquota_cheia": r["ganho"], "isencao": r["isencao"], "isento": r["isento"],
                       "aliquota_proventos": r["proventos"],
                       "retorno_bruto": mu[i] * 100, "parte_proventos": dy * 100, "parte_ganho": ganho * 100,
                       "retorno_liquido": liq * 100, "base_legal": r["base_legal"], "nota": r["nota"]})

    fator = 1 - np.array(t_ganho)
    cov_liq = cov * np.outer(fator, fator)
    for i, l in enumerate(linhas):
        l["vol_bruta"] = float(np.sqrt(cov[i, i])) * 100
        l["vol_liquida"] = float(np.sqrt(cov_liq[i, i])) * 100

    dias = int(horizonte_anos * 365)
    a_rf = aliquota_renda_fixa(dias)
    rf_liq = rf * (1 - a_rf / 100)
    return {
        "parametros": {"horizonte_anos": horizonte_anos, "dentro_isencao": dentro_isencao},
        "ativos": linhas,
        "renda_fixa": {"bruto": rf * 100, "aliquota": a_rf, "liquido": rf_liq * 100, "dias": dias,
                       "base_legal": BASE_LEGAL_RF},
        "resultado": otimizar(tickers, np.array(mu_liq), cov_liq, rf_liq, peso_max),
    }


# ---------- Entrada principal ----------
def carteira(tickers: list[str], periodo="3y", rf_pct: float | None = None, peso_max_pct=100.0,
             horizonte_anos=2.0, dentro_isencao=False, modelo="historico",
             mercado_pct: float | None = None) -> dict:
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if len(tickers) < 2:
        raise ValueError("Informe pelo menos 2 ativos.")
    if periodo not in PERIODOS:
        raise ValueError("Período inválido.")
    if modelo not in MODELOS:
        raise ValueError("Modelo de retorno inválido.")
    peso_max = peso_max_pct / 100
    if peso_max * len(tickers) < 1:
        raise ValueError(f"Com {len(tickers)} ativos, o peso máximo precisa ser de pelo menos "
                         f"{100 / len(tickers):.1f}% para a soma chegar a 100%.")

    rf_info = None
    if rf_pct is None:  # sem taxa informada: usa o CDI oficial
        rf_info = cdi_atual()
        rf_pct = rf_info["valor"]

    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    series, info = {}, {}
    for t in tickers:
        s, i = _serie(t, periodo, hoje)
        series[i["ticker"]], info[i["ticker"]] = s, i
    tickers = list(series)
    px = pd.DataFrame(series)
    curtos = [t for t in tickers if px[t].count() < 60]
    if curtos:
        raise ValueError(f"Histórico insuficiente para: {', '.join(curtos)}")
    px = px.dropna()  # só dias em que todos têm preço
    ret = px.pct_change().dropna()
    if len(ret) < 60:
        raise ValueError("Poucos dias em comum entre os ativos (menos de 60).")

    rf = rf_pct / 100
    mu_hist = ret.mean().values * DIAS_UTEIS
    cov = ret.cov().values * DIAS_UTEIS
    try:
        c_capm = capm(ret, periodo, hoje, rf, mercado_pct)
    except LookupError as e:
        if modelo == "capm":
            raise
        c_capm = {"erro": erro_amigavel(e)}
    mu = (np.array([a["retorno_capm"] for a in c_capm["ativos"]]) / 100) if modelo == "capm" else mu_hist
    if modelo in ("blocos", "bl"):
        from indicadores_b3.portfolio import premissas as prem
        pr = prem.premissas(tickers, {t: float(px[t].iloc[-1]) for t in tickers},
                            {t: classe_fiscal(t) for t in tickers if info[t]["classe"] == "b3"})
        mu = np.array([a["valor"] if a["valor"] is not None else mu_hist[i] * 100 for i, a in enumerate(pr["ativos"])]) / 100
        rf = pr["rf_bloco"] / 100
    bruto = otimizar(tickers, mu, cov, rf, peso_max)
    for a in bruto["ativos"]:
        t = a["ticker"]
        a.update({"retorno_hist": float(mu_hist[tickers.index(t)] * 100),
                  "preco_inicial": float(px[t].iloc[0]), "preco_final": float(px[t].iloc[-1]),
                  "nome": info[t]["nome"], "moeda": info[t]["moeda"], "fontes": info[t]["fontes"]})

    return {
        "dados": {
            "inicio": px.index[0].strftime("%Y-%m-%d"), "fim": px.index[-1].strftime("%Y-%m-%d"),
            "dias": int(len(ret)), "periodo": PERIODOS[periodo], "rf": rf_pct, "rf_fonte": rf_info,
            "peso_max": peso_max_pct, "modelo": modelo, "modelo_nome": MODELOS[modelo],
        },
        "capm": c_capm,
        "correlacao": {"tickers": tickers, "matriz": ret.corr().round(2).values.tolist()},
        **bruto,
        "impostos": com_impostos(tickers, info, px, mu, cov, rf, peso_max, horizonte_anos, dentro_isencao),
    }
