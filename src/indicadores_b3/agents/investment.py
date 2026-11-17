"""Agente 3 — Investment Research Analyst: consolida os outros dois, compara pares, faz valuation e monta a tese.

Recebe:
  - o dossiê do Financial Analyst da empresa e dos pares;
  - o dossiê do Market Research Analyst.
Escolhe a metodologia pelo tipo de empresa:
  - banco: P/VP justificado (Gordon) = (ROE − g) ÷ (Ke − g), com Ke pelo CAPM, e o "ROE implícito no preço";
           o DCF de fluxo de caixa livre não se aplica a bancos.
  - demais: múltiplos contra os pares; o DCF fica na aba Balanços → DCF.
Cenários (pessimista, base, otimista) com premissas explícitas e pesos declarados.
Confronta as informações (divergências) e separa a tese em FATOS, ESTIMATIVAS e OPINIÕES.
Nada aqui é recomendação de investimento.
"""
from __future__ import annotations

import statistics

from indicadores_b3.agents.fatos import Dossie, decimal_br

COMPARAR_BANCO = ["ROE", "ROA", "P/VP", "P/L", "Custo do crédito", "Alavancagem (ativo ÷ PL)",
                  "Lucro dos controladores: variação", "Crescimento da carteira no ano"]
COMPARAR_GERAL_PREFIXOS = ["P/L", "P/VP", "EV/EBITDA", "ROE", "Margem líq.", "Dív.Líq/EBITDA", "DY"]

ERP_PADRAO = 5.0
BETA_BANCO = 1.0
CRESC_REAL = 1.0  # % a.a. de crescimento real na perpetuidade
PESOS = {"pessimista": 0.25, "base": 0.5, "otimista": 0.25}


def _item(d: dict, nome: str):
    return next((x for x in d["itens"] if x["nome"] == nome or x["nome"].startswith(nome + " ")), None)


def _v(d: dict, nome: str):
    x = _item(d, nome)
    return None if x is None else x["valor"]


def analisar(fin: dict, pares: dict[str, dict], mkt: dict | None, premissas: dict | None = None) -> Dossie:
    """fin, pares[...] e mkt são dossiês (to_dict()). premissas: {erp, beta, cresc_real, roe_base, ...} opcionais."""
    p = premissas or {}
    t, tipo = fin["extras"]["ticker"], fin["extras"].get("tipo", "geral")
    D = Dossie("Investment Research Analyst", "I", fin["assunto"])
    D.extras.update({"ticker": t, "tipo": tipo, "pares": list(pares)})

    # ---------- 1. comparação com pares ----------
    metricas = COMPARAR_BANCO if tipo == "banco" else [x["nome"] for x in fin["itens"] if any(x["nome"].startswith(pfx) for pfx in COMPARAR_GERAL_PREFIXOS)]
    tabela = []
    for m in metricas:
        linha = {"metrica": m, "valores": {}, "unidade": (_item(fin, m) or {}).get("unidade", "")}
        for tk, d in {t: fin, **pares}.items():
            linha["valores"][tk] = _v(d, m)
        vals = [v for k, v in linha["valores"].items() if v is not None and k != t]
        linha["mediana_pares"] = statistics.median(vals) if vals else None
        tabela.append(linha)
    D.extras["comparacao"] = tabela
    S = "Comparação com pares"
    for linha in tabela:
        vt, med = linha["valores"].get(t), linha["mediana_pares"]
        if vt is not None and med is not None:
            D.fato(f"{linha['metrica']} — {t}", vt, linha["unidade"], {"fonte": "Financial Analyst", "documento": "dossiê da empresa",
                   "descricao": linha["metrica"], "data_ref": fin["extras"].get("ref")}, S)
            D.calc(f"{linha['metrica']} — mediana dos pares", med, linha["unidade"],
                   "mediana de " + ", ".join(k for k in linha["valores"] if k != t and linha["valores"][k] is not None), [], S)
    if len(pares) == 0:
        D.ausente("Comparação com pares", "Nenhum par informado.", "informe tickers de empresas do mesmo setor")

    # ---------- 2. valuation ----------
    if tipo == "banco":
        _valuation_banco(D, fin, pares, mkt, p)
    else:
        D.alerta("info", "Empresa não financeira: valuation por múltiplos frente aos pares; para o DCF use a aba Balanços → DCF.")
        _valuation_multiplos(D, fin, pares)

    # ---------- 3. confronto entre as análises ----------
    _divergencias(D, fin, mkt, tipo)
    _tese(D, fin, mkt, tipo)
    return D


