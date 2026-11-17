"""Relatório final em Markdown (e HTML pronto para imprimir em PDF pelo navegador).

Estrutura: resumo · análise financeira · mercado · comparação · valuation e cenários · sensibilidade ·
tese (fatos / estimativas / opinião) · riscos e oportunidades · premissas · dados ausentes · fontes · aviso.
Todo número aparece com o id do item ([F12], [M3], [I20]) que leva à fonte na tabela final.
"""
from __future__ import annotations

import html
import re

from indicadores_b3.agents.estilo import celula, rotulo, texto
from indicadores_b3.agents.redator import fmt

TIPO = {"fato": "Fato", "calculado": "Calculado", "premissa": "Premissa", "estimativa": "Estimativa"}


def _tab(cab: list[str], linhas: list[list]) -> str:
    out = ["| " + " | ".join(cab) + " |", "|" + "|".join("---" for _ in cab) + "|"]
    for l in linhas:
        out.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in l) + " |")
    return "\n".join(out)


def _secoes(d: dict, nivel: str = "####") -> list[str]:
    md = []
    por_id = {x["id"]: x for x in d["itens"]}
    for nome, ids in d["secoes"].items():
        md.append(f"{nivel} {nome}\n")
        linhas = []
        for i in ids:
            x = por_id[i]
            origem = (x.get("fonte") or {}).get("fonte") or x.get("formula") or x.get("nota", "")[:80]
            linhas.append([f"[{i}]", rotulo(x["nome"]), _f(x["valor"], x.get("unidade")), TIPO[x["tipo"]], texto(origem)])
        md.append(_tab(["id", "Item", "Valor", "Tipo", "Origem ou fórmula"], linhas) + "\n")
    return md


def _f(v, u=""):
    return celula(None if v is None else fmt(v, u))


def _lista(itens, vazio="Nenhum."):
    itens = [texto(t) for t in itens if t]
    return "\n".join(f"- {t}" for t in itens) if itens else vazio


def _item(d, nome):
    return next((x for x in (d or {}).get("itens", []) if x["nome"] == nome), None)


def _cit(x):
    return f"{_f(x['valor'], x.get('unidade'))} [{x['id']}]" if x else "n/d"


