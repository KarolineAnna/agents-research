"""Anomalias contábeis (usado na aba Saúde dos dados): Isolation Forest (Liu, Ting e Zhou, 2008) sobre razões contábeis de
todas as companhias do mesmo ITR da CVM, mais checagens de identidade contábil. Serve para achar números estranhos que
merecem conferência, não para escolher investimentos. Bancos e seguradoras ficam de fora (plano de contas diferente).
(O agrupamento por k-means foi retirado: a literatura de pares usa setor, distância de preços ou cointegração, e o site
já escolhe pares pelo setor declarado à CVM.)"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from indicadores_b3.data import fundamentos as f

DIAS = 252


# =====================================================================
# ANOMALIAS (todas as companhias do mesmo ITR)
# =====================================================================
RAZOES = {
    "margem_bruta": ("Margem bruta", "Resultado bruto (3.03) ÷ Receita (3.01)"),
    "margem_ebit": ("Margem EBIT", "EBIT (3.05) ÷ Receita (3.01)"),
    "margem_liq": ("Margem líquida", "Lucro líquido (3.11) ÷ Receita (3.01)"),
    "roe": ("Lucro ÷ Patrimônio (no ano)", "Lucro líquido (3.11) ÷ Patrimônio líquido (2.03)"),
    "endividamento": ("Endividamento geral", "(Passivo circulante 2.01 + não circulante 2.02) ÷ Ativo total (1)"),
    "liquidez": ("Liquidez corrente", "Ativo circulante (1.01) ÷ Passivo circulante (2.01)"),
    "giro": ("Giro do ativo (no ano)", "Receita (3.01) ÷ Ativo total (1)"),
}
CONTAS_DRE = ["3.01", "3.02", "3.03", "3.04", "3.05", "3.06", "3.07", "3.08", "3.09", "3.10", "3.11"]
CONTAS_BP = ["1", "1.01", "2", "2.01", "2.02", "2.03"]


def _painel(ano: int) -> pd.DataFrame:
    """Uma linha por companhia: contas do último ITR do ano (valores acumulados no ano)."""
    partes = []
    for suf, contas in (("DRE_con", CONTAS_DRE), ("BPA_con", CONTAS_BP), ("BPP_con", CONTAS_BP)):
        d = f.ler_csv("ITR", ano, suf)
        if d.empty:
            return pd.DataFrame()
        d = d[d.ORDEM_EXERC.str.startswith("ÚLT") & d.CD_CONTA.isin(contas)].copy()
        d["VERSAO"] = d.VERSAO.astype(int)
        d = d[d.VERSAO == d.groupby(["CNPJ", "DT_REFER"]).VERSAO.transform("max")]
        if "DT_INI_EXERC" in d:  # DRE: acumulado do ano (menor data de início)
            d = d[d.DT_INI_EXERC == d.groupby(["CNPJ", "DT_REFER"]).DT_INI_EXERC.transform("min")]
        mult = d.ESCALA_MOEDA.str.upper().eq("MIL").map({True: 1000, False: 1})
        d["VL"] = d.VL_CONTA.astype(float) * mult
        partes.append(d[["CNPJ", "DENOM_CIA", "DT_REFER", "CD_CONTA", "VL"]])
    d = pd.concat(partes)
    return d.pivot_table(index=["CNPJ", "DENOM_CIA", "DT_REFER"], columns="CD_CONTA", values="VL", aggfunc="first").reset_index()


def _razoes(p: pd.DataFrame) -> pd.DataFrame:
    g = lambda c: p[c] if c in p else np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        out = pd.DataFrame({
            "margem_bruta": g("3.03") / g("3.01"), "margem_ebit": g("3.05") / g("3.01"),
            "margem_liq": g("3.11") / g("3.01"), "roe": g("3.11") / g("2.03"),
            "endividamento": (g("2.01") + g("2.02")) / g("1"), "liquidez": g("1.01") / g("2.01"),
            "giro": g("3.01") / g("1"),
        })
    return out.replace([np.inf, -np.inf], np.nan) * np.array([100, 100, 100, 100, 100, 1, 1])


def identidades(linha: pd.Series) -> list[dict]:
    """Contas que deveriam fechar entre si no próprio documento."""
    v = lambda c: linha.get(c, np.nan)
    regras = [("Ativo total (1) = Passivo + PL (2)", v("1"), v("2")),
              ("Resultado bruto (3.03) = Receita (3.01) + Custo (3.02)", v("3.03"), v("3.01") + v("3.02")),
              ("EBIT (3.05) = Resultado bruto (3.03) + Despesas operacionais (3.04)", v("3.05"), v("3.03") + v("3.04")),
              ("Antes dos tributos (3.07) = EBIT (3.05) + Financeiro (3.06)", v("3.07"), v("3.05") + v("3.06")),
              ("Operações continuadas (3.09) = Antes dos tributos (3.07) + IR/CSLL (3.08)", v("3.09"), v("3.07") + v("3.08")),
              ("Lucro (3.11) = Continuadas (3.09) + Descontinuadas (3.10)", v("3.11"), v("3.09") + (0 if pd.isna(v("3.10")) else v("3.10")))]
    out = []
    for nome, a, b in regras:
        if pd.isna(a) or pd.isna(b):
            out.append({"regra": nome, "status": "sem dados", "informado": None, "calculado": None})
            continue
        ok = abs(a - b) <= max(abs(a), 1) * 0.005 + 1000
        out.append({"regra": nome, "status": "ok" if ok else "não fecha", "informado": float(a), "calculado": float(b)})
    return out


def anomalias(ticker: str) -> dict:
    t = ticker.strip().upper()
    cnpj = f.mapa_tickers().get(t)
    if not cnpj:
        raise LookupError(f"{t}: só ações de companhias abertas (cadastro CVM).")
    ano = pd.Timestamp.now().year
    p = _painel(ano)
    if p.empty or cnpj not in set(p.CNPJ):
        ano -= 1
        p = _painel(ano)
    alvo = p[p.CNPJ == cnpj].sort_values("DT_REFER")
    if alvo.empty:
        raise LookupError(f"{t}: sem ITR consolidado em {ano}.")
    ref = alvo.DT_REFER.iloc[-1]
    p = p[p.DT_REFER == ref].reset_index(drop=True)  # só quem reportou o mesmo período
    linha_alvo = p[p.CNPJ == cnpj].iloc[0]
    ident = identidades(linha_alvo)

    rz = _razoes(p)
    validos = (p.get("3.01", 0) > 0) & p.get("3.03").notna() & rz.notna().all(axis=1)  # tira bancos/seguradoras
    p, rz = p[validos].reset_index(drop=True), rz[validos].reset_index(drop=True)
    if cnpj not in set(p.CNPJ):
        return {"ticker": t, "ref": ref, "identidades": ident, "erro_pares": "A empresa não usa o modelo padrão de DRE/balanço "
                "(ex.: banco ou seguradora); a comparação com as outras companhias não se aplica.", "n_empresas": 0}
    i_alvo = int(p.index[p.CNPJ == cnpj][0])

    # winsoriza (corta extremos em 2%/98%) e padroniza antes dos modelos
    rw = rz.clip(rz.quantile(0.02), rz.quantile(0.98), axis=1)
    X = StandardScaler().fit_transform(rw)
    iso = IsolationForest(contamination=0.05, random_state=42).fit(X)
    score = -iso.score_samples(X)  # maior = mais anômalo
    if len(p) < 10:
        raise ValueError(f"Poucas companhias comparáveis no período ({len(p)}).")

    percentis = {r: float((rz[r] < rz[r].iloc[i_alvo]).mean() * 100) for r in RAZOES}
    med, mad = rw.median(), (rw - rw.median()).abs().median() * 1.4826
    zrob = {r: float((rw[r].iloc[i_alvo] - med[r]) / mad[r]) if mad[r] > 0 else 0.0 for r in RAZOES}

    return {
        "ticker": t, "empresa": linha_alvo.DENOM_CIA, "ref": ref, "n_empresas": int(len(p)),
        "fonte": {"arquivos": [f"itr_cia_aberta_{s}_{ano}.csv" for s in ("DRE_con", "BPA_con", "BPP_con")],
                  "url": f"{f.CVM}/ITR/DADOS/itr_cia_aberta_{ano}.zip"},
        "razoes_def": RAZOES,
        "alvo": {r: float(rz[r].iloc[i_alvo]) for r in RAZOES},
        "percentis": percentis, "z_robusto": zrob,
        "mediana_mercado": {r: float(rz[r].median()) for r in RAZOES},
        "anomalia": {"score": float(score[i_alvo]), "percentil": float((score < score[i_alvo]).mean() * 100),
                     "sinalizada": bool(iso.predict(X)[i_alvo] == -1)},
        "identidades": ident,
    }