def _mkt(mkt, nome):
    if not mkt:
        return None
    return next((x for x in mkt["itens"] if x["nome"].startswith(nome)), None)


def _valuation_banco(D: Dossie, fin, pares, mkt, p):
    S = "Custo do capital próprio (Ke)"
    rf_m = _mkt(mkt, "Juro prefixado em 5 anos")
    inf_m = _mkt(mkt, "Inflação implícita em 5 anos")
    if rf_m:
        rf = D.fato("Taxa livre de risco (juro prefixado 5 anos)", rf_m["valor"], "% a.a.", rf_m["fonte"], S,
                    "Do Market Research Analyst (curva do Tesouro).")
    else:
        rf = D.premissa("Taxa livre de risco", p.get("rf", 14.0), "% a.a.", "Curva do Tesouro indisponível; valor informado como premissa.", S)
    beta = D.premissa("Beta do banco", p.get("beta", BETA_BANCO), "", "Grandes bancos brasileiros costumam ter beta próximo de 1 contra o Ibovespa.", S)
    erp = D.premissa("Prêmio de risco de ações", p.get("erp", ERP_PADRAO), "% a.a.", "Faixa usual de casas de análise no Brasil: 4% a 6%.", S)
    ke = D.estimativa("Ke (CAPM)", D.v(rf) + D.v(beta) * D.v(erp), "% a.a.", "rf + β × prêmio de risco", [rf, beta, erp], S)
    if inf_m:
        inf = D.fato("Inflação implícita de longo prazo", inf_m["valor"], "% a.a.", inf_m["fonte"], S)
    else:
        inf = D.premissa("Inflação de longo prazo", p.get("inflacao", 4.0), "% a.a.", "Curva indisponível; premissa.", S)
    cr = D.premissa("Crescimento real na perpetuidade", p.get("cresc_real", CRESC_REAL), "% a.a.", "Crescimento real de longo prazo do lucro dos bancos, próximo do PIB potencial.", S)
    g = D.estimativa("g (crescimento nominal na perpetuidade)", ((1 + D.v(inf) / 100) * (1 + D.v(cr) / 100) - 1) * 100, "% a.a.",
                     "(1 + inflação) × (1 + crescimento real) − 1", [inf, cr], S)

    S = "Valuation: P/VP justificado"
    roe_i = _item(fin, "ROE")
    vpa_i, px_i, pvp_i = _item(fin, "VPA (valor patrimonial por ação)"), _item(fin, "Preço"), _item(fin, "P/VP")
    if not (roe_i and vpa_i and px_i):
        D.ausente("Valuation por P/VP justificado", "Faltam ROE, VPA ou preço no dossiê financeiro.")
        return
    roe = D.fato("ROE atual (12 meses)", roe_i["valor"], "%", {"fonte": "Financial Analyst", "documento": "dossiê", "descricao": roe_i["formula"],
                 "data_ref": fin["extras"].get("ref")}, S)
    vpa = D.fato("VPA", vpa_i["valor"], "R$", {"fonte": "Financial Analyst", "documento": "dossiê", "descricao": vpa_i["formula"],
                 "data_ref": fin["extras"].get("ref")}, S)
    px = D.fato("Preço atual", px_i["valor"], "R$", {"fonte": (px_i.get("fonte") or {}).get("fonte", "mercado"), "documento": "preço",
                "data_ref": (px_i.get("fonte") or {}).get("data_ref"), "url": (px_i.get("fonte") or {}).get("url")}, S)
    kev, gv = D.v(ke), D.v(g)
    if kev <= gv:
        D.alerta("erro", "Ke menor ou igual a g: a fórmula de Gordon não se aplica com essas premissas.", [ke, g])
        return
    # ROE que o preço de hoje "embute": P/VP = (ROE − g) ÷ (Ke − g)  →  ROE = g + P/VP × (Ke − g)
    if pvp_i:
        pvp = D.fato("P/VP atual", pvp_i["valor"], "x", {"fonte": "Financial Analyst", "documento": "dossiê", "descricao": "Preço ÷ VPA"}, S)
        P = D.v(pvp)
        if P >= 1:  # P/VP ≥ 1: o mercado vê ROE ≥ Ke, e aí crescer cria valor (usa g)
            D.estimativa("ROE sustentável implícito no preço", gv + P * (kev - gv), "%", "g + P/VP × (Ke − g)", [g, pvp, ke], S,
                         "O ROE de longo prazo que o mercado precisa acreditar para o preço de hoje ser justo, dadas Ke e g.")
        else:       # P/VP < 1: o mercado vê ROE < Ke; sem crescimento, P/VP = ROE ÷ Ke
            D.estimativa("ROE sustentável implícito no preço", P * kev, "%", "P/VP × Ke (sem crescimento, pois P/VP < 1)", [pvp, ke], S,
                         "O ROE de longo prazo que o mercado precisa acreditar para o preço de hoje ser justo. Com P/VP abaixo de 1, "
                         "o mercado vê ROE abaixo do Ke, e crescer destruiria valor: a conta usa crescimento zero.")
        if D.v(roe) > 0:
            if P >= 1:
                D.estimativa("Ke implícito no preço", gv + (D.v(roe) - gv) / P, "% a.a.", "g + (ROE − g) ÷ P/VP", [g, roe, pvp], S,
                             "O custo de capital que o mercado aplica se acreditar que o ROE atual se mantém. Compare com o Ke do CAPM.")
            else:
                D.estimativa("Ke implícito no preço", D.v(roe) / P, "% a.a.", "ROE ÷ P/VP (sem crescimento, pois P/VP < 1)", [roe, pvp], S,
                             "O custo de capital que o mercado aplica se acreditar que o ROE atual se mantém, sem crescimento. "
                             "Compare com o Ke do CAPM.")

    S = "Cenários"
    roe_base = p.get("roe_base", D.v(roe))
    cen = {"pessimista": (roe_base - p.get("delta_roe_pess", 4.0), kev + 1.0),
           "base": (roe_base, kev),
           "otimista": (roe_base + p.get("delta_roe_otim", 2.0), kev - 1.0)}
    pesos = p.get("pesos", PESOS)
    peso_ids = {k: D.premissa(f"Peso do cenário {k}", pesos[k] * 100, "%", "Escolha subjetiva, declarada: o cenário base pesa o dobro dos extremos.", S)
                for k in ("pessimista", "base", "otimista")}
    resultados, sem_cresc = {}, []
    for nome, (roe_c, ke_c) in cen.items():
        r_id = D.premissa(f"ROE sustentável — {nome}", roe_c, "%",
                          {"pessimista": "ROE atual − 4 p.p.: piora do crédito/concorrência.", "base": "ROE dos últimos 12 meses mantido.",
                           "otimista": "ROE atual + 2 p.p.: ganhos de eficiência/crescimento."}[nome], S)
        k_id = D.premissa(f"Ke — {nome}", ke_c, "% a.a.", {"pessimista": "Ke base + 1 p.p.", "base": "Ke pelo CAPM", "otimista": "Ke base − 1 p.p."}[nome], S)
        pv = _pvp_justo(roe_c, ke_c, gv)
        if pv is None:
            if roe_c <= 0:
                D.ausente(f"Preço justo — {nome}", f"ROE do cenário {nome} igual ou abaixo de zero: o P/VP justificado não se aplica a banco com prejuízo.",
                          "Avalie pelo VPA ajustado ou por múltiplos dos pares.")
            continue
        if pv[1] == gv:
            pvj = D.estimativa(f"P/VP justo — {nome}", pv[0], "x", "(ROE − g) ÷ (Ke − g)", [r_id, g, k_id], S)
        else:
            sem_cresc.append(nome)
            pvj = D.estimativa(f"P/VP justo — {nome}", pv[0], "x", "ROE ÷ Ke (sem crescimento, pois ROE < Ke)", [r_id, k_id], S,
                               "Com ROE abaixo do Ke, cada real reinvestido vale menos que um real: o banco não deve crescer, e o lucro "
                               "inteiro vira dividendo. Usar g aqui daria P/VP menor (ou negativo, se ROE < g).")
        pj = D.estimativa(f"Preço justo — {nome}", D.v(pvj) * D.v(vpa), "R$", "P/VP justo × VPA", [pvj, vpa], S)
        D.estimativa(f"Potencial — {nome}", (D.v(pj) / D.v(px) - 1) * 100, "%", "preço justo ÷ preço atual − 1", [pj, px], S)
        resultados[nome] = D.v(pj)
    if sem_cresc:
        D.alerta("aviso", f"ROE abaixo do Ke nos cenários {', '.join(sem_cresc)}: nesses cenários o P/VP justo usa crescimento zero (ROE ÷ Ke), "
                 "porque crescer com ROE menor que o custo de capital destrói valor.", [roe, ke])
    if len(resultados) == 3:
        pond = sum(pesos[k] * v for k, v in resultados.items())
        ids = [x["id"] for x in D.itens if x["nome"].startswith("Preço justo —")] + list(peso_ids.values())
        pp = D.estimativa("Preço justo ponderado pelos cenários", pond, "R$", f"{pesos['pessimista']:.0%} pessimista + {pesos['base']:.0%} base + {pesos['otimista']:.0%} otimista", ids, S)
        D.estimativa("Potencial ponderado", (pond / D.v(px) - 1) * 100, "%", "preço justo ponderado ÷ preço atual − 1", [pp, px], S)
    D.extras["sensibilidade"] = _sensibilidade(D.v(roe), kev, gv, D.v(vpa))

    # cruzamento com os pares: P/VP mediano dos pares aplicado ao VPA
    pvps = [_v(d, "P/VP") for d in pares.values() if _v(d, "P/VP")]
    if pvps:
        med = statistics.median(pvps)
        m_id = D.calc("P/VP mediano dos pares", med, "x", "mediana do P/VP de " + ", ".join(pares), [], "Valuation por múltiplos")
        D.estimativa("Preço pelo P/VP dos pares", med * D.v(vpa), "R$", "P/VP mediano dos pares × VPA", [m_id, vpa], "Valuation por múltiplos",
                     "Ignora diferenças de rentabilidade: um banco com ROE maior merece P/VP maior.")


