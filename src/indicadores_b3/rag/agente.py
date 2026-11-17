"""Agente de perguntas sobre os comunicados, com citações VALIDADAS.

Ferramentas: listar documentos, buscar trechos (busca híbrida) e ler uma página inteira.
Formato obrigatório de citação: [D12 p3] = documento 12, página 3. Trechos literais vão entre aspas.

O validador reprova a resposta quando:
  - não há citação (a não ser que a resposta diga que não encontrou);
  - cita documento/página que o agente não leu nesta conversa;
  - põe entre aspas um texto que não está nas páginas citadas;
  - escreve um número que não aparece nas páginas citadas (aceita R$ 1,2 bi = 1.200.000.000).
Reprovada, a resposta volta ao modelo com os problemas; se insistir, é descartada.
"""
from __future__ import annotations

import re
from datetime import datetime

from indicadores_b3.agents.nucleo import AgenteFerramentas, Ferramenta
from indicadores_b3.agents.redator import NUM, _paraf
from indicadores_b3.rag import armazem

CITACAO = re.compile(r"\[D(\d+)[\s,·]*p\.?\s*(\d+)\]", re.I)
ASPAS = re.compile(r"[“\"]([^”\"]{12,})[”\"]")
NAO_ACHOU = re.compile(r"n[ãa]o (encontrei|h[áa] (informa|men)|consta|foi poss[íi]vel encontrar)", re.I)

SISTEMA = """Você é analista de relações com investidores e responde perguntas sobre comunicados de empresas
(fatos relevantes, comunicados ao mercado, avisos aos acionistas e relatórios de resultados) entregues à CVM. Escreva em português.
Trechos que começam com "Tabela ·" são linhas de tabela: rótulo e valores com o período de cada coluna (ex.: 3T26: 15,8%).

COMO TRABALHAR
- Use buscar para achar trechos relevantes. Refaça a busca com outras palavras se o resultado for fraco.
- Use ler_pagina quando o trecho estiver cortado ou precisar de contexto.
- Responda só com o que está nos documentos lidos. Se não encontrar, diga claramente que não encontrou.

CITAÇÕES (obrigatórias)
- Depois de cada afirmação, cite a fonte no formato [D12 p3] (documento 12, página 3), usando os ids das ferramentas.
- Para trechos literais, use aspas e copie exatamente como está no documento.
- Números (valores, datas, percentuais) devem ser escritos como aparecem no documento citado.
- Não use conhecimento externo, não faça contas e não dê recomendação de investimento.

FORMATO: resposta direta em 1 a 3 parágrafos curtos (ou lista), com as citações."""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", armazem.sem_acento(s.lower())).strip()


def _numeros(texto: str) -> list[float]:
    out = []
    for m in NUM.finditer(texto):
        v = _paraf(m.group(0))
        if v is not None:
            out += [abs(v), abs(v) / 1e3, abs(v) / 1e6, abs(v) / 1e9, abs(v) * 1e3, abs(v) * 1e6, abs(v) * 1e9]
    return out


def validar_citacoes(resposta: str, vistos: dict[tuple[int, int], str]) -> list[str]:
    """Problemas da resposta frente às páginas efetivamente lidas (vistos: {(doc, pagina): texto})."""
    probs = []
    cits = {(int(d), int(p)) for d, p in CITACAO.findall(resposta)}
    if not cits:
        return [] if NAO_ACHOU.search(resposta) else ["a resposta não tem nenhuma citação no formato [D12 p3]"]
    fora = sorted(c for c in cits if c not in vistos)
    if fora:
        probs.append("cita páginas que não foram lidas nesta conversa: " + ", ".join(f"[D{d} p{p}]" for d, p in fora))
    texto_citado = " ".join(vistos[c] for c in cits if c in vistos)
    base = _norm(texto_citado)
    for q in ASPAS.findall(resposta):
        if len(q.split()) >= 3 and _norm(q) not in base:
            probs.append(f'o trecho entre aspas "{q[:80]}" não está nas páginas citadas')
    # números: tira citações, datas e anos; o resto precisa existir nas páginas citadas
    corpo = CITACAO.sub(" ", resposta)
    corpo = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", " ", corpo)
    corpo = re.sub(r"\b[A-Z]{4}\d{1,2}\b", " ", corpo)
    permitidos = _numeros(texto_citado)
    ruins = []
    for m in NUM.finditer(corpo):
        s = m.group(0)
        v = _paraf(s)
        if v is None:
            continue
        if float(v).is_integer() and "," not in s and (abs(v) <= 31 or 1990 <= abs(v) <= 2100):
            continue
        casas = len(s.split(",")[1]) if "," in s else 0
        tol = 0.5 * 10 ** (-casas) + 1e-9
        if not any(abs(abs(v) - p) <= max(tol, abs(p) * 1e-9) for p in permitidos):
            ruins.append(s)
    if ruins:
        probs.append("números que não aparecem nas páginas citadas: " + ", ".join(dict.fromkeys(ruins)))
    return probs


