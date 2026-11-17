"""Agente de pesquisa com IA: o modelo decide o que investigar, chama as ferramentas, lê os resultados e repete
até ter o suficiente para escrever a análise.

O que a IA PODE fazer: escolher ferramentas (balanço, pares, macro, valuation, detalhe de um número), interpretar,
confrontar e escrever.
O que a IA NÃO PODE fazer: criar números ou mudar premissas. Todo número vem de uma ferramenta, que lê fontes
oficiais (CVM, B3, Tesouro, Banco Central). O texto final passa pelo validador: número que não veio de uma
ferramenta → o texto volta para a IA corrigir; se insistir, é descartado e o relatório usa o texto por regras.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from indicadores_b3.agents import financial, investment, market, redator
from indicadores_b3.agents.nucleo import AgenteFerramentas, Ferramenta

MAX_PASSOS = 14
MAX_CORRECOES = 2

SISTEMA = """Você é um analista de investment research sell-side no Brasil, escrevendo em português.
Seu trabalho: investigar a empresa pedida usando as FERRAMENTAS e escrever uma análise.

COMO TRABALHAR
- Planeje: decida o que precisa saber e chame as ferramentas. Pode chamar várias, em qualquer ordem, e voltar a elas.
- Comece pela análise financeira da empresa. Para comparar, analise os pares; se não foram informados, descubra-os com
  empresas_do_setor (mesmo setor no cadastro da CVM) e escolha os mais comparáveis, explicando a escolha. Para o contexto, veja o mercado/macro.
  Para preço justo, rode o valuation (ele usa premissas declaradas que você NÃO pode mudar).
- Investigue o que chamar atenção: números fora do padrão, divergências, dados ausentes. Use detalhe_item para ver de onde um número veio.
- Para o que os demonstrativos da CVM não trazem (inadimplência acima de 90 dias, índice de Basileia, lucro recorrente, guidance,
  explicação da própria empresa para um número), use relatorios_ri: ele busca no relatório de resultados e na apresentação que a
  empresa entregou à CVM. Use ler_pagina_ri quando o trecho estiver cortado.
- Quando tiver o suficiente, responda SEM chamar ferramentas, com a análise final.

REGRAS DE NÚMEROS (obrigatórias)
- Use SOMENTE números que apareceram nas respostas das ferramentas, escritos exatamente como lá (ex.: 22,2%, R$ 46,8 bi, 1,96x).
- Depois de cada número, cite o id entre colchetes: 22,2% [F19]. Itens de pares têm id com o ticker: [BBDC4.F19].
- Não faça contas novas, não arredonde de outro jeito, não invente datas, eventos, notícias ou projeções.
- Números tirados dos relatórios de RI levam a citação da página no lugar do id: 15,8% [D12 p3]. Escreva o número como está no documento.
  Não misture na mesma frase um número do relatório de RI e um número das outras ferramentas.
- Se um dado não existe nas ferramentas, diga que não está disponível.

FORMATO DA ANÁLISE FINAL (Markdown, curto e organizado, até 400 palavras)
As tabelas de indicadores, pares, valuation e macro são montadas automaticamente pelo sistema: NÃO as repita.
Escreva só a interpretação, com os números essenciais (no máximo uns 12), nesta ordem e com estes títulos:
## Destaques
3 a 5 itens de lista, uma frase curta cada (até 25 palavras), começando pelo mais importante.
## Tese
Um parágrafo de até 120 palavras: o que os dados dizem sobre o negócio, os pares e o preço.
## Riscos
Até 4 itens de lista, uma frase cada.
## Oportunidades
Até 3 itens de lista, uma frase cada.
## Leitura final
Opinião em 1 ou 2 frases, começando por "Opinião:". Não recomende comprar ou vender.
## Limitações
Até 3 itens: dados que não estavam disponíveis e que mudariam a análise.

