"""DRE e Balanço Patrimonial da CVM, linha a linha, com rastreio.

- DRE: cada conta (até o 3º nível, ex.: 3.04.01) nos últimos 12 meses e em cada ano fechado (DFP).
- Balanço: cada conta na data do último documento e no fim do exercício anterior
  (o próprio ITR/DFP traz as duas colunas: ÚLTIMO e PENÚLTIMO).

Os nomes das contas vêm do próprio arquivo da CVM (DS_CONTA), então batem com o documento oficial.
"""
import pandas as pd

from indicadores_b3.data import fundamentos as f

NIVEL_MAX = 4  # 4 = "3.06.01.01"; aumente para ver mais detalhe


def nivel(conta: str) -> int:
    return conta.count(".") + 1


def contas(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Códigos e nomes, na ordem do plano de contas, usando o nome do documento mais recente."""
    d = df[df.CD_CONTA.map(nivel) <= NIVEL_MAX].sort_values("DT_REFER")
    nomes = d.groupby("CD_CONTA")["DS_CONTA"].last()
    chave = lambda c: [int(x) for x in c.split(".")]
    return sorted(nomes.items(), key=lambda kv: chave(kv[0]))


def dre(cnpj: str) -> dict:
    df = f.demonstrativo("DRE_con", cnpj)
    if df.empty:
        raise LookupError("DRE consolidada não encontrada na CVM.")
    anos = sorted(df[df.FONTE == "DFP"].DT_REFER.unique())
    # período acumulado mais recente (ITR do trimestre ou DFP do ano) e o mesmo período do ano anterior
    ref_ult = df.DT_REFER.max()
    fonte_ult = "DFP" if (df[df.DT_REFER == ref_ult].FONTE == "DFP").any() else "ITR"
    periodos = {}
    for ordem, chave in (("ÚLT", "atual"), ("PEN", "anterior")):
        d = df[(df.FONTE == fonte_ult) & (df.DT_REFER == ref_ult) & df.ORDEM_EXERC.str.startswith(ordem)]
        if not d.empty:
            d = d[d.DT_INI_EXERC == d.DT_INI_EXERC.min()]
            periodos[chave] = {"inicio": d.DT_INI_EXERC.iloc[0], "fim": d.DT_FIM_EXERC.iloc[0]}
    linhas = []
    for conta, nome in contas(df):
        anual = {}
        for ref in anos:
            # o DFP traz o ano (ÚLTIMO) e o ano anterior (PENÚLTIMO); o ÚLTIMO de um DFP mais novo prevalece
            for ordem, ano in (("PEN", str(int(ref[:4]) - 1)), ("ÚLT", ref[:4])):
                r = f.linha_acumulada(df, "DFP", ref, ordem, conta)
                if r is not None and (ordem == "ÚLT" or ano not in anual):
                    anual[ano] = {"valor": float(r.VL), "nota": "",
                                  "componentes": [f.comp("+", "Exercício completo", f.linha_cvm(r))]}
        acum = {}
        for ordem, chave in (("ÚLT", "atual"), ("PEN", "anterior")):
            r = f.linha_acumulada(df, fonte_ult, ref_ult, ordem, conta)
            if r is not None:
                acum[chave] = {"valor": float(r.VL), "componentes": [f.comp("+", "Acumulado no exercício", f.linha_cvm(r))],
                               "nota": ""}
        linhas.append({"conta": conta, "descricao": nome, "nivel": nivel(conta), "ttm": f.ttm(df, conta), "anos": anual,
                       "acumulado": acum})
    # Depreciação e amortização (DVA 7.04.01), para calcular o EBITDA na página
    dva = f.demonstrativo("DVA_con", cnpj)
    da = None
    if not dva.empty:
        anual = {}
        for ref in anos:
            r = f.linha_acumulada(dva, "DFP", ref, "ÚLT", "7.04.01")
            if r is not None:
                anual[ref[:4]] = {"valor": abs(float(r.VL)), "nota": "Na DVA a depreciação vem negativa; usamos o valor absoluto.",
                                  "componentes": [f.comp("+", "Exercício completo", f.linha_cvm(r))]}
        t = f.ttm(dva, "7.04.01")
        if t["valor"] is not None:
            t = {**t, "valor": abs(t["valor"]), "nota": t["nota"] + " Na DVA a depreciação vem negativa; usamos o valor absoluto."}
        da = {"conta": "7.04.01", "descricao": "Depreciação, Amortização e Exaustão (DVA)", "ttm": t, "anos": anual}
    anos_dre = sorted({a for l in linhas for a in l["anos"]})
    return {"ref": df.DT_REFER.max(), "anos": anos_dre, "linhas": linhas, "depreciacao": da,
            "acumulado": {"fonte": fonte_ult, **periodos}}


def balanco(cnpj: str) -> dict:
    bpa, bpp = f.demonstrativo("BPA_con", cnpj), f.demonstrativo("BPP_con", cnpj)
    if bpa.empty or bpp.empty:
        raise LookupError("Balanço patrimonial consolidado não encontrado na CVM.")
    ref = max(bpa.DT_REFER.max(), bpp.DT_REFER.max())
    linhas, ref_anterior = [], None
    for df in (bpa, bpp):
        doc = df[df.DT_REFER == ref]
        for conta, nome in contas(doc):
            atual = doc[(doc.CD_CONTA == conta) & doc.ORDEM_EXERC.str.startswith("ÚLT")]
            ant = doc[(doc.CD_CONTA == conta) & doc.ORDEM_EXERC.str.startswith("PEN")]
            if atual.empty:
                continue
            a = atual.iloc[0]
            linha = {"conta": conta, "descricao": nome, "nivel": nivel(conta),
                     "atual": {"valor": float(a.VL), "componentes": [f.comp("+", "Saldo na data", f.linha_cvm(a))],
                               "nota": ""},
                     "anterior": None}
            if not ant.empty:
                p = ant.iloc[0]
                ref_anterior = p.DT_FIM_EXERC if "DT_FIM_EXERC" in p and pd.notna(p.DT_FIM_EXERC) else ref_anterior
                linha["anterior"] = {"valor": float(p.VL),
                                     "componentes": [f.comp("+", "Saldo no fim do exercício anterior", f.linha_cvm(p))],
                                     "nota": ""}
            linhas.append(linha)
    # saldos no fim de cada exercício (DFP): ÚLTIMO = ano do documento, PENÚLTIMO = ano anterior
    anos = {}
    for df in (bpa, bpp):
        dfp = df[df.FONTE == "DFP"]
        for _, r in dfp.iterrows():
            ano = r.DT_FIM_EXERC[:4] if "DT_FIM_EXERC" in r and pd.notna(r.DT_FIM_EXERC) else None
            if ano and (r.ORDEM_EXERC.startswith("ÚLT") or (ano, r.CD_CONTA) not in anos):
                anos[(ano, r.CD_CONTA)] = float(r.VL)
    lista_anos = sorted({a for a, _ in anos})
    for l in linhas:
        l["anos"] = {a: anos[(a, l["conta"])] for a in lista_anos if (a, l["conta"]) in anos}
    return {"ref": ref, "ref_anterior": ref_anterior, "linhas": linhas, "anos": lista_anos}


def demonstracoes(ticker: str) -> dict:
    t = ticker.strip().upper()
    cnpj = f.mapa_tickers().get(t)
    if not cnpj:
        raise LookupError(f"{t}: não é uma companhia aberta no cadastro da CVM (só ações têm DRE e balanço aqui).")
    d = f.demonstrativo("DRE_con", cnpj)
    nome = d.DENOM_CIA.iloc[0] if not d.empty else t
    return {"ticker": t, "empresa": nome, "dre": dre(cnpj), "balanco": balanco(cnpj)}