def _pvp_justo(roe: float, ke: float, g: float) -> tuple[float, float] | None:
    """P/VP justificado com o crescimento que maximiza o valor dentro de [0, g]; devolve (P/VP, g usado) ou None.

    P/VP = (ROE − g) ÷ (Ke − g) cresce com g quando ROE > Ke e cai quando ROE < Ke. Então:
      ROE ≥ Ke → usa g (crescer cria valor);  ROE < Ke → g = 0 e P/VP = ROE ÷ Ke (crescer destrói valor).
    A regra é contínua em ROE = Ke (as duas dão 1) e nunca dá P/VP negativo com ROE positivo (antes, ROE < g dava).
    ROE ≤ 0 (prejuízo) ou Ke ≤ g → None: a fórmula não se aplica.
    """
    g_usado = g if roe >= ke else 0.0
    if roe <= 0 or ke <= g_usado:
        return None
    return (roe - g_usado) / (ke - g_usado), g_usado


def _sensibilidade(roe, ke, g, vpa):
    kes = [round(ke + d, 1) for d in (-2, -1, 0, 1, 2)]
    roes = [round(roe + d, 1) for d in (-4, -2, 0, 2, 4)]
    def preco(r, k):
        pv = _pvp_justo(r, k, g)
        return None if pv is None else round(pv[0] * vpa, 2)
    return {"ke": kes, "roe": roes, "g": g, "precos": [[preco(r, k) for r in roes] for k in kes]}


