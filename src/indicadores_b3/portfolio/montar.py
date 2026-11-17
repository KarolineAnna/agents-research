"""Montar uma carteira de verdade, a partir da análise de Markowitz.

O que este módulo faz, além da fronteira de carteira.py:
  1. Objetivo escolhido por você: menor risco, melhor risco × retorno (máximo Sharpe),
     risco-alvo (volatilidade máxima) ou retorno-alvo.
  2. Renda fixa (CDI) como opção na mistura: retorno = taxa livre de risco, risco zero.
  3. Limites mínimo e máximo por ativo (e para a renda fixa).
  4. Risco estimado com Ledoit-Wolf (mais estável que a covariância amostral) ou amostral.
  5. Métricas de perda: VaR e CVaR de 1 mês (95%), pior queda no período (drawdown),
     contribuição de cada ativo para o risco e número efetivo de ativos.
  6. Estabilidade: reamostra o histórico (bootstrap) e reotimiza, para mostrar a faixa
     em que cada peso costuma cair.
  7. Lista de compras: transforma pesos em quantidades (ações inteiras, Tesouro em
     frações de 0,01, cripto fracionada) com o valor que você vai investir.

Tudo usa as mesmas séries de preço em R$ do resto do site (ativos.serie_brl, com fontes).
"""
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from indicadores_b3.data.fontes import cdi_atual
from indicadores_b3.portfolio import carteira as cart
from indicadores_b3.portfolio import premissas as prem

DU = 252
RF_ID = "RENDA FIXA (CDI)"
OBJETIVOS = {
    "min_risco": "Menor risco",
    "max_sharpe": "Melhor risco × retorno (máximo Sharpe)",
    "vol_alvo": "Risco-alvo",
    "ret_alvo": "Retorno-alvo",
}
COMO_COMPRAR = {
    "b3": "Ações, FIIs e ETFs: quantidade inteira (o mercado fracionário aceita a partir de 1 unidade).",
    "tesouro": "Tesouro Direto: frações de 0,01 título.",
    "cripto": "Cripto: fracionada (até 8 casas).",
    "commodity": "Ouro (GC=F) é referência de preço; na B3 compre via ETF (ex.: GOLD11).",
    "moeda": "Dólar: referência pela PTAX; compre via conta em dólar ou ETF cambial.",
}