ESTILO
- Frases curtas e diretas. Nada de introduções ("Neste relatório...").
- Não use travessão (— ou –) nem linhas separadoras (---). Use vírgula, dois-pontos ou parênteses.
- Não use tabelas nem negrito em frases inteiras."""

FERRAMENTAS = [
    {"type": "function", "function": {
        "name": "analise_financeira",
        "description": "Demonstrações da CVM (12 meses, balanço, rentabilidade, crédito/endividamento) e preço da B3 de uma empresa. "
                       "Detecta se é banco. Devolve itens com id, valor formatado e tipo (fato/calculado), dados ausentes e alertas.",
        "parameters": {"type": "object", "properties": {"ticker": {"type": "string", "description": "Código na B3, ex.: ITUB4"}},
                       "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "mercado_macro",
        "description": "Contexto de mercado: Selic, IPCA, Focus, curva de juros do Tesouro (pré, inflação implícita, juro real), "
                       "indicadores externos e comunicados recentes da empresa na CVM (só título e link).",
        "parameters": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "valuation",
        "description": "Valuation da empresa já analisada contra os pares já analisados: banco → P/VP justificado (Gordon) com Ke pelo CAPM, "
                       "ROE e Ke implícitos no preço, 3 cenários e sensibilidade; demais → múltiplos dos pares. "
                       "Roda a análise financeira e o macro antes, se ainda não rodaram.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "empresas_do_setor",
        "description": "Setor e macrossetor da empresa (cadastro FCA da CVM) e as empresas do mesmo setor, mais negociadas primeiro. "
                       "Use para escolher pares de comparação.",
        "parameters": {"type": "object", "properties": {"ticker": {"type": "string"}, "quantidade": {"type": "integer", "description": "até 10"}},
                       "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "relatorios_ri",
        "description": "Busca nos relatórios de resultados da empresa entregues à CVM (relatório gerencial, press-release, apresentação). "
                       "Tabelas vêm linha a linha com o período (ex.: 'Índice de Basileia | 3T26: 15,8%'). Devolve trechos e como citar ([D12 p3]). "
                       "Na primeira chamada baixa os 2 relatórios mais recentes (pode demorar).",
        "parameters": {"type": "object", "properties": {"pergunta": {"type": "string", "description": "o que procurar, ex.: 'índice de Basileia'"}},
                       "required": ["pergunta"]}}},
    {"type": "function", "function": {
        "name": "ler_pagina_ri",
        "description": "Lê a página inteira de um relatório de RI (com as tabelas da página linha a linha).",
        "parameters": {"type": "object", "properties": {"documento": {"type": "integer"}, "pagina": {"type": "integer"}},
                       "required": ["documento", "pagina"]}}},
    {"type": "function", "function": {
        "name": "detalhe_item",
        "description": "Origem completa de um número: fonte, documento, conta da CVM, período, fórmula e componentes.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string", "description": "ex.: F19, M2, I28 ou BBDC4.F19"}},
                       "required": ["id"]}}},
]


def _compacto(d: dict) -> dict:
    return {"assunto": d["assunto"], "data_base": d["extras"].get("ref"), "tipo": d["extras"].get("tipo"),
            "itens": [{"id": x["id"], "nome": x["nome"], "valor": redator.fmt(x["valor"], x.get("unidade")), "tipo": x["tipo"],
                       **({"formula": x["formula"]} if x.get("formula") else {})} for x in d["itens"] if x["valor"] is not None],
            "ausentes": [f"{a['nome']}: {a['motivo']}" for a in d["ausentes"]],
            "alertas": [a["texto"] for a in d["alertas"]],
            "leituras": [l["texto"] for l in d.get("leituras", [])]}


def _reprefixar(d: dict, t: str) -> dict:
    """Ids de pares ganham o ticker (BBDC4.F19) para não colidir com os da empresa principal."""
    m = {x["id"]: f"{t}.{x['id']}" for x in d["itens"]}
    d = json.loads(json.dumps(d))
    for x in d["itens"]:
        x["id"] = m[x["id"]]
        x["insumos"] = [m.get(i, i) for i in x.get("insumos", [])]
    d["secoes"] = {s: [m[i] for i in ids] for s, ids in d["secoes"].items()}
    return d


class Agente:
    def __init__(self, ticker: str, pares: list[str] | None = None):
        self.t = ticker.upper()
        self.pares_sug = pares
        self.fin = self.mkt = self.inv = None
        self.pares: dict[str, dict] = {}
        self.pares_brutos: dict[str, dict] = {}
        self.passos: list[dict] = []
        self._ri = None          # agente de documentos (rag) usado pelas ferramentas de RI
        self.ri_coleta: dict = {"documentos": [], "falhas": []}

    # ---------- ferramentas ----------
    def analise_financeira(self, ticker: str):
        t = ticker.strip().upper()
        if t == self.t:
            if not self.fin:
                self.fin = financial.analisar(t).to_dict()
            return _compacto(self.fin)
        if t not in self.pares:
            bruto = financial.analisar(t).to_dict()
            self.pares_brutos[t] = bruto
            self.pares[t] = _reprefixar(bruto, t)
        return _compacto(self.pares[t])

    def mercado_macro(self, ticker: str | None = None):
        if not self.mkt:
            tipo = (self.fin or {}).get("extras", {}).get("tipo", "geral")
            self.mkt = market.analisar(self.t, tipo).to_dict()
        out = _compacto(self.mkt)
        out["comunicados"] = [f"{n.get('data', '')} · {n['titulo']}" for n in self.mkt["extras"].get("noticias", [])
                              if str(n.get("fonte", "")).startswith("CVM")][:10]
        return out

    def valuation(self):
        if not self.fin:
            self.analise_financeira(self.t)
        if not self.mkt:
            self.mercado_macro(self.t)
        self.inv = investment.analisar(self.fin, self.pares_brutos, self.mkt).to_dict()
        out = _compacto(self.inv)
        out["comparacao"] = [{"metrica": l["metrica"], "valores": {k: redator.fmt(v, l["unidade"]) for k, v in l["valores"].items()},
                              "mediana_pares": redator.fmt(l["mediana_pares"], l["unidade"])} for l in self.inv["extras"].get("comparacao", [])]
        s = self.inv["extras"].get("sensibilidade")
        if s:
            out["sensibilidade_preco_justo"] = {"linhas_ke": [redator.fmt(k, "%") for k in s["ke"]], "colunas_roe": [redator.fmt(r, "%") for r in s["roe"]],
                                                "precos": [[redator.fmt(p, "R$") for p in l] for l in s["precos"]]}
        if not self.pares_brutos:
            out["aviso"] = "Nenhum par analisado ainda: rode analise_financeira nos pares e depois o valuation de novo para comparar."
        return out

    def empresas_do_setor(self, ticker: str, quantidade: int = 6):
        from indicadores_b3.data import setores
        r = setores.pares(ticker, max(1, min(int(quantidade), 10)))
        return {"ticker": r["ticker"], "setor": r.get("setor"), "macrossetor": r.get("macro"), "criterio": r.get("criterio"),
                "ordem": r.get("ordem"), "empresas": [{"ticker": p["ticker"], "empresa": p["empresa"]} for p in r["pares"]],
                "fonte": "CVM · FCA (Setor_Atividade); macrossetor é agrupamento do projeto"}

    def detalhe_item(self, id: str):
        for d in [self.fin, self.mkt, self.inv, *self.pares.values()]:
            for x in (d or {}).get("itens", []):
                if x["id"] == id:
                    return {k: x.get(k) for k in ("id", "nome", "tipo", "fonte", "formula", "insumos", "nota", "componentes") if x.get(k)} | \
                           {"valor": redator.fmt(x["valor"], x.get("unidade"))}
        return {"erro": f"id {id} não encontrado"}

    # ---------- relatórios de RI entregues à CVM (busca com citação conferida) ----------
    def _docs(self):
        if self._ri is None:
            from indicadores_b3.rag import coleta
            from indicadores_b3.rag.agente import AgenteDocumentos
            try:
                self.ri_coleta = coleta.indexar_ri(self.t)
            except Exception as e:  # noqa: BLE001 — sem IPE/CVM: a ferramenta avisa e o agente segue sem
                self.ri_coleta = {"documentos": [], "falhas": [{"erro": str(e)[:200]}]}
            self._ri = AgenteDocumentos(self.t)
        return self._ri

    def relatorios_ri(self, pergunta: str):
        ag = self._docs()
        docs = [d for d in self.ri_coleta["documentos"] if d.get("id")]
        if not docs:
            falha = "; ".join(f.get("erro", "") for f in self.ri_coleta.get("falhas", []))[:300]
            return {"erro": "Não encontrei relatórios de resultados desta empresa na CVM" + (f" ({falha})" if falha else "")
                            + ". Diga que o dado não está disponível."}
        res = []
        for d in docs:
            res += ag.buscar(pergunta, documento=d["id"], k=4)["resultados"]
        return {"documentos": [{"id": d["id"], "tipo": d.get("tipo"), "assunto": d.get("assunto"), "entregue_em": d.get("data_entrega")}
                               for d in docs],
                "resultados": res[:8], "aviso": None if res else "nada encontrado; tente outras palavras"}

    def ler_pagina_ri(self, documento: int, pagina: int):
        return self._docs().ler_pagina(documento, pagina)

    def documentos_usados(self) -> list[dict]:
        if not self._ri:
            return []
        lidas: dict[int, list[int]] = {}
        for d, p in self._ri.vistos:
            lidas.setdefault(d, []).append(p)
        return [{"id": d["id"], "tipo": d.get("tipo"), "assunto": d.get("assunto"), "data_entrega": d.get("data_entrega"),
                 "url": d.get("url"), "paginas_lidas": sorted(lidas.get(d["id"], []))}
                for d in self.ri_coleta["documentos"] if d.get("id")]

    def dossies(self) -> list[dict]:
        return [d for d in [self.fin, self.mkt, self.inv, *self.pares.values()] if d]

    def _validar(self, texto: str) -> list[str]:
        """Frases com citação de documento [D12 p3] são conferidas contra a página lida; o resto, contra os dossiês."""
        from indicadores_b3.rag.agente import CITACAO, validar_citacoes
        partes = [p for p in re.split(r"(?<=[.!?;])\s+|\n+", texto) if p.strip()]
        com_doc = [p for p in partes if CITACAO.search(p)]
        probs = []
        ruins = redator.validar(" ".join(p for p in partes if not CITACAO.search(p)), self.dossies())
        if ruins:
            probs.append(f"números que não vieram das ferramentas: {', '.join(ruins)}. Use só números exatamente como as ferramentas "
                         "devolveram, com o id ao lado")
        if com_doc:
            vistos = self._ri.vistos if self._ri else {}
            probs += [f"relatórios de RI: {p}" for p in validar_citacoes(" ".join(com_doc), vistos)]
        return probs

    def _ferramentas(self) -> list[Ferramenta]:
        esq = {f["function"]["name"]: f["function"] for f in FERRAMENTAS}
        def nome_ou_qtd(r):
            if r.get("empresas") is not None:
                return f"{r.get('setor')}: {', '.join(e['ticker'] for e in r['empresas']) or 'nenhuma'}"
            return r.get("assunto") or (f"{r['nome']} = {r['valor']}" if r.get("nome") else "ok")
        return [Ferramenta(n, esq[n]["description"], getattr(self, n), esq[n]["parameters"], nome_ou_qtd)
                for n in ("analise_financeira", "empresas_do_setor", "mercado_macro", "valuation", "detalhe_item")] + [
            Ferramenta("relatorios_ri", esq["relatorios_ri"]["description"], self.relatorios_ri, esq["relatorios_ri"]["parameters"],
                       lambda r: r.get("erro") or ", ".join(x["cite_como"] for x in r.get("resultados", [])) or "nada encontrado"),
            Ferramenta("ler_pagina_ri", esq["ler_pagina_ri"]["description"], self.ler_pagina_ri, esq["ler_pagina_ri"]["parameters"],
                       lambda r: r.get("cite_como") or r.get("erro", ""))]

    # ---------- laço do agente (núcleo genérico em nucleo.py) ----------
    def rodar(self) -> dict:
        pares = self.pares_sug or []
        pedido = (f"Analise {self.t}. " + (f"Pares sugeridos para comparação: {', '.join(pares)}. " if pares
                                     else "Nenhum par informado: use empresas_do_setor para encontrar os comparáveis. ") +
                  f"Data de hoje: {datetime.now():%Y-%m-%d}.")
        nucleo = AgenteFerramentas(SISTEMA, self._ferramentas(), self._validar, max_passos=MAX_PASSOS, max_correcoes=MAX_CORRECOES,
                                   podar=True)
        r = nucleo.rodar(pedido)
        self.passos = r.passos
        return r.to_dict()