def _valuation_multiplos(D: Dossie, fin, pares):
    S = "Valuation por múltiplos"
    for m, base_nome in (("P/L", "LPA"), ("P/VP", "VPA")):
        meds = [_v(d, m) for d in pares.values() if _v(d, m) and _v(d, m) > 0]
        base = _item(fin, base_nome)
        if meds and base:
            med = statistics.median(meds)
            m_id = D.calc(f"{m} mediano dos pares", med, "x", f"mediana de {m} dos pares", [], S)
            b_id = D.fato(base_nome, base["valor"], "R$", {"fonte": "Financial Analyst", "documento": "dossiê"}, S)
            D.estimativa(f"Preço pelo {m} dos pares", med * base["valor"], "R$", f"{m} mediano dos pares × {base_nome}", [m_id, b_id], S)


def _divergencias(D: Dossie, fin, mkt, tipo):
    """Confronta números dos dois agentes e aponta inconsistências ou tensões."""
    ref = fin["extras"].get("ref")
    px = _item(fin, "Preço")
    if px and ref:
        D.leitura(f"Os números contábeis são de {ref} e o preço é de {(px.get('fonte') or {}).get('data_ref')}: "
                  "o valuation mistura balanço passado com preço atual, como é usual, mas eventos depois do balanço não estão nos números.",
                  [], "inferência")
    roe, ke = _item(fin, "ROE"), next((x for x in D.itens if x["nome"] == "Ke (CAPM)"), None)
    pvp = _item(fin, "P/VP")
    if roe and ke and pvp:
        spread = roe["valor"] - ke["valor"]
        if spread > 0 and pvp["valor"] < 1:
            D.alerta("divergencia", f"ROE ({roe['valor']:.1f}%) acima do Ke ({ke['valor']:.1f}%), mas P/VP abaixo de 1 ({pvp['valor']:.2f}): "
                     "o mercado duvida que esse ROE se sustente.", [ke["id"]])
        elif spread < 0 and pvp["valor"] > 1:
            D.alerta("divergencia", f"ROE ({roe['valor']:.1f}%) abaixo do Ke ({ke['valor']:.1f}%), mas P/VP acima de 1 ({pvp['valor']:.2f}): "
                     "o preço embute melhora relevante de rentabilidade.", [ke["id"]])
        else:
            D.leitura(f"ROE − Ke = {spread:+.1f} p.p., coerente com P/VP {'acima' if pvp['valor'] >= 1 else 'abaixo'} de 1.", [ke["id"]], "inferência")
    jr = _mkt(mkt, "Juro real")
    cc = _item(fin, "Perda esperada com crédito: variação")
    if tipo == "banco" and jr and cc and jr["valor"] > 6 and cc["valor"] > 10:
        D.alerta("divergencia", f"Juro real de {jr['valor']:.1f}% e perdas com crédito crescendo {cc['valor']:.1f}%: "
                 "o ambiente macro reforça o risco de crédito apontado nas demonstrações.", [])
    faltando = [a["nome"] for a in (mkt or {}).get("ausentes", [])]
    if faltando:
        D.alerta("aviso", f"{len(faltando)} indicador(es) macro indisponível(is) nesta execução: " + ", ".join(faltando[:6]) +
                 ("…" if len(faltando) > 6 else "") + ". As leituras macro ficam incompletas.")