def montar(res: dict) -> str:
    """Relatório no formato de nota de research: resumo no topo, tabelas no meio, anexos (dossiês e fontes) no fim."""
    fin, mkt, inv, red = res.get("financial"), res.get("market"), res.get("investment"), res.get("redacao") or {}
    sec = red.get("secoes") or {}
    t = res["ticker"]
    setor = (fin or {}).get("extras", {}).get("setor") or {}
    autor = (f"agente de IA ({red['modelo']})" if red.get("modo") == "agente" else f"IA ({red['modelo']})" if red.get("modo") == "ia"
             else "regras fixas")
    md = [f"# {fin['assunto'] if fin else t}", ""]

    # cabeçalho em tabela
    preco = _item(inv, "Preço atual") or _item(fin, "Preço")
    justo = _item(inv, "Preço justo ponderado pelos cenários") or _item(inv, "Preço pelo P/L dos pares")
    pot = _item(inv, "Potencial ponderado")
    tese = (inv or {}).get("extras", {}).get("tese", {})
    leitura = tese.get("opiniao", "")
    cab = [["Data do relatório", res["gerado_em"]], ["Dados contábeis até", (fin or {}).get("extras", {}).get("ref") or "n/d"],
           ["Setor", f"{setor.get('macro')} › {setor.get('setor')}" if setor.get("setor") else "n/d"],
           ["Preço", _cit(preco)], ["Preço justo (ponderado)", _cit(justo)], ["Potencial", _cit(pot)],
           ["Pares", ", ".join(res.get("pares") or {}) or "n/d"], ["Texto", autor]]
    md.append(_tab(["", ""], cab) + "\n")
    md.append("> Estudo automatizado para fins educacionais. Não é recomendação de compra ou venda. Cada número traz um id "
              "entre colchetes; o anexo Fontes diz de onde ele veio.\n")
    if red.get("aviso"):
        md.append(f"> {texto(red['aviso'])}\n")

    # 1 a 3: texto
    md.append("## 1. Destaques\n")
    md.append((sec.get("destaques") or _lista([])) + "\n")
    md.append("## 2. Tese\n")
    md.append((sec.get("tese") or "n/d") + "\n")
    if sec.get("leitura") or leitura:
        md.append(f"**{texto(sec.get('leitura') or 'Opinião: ' + leitura)}**\n")
        md.append("*Regra do projeto para a opinião automática (escolhida, não vem de estudo): potencial acima de +15% = preço abaixo do valor estimado; abaixo de -15% = acima; "
                  "entre os dois = próximo.*\n")

    # 4: indicadores e pares
    comp = (inv or {}).get("extras", {}).get("comparacao", [])
    if comp:
        md.append("## 3. Indicadores e pares\n")
        tks = list(comp[0]["valores"])
        md.append(_tab(["Indicador"] + tks + ["Mediana dos pares"],
                       [[l["metrica"]] + [_f(l["valores"][k], l["unidade"]) for k in tks] + [_f(l["mediana_pares"], l["unidade"])]
                        for l in comp]) + "\n")

    # 5: valuation
    if inv:
        md.append("## 4. Valuation\n")
        cen = [(c, _item(inv, f"ROE sustentável — {c}"), _item(inv, f"Ke — {c}"), _item(inv, f"P/VP justo — {c}"),
                _item(inv, f"Preço justo — {c}"), _item(inv, f"Potencial — {c}"), _item(inv, f"Peso do cenário {c}"))
               for c in ("pessimista", "base", "otimista")]
        if any(c[4] for c in cen):
            md.append("P/VP justificado: P/VP = (ROE - g) ÷ (Ke - g); preço justo = P/VP × VPA.\n")
            md.append(_tab(["Cenário", "Peso", "ROE", "Ke", "P/VP justo", "Preço justo", "Potencial"],
                           [[c[0].capitalize(), _cit(c[6]), _cit(c[1]), _cit(c[2]), _cit(c[3]), _cit(c[4]), _cit(c[5])] for c in cen]) + "\n")
            prem = [x for x in inv["itens"] if x["nome"] in ("Taxa livre de risco (juro prefixado 5 anos)", "Beta do banco", "Prêmio de risco de ações",
                                                            "Ke (CAPM)", "g (crescimento nominal na perpetuidade)", "ROE sustentável implícito no preço",
                                                            "Ke implícito no preço")]
            md.append(_tab(["Premissa ou resultado", "Valor"], [[rotulo(x["nome"]), _cit(x)] for x in prem]) + "\n")
        mult = [x for x in inv["itens"] if x["nome"].startswith(("Preço pelo", "P/L mediano", "P/VP mediano"))]
        if mult:
            md.append("Por múltiplos dos pares:\n")
            md.append(_tab(["Item", "Valor"], [[rotulo(x["nome"]), _cit(x)] for x in mult]) + "\n")
        s = inv["extras"].get("sensibilidade")
        if s:
            md.append(f"Sensibilidade do preço justo (R$) a Ke e ROE, com g = {_f(s['g'], '%')}:\n")
            md.append(_tab(["Ke \\ ROE"] + [_f(r, "%") for r in s["roe"]],
                           [[_f(k, "%")] + [_f(p, "R$") for p in linha] for k, linha in zip(s["ke"], s["precos"], strict=False)]) + "\n")

    # 6: macro
    if mkt and mkt.get("itens"):
        md.append("## 5. Cenário macro\n")
        md.append(_tab(["Indicador", "Valor", "Fonte", "Data"],
                       [[rotulo(x["nome"]), _cit(x), (x.get("fonte") or {}).get("fonte") or "calculado", (x.get("fonte") or {}).get("data_ref") or ""]
                        for x in mkt["itens"]]) + "\n")

    # 7: riscos e oportunidades
    md.append("## 6. Riscos\n")
    md.append((sec.get("riscos") or _lista(tese.get("riscos", [])[:4])) + "\n")
    md.append("## 7. Oportunidades\n")
    md.append((sec.get("oportunidades") or _lista(tese.get("oportunidades", [])[:3], "Nenhuma identificada pelas regras.")) + "\n")
    md.append("## 8. Limitações\n")
    aus = [a for d in (fin, mkt, inv) if d for a in d.get("ausentes", [])]
    md.append((sec.get("limitacoes") or "") + "\n")
    if aus:
        md.append(_tab(["Dado ausente", "Motivo", "Onde obter"], [[a["nome"], texto(a["motivo"]), a.get("fonte_sugerida", "")] for a in aus]) + "\n")

    # anexos
    md.append("## Anexo A. Fatos e estimativas usados\n")
    if tese:
        por_id = {x["id"]: x for x in inv["itens"]}
        md.append(_tab(["Tipo", "Item", "Valor"],
                       [["Fato", rotulo(por_id[i]["nome"]), _cit(por_id[i])] for i in tese.get("fatos", []) if i in por_id]
                       + [["Estimativa", rotulo(por_id[i]["nome"]), _cit(por_id[i])] for i in tese.get("estimativas", []) if i in por_id]) + "\n")
    md.append("## Anexo B. Dossiês completos\n")
    for d, nome in ((fin, "Financial Analyst"), (mkt, "Market Research Analyst"), (inv, "Investment Research Analyst")):
        if d:
            md.append(f"### {nome}\n")
            md += _secoes(d)
            al = [a["texto"] for a in d.get("alertas", [])]
            if al:
                md.append("Alertas:\n\n" + _lista(al) + "\n")
    nots = [n for n in (mkt or {}).get("extras", {}).get("noticias") or [] if str(n.get("fonte", "")).startswith("CVM")]
    if nots:
        md.append("### Comunicados recentes (título e link)\n")
        md.append(_lista(f"{n.get('data', '')}, {n['fonte']}: [{n['titulo']}]({n['url']})" for n in nots[:12]) + "\n")
    if res.get("passos"):
        md.append("## Anexo C. Como o agente investigou\n")
        md.append(_lista(f"{x['nome']}({', '.join(f'{k}={v}' for k, v in x['args'].items())}): {x['resumo']}" if x["tipo"] == "ferramenta"
                         else f"{x['tipo']}: {x['texto']}" for x in res["passos"]) + "\n")
    md.append("## Anexo D. Fontes\n")
    linhas = []
    for d in (fin, mkt, inv, *(res.get("pares_dossies") or {}).values()):
        for x in (d or {}).get("itens", []):
            f = x.get("fonte")
            if x["tipo"] == "fato" and f:
                url = f.get("url") or ""
                linhas.append([f"[{x['id']}]", rotulo(x["nome"]), f.get("fonte") or "", f.get("documento") or "", f.get("conta") or "",
                               f.get("periodo") or "", f.get("data_ref") or "", f"[link]({url})" if url.startswith("http") else ""])
    md.append(_tab(["id", "Item", "Fonte", "Documento", "Conta", "Período", "Data", "Link"], linhas) + "\n")
    docs = [d for d in res.get("documentos_ri") or [] if d.get("paginas_lidas")]
    if docs:
        md.append("### Relatórios da empresa lidos pelo agente (entregues à CVM)\n")
        md.append(_tab(["id", "Documento", "Entregue em", "Páginas lidas", "Link"],
                       [[f"D{d['id']}", texto(f"{d.get('tipo') or ''}: {d.get('assunto') or ''}"), d.get("data_entrega") or "",
                         ", ".join(str(p) for p in d["paginas_lidas"]), f"[link]({d['url']})" if d.get("url") else ""] for d in docs]) + "\n")
    md.append("*Estudo automatizado para fins educacionais. Não é recomendação de investimento. Confira os números na fonte antes de qualquer decisão.*")
    return texto_md("\n".join(md))


