"""Carteira robusta: Markowitz clássico × Ledoit-Wolf × mínima variância × HRP × pesos iguais,
com bootstrap (estabilidade dos pesos) e backtest walk-forward fora da amostra. A referência é a carteira de pesos iguais."""
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

from indicadores_b3.data.fontes import cdi_atual
from indicadores_b3.portfolio.carteira import _min, _serie

DIAS = 252


# =====================================================================
# 1. CARTEIRA ROBUSTA
# =====================================================================
def _cov(ret: np.ndarray, metodo: str) -> np.ndarray:
    if metodo == "lw":
        return LedoitWolf().fit(ret).covariance_ * DIAS
    return np.cov(ret, rowvar=False) * DIAS


def _max_sharpe(mu, cov, rf, peso_max):
    n = len(mu)
    w = _min(lambda w: -(w @ mu - rf) / np.sqrt(w @ cov @ w), n, peso_max)
    return w if w is not None else np.full(n, 1 / n)


def _min_var(cov, peso_max):
    n = len(cov)
    w = _min(lambda w: w @ cov @ w, n, peso_max)
    return w if w is not None else np.full(n, 1 / n)


def _hrp(ret: np.ndarray) -> np.ndarray:
    """Hierarchical Risk Parity (López de Prado, 2016)."""
    cov = np.cov(ret, rowvar=False)
    corr = np.corrcoef(ret, rowvar=False)
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, None))
    np.fill_diagonal(dist, 0)
    ordem = list(leaves_list(linkage(squareform(dist, checks=False), "single")))
    w = np.ones(len(cov))
    grupos = [ordem]
    while grupos:
        novos = []
        for g in grupos:
            if len(g) < 2:
                continue
            a, b = g[: len(g) // 2], g[len(g) // 2:]
            def var_grupo(idx):
                c = cov[np.ix_(idx, idx)]
                ivp = 1 / np.diag(c)
                ivp /= ivp.sum()
                return ivp @ c @ ivp
            va, vb = var_grupo(a), var_grupo(b)
            alfa = 1 - va / (va + vb)
            w[a] *= alfa
            w[b] *= 1 - alfa
            novos += [a, b]
        grupos = novos
    return w / w.sum()


METODOS = {
    "iguais": "Pesos iguais (referência)",
    "classico": "Markowitz clássico (máx. Sharpe)",
    "lw": "Markowitz + Ledoit-Wolf (máx. Sharpe)",
    "minvar_lw": "Mínima variância + Ledoit-Wolf",
    "hrp": "HRP (clusters hierárquicos)",
}


def _pesos(metodo, ret, rf, peso_max):
    n = ret.shape[1]
    if metodo == "iguais":
        return np.full(n, 1 / n)
    if metodo == "hrp":
        return _hrp(ret)
    mu = ret.mean(axis=0) * DIAS
    if metodo == "classico":
        return _max_sharpe(mu, _cov(ret, "amostral"), rf, peso_max)
    if metodo == "lw":
        return _max_sharpe(mu, _cov(ret, "lw"), rf, peso_max)
    if metodo == "minvar_lw":
        return _min_var(_cov(ret, "lw"), peso_max)
    raise ValueError(metodo)


def _metricas(r: pd.Series, rf: float) -> dict:
    acum = (1 + r).cumprod()
    anos = len(r) / DIAS
    ret_a = acum.iloc[-1] ** (1 / anos) - 1 if anos > 0 else None
    vol = r.std() * np.sqrt(DIAS)
    dd = (acum / acum.cummax() - 1).min()
    return {"retorno": ret_a * 100, "volatilidade": vol * 100,
            "sharpe": (ret_a - rf) / vol if vol > 0 else None, "max_drawdown": dd * 100}


def carteira_robusta(tickers, periodo="5y", peso_max_pct=100.0, janela=252, rebal=21, n_boot=150) -> dict:
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if len(tickers) < 3:
        raise ValueError("Use pelo menos 3 ativos para comparar os métodos.")
    peso_max = peso_max_pct / 100
    if peso_max * len(tickers) < 1:
        raise ValueError(f"Com {len(tickers)} ativos, o peso máximo precisa ser de pelo menos {100 / len(tickers):.1f}%.")
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    series, fontes = {}, {}
    for t in tickers:
        s, info = _serie(t, periodo, hoje)
        series[info["ticker"]], fontes[info["ticker"]] = s, info["fontes"]
    tickers = list(series)
    px = pd.DataFrame(series).dropna()
    ret = px.pct_change().dropna()
    if len(ret) < janela + 2 * rebal:
        raise ValueError(f"Histórico em comum muito curto ({len(ret)} dias). Use um período maior ou outros ativos.")
    try:
        cdi = cdi_atual()
        rf = cdi["valor"] / 100
    except Exception:
        cdi, rf = None, 0.10
    out = avaliar(ret, rf, peso_max, janela, rebal, n_boot)
    out["parametros"]["rf_fonte"] = cdi
    out["fontes"] = fontes
    return out


def avaliar(ret: pd.DataFrame, rf: float, peso_max: float = 1.0, janela: int = 252, rebal: int = 21, n_boot: int = 150,
            seed: int = 42) -> dict:
    """Núcleo puro (sem internet): pesos atuais, estabilidade por bootstrap e backtest walk-forward.

    ``ret``: retornos diários (linhas = dias, colunas = ativos). Sem olhar o futuro: em cada rebalanceamento os pesos
    usam só os ``janela`` dias anteriores e são aplicados aos ``rebal`` dias seguintes.
    """
    if len(ret) < janela + 2 * rebal:
        raise ValueError(f"Histórico em comum muito curto ({len(ret)} dias).")
    tickers = list(ret.columns)
    # Layout fixo na memória: um DataFrame não contíguo (ex.: depois de uma atribuição com .iloc) muda a ordem das somas
    # na álgebra linear (~1e-17 na covariância), o SLSQP amplia para ~1e-9 nos pesos e o mesmo histórico dava curvas diferentes.
    R = np.ascontiguousarray(ret.to_numpy(dtype=float))

    # Pesos de hoje (estimados com a última janela)
    atual = {m: dict(zip(tickers, (_pesos(m, R[-janela:], rf, peso_max) * 100).round(2).tolist())) for m in METODOS}

    # Bootstrap: reamostra os dias da última janela e reotimiza
    rng = np.random.default_rng(seed)
    boot = {m: [] for m in METODOS if m != "iguais"}
    base = R[-janela:]
    for _ in range(n_boot):
        amostra = base[rng.integers(0, len(base), len(base))]
        for m in boot:
            boot[m].append(_pesos(m, amostra, rf, peso_max))
    estabilidade = {}
    for m, ws in boot.items():
        W = np.array(ws) * 100
        estabilidade[m] = {
            "instabilidade": float(W.std(axis=0).mean()),
            "faixas": {t: {"p5": float(np.percentile(W[:, i], 5)), "p50": float(np.percentile(W[:, i], 50)),
                           "p95": float(np.percentile(W[:, i], 95))} for i, t in enumerate(tickers)},
        }

    # Walk-forward: estima com os últimos `janela` dias, aplica nos próximos `rebal` dias, repete
    oos = {m: [] for m in METODOS}
    giro = {m: [] for m in METODOS}
    anterior = {m: None for m in METODOS}
    datas = []
    for ini in range(janela, len(R), rebal):
        bloco = R[ini: ini + rebal]
        datas += list(ret.index[ini: ini + rebal])
        for m in METODOS:
            w = _pesos(m, R[ini - janela: ini], rf, peso_max)
            oos[m] += list(bloco @ w)
            if anterior[m] is not None:
                giro[m].append(np.abs(w - anterior[m]).sum() / 2)
            anterior[m] = w
    idx = pd.DatetimeIndex(datas)
    backtest = {}
    for m in METODOS:
        r = pd.Series(oos[m], index=idx)
        backtest[m] = {**_metricas(r, rf), "giro_medio": float(np.mean(giro[m]) * 100) if giro[m] else 0.0,
                       "curva": [round(float(x), 4) for x in (1 + r).cumprod() * 100]}
    ref = backtest["iguais"]["sharpe"] or 0
    for m in METODOS:
        s = backtest[m]["sharpe"]
        backtest[m]["ganha_da_referencia"] = None if m == "iguais" or s is None else bool(s > ref)

    return {
        "tickers": tickers, "metodos": METODOS, "atual": atual, "estabilidade": estabilidade,
        "backtest": backtest, "datas": [d.strftime("%Y-%m-%d") for d in idx],
        "parametros": {"janela": janela, "rebal": rebal, "n_boot": n_boot, "peso_max": peso_max * 100,
                       "rf": rf * 100, "inicio": ret.index[0].strftime("%Y-%m-%d"),
                       "fim": ret.index[-1].strftime("%Y-%m-%d"), "dias": len(ret)},
    }


