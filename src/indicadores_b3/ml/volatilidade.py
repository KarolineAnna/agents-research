"""Volatilidade: GARCH(1,1) contra a volatilidade histórica de 21 dias, avaliados fora da amostra."""
import numpy as np
import pandas as pd

from indicadores_b3.portfolio.carteira import _serie

DIAS = 252


# =====================================================================
# 2. GARCH
# =====================================================================
def garch(ticker: str, periodo="5y", fracao_teste=0.25) -> dict:

    t = ticker.strip().upper()
    s, info = _serie(t, periodo, pd.Timestamp.now().strftime("%Y-%m-%d"))
    r = (np.log(s).diff().dropna() * 100)  # em %, como a biblioteca arch recomenda
    if len(r) < 400:
        raise ValueError("Histórico curto demais para o GARCH (precisa de ~400 dias).")
    out = avaliar_garch(r, fracao_teste)
    return {"ticker": info["ticker"], "nome": info["nome"], "fontes": info["fontes"], **out}


def avaliar_garch(r: pd.Series, fracao_teste: float = 0.25) -> dict:
    """Núcleo puro: GARCH(1,1) × volatilidade histórica de 21 dias, avaliados fora da amostra (MSE e QLIKE).
    ``r``: log-retornos diários em % (índice de datas). Parâmetros estimados só com o trecho de treino."""
    from arch import arch_model

    if len(r) < 400:
        raise ValueError("Histórico curto demais para o GARCH (precisa de ~400 dias).")
    corte = int(len(r) * (1 - fracao_teste))
    obs_ano = len(r) / ((r.index[-1] - r.index[0]).days / 365.25)  # ~252 B3, ~365 cripto

    # Fora da amostra: parâmetros estimados só com o início, previsões de 1 dia no trecho final
    mod = arch_model(r, vol="GARCH", p=1, q=1, mean="Constant", dist="normal")
    res_treino = mod.fit(last_obs=r.index[corte], disp="off")
    prev = res_treino.forecast(horizon=1, start=r.index[corte], reindex=False).variance.iloc[:, 0]
    # previsão feita em t vale para t+1
    var_garch = prev.shift(1).dropna()
    var_hist = (r.rolling(21).var().shift(1)).reindex(var_garch.index)
    real = ((r - r[:corte].mean()) ** 2).reindex(var_garch.index)
    ok = var_hist.notna() & (real > 0)
    var_garch, var_hist, real = var_garch[ok], var_hist[ok], real[ok]

    def perdas(v):
        return {"mse": float(((real - v) ** 2).mean()), "qlike": float((np.log(v) + real / v).mean())}

    p_g, p_h = perdas(var_garch), perdas(var_hist)

    # Modelo com todos os dados, para a previsão de hoje
    res = mod.fit(disp="off")
    w, a, b = (float(res.params[k]) for k in ("omega", "alpha[1]", "beta[1]"))
    persist = a + b
    fc = res.forecast(horizon=21, reindex=False).variance.iloc[-1].values
    anual = lambda var: float(np.sqrt(var * obs_ano))
    cond = res.conditional_volatility * np.sqrt(obs_ano)
    hist21 = r.rolling(21).std() * np.sqrt(obs_ano)
    ult = r.index[-min(len(r), int(obs_ano * 2)):]

    return {
        "parametros": {"omega": w, "alpha": a, "beta": b, "persistencia": persist,
                       "meia_vida": float(np.log(0.5) / np.log(persist)) if 0 < persist < 1 else None,
                       "vol_longo_prazo": anual(w / (1 - persist)) if persist < 1 else None, "obs_ano": obs_ano},
        "previsao": {"amanha": anual(fc[0]), "media_21d": anual(fc.mean()), "hist_21d": float(hist21.iloc[-1])},
        "teste": {"inicio": r.index[corte].strftime("%Y-%m-%d"), "fim": r.index[-1].strftime("%Y-%m-%d"),
                  "dias": int(ok.sum()), "garch": p_g, "historica": p_h,
                  "vencedor_qlike": "garch" if p_g["qlike"] < p_h["qlike"] else "historica",
                  "vencedor_mse": "garch" if p_g["mse"] < p_h["mse"] else "historica"},
        "grafico": {"datas": [d.strftime("%Y-%m-%d") for d in ult],
                    "garch": [round(float(x), 2) for x in cond.reindex(ult)],
                    "hist21": [None if pd.isna(x) else round(float(x), 2) for x in hist21.reindex(ult)],
                    "inicio_teste": r.index[corte].strftime("%Y-%m-%d")},
    }