def texto_md(md: str) -> str:
    """Última passada: nenhum travessão no relatório (nem em tabelas)."""
    return re.sub(r"[—–]", "-", md)


# ---------------- Markdown → HTML (subconjunto usado acima) ----------------
def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", s)
    return s


def para_html(md: str, titulo: str) -> str:
    out, i, L = [], 0, md.split("\n")
    while i < len(L):
        l = L[i]
        if l.startswith("|") and i + 1 < len(L) and L[i + 1].startswith("|---"):
            cab = [c.strip() for c in l.strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cab) + "</tr></thead><tbody>")
            i += 2
            while i < len(L) and L[i].startswith("|"):
                out.append("<tr>" + "".join(f"<td>{_inline(c.strip())}</td>" for c in L[i].strip("|").split("|")) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        if l.startswith("- "):
            out.append("<ul>")
            while i < len(L) and L[i].startswith("- "):
                out.append(f"<li>{_inline(L[i][2:])}</li>")
                i += 1
            out.append("</ul>")
            continue
        m = re.match(r"(#{1,4}) (.*)", l)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif l.startswith("> "):
            out.append(f"<blockquote>{_inline(l[2:])}</blockquote>")
        elif l.strip() == "---":
            out.append("<hr>")
        elif l.strip():
            out.append(f"<p>{_inline(l)}</p>")
        i += 1
    css = """p,li{text-align:justify;hyphens:auto}body{font:14px/1.55 Georgia,serif;color:#1b2430;max-width:960px;margin:32px auto;padding:0 20px}
h1{color:#0f2d4a;border-bottom:2px solid #0f2d4a;padding-bottom:6px}h2{color:#0f2d4a;margin-top:32px}h4{margin:18px 0 6px;color:#1f5d6b}
table{border-collapse:collapse;width:100%;font:12px/1.4 system-ui,sans-serif;margin:6px 0 14px}
th,td{border:1px solid #d5dce4;padding:4px 7px;text-align:left;vertical-align:top}th{background:#eef3f7}
blockquote{border-left:3px solid #1f5d6b;margin:10px 0;padding:6px 12px;background:#f4f8fa}
a{color:#1f5d6b}.imprimir{position:fixed;top:12px;right:12px;padding:8px 14px;background:#0f2d4a;color:#fff;border:0;border-radius:6px;cursor:pointer}
@media print{.imprimir{display:none}body{margin:0}h2{page-break-after:avoid}table{page-break-inside:auto}tr{page-break-inside:avoid}}"""
    return (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>{html.escape(titulo)}</title><style>{css}</style></head>"
            f"<body><button class='imprimir' onclick='print()'>Salvar em PDF</button>{''.join(out)}</body></html>")