class AgenteDocumentos:
    def __init__(self, ticker: str | None = None, db=None):
        self.ticker = ticker.upper() if ticker else None
        self.db = db
        self.vistos: dict[tuple[int, int], str] = {}
        self.docs = {d["id"]: d for d in armazem.documentos(None, db)}

    # ---------- ferramentas ----------
    def documentos(self, ticker: str | None = None, termo: str | None = None) -> dict:
        t = (ticker or self.ticker or "").upper() or None
        ds = [d for d in self.docs.values() if (not t or d["ticker"] == t)
              and (not termo or _norm(termo) in _norm(f"{d['assunto']} {d['categoria']} {d['tipo']}"))]
        return {"documentos": [{"id": d["id"], "ticker": d["ticker"], "data": d["data_entrega"], "categoria": d["categoria"],
                                "assunto": d["assunto"], "paginas": d["paginas"]} for d in ds[:40]],
                "total": len(ds)}

    def buscar(self, pergunta: str, ticker: str | None = None, documento: int | None = None, k: int = 6) -> dict:
        rs = armazem.buscar(pergunta, k=max(1, min(int(k), 10)), ticker=(ticker or self.ticker), doc_id=documento, db=self.db)
        out = []
        for r in rs:
            self.vistos.setdefault((r["doc_id"], r["pagina"]), armazem.pagina(r["doc_id"], r["pagina"], self.db) or r["texto"])
            d = self.docs.get(r["doc_id"], {})
            out.append({"cite_como": f"[D{r['doc_id']} p{r['pagina']}]", "ticker": r["ticker"], "data": d.get("data_entrega"),
                        "assunto": d.get("assunto"), "trecho": r["texto"], "metodo": r["metodo"]})
        return {"resultados": out, "aviso": None if out else "nada encontrado; tente outras palavras ou outro ticker"}

    def ler_pagina(self, documento: int, pagina: int) -> dict:
        txt = armazem.pagina(int(documento), int(pagina), self.db)
        if txt is None:
            return {"erro": f"página {pagina} do documento {documento} não existe"}
        self.vistos[(int(documento), int(pagina))] = txt
        return {"cite_como": f"[D{documento} p{pagina}]", "texto": txt[:7000]}

    def _ferramentas(self) -> list[Ferramenta]:
        obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731
        return [
            Ferramenta("documentos", "Lista os documentos indexados (id, data, categoria, assunto), filtrando por ticker ou termo.",
                       self.documentos, obj({"ticker": {"type": "string"}, "termo": {"type": "string"}}),
                       lambda r: f"{r.get('total', 0)} documentos"),
            Ferramenta("buscar", "Busca trechos relevantes nos documentos (palavras + significado). Devolve o texto e como citar.",
                       self.buscar, obj({"pergunta": {"type": "string"}, "ticker": {"type": "string"},
                                         "documento": {"type": "integer"}, "k": {"type": "integer"}}, ["pergunta"]),
                       lambda r: ", ".join(x["cite_como"] for x in r.get("resultados", [])) or "nada encontrado"),
            Ferramenta("ler_pagina", "Lê a página inteira de um documento.", self.ler_pagina,
                       obj({"documento": {"type": "integer"}, "pagina": {"type": "integer"}}, ["documento", "pagina"]),
                       lambda r: r.get("cite_como", "")),
        ]

    def perguntar(self, pergunta: str, provedores=None, max_passos: int = 8) -> dict:
        pedido = (f"Pergunta: {pergunta}\n" + (f"Empresa: {self.ticker}\n" if self.ticker else "")
                  + f"Data de hoje: {datetime.now():%Y-%m-%d}.")
        nucleo = AgenteFerramentas(SISTEMA, self._ferramentas(), lambda t: validar_citacoes(t, self.vistos),
                                   max_passos=max_passos, max_correcoes=2, provedores=provedores)
        r = nucleo.rodar(pedido).to_dict()
        cits = sorted({(int(d), int(p)) for d, p in CITACAO.findall(r["texto"] or "")})
        r["citacoes"] = [{"id": f"D{d} p{p}", "doc_id": d, "pagina": p, "assunto": self.docs.get(d, {}).get("assunto"),
                          "data": self.docs.get(d, {}).get("data_entrega"), "url": self.docs.get(d, {}).get("url"),
                          "texto": self.vistos.get((d, p), "")} for d, p in cits]
        r["paginas_lidas"] = len(self.vistos)
        r["pergunta"], r["ticker"] = pergunta, self.ticker
        return r