def _tese(D: Dossie, fin, mkt, tipo):
    """Monta a tese separando fatos, estimativas e opinião. A 'opinião' é uma regra explícita, não recomendação."""
    pot = next((x for x in D.itens if x["nome"] == "Potencial ponderado"), None) or next((x for x in D.itens if x["nome"] == "Potencial — base"), None)
    roe_impl = next((x for x in D.itens if x["nome"] == "ROE sustentável implícito no preço"), None)
    roe = _item(fin, "ROE")
    fatos = [x["id"] for x in D.itens if x["tipo"] == "fato"][:8]
    estim = [x["id"] for x in D.itens if x["tipo"] == "estimativa" and ("Potencial" in x["nome"] or "implícito" in x["nome"] or "ponderado" in x["nome"] or x["nome"] == "Ke (CAPM)")]
    opiniao = "Sem valuation suficiente para uma leitura."
    if pot:
        v = pot["valor"]
        opiniao = ("Pelo modelo e pelas premissas declaradas, o preço está ABAIXO do valor estimado" if v > 15 else
                   "Pelo modelo e pelas premissas declaradas, o preço está ACIMA do valor estimado" if v < -15 else
                   "Pelo modelo e pelas premissas declaradas, o preço está PRÓXIMO do valor estimado") + f" ({v:+.1f}%)".replace(".", ",") + "."
    riscos, oportunidades = [], []
    for a in fin.get("alertas", []) + D.alertas:
        if a["nivel"] in ("aviso", "divergencia"):
            riscos.append(a["texto"])
    if roe_impl and roe:
        if roe_impl["valor"] < roe["valor"] - 2:
            oportunidades.append(f"O preço embute ROE sustentável de {roe_impl['valor']:.1f}%, abaixo do ROE atual de {roe['valor']:.1f}%: "
                                 "se a rentabilidade se mantiver, há espaço para reprecificação.")
        elif roe_impl["valor"] > roe["valor"] + 2:
            riscos.append(f"O preço embute ROE sustentável de {roe_impl['valor']:.1f}%, acima do ROE atual de {roe['valor']:.1f}%: "
                          "o mercado já espera melhora relevante.")
    ke_impl = next((x for x in D.itens if x["nome"] == "Ke implícito no preço"), None)
    ke_capm = next((x for x in D.itens if x["nome"] == "Ke (CAPM)"), None)
    if ke_impl and ke_capm and abs(ke_impl["valor"] - ke_capm["valor"]) > 2:
        riscos.append(f"Grande parte do resultado depende do Ke: o preço de hoje equivale a Ke de {ke_impl['valor']:.1f}% (mantido o ROE atual), "
                      f"contra {ke_capm['valor']:.1f}% pelo CAPM com as premissas declaradas. Veja a tabela de sensibilidade.")
    for l in (mkt or {}).get("leituras", []):
        (oportunidades if "aliviar" in l["texto"] or "favorece" in l["texto"] else riscos if "pressiona" in l["texto"] or "elevar" in l["texto"] else []).append(l["texto"])
    riscos = [decimal_br(r) for r in dict.fromkeys(riscos)]
    oportunidades = [decimal_br(o) for o in dict.fromkeys(oportunidades)]
    D.extras["tese"] = {"fatos": fatos, "estimativas": estim, "opiniao": opiniao, "riscos": riscos, "oportunidades": oportunidades,
                        "aviso": "Estudo automatizado para fins educacionais. Não é recomendação de compra ou venda."}
