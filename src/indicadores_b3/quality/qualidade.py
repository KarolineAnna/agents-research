"""Checagens determinísticas sobre o resultado de indicadores.calcular()."""
import pandas as pd
import yfinance as yf

FAIXAS = {  # limites de plausibilidade (ajuste ao seu gosto)
    "pl": (-100, 200),
    "pvp": (0, 50),
    "dy": (0, 30),
    "roe": (-100, 100),
    "margem_liq": (-100, 100),
    "dl_ebitda": (-10, 15),
}
MAX_DIAS_BALANCO = 150   # fim do trimestre + 45 dias de prazo do ITR + folga
MAX_DIVERGENCIA = 0.30   # 30% de diferença vs. fonte externa


def checar(r: dict) -> list[dict]:
    """Recebe o dict de calcular(ticker) e devolve os problemas (vazio = ok)."""
    tk, problemas = r["ticker"], []
    ind = {i["id"]: i["valor"] for i in r["indicadores"]}

    def add(regra, campo, detalhe, severidade="alerta"):
        problemas.append({"ticker": tk, "regra": regra, "campo": campo,
                          "detalhe": detalhe, "severidade": severidade})

    # 1. Completude (campos que não se aplicam ao tipo de empresa, como EBITDA de banco, não contam)
    nao_aplica = {k for k, x in (r.get("rastreio") or {}).items() if (x.get("nota") or "").startswith("Não se aplica")}
    entradas_de = {i["id"]: set(i.get("entradas") or {}) for i in r["indicadores"]}
    for campo, v in {**r["valores"], **ind}.items():
        if v is None and campo not in nao_aplica and not (entradas_de.get(campo, set()) & nao_aplica):
            add("nulo", campo, "valor ausente")

    # 2. Defasagem do balanço
    dias = (pd.Timestamp.now() - pd.Timestamp(r["balanco_ref"])).days
    if dias > MAX_DIAS_BALANCO:
        add("defasagem", "balanco_ref", f"balanço com {dias} dias")

    # 3. Faixas de plausibilidade
    for campo, (lo, hi) in FAIXAS.items():
        v = ind.get(campo)
        if v is not None and not lo <= v <= hi:
            add("fora_da_faixa", campo, f"{v:.2f} fora de [{lo}, {hi}]")

    # 4. Comparação com fonte externa (yfinance)
    try:
        info = yf.Ticker(f"{tk}.SA").info or {}
    except Exception:  # noqa: BLE001 — sem internet: a comparação externa fica de fora
        info = {}
        add("sem_fonte_externa", "yfinance", "não consegui consultar o yfinance para comparar", "info")
    externos = {"pl": info.get("trailingPE"), "pvp": info.get("priceToBook"), "lpa": info.get("trailingEps")}
    for campo, ext in externos.items():
        v = ind.get(campo)
        if v and ext and abs(v - ext) / abs(ext) > MAX_DIVERGENCIA:
            add("divergencia_externa", campo, f"CVM={v:.2f} vs yfinance={ext:.2f}")

    return problemas
