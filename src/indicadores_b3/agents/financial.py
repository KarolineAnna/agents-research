"""Agente 1 — Financial Analyst: análise fundamentalista a partir das demonstrações da CVM.

Identifica o tipo de empresa pelo plano de contas:
  - banco: DRE começa por "Receitas da Intermediação Financeira" (plano de instituições financeiras);
  - demais: plano padrão (indicadores.py do site).
Bancos não seguem a mesma numeração de contas entre si (o lucro do Itaú é 3.09.01, o do Bradesco 3.11.01),
então as contas são encontradas pela DESCRIÇÃO, e a conta usada fica registrada em cada fato.

Saída: um Dossie (fatos.py) com fatos (CVM, preço), calculados (indicadores com fórmula), ausentes e alertas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from indicadores_b3.agents.fatos import Dossie, div, vezes
from indicadores_b3.data import fundamentos as f

# ações por unit (a unit é negociada como um pacote de ações) — conferir no estatuto/RI
ACOES_POR_UNIT = {"SANB11": 2, "BPAC11": 3, "TAEE11": 3, "KLBN11": 5, "ENGI11": 5, "SAPR11": 5, "ALUP11": 3}

# conceitos de banco → expressões que identificam a conta pela descrição
BANCO_DRE = {
    "receitas_intermediacao": r"^Receitas? (?:da|de) Intermedia",
    "resultado_bruto": r"^Resultado Bruto (?:de |da )?Intermedia",
    "receita_juros": r"^Receitas? (?:com |de )?Juros",
    "despesa_juros": r"^Despesas? (?:com |de )?Juros",
    "perdas_credito": r"Perda.*(?:Esperada|Cr[ée]dito)|Provis[ãa]o para Perda",
    "servicos": r"Presta[çc][ãa]o de Servi[çc]os",
    "seguros": r"Seguro",
    "pessoal": r"^Despesas? (?:de|com) Pessoal",
    "administrativas": r"Despesas? (?:Gerais e )?Administrativ|Outras Despesas (?:de )?Administrativ",
    "lucro_controladores": r"Atribu[íi]do (?:a|aos) S[óo]cios da Empresa Controladora",
    "lucro_total": r"^Lucro.*(?:Consolidado|L[íi]quido)",
}
BANCO_BP = {
    "ativo_total": r"^Ativo Total",
    "ativos_financeiros": r"^Ativos Financeiros$",
    "carteira_credito": r"^Opera[çc][õo]es de Cr[ée]dito|^Empr[ée]stimos e Adiantamentos a Clientes",
    "provisao_credito": r"Provis[ãa]o para Perda",
    "pl_consolidado": r"^Patrim[ôo]nio L[íi]quido Consolidado",
    "nao_controladores": r"N[ãa]o Controladores",
}


# ---------- utilidades CVM ----------
def _nivel(c: str) -> int:
    return c.count(".") + 1


def achar(df: pd.DataFrame, regex: str, raiz: str = "", max_nivel: int = 4) -> list[str]:
    """Contas cuja descrição casa com a regex (no documento mais recente), sem contar subcontas de uma conta já achada."""
    if df.empty:
        return []
    d = df[df.DT_REFER == df.DT_REFER.max()]
    d = d[d.CD_CONTA.str.startswith(raiz) & (d.CD_CONTA.map(_nivel) <= max_nivel)]
    d = d[d.DS_CONTA.str.contains(regex, case=False, regex=True, na=False)]
    if d.empty:
        return []
    if "VL" in d:
        d = d[d.groupby("CD_CONTA")["VL"].transform(lambda s: (s.abs() > 0).any())]
    contas = sorted(d.CD_CONTA.unique(), key=lambda c: [int(x) for x in c.split(".")])
    out = []
    for c in contas:
        if not any(c.startswith(o + ".") for o in out):
            out.append(c)
    return out


def combinar(rastros: list[tuple[str, dict]], nota: str = "") -> dict:
    """Soma rastros com sinal (+/−), juntando os componentes."""
    if not rastros or any(r["valor"] is None for _, r in rastros):
        return f.rastro(None, [], "Faltam contas para a conta composta.")
    total = sum(r["valor"] if s == "+" else -r["valor"] for s, r in rastros)
    comps = [{**c, "sinal": "−" if s == "−" else c.get("sinal", "+")} for s, r in rastros for c in r["componentes"]]
    return f.rastro(total, comps, nota)


def acumulado(dre: pd.DataFrame, contas: list[str], ordem: str) -> dict:
    """Acumulado do ano no último documento (ordem 'ÚLT') ou mesmo período do ano anterior ('PEN')."""
    if not contas or dre.empty:
        return f.rastro(None, [], "")
    ref = dre.DT_REFER.max()
    fonte = "DFP" if (dre[dre.DT_REFER == ref].FONTE == "DFP").any() else "ITR"
    total, comps = 0.0, []
    for c in contas:
        r = f.linha_acumulada(dre, fonte, ref, ordem, c)
        if r is None:
            return f.rastro(None, [], f"Conta {c} sem o período {ordem}.")
        total += float(r.VL)
        comps.append(f.comp("+", "Acumulado no exercício", f.linha_cvm(r)))
    return f.rastro(total, comps, "")


def saldo(bp: pd.DataFrame, contas: list[str], ordem: str = "ÚLT") -> dict:
    """Saldo de balanço no último documento: ÚLT = data do documento; PEN = fim do exercício anterior."""
    if not contas or bp.empty:
        return f.rastro(None, [], "Conta não encontrada pela descrição.")
    ref = bp.DT_REFER.max()
    total, comps = 0.0, []
    for c in contas:
        d = bp[(bp.DT_REFER == ref) & bp.ORDEM_EXERC.str.startswith(ordem) & (bp.CD_CONTA == c)]
        if d.empty:
            return f.rastro(None, [], f"Conta {c} sem a coluna {ordem}.")
        r = d.iloc[0]
        total += float(r.VL)
        comps.append(f.comp("+", "Saldo", f.linha_cvm(r)))
    return f.rastro(total, comps, "")


def _codigos_doc(d: pd.DataFrame, regex: str, raiz: str, max_nivel: int, modo: str | None) -> list[str]:
    d = d[d.CD_CONTA.str.startswith(raiz) & (d.CD_CONTA.map(_nivel) <= max_nivel)]
    d = d[d.DS_CONTA.str.contains(regex, case=False, regex=True, na=False)]
    if d.empty:
        return []
    d = d[d.groupby("CD_CONTA")["VL"].transform(lambda x: (x.abs() > 0).any())]
    cods = sorted(d.CD_CONTA.unique(), key=lambda c: [int(x) for x in c.split(".")])
    out = []
    for c in cods:
        if not any(c.startswith(o + ".") for o in out):
            out.append(c)
    if modo == "ultimo_nivel2":
        out = [c for c in out if _nivel(c) == 2][-1:]
    return out


def normalizar(dre: pd.DataFrame, conceitos: dict) -> pd.DataFrame:
    """Reescreve a DRE por CONCEITO: em cada documento (DFP/ITR de cada data) acha as contas pela descrição
    e soma numa linha com CD_CONTA = nome do conceito. Necessário porque o código da mesma conta pode mudar
    entre documentos da mesma empresa (ex.: lucro dos controladores 3.11.01 no DFP e 3.09.01 no ITR)."""
    linhas = []
    for (_, _), d in dre.groupby(["FONTE", "DT_REFER"]):
        for chave, (rx, raiz, mx, modo) in conceitos.items():
            cods = _codigos_doc(d, rx, raiz, mx, modo)
            if not cods:
                continue
            sub = d[d.CD_CONTA.isin(cods)]
            for _, g in sub.groupby(["ORDEM_EXERC", "DT_INI_EXERC", "DT_FIM_EXERC"], dropna=False):
                r = g.iloc[0].copy()
                r["VL"] = float(g.VL.sum())
                r["VL_CONTA"] = float(pd.to_numeric(g.VL_CONTA, errors="coerce").sum())
                r["CD_CONTA"] = chave
                r["DS_CONTA"] = f"[{' + '.join(g.CD_CONTA)}] " + " + ".join(g.DS_CONTA.unique())
                linhas.append(r)
    return pd.DataFrame(linhas)


def _contas_reais(r: dict) -> dict:
    """Devolve, nos componentes, o código e a descrição originais da CVM."""
    for c in r.get("componentes", []):
        m = re.match(r"\[(.*?)\] (.*)", c.get("descricao") or "")
        if m:
            c["conta"], c["descricao"] = m.group(1), m.group(2)
    return r


def ttm_c(norm: pd.DataFrame, chave: str) -> dict:
    if norm.empty or chave not in set(norm.CD_CONTA):
        return f.rastro(None, [], "Conta não encontrada pela descrição.")
    r = f.ttm(norm, chave)
    if r["valor"] is None:
        r = {**r, "nota": "Faltam documentos (DFP do último ano ou ITR do mesmo período do ano anterior) para somar 12 meses."}
    return _contas_reais(r)


def acum_c(norm: pd.DataFrame, chave: str, ordem: str) -> dict:
    if norm.empty or chave not in set(norm.CD_CONTA):
        return f.rastro(None, [], "")
    return _contas_reais(acumulado(norm, [chave], ordem))


def eh_banco(dre: pd.DataFrame) -> bool:
    return bool(achar(dre, BANCO_DRE["receitas_intermediacao"], "3", 2))


# ---------- preço ----------
def preco(ticker: str) -> dict:
    """Último preço: yfinance; sem internet, o último COTAHIST da B3 em cache."""
    from indicadores_b3.data.fontes import historico_yf, url_yahoo
    try:
        s = historico_yf(f"{ticker}.SA", "1mo")
        if not s.empty:
            return f.rastro(float(s.iloc[-1]), [f.comp("+", "Fechamento", {
                "fonte": "yfinance", "documento": f"{ticker}.SA", "url": url_yahoo(f"{ticker}.SA"),
                "data_ref": s.index[-1].strftime("%Y-%m-%d"), "periodo": "último fechamento", "conta": "Close",
                "descricao": "Preço de fechamento (ajustado por proventos)", "valor": float(s.iloc[-1])})],
                "yfinance usa preço ajustado por proventos; pode diferir levemente do fechamento oficial.")
    except Exception:  # noqa: BLE001
        pass
    try:
        from indicadores_b3.data import opcoes
        arqs = sorted(Path(opcoes.CACHE).glob("cotahist_*.zip"))
        for arq in reversed(arqs):
            df = opcoes.ler(arq)
            r = df[(df.CODNEG == ticker) & (df.TPMERC == "010")]
            if not r.empty:
                r = r.iloc[0]
                d = f"{r.DATA[:4]}-{r.DATA[4:6]}-{r.DATA[6:]}"
                return f.rastro(float(r.PREULT), [f.comp("+", "Fechamento", {
                    "fonte": "B3", "documento": arq.name, "url": opcoes.url_dia(pd.Timestamp(d)), "data_ref": d,
                    "periodo": f"pregão de {d}", "conta": "PREULT", "descricao": "Preço do último negócio", "valor": float(r.PREULT)})],
                    "Sem resposta do yfinance; usado o arquivo COTAHIST da B3 em cache.")
    except Exception:  # noqa: BLE001
        pass
    return f.rastro(None, [], "Preço indisponível (yfinance e COTAHIST em cache).")


# ---------- agente ----------
def analisar(ticker: str) -> Dossie:
    t = ticker.strip().upper()
    cnpj = f.mapa_tickers().get(t)
    if not cnpj:
        raise LookupError(f"{t}: não encontrado no cadastro de companhias abertas da CVM (FCA).")
    dre = f.demonstrativo("DRE_con", cnpj)
    if dre.empty:
        raise LookupError(f"{t}: sem DRE consolidada na CVM.")
    nome = dre.DENOM_CIA.iloc[0]
    D = Dossie("Financial Analyst", "F", f"{nome} ({t})")
    D.extras.update({"ticker": t, "empresa": nome, "cnpj": cnpj, "ref": dre.DT_REFER.max()})
    try:
        from indicadores_b3.data import setores
        st = setores.setor_de(t)
        D.extras["setor"] = {k: st.get(k) for k in ("setor", "macro", "holding", "setor_cvm", "atividade")}
        if st.get("setor"):
            D.leitura(f"Setor: {st['setor']} (macrossetor {st['macro']}), segundo o cadastro da companhia na CVM (FCA).", [], "fato")
    except Exception:  # noqa: BLE001 — classificação é complementar
        pass
    if eh_banco(dre):
        D.extras["tipo"] = "banco"
        _banco(D, t, cnpj, dre)
    else:
        D.extras["tipo"] = "geral"
        _geral(D, t)
    return D


def _banco(D: Dossie, t: str, cnpj: str, dre: pd.DataFrame):
    bpa, bpp = f.demonstrativo("BPA_con", cnpj), f.demonstrativo("BPP_con", cnpj)
    cap = f.demonstrativo("composicao_capital", cnpj)
    c = {k: achar(dre, r, "3", 4) for k, r in BANCO_DRE.items()}
    c["receita_juros"] = achar(dre, BANCO_DRE["receita_juros"], "3.01", 3)
    c["despesa_juros"] = achar(dre, BANCO_DRE["despesa_juros"], "3.02", 3)
    c["lucro_total"] = [x for x in achar(dre, BANCO_DRE["lucro_total"], "3", 2) if _nivel(x) == 2][-1:]
    b = {"ativo_total": ["1"] if not bpa.empty else [],
         "ativos_financeiros": achar(bpa, BANCO_BP["ativos_financeiros"], "1", 2),
         "carteira_credito": achar(bpa, BANCO_BP["carteira_credito"], "1.02", 4)[:1],
         "provisao_credito": achar(bpa, BANCO_BP["provisao_credito"], "1.02", 4)}
    pl = achar(bpp, BANCO_BP["pl_consolidado"], "2", 2)
    b["pl_consolidado"] = pl
    b["nao_controladores"] = achar(bpp, BANCO_BP["nao_controladores"], pl[0] if pl else "2.x", 3)
    D.extras["contas"] = {**c, **b}
    D.alerta("info", "Plano de contas de instituição financeira: o DCF de fluxo de caixa livre não se aplica; "
                     "use ROE, custo do capital próprio e P/VP.")

    # conceitos procurados pela descrição em CADA documento (o código muda entre documentos)
    R = BANCO_DRE
    norm = normalizar(dre, {
        "lucro_controladores": (R["lucro_controladores"], "3", 4, None),
        "lucro_total": (R["lucro_total"], "3", 2, "ultimo_nivel2"),
        "resultado_bruto": (R["resultado_bruto"], "3", 2, None),
        "perdas_credito": (R["perdas_credito"], "3", 4, None),
        "perdas_na_intermediacao": (R["perdas_credito"], "3.02", 4, None),
        "servicos": (R["servicos"], "3", 4, None),
        "servicos_seguros_na_intermediacao": (f"(?:{R['servicos']})|(?:{R['seguros']})", "3.01", 4, None),
        "despesas_operacionais": (f"(?:{R['pessoal']})|(?:{R['administrativas']})", "3", 4, None),
    })
    tem = set(norm.CD_CONTA) if not norm.empty else set()
    # margem financeira = resultado bruto da intermediação, sem as perdas com crédito, serviços e seguros
    # que alguns bancos (ex.: Itaú) registram dentro da intermediação
    mf = [("+", "resultado_bruto")] + [("−", k) for k in ("perdas_na_intermediacao", "servicos_seguros_na_intermediacao") if k in tem]
    D.extras["formula_margem"] = "Resultado bruto da intermediação" + "".join(
        {"perdas_na_intermediacao": " − perdas com crédito registradas na intermediação",
         "servicos_seguros_na_intermediacao": " − serviços e seguros registrados na intermediação"}[k] for sn, k in mf if sn == "−")

    S = "Resultado (12 meses)"
    lucro = D.fato_rastro("Lucro líquido dos controladores (12m)", ttm_c(norm, "lucro_controladores"), "R$", S)
    lucro_t = D.fato_rastro("Lucro líquido consolidado (12m)", ttm_c(norm, "lucro_total"), "R$", S)
    nii = D.fato_rastro("Margem financeira (12m)", combinar([(sn, ttm_c(norm, k)) for sn, k in mf],
                        "Resultado bruto da intermediação financeira sem perdas com crédito, serviços e seguros."), "R$", S)
    pc = D.fato_rastro("Perda esperada com crédito (12m)", ttm_c(norm, "perdas_credito"), "R$", S)
    sv = D.fato_rastro("Receitas de prestação de serviços (12m)", ttm_c(norm, "servicos"), "R$", S)
    desp = D.fato_rastro("Despesas de pessoal e administrativas (12m)", ttm_c(norm, "despesas_operacionais"), "R$", S)

    S = "Balanço"
    at = D.fato_rastro("Ativo total", saldo(bpa, b["ativo_total"]), "R$", S)
    at0 = D.fato_rastro("Ativo total (fim do ano anterior)", saldo(bpa, b["ativo_total"], "PEN"), "R$", S)
    af = D.fato_rastro("Ativos financeiros", saldo(bpa, b["ativos_financeiros"]), "R$", S)
    cart = D.fato_rastro("Carteira de crédito (bruta)", saldo(bpa, b["carteira_credito"]), "R$", S)
    cart0 = D.fato_rastro("Carteira de crédito (fim do ano anterior)", saldo(bpa, b["carteira_credito"], "PEN"), "R$", S)
    prov = D.fato_rastro("Provisão para perdas no balanço", saldo(bpa, b["provisao_credito"]), "R$", S)
    plc = D.fato_rastro("Patrimônio líquido consolidado", saldo(bpp, b["pl_consolidado"]), "R$", S)
    plc0 = D.fato_rastro("Patrimônio líquido consolidado (fim do ano anterior)", saldo(bpp, b["pl_consolidado"], "PEN"), "R$", S)
    nc = D.fato_rastro("Participação de não controladores", saldo(bpp, b["nao_controladores"]), "R$", S) if b["nao_controladores"] else None
    nc0 = D.fato_rastro("Não controladores (fim do ano anterior)", saldo(bpp, b["nao_controladores"], "PEN"), "R$", S) if b["nao_controladores"] else None
    v = D.v
    pl = D.calc("PL dos controladores", (v(plc) or 0) - (v(nc) or 0) if plc else None, "R$",
                "PL consolidado − não controladores", [plc] + ([nc] if nc else []), S)
    pl0 = D.calc("PL dos controladores (fim do ano anterior)", (v(plc0) or 0) - (v(nc0) or 0) if plc0 else None, "R$",
                 "PL consolidado − não controladores", [plc0] + ([nc0] if nc0 else []), S)

    S = "Rentabilidade e eficiência"
    pl_med = div((v(pl) or 0) + (v(pl0) or 0), 2) if pl and pl0 else None
    D.calc("ROE", vezes(div(v(lucro), pl_med), 100) if pl_med else None, "%",
           "Lucro dos controladores (12m) ÷ média do PL dos controladores (atual e fim do ano anterior) × 100", [lucro, pl, pl0], S)
    at_med = div((v(at) or 0) + (v(at0) or 0), 2) if at and at0 else None
    D.calc("ROA", vezes(div(v(lucro_t), at_med), 100) if at_med else None, "%",
           "Lucro consolidado (12m) ÷ média do ativo total × 100", [lucro_t, at, at0], S)
    D.calc("Margem financeira ÷ ativos financeiros", vezes(div(v(nii), v(af)), 100) if nii and af else None, "%",
           "Margem financeira (12m) ÷ ativos financeiros × 100", [nii, af], S,
           "Aproximação da NIM: os bancos divulgam a NIM sobre ativos rentáveis médios, com ajustes gerenciais, e o número oficial é diferente.")
    D.calc("Índice de eficiência aproximado", div(abs(v(desp) or 0), (v(nii) or 0) + (v(sv) or 0)) * 100 if desp and nii and sv else None,
           "%", "|Despesas de pessoal e administrativas| ÷ (margem financeira + serviços) × 100", [desp, nii, sv], S,
           "NÃO COMPARÁVEL ENTRE BANCOS: cada banco agrupa receitas de forma diferente nas demonstrações da CVM. "
           "Use o índice de eficiência divulgado no relatório de RI para comparar.")
    D.calc("Alavancagem (ativo ÷ PL)", div(v(at), v(plc)), "x", "Ativo total ÷ PL consolidado", [at, plc], S)

    S = "Qualidade do crédito"
    cart_med = div((v(cart) or 0) + (v(cart0) or 0), 2) if cart and cart0 else None
    D.calc("Custo do crédito", div(abs(v(pc) or 0), cart_med) * 100 if pc and cart_med else None, "%",
           "|Perda esperada com crédito (12m)| ÷ média da carteira de crédito × 100", [pc, cart, cart0], S)
    D.calc("Provisão ÷ carteira", div(abs(v(prov) or 0), v(cart)) * 100 if prov and cart else None, "%",
           "|Provisão para perdas no balanço| ÷ carteira de crédito × 100", [prov, cart], S)
    D.calc("Crescimento da carteira no ano", (div(v(cart), v(cart0)) - 1) * 100 if cart and cart0 and v(cart0) else None, "%",
           "Carteira atual ÷ carteira no fim do ano anterior − 1", [cart, cart0], S)
    for nome_, fonte_ in [("Inadimplência acima de 90 dias", "IF.data do Banco Central ou relatório de RI"),
                          ("Índice de Basileia / capital principal (CET1)", "IF.data do Banco Central ou relatório de RI"),
                          ("Lucro recorrente gerencial", "relatório de resultados (RI) do banco")]:
        D.ausente(nome_, "Não consta nas demonstrações padronizadas da CVM.", fonte_)
    D.alerta("aviso", "Desde 2025 a Resolução CMN 4.966 mudou a forma de provisionar perdas com crédito (perda esperada): "
                      "comparações de custo do crédito e provisões com anos anteriores a 2025 não são diretas.")

    _evolucao(D, norm, {"Lucro dos controladores": [("+", "lucro_controladores")], "Margem financeira": mf,
                        "Perda esperada com crédito": [("+", "perdas_credito")], "Serviços": [("+", "servicos")],
                        "Despesas de pessoal e administrativas": [("+", "despesas_operacionais")]})
    _mercado(D, t, cap, lucro, pl)
    _alertas_banco(D)


def _evolucao(D: Dossie, norm, mapa: dict):
    """Acumulado do ano × mesmo período do ano anterior (o ITR traz as duas colunas)."""
    S = "Evolução (acumulado no ano × ano anterior)"
    tem = set(norm.CD_CONTA) if not norm.empty else set()
    for nome, partes in mapa.items():
        partes = [(sn, k) for sn, k in partes if k in tem]
        if not partes:
            continue
        a = D.fato_rastro(f"{nome} — acumulado no ano", combinar([(sn, acum_c(norm, k, "ÚLT")) for sn, k in partes]), "R$", S)
        p = D.fato_rastro(f"{nome} — mesmo período do ano anterior", combinar([(sn, acum_c(norm, k, "PEN")) for sn, k in partes]), "R$", S)
        if a and p and D.v(p) and (D.v(a) > 0) == (D.v(p) > 0):
            D.calc(f"{nome}: variação", (D.v(a) / D.v(p) - 1) * 100, "%", "acumulado atual ÷ mesmo período do ano anterior − 1", [a, p], S)


def _mercado(D: Dossie, t, cap, lucro, pl):
    S = "Mercado"
    px = D.fato_rastro("Preço", preco(t), "R$", S)
    ra = f.rastro_acoes(cap)
    k = ACOES_POR_UNIT.get(t, 1)
    # o arquivo de composição do capital não traz a escala; algumas empresas informam em milhares.
    # Se preço × ações der menos de 5% do PL, a quantidade só pode estar em milhares.
    if ra["valor"] and D.v(px) and D.v(pl) and D.v(px) * ra["valor"] / k < 0.05 * D.v(pl):
        ra = {**ra, "valor": ra["valor"] * 1000,
              "nota": "Quantidade informada em milhares no arquivo de composição do capital da CVM: multiplicada por 1.000. " + ra["nota"]}
        D.alerta("aviso", "A CVM informa as ações desta empresa em milhares (o arquivo não traz a escala); a quantidade foi multiplicada por 1.000.")
    n = D.fato_rastro("Ações em circulação", ra, "ações", S)
    if k > 1:
        D.premissa("Ações por unit", k, "ações", f"{t} é uma unit: cada unit representa {k} ações (conferir no RI).", S)
    vpa = D.calc("VPA (valor patrimonial por ação)", vezes(div(D.v(pl), D.v(n)), k) if pl and n else None, "R$",
                 "PL dos controladores ÷ ações" + (f" × {k} (unit)" if k > 1 else ""), [pl, n], S)
    lpa = D.calc("LPA (lucro por ação, 12m)", vezes(div(D.v(lucro), D.v(n)), k) if lucro and n else None, "R$",
                 "Lucro dos controladores (12m) ÷ ações" + (f" × {k} (unit)" if k > 1 else ""), [lucro, n], S)
    D.calc("P/VP", div(D.v(px), D.v(vpa)), "x", "Preço ÷ VPA", [px, vpa], S)
    D.calc("P/L", div(D.v(px), D.v(lpa)), "x", "Preço ÷ LPA", [px, lpa], S)
    D.calc("Valor de mercado", D.v(px) * D.v(n) / k if px and n else None, "R$", "Preço × ações" + (f" ÷ {k}" if k > 1 else ""), [px, n], S,
           "Supõe o mesmo preço para todas as classes de ações (ON e PN); é uma aproximação.")


def _por_nome(D: Dossie, nome):
    return next((x for x in D.itens if x["nome"] == nome), None)


def _alertas_banco(D: Dossie):
    roe = _por_nome(D, "ROE")
    var_l = _por_nome(D, "Lucro dos controladores: variação")
    var_p = _por_nome(D, "Perda esperada com crédito: variação")
    var_m = _por_nome(D, "Margem financeira: variação")
    if var_l:
        D.leitura(f"O lucro dos controladores {'cresceu' if var_l['valor'] >= 0 else 'caiu'} {abs(var_l['valor']):.1f}% "
                  "no acumulado do ano contra o mesmo período do ano anterior.", [var_l["id"]])
    if var_m:
        D.leitura(f"A margem financeira {'cresceu' if var_m['valor'] >= 0 else 'caiu'} {abs(var_m['valor']):.1f}% no mesmo critério.", [var_m["id"]])
    if var_p and var_m and var_p["valor"] > var_m["valor"] + 5:
        D.alerta("aviso", f"As perdas com crédito cresceram {var_p['valor']:.1f}%, acima da margem financeira "
                          f"({var_m['valor']:.1f}%): a qualidade do crédito está pesando mais no resultado.", [var_p["id"], var_m["id"]])
    if roe and roe["valor"] < 10:
        D.alerta("aviso", f"ROE de {roe['valor']:.1f}%: abaixo do custo de capital típico de bancos brasileiros.", [roe["id"]])


def _geral(D: Dossie, t: str):
    """Empresas não financeiras: reaproveita o catálogo de indicadores do site (já rastreado)."""
    from indicadores_b3.analytics import indicadores
    r = indicadores.calcular(t)
    cat = {i.id: i for i in indicadores.TIPOS[r["tipo"]]["catalogo"]}
    base = r.get("rastreio", {})
    ids = {}
    for k, rs in base.items():
        nome, _, un = indicadores.TIPOS[r["tipo"]]["base"].get(k, (k, "", "R$"))
        ids[k] = D.fato_rastro(nome, rs, un, "Dados de base")
    for res in r["indicadores"]:
        ind = cat[res["id"]]
        D.calc(f"{ind.sigla} — {ind.nome}", res["valor"], ind.unidade, ind.formula,
               [ids.get(e) or next((x["id"] for x in D.itens if x["nome"].startswith(cat[e].sigla + " ")), None) if e in cat else ids.get(e)
                for e in ind.entradas], ind.categoria)
    D.alerta("info", "Empresa não financeira: o valuation pode usar DCF (aba Balanços → DCF) e múltiplos.")


# ---------- base para a aba Indicadores (mesmo formato de fundamentos.dados_base) ----------
NAO_SE_APLICA = ("Não se aplica a bancos: o dinheiro é a matéria-prima do banco, então dívida, caixa, EBIT e "
                 "EBITDA não têm o mesmo significado que numa empresa comum. Use ROE, P/VP e P/L.")


def dados_banco(t: str, cnpj: str, dre: pd.DataFrame, preco_r: dict, proventos: dict) -> dict:
    """Entradas da aba Indicadores para bancos, com as contas achadas pela descrição (o código muda entre bancos)."""
    bpp, cap = f.demonstrativo("BPP_con", cnpj), f.demonstrativo("composicao_capital", cnpj)
    R = BANCO_DRE
    norm = normalizar(dre, {
        "lucro_controladores": (R["lucro_controladores"], "3", 4, None),
        "lucro_total": (R["lucro_total"], "3", 2, "ultimo_nivel2"),
        "receitas_intermediacao": (R["receitas_intermediacao"], "3", 2, None),
    })
    lucro_t = ttm_c(norm, "lucro_total")
    lucro_c = ttm_c(norm, "lucro_controladores")
    if lucro_c["valor"] is None:
        lucro_c = {**lucro_t, "nota": "O banco não separa o lucro dos controladores; usado o lucro consolidado. " + lucro_t["nota"]}
    receita = ttm_c(norm, "receitas_intermediacao")
    receita = {**receita, "nota": "Em bancos, a 'receita' é a receita da intermediação financeira (juros, títulos, câmbio…). "
               "Ela é bruta: o custo de captação fica em outra linha. " + receita.get("nota", "")}
    pl = achar(bpp, BANCO_BP["pl_consolidado"], "2", 2)
    nc = achar(bpp, BANCO_BP["nao_controladores"], pl[0] if pl else "2.x", 3)
    partes = [("+", _rotular(saldo(bpp, pl), "Patrimônio líquido consolidado"))]
    if nc:
        partes.append(("−", _rotular(saldo(bpp, nc), "Parte dos sócios minoritários das controladas")))
    pl_c = combinar(partes, "PL consolidado menos a parte dos sócios minoritários. No plano de contas de bancos o PL "
                            f"fica na conta {pl[0] if pl else '?'} (não na 2.03 das demais empresas).")
    avisos = ["Banco: indicadores de dívida, caixa, EBIT e EBITDA não se aplicam. Para a análise completa "
              "(ROE, custo do crédito, P/VP justificado), use a aba Research."]

    acoes = f.rastro_acoes(cap)
    k = ACOES_POR_UNIT.get(t, 1)
    acoes, aviso = f.acoes_na_escala(acoes, {"valor": (preco_r.get("valor") or 0) / k or None}, pl_c)
    if aviso:
        avisos.append(aviso)
    if k > 1 and acoes["valor"]:
        acoes = {**acoes, "valor": acoes["valor"] / k,
                 "nota": f"{t} é uma unit (pacote de {k} ações): a quantidade foi dividida por {k} para os valores ficarem por unit. " + acoes["nota"]}
    na = f.rastro(None, [], NAO_SE_APLICA)
    rastreio = {"preco": preco_r, "proventos_12m": proventos, "receita": receita, "ebit": na, "depreciacao": na,
                "lucro_total": lucro_t, "lucro_contr": lucro_c, "pl_contr": pl_c, "divida_bruta": na, "caixa": na, "acoes": acoes}
    return {"ticker": t, "empresa": dre.DENOM_CIA.iloc[0], "balanco_ref": dre.DT_REFER.max(), "banco": True,
            "valores": {k_: r["valor"] for k_, r in rastreio.items()}, "rastreio": rastreio, "avisos": avisos}


def _rotular(r: dict, papel: str) -> dict:
    for c in r.get("componentes", []):
        c["papel"] = papel
    return r