def _br(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


# ---------- dados ----------
def carregar(tickers: list[str], periodo: str):
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not tickers:
        raise ValueError("Informe pelo menos 1 ativo.")
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    series, info = {}, {}
    for t in tickers:
        s, i = cart._serie(t, periodo, hoje)
        series[i["ticker"]], info[i["ticker"]] = s, i
    px = pd.DataFrame(series)
    curtos = [t for t in px.columns if px[t].count() < 60]
    if curtos:
        raise ValueError(f"Histórico insuficiente para: {', '.join(curtos)}")
    px = px.dropna()
    ret = px.pct_change().dropna()
    if len(ret) < 60:
        raise ValueError("Poucos dias em comum entre os ativos (menos de 60).")
    return list(px.columns), px, ret, info, hoje


def estimar_cov(ret: pd.DataFrame, metodo: str) -> np.ndarray:
    if metodo == "ledoit":
        return LedoitWolf().fit(ret.values).covariance_ * DU
    return ret.cov().values * DU


# ---------- otimização ----------
def otimizar(mu, cov, rf, lim_min, lim_max, objetivo, alvo=None, fixar_rf=None):
    """Pesos ótimos. mu/cov já incluem a renda fixa na última posição, se ela estiver na mistura.
    fixar_rf=(índice, peso) prende a renda fixa num peso (usado no máximo Sharpe)."""
    n = len(mu)
    lo, hi = np.array(lim_min, float), np.array(lim_max, float)
    if fixar_rf is not None:
        i, p = fixar_rf
        lo[i] = hi[i] = p
    if lo.sum() > 1 + 1e-9:
        raise ValueError("A soma dos mínimos passa de 100%.")
    if hi.sum() < 1 - 1e-9:
        raise ValueError("A soma dos máximos não chega a 100%: aumente algum limite.")
    var = lambda w: w @ cov @ w  # noqa: E731
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    if objetivo == "min_risco":
        f = var
    elif objetivo == "max_sharpe":
        f = lambda w: -(w @ mu - rf) / math.sqrt(max(var(w), 1e-12))  # noqa: E731
    elif objetivo == "vol_alvo":
        f = lambda w: -(w @ mu)  # noqa: E731
        cons.append({"type": "ineq", "fun": lambda w: (alvo / 100) ** 2 - var(w)})
    elif objetivo == "ret_alvo":
        f = var
        cons.append({"type": "ineq", "fun": lambda w: w @ mu - alvo / 100})
    else:
        raise ValueError("Objetivo inválido.")
    x0 = np.clip(np.full(n, 1 / n), lo, hi)
    x0 = x0 / x0.sum() if x0.sum() > 0 else x0
    melhor = None
    for tentativa in (x0, (lo + hi) / 2, lo + (1 - lo.sum()) * (hi - lo) / max((hi - lo).sum(), 1e-12)):
        r = minimize(f, tentativa, method="SLSQP", bounds=list(zip(lo, hi)), constraints=cons,
                     options={"maxiter": 800, "ftol": 1e-12})
        viavel = r.success and all(c["fun"](r.x) >= -1e-6 for c in cons if c["type"] == "ineq")
        if viavel and (melhor is None or r.fun < melhor.fun):
            melhor = r
    if melhor is None:
        if objetivo == "vol_alvo":
            raise ValueError(f"Não há carteira com risco de até {_br(alvo)}% a.a. com esses limites. "
                             "Aumente o risco-alvo ou permita mais renda fixa.")
        if objetivo == "ret_alvo":
            raise ValueError(f"Nenhuma carteira chega a {_br(alvo)}% a.a. de retorno esperado com esses limites. "
                             "Reduza o retorno-alvo ou afrouxe os limites.")
        raise ValueError("A otimização não convergiu com esses limites.")
    w = np.clip(melhor.x, 0, None)
    return w / w.sum()


# ---------- métricas ----------
def metricas(w, nomes, mu, cov, rf, ret_dia: pd.DataFrame):
    var = float(w @ cov @ w)
    vol = math.sqrt(max(var, 0))
    er = float(w @ mu)
    rc = (w * (cov @ w)) / var if var > 0 else np.zeros_like(w)
    rp = ret_dia.values @ w  # retorno diário da carteira no histórico (in-sample)
    serie = pd.Series(np.cumprod(1 + rp), index=ret_dia.index)
    mes = (serie / serie.shift(21) - 1).dropna()
    var95 = float(np.quantile(mes, 0.05)) if len(mes) > 20 else None
    cvar95 = float(mes[mes <= var95].mean()) if var95 is not None else None
    topo = serie.cummax()
    dd = serie / topo - 1
    fundo = dd.idxmin()
    inicio_dd = serie.loc[:fundo].idxmax()
    w_risco = w[[n != RF_ID for n in nomes]]
    return {
        "retorno": er * 100, "volatilidade": vol * 100,
        "sharpe": (er - rf) / vol if vol > 0 else None,
        "var95_mes": var95 * 100 if var95 is not None else None,
        "cvar95_mes": cvar95 * 100 if cvar95 is not None else None,
        "max_drawdown": float(dd.min()) * 100, "drawdown_de": inicio_dd.strftime("%Y-%m-%d"),
        "drawdown_ate": fundo.strftime("%Y-%m-%d"),
        "retorno_hist_aa": float((serie.iloc[-1] ** (DU / len(serie)) - 1) * 100),
        "n_efetivo": float(1 / (w_risco ** 2).sum() * (w_risco.sum() ** 2)) if w_risco.sum() > 0 else 0.0,
        "contribuicao_risco": {n: float(c * 100) for n, c in zip(nomes, rc)},
        "serie": serie,
    }


def estabilidade(ret_risco: pd.DataFrame, mu_fixo, cov_metodo, rf, lim_min, lim_max, objetivo, alvo,
                 com_rf, fixar_rf, nomes, n=60):
    """Reamostra os dias (bootstrap) e reotimiza: faixa de 10% a 90% de cada peso."""
    rng = np.random.default_rng(7)
    pesos = []
    T = len(ret_risco)
    for _ in range(n):
        amostra = ret_risco.iloc[rng.integers(0, T, T)]
        mu = amostra.mean().values * DU if mu_fixo is None else mu_fixo[:ret_risco.shape[1]]
        cov = estimar_cov(amostra, cov_metodo)
        if com_rf:
            mu = np.append(mu, rf)
            cov = np.pad(cov, ((0, 1), (0, 1)))
        try:
            pesos.append(otimizar(mu, cov, rf, lim_min, lim_max, objetivo, alvo, fixar_rf))
        except ValueError:
            continue
    if len(pesos) < 10:
        return None
    p = np.array(pesos) * 100
    return {nm: {"p10": float(np.percentile(p[:, i], 10)), "p50": float(np.percentile(p[:, i], 50)),
                 "p90": float(np.percentile(p[:, i], 90))} for i, nm in enumerate(nomes)} | {"_n": len(pesos)}


# ---------- lista de compras ----------
def lista_compras(w, nomes, px, info, valor):
    itens, gasto = [], 0.0
    alvo = {n: valor * p for n, p in zip(nomes, w)}
    for nm in nomes:
        if nm == RF_ID:
            continue
        preco = float(px[nm].iloc[-1])
        classe = info[nm]["classe"]
        bruto = alvo[nm] / preco
        if classe == "b3":
            q = math.floor(bruto)
        elif classe == "tesouro":
            q = math.floor(bruto * 100) / 100
        elif classe == "cripto":
            q = math.floor(bruto * 1e8) / 1e8
        else:
            q = bruto
        itens.append({"ticker": nm, "nome": info[nm].get("nome", nm), "classe": classe, "preco": preco,
                      "data_preco": px.index[-1].strftime("%Y-%m-%d"), "quantidade": q, "alvo": alvo[nm],
                      "passo": 1 if classe == "b3" else 0.01 if classe == "tesouro" else 0,
                      "como": COMO_COMPRAR.get(classe, "")})
    # sobra: compra mais 1 unidade de quem está mais abaixo do alvo, enquanto couber
    sobra = valor * (1 - (w[nomes.index(RF_ID)] if RF_ID in nomes else 0)) - sum(i["quantidade"] * i["preco"] for i in itens)
    for _ in range(500):
        cand = [i for i in itens if i["passo"] and i["passo"] * i["preco"] <= sobra + 1e-9]
        if not cand:
            break
        # só compra mais uma unidade se isso deixar o ativo MAIS PERTO do alvo; o resto vai para a renda fixa
        cand = [i for i in cand if abs(i["quantidade"] * i["preco"] + i["passo"] * i["preco"] - i["alvo"])
                < abs(i["quantidade"] * i["preco"] - i["alvo"])]
        if not cand:
            break
        i = min(cand, key=lambda x: (x["quantidade"] * x["preco"] - x["alvo"]) / max(x["alvo"], 1e-9))
        i["quantidade"] = round(i["quantidade"] + i["passo"], 2)
        sobra -= i["passo"] * i["preco"]
    for i in itens:
        i["valor"] = i["quantidade"] * i["preco"]
        gasto += i["valor"]
    rf_valor = valor - gasto
    if RF_ID in nomes or rf_valor > 0.005:
        itens.append({"ticker": RF_ID, "nome": "Renda fixa pós-fixada (Tesouro Selic, CDB 100% CDI…)", "classe": "rf",
                      "preco": None, "quantidade": None, "alvo": alvo.get(RF_ID, 0.0), "valor": rf_valor,
                      "como": "Inclui a sobra das compras em unidades inteiras."})
    for i in itens:
        i["peso_real"] = i["valor"] / valor * 100
    return itens


def selic_equivalente() -> str | None:
    """Tesouro Selic à venda com vencimento mais curto: o equivalente real da 'renda fixa (CDI)'."""
    try:
        from indicadores_b3.data import tesouro
        cods = sorted(o["ticker"] for o in tesouro.ofertados() if o["ticker"].startswith("TD-SELIC-"))
        return cods[0] if cods else None
    except Exception:  # noqa: BLE001
        return None


# ---------- entrada ----------
MODELOS = {"historico": "Média histórica", "capm": "CAPM", "blocos": "Premissas de mercado (blocos)",
           "bl": "Black-Litterman (premissas + suas visões)"}


def calcular_premissas(tickers, periodo, globais=None, sobrescritas=None) -> dict:
    """Premissas por blocos para os ativos (usado para mostrar e editar antes de montar)."""
    risco, px, ret, info, hoje = carregar(tickers, periodo)
    precos = {t: float(px[t].iloc[-1]) for t in risco}
    classes = {t: cart.classe_fiscal(t) for t in risco if info[t]["classe"] == "b3"}
    return prem.premissas(risco, precos, classes, globais, sobrescritas)


def montar(tickers, periodo="3y", rf_pct=None, modelo="historico", mercado_pct=None, cov_metodo="ledoit",
           objetivo="max_sharpe", alvo=None, limites=None, com_rf=True, rf_min=0.0, rf_max=100.0,
           valor=10000.0, bootstrap=True, globais=None, sobrescritas=None, visoes=None) -> dict:
    if periodo not in cart.PERIODOS:
        raise ValueError("Período inválido.")
    if objetivo not in OBJETIVOS:
        raise ValueError("Objetivo inválido.")
    if objetivo in ("vol_alvo", "ret_alvo") and (alvo is None or alvo <= 0):
        raise ValueError("Informe o valor-alvo (% ao ano).")
    if valor <= 0:
        raise ValueError("Informe um valor a investir maior que zero.")
    rf_info = None
    if rf_pct is None:
        rf_info = cdi_atual()
        rf_pct = rf_info["valor"]
    rf = rf_pct / 100
    risco, px, ret, info, hoje = carregar(tickers, periodo)

    if modelo not in MODELOS:
        raise ValueError("Modelo de retorno inválido.")
    mu = ret.mean().values * DU
    capm_info = prem_info = bl_info = None
    cov = estimar_cov(ret, cov_metodo)
    if modelo == "capm":
        capm_info = cart.capm(ret, periodo, hoje, rf, mercado_pct)
        mu = np.array([a["retorno_capm"] for a in capm_info["ativos"]]) / 100
    elif modelo in ("blocos", "bl"):
        precos = {t: float(px[t].iloc[-1]) for t in risco}
        classes = {t: cart.classe_fiscal(t) for t in risco if info[t]["classe"] == "b3"}
        prem_info = prem.premissas(risco, precos, classes, globais, sobrescritas)
        faltam = [a["ticker"] for a in prem_info["ativos"] if a["valor"] is None]
        if faltam:
            raise ValueError(f"Sem premissa de retorno para {', '.join(faltam)}: informe um valor na tabela de premissas.")
        mu = np.array([a["valor"] for a in prem_info["ativos"]]) / 100
        # com premissas de mercado, a renda fixa rende o CDI esperado no horizonte (juro prefixado no prazo)
        rf = prem_info["rf_bloco"] / 100
        if modelo == "bl":
            bl_info = prem.black_litterman(mu, cov, list(risco), visoes or [])
            for v in bl_info["visoes"]:
                v["ativo_nome"] = info.get(v["a"], {}).get("nome", v["a"])
            mu = bl_info["posterior"]

    limites = limites or {}
    nomes = list(risco)
    lim_min = [limites.get(t, {}).get("min", 0) / 100 for t in risco]
    lim_max = [limites.get(t, {}).get("max", 100) / 100 for t in risco]
    if com_rf:
        nomes.append(RF_ID)
        mu = np.append(mu, rf)
        cov = np.pad(cov, ((0, 1), (0, 1)))
        lim_min.append(rf_min / 100)
        lim_max.append(rf_max / 100)
    # máximo Sharpe e menor risco: a renda fixa fica no mínimo pedido (senão o "menor risco" seria 100% CDI
    # e o Sharpe não muda com ela); nos objetivos com alvo, o otimizador decide quanto de renda fixa usar
    fixar = (len(nomes) - 1, rf_min / 100) if com_rf and objetivo in ("max_sharpe", "min_risco") else None

    w = otimizar(mu, cov, rf, lim_min, lim_max, objetivo, alvo, fixar)
    ret_dia = ret.copy()
    if com_rf:
        ret_dia[RF_ID] = (1 + rf) ** (1 / DU) - 1
    m = metricas(w, nomes, mu, cov, rf, ret_dia)

    est = None
    if bootstrap:
        est = estabilidade(ret, mu if modelo == "capm" else None, cov_metodo, rf, lim_min, lim_max,
                           objetivo, alvo, com_rf, fixar, nomes)

    # referências no mesmo período: Ibovespa e CDI à taxa atual
    serie = m.pop("serie")
    ib = cart._ibov(periodo, hoje)
    ib = ib.reindex(serie.index).ffill()
    refs = {"Ibovespa": (ib / ib.dropna().iloc[0] * 100) if ib.notna().any() else None,
            "CDI (taxa atual)": pd.Series((1 + rf) ** (np.arange(1, len(serie) + 1) / DU) * 100, index=serie.index)}

    alocacao = [{"ticker": nm, "nome": info[nm]["nome"] if nm in info else "Renda fixa (CDI)",
                 "peso": float(w[i] * 100), "retorno_esperado": float(mu[i] * 100),
                 "volatilidade": float(math.sqrt(cov[i, i]) * 100),
                 "contribuicao_risco": m["contribuicao_risco"][nm],
                 "min": lim_min[i] * 100, "max": lim_max[i] * 100,
                 "faixa": est.get(nm) if est else None,
                 "fontes": info[nm]["fontes"] if nm in info else []} for i, nm in enumerate(nomes)]

    return {
        "parametros": {"periodo": cart.PERIODOS[periodo], "rf": rf * 100, "rf_fonte": rf_info, "modelo": modelo,
                       "modelo_nome": MODELOS[modelo],
                       "cov": cov_metodo, "objetivo": objetivo, "objetivo_nome": OBJETIVOS[objetivo], "alvo": alvo,
                       "com_rf": com_rf, "valor": valor, "inicio": ret.index[0].strftime("%Y-%m-%d"),
                       "fim": ret.index[-1].strftime("%Y-%m-%d"), "dias": len(ret)},
        "alocacao": sorted(alocacao, key=lambda a: -a["peso"]),
        "metricas": {k: v for k, v in m.items() if k != "contribuicao_risco"},
        "estabilidade_n": est.get("_n") if est else None,
        "compras": lista_compras(w, nomes, px, info, valor),
        "historico": {"datas": [d.strftime("%Y-%m-%d") for d in serie.index],
                      "carteira": [round(float(x) * 100, 3) for x in serie],
                      "refs": {k: (None if v is None else [None if pd.isna(x) else round(float(x), 3) for x in v])
                               for k, v in refs.items()}},
        "capm": capm_info,
        "premissas": prem_info,
        "black_litterman": None if bl_info is None else {
            "visoes": bl_info["visoes"], "tau": prem.TAU,
            "ativos": [{"ticker": t, "prior": next(a["valor"] for a in prem_info["ativos"] if a["ticker"] == t),
                        "posterior": float(bl_info["posterior"][i] * 100)} for i, t in enumerate(risco)]},
        "rf_usado": rf * 100,
        "rf_equivalente": selic_equivalente() if com_rf else None,
    }
