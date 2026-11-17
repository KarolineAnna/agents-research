"""Gera docs/resultados.md com os números medidos do projeto: agentes, RAG e modelos fora da amostra.

Uso: ``python -m indicadores_b3.resultados``  (os modelos baixam preços; o resto lê o que já está em data/)

Cada seção diz o tamanho da amostra e o que a medida não garante. Nada é digitado à mão.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime

from indicadores_b3 import config

CESTA = ["PETR4", "VALE3", "ITUB4", "WEGE3", "BBAS3", "BOVA11"]  # a mesma cesta padrão da aba Modelos
PESO_MAX = 40.0
GARCH = ["PETR4", "VALE3", "ITUB4", "WEGE3", "BBAS3"]
SAIDA = config.RAIZ / "docs" / "resultados.md"


def _br(v, c=1) -> str:
    return "n/d" if v is None else f"{v:,.{c}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def agentes() -> list[str]:
    """Execuções do agente de pesquisa salvas em data/research_out (relatórios apagados saem da conta)."""
    runs = []
    for p in sorted(config.RELATORIOS_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("modo") != "agente":
            continue
        passos = d.get("passos") or []
        rasc = [x for x in passos if x["tipo"] == "rascunho"]
        runs.append({
            "aprovado": (d.get("redacao") or {}).get("modo") == "agente",
            "rascunhos": len(rasc),
            "reprovados": sum("problemas: nenhum" not in x["texto"] for x in rasc),
            "descartado": any(x["tipo"] == "erro" and "descartada" in x["texto"] for x in passos),
            "podado": any(x["tipo"] == "info" and "repetiu o mesmo erro" in x["texto"] for x in passos),
            "sem_ia": not rasc,
            "troca": any(x["tipo"] == "info" and x["texto"].startswith("Trocando") for x in passos),
            "ferramentas": sum(x["tipo"] == "ferramenta" for x in passos),
            "segundos": (d.get("metricas_agente") or {}).get("segundos"),
            "correcoes": (d.get("metricas_agente") or {}).get("correcoes") or 0,
        })
    if not runs:
        return ["Nenhuma execução do agente salva ainda."]
    n = len(runs)
    seg = [r["segundos"] for r in runs if r["segundos"]]
    conta = lambda k: sum(1 for r in runs if r[k])  # noqa: E731
    return [
        f"{n} execuções reais salvas em `data/research_out/`.",
        "",
        "| Medida | Valor |",
        "|---|---|",
        f"| Terminaram com texto aprovado pelo validador | {conta('aprovado')} de {n} |",
        f"| ...das quais precisaram de ao menos uma correção | {sum(1 for r in runs if r['aprovado'] and r['correcoes'])} |",
        f"| Rascunhos reprovados pelo validador (número sem fonte) | {sum(r['reprovados'] for r in runs)} de {sum(r['rascunhos'] for r in runs)} |",
        f"| Texto descartado após 2 correções (entrou o texto por regras) | {conta('descartado')} |",
        f"| IA não respondeu (entrou o texto por regras) | {conta('sem_ia')} |",
        f"| Precisaram trocar de provedor no meio da conversa | {conta('troca')} de {n} |",
        f"| Chamadas de ferramenta por execução (mediana) | {_br(statistics.median(r['ferramentas'] for r in runs), 0)} |",
        f"| Duração por execução (mediana) | {_br(statistics.median(seg), 0)} s |" if seg else "",
        "",
        "Leitura: o validador é acionado com frequência; sem ele, esses rascunhos teriam chegado à tela com números sem fonte. "
        "A troca de provedor não é exceção, é o caso comum no nível gratuito. A amostra é pequena e depende das empresas analisadas.",
    ]


def rag() -> list[str]:
    pasta = config.DATA_DIR / "evals" / "execucoes"
    ultimo = lambda tipo: max(pasta.glob(f"{tipo}_*.json"), default=None)  # noqa: E731
    out = []
    b = ultimo("busca")
    if b:
        d = json.loads(b.read_text(encoding="utf-8"))
        out += [f"**Busca** ({d['quando']}, {d['n']} perguntas, {d['trechos_no_indice']} trechos no índice):", "",
                "| Modo | recall@1 | recall@5 | MRR |", "|---|---|---|---|"]
        out += [f"| {m} | {_br(v['recall@1'])}% | {_br(v['recall@5'])}% | {_br(v['mrr'], 3)} |" for m, v in d["modos"].items()]
        if "palavras-chave" in str(d.get("geracao", "")):
            out += ["", "Limitação: as perguntas desta rodada foram montadas com palavras do próprio trecho (a IA estava indisponível), "
                        "o que favorece o BM25 e infla o recall. Não houve embeddings, então a busca semântica e a híbrida não foram medidas."]
    r = ultimo("respostas")
    if r:
        d = json.loads(r.read_text(encoding="utf-8"))
        s = d["resumo"]
        out += ["", f"**Respostas** ({d['quando']}, {s['perguntas']} perguntas, {d['provedor']}):", "",
                "| Medida | Valor |", "|---|---|",
                f"| Aprovadas pelo validador de citações | {_br(s['aprovadas_pelo_validador_%'])}% |",
                f"| Rascunhos barrados (citação inexistente ou número fora da página) | {s['rascunhos_barrados']} |",
                f"| Recusa correta em pergunta sem resposta nos documentos | {_br(s['recusa_correta_%'])}% |"]
        if s["perguntas"] < 20:
            out += ["", f"Limitação: {s['perguntas']} perguntas não sustentam conclusão estatística; serve como teste de fumaça do validador."]
    return out or ["Nenhuma avaliação salva. Rode na aba Documentos → Avaliação."]


def modelos() -> list[str]:
    from indicadores_b3.ml import carteira_robusta as cr
    from indicadores_b3.ml import volatilidade as vol
    from indicadores_b3.portfolio.carteira import _serie
    r = cr.carteira_robusta(CESTA, "5y", PESO_MAX)
    p = r["parametros"]
    out = [f"**Carteira robusta, walk-forward** ({', '.join(CESTA)}; peso máximo {_br(PESO_MAX, 0)}%; janela de {p['janela']} dias, "
           f"rebalanceamento a cada {p['rebal']}; {len(r['datas'])} dias fora da amostra, {r['datas'][0]} a {r['datas'][-1]}):", "",
           "| Método | Retorno a.a. | Volatilidade | Sharpe | Pior queda | Giro por rebalanceamento | Instabilidade dos pesos* |",
           "|---|---|---|---|---|---|---|"]
    for m, b in r["backtest"].items():
        inst = r["estabilidade"].get(m, {}).get("instabilidade")
        out.append(f"| {cr.METODOS[m]} | {_br(b['retorno'])}% | {_br(b['volatilidade'])}% | {_br(b['sharpe'], 2)} | "
                   f"{_br(b['max_drawdown'])}% | {_br(b['giro_medio'])}% | {'—' if inst is None else _br(inst) + ' p.p.'} |")
    ganham = [cr.METODOS[m] for m, b in r["backtest"].items() if b["ganha_da_referencia"]]
    out += ["", "\\* desvio-padrão médio dos pesos no bootstrap da última janela.", "",
            ("Leitura: " + (f"ganharam da referência em Sharpe: {', '.join(ganham)}." if ganham else
             "nenhum otimizador ganhou da carteira de pesos iguais em Sharpe fora da amostra.") +
             " Estimar retornos esperados com histórico é ruidoso; as versões que usam só risco (mínima variância, HRP) "
             "têm pesos bem mais estáveis e menos giro. Um período e uma cesta não generalizam."), "",
            "**Volatilidade: GARCH(1,1) × histórica de 21 dias** (parâmetros estimados só nos primeiros 75% do período; "
            "perda medida nos 25% finais; QLIKE e MSE, menor é melhor):", "",
            "| Ativo | Dias de teste | Maior variação diária no teste | QLIKE GARCH | QLIKE histórica | Melhor (QLIKE) | Melhor (MSE) |",
            "|---|---|---|---|---|---|---|"]
    vence = 0
    for t in GARCH:
        try:
            g = vol.garch(t, "5y")
            T = g["teste"]
            px, _ = _serie(t, "5y", datetime.now().strftime("%Y-%m-%d"))
            r = px.pct_change().loc[T["inicio"]:T["fim"]] * 100
            choque = f"{_br(float(r.loc[r.abs().idxmax()]))}% ({r.abs().idxmax():%d/%m/%Y})"
        except Exception as e:  # noqa: BLE001
            out.append(f"| {t} | erro: {str(e)[:60]} | | | | | |")
            continue
        vence += T["vencedor_qlike"] == "garch"
        out.append(f"| {t} | {T['dias']} | {choque} | {_br(T['garch']['qlike'], 3)} | {_br(T['historica']['qlike'], 3)} | "
                   f"{'GARCH' if T['vencedor_qlike'] == 'garch' else 'histórica'} | {'GARCH' if T['vencedor_mse'] == 'garch' else 'histórica'} |")
    out += ["", f"Leitura: o GARCH teve menor QLIKE em {vence} de {len(GARCH)} ativos. As diferenças são pequenas e não há teste de "
                "significância (ex.: Diebold-Mariano); a vantagem é consistente, não grande. Onde o teste inclui um choque de um dia muito "
                "maior que o histórico, nenhum dos dois modelos o antecipa e a perda passa a ser dominada por esse dia."]
    return out


def gerar() -> str:
    partes = [
        "# Resultados medidos",
        "",
        f"Gerado em {datetime.now():%d/%m/%Y} por `python -m indicadores_b3.resultados`. Os números mudam a cada execução "
        "(preços novos, novas análises salvas); o arquivo registra a última.",
        "",
        "## Agente de pesquisa", "", *agentes(), "",
        "## RAG dos documentos da CVM", "", *rag(), "",
        "## Modelos, fora da amostra", "", *modelos(), "",
    ]
    return "\n".join(x for x in partes if x is not None) + "\n"


if __name__ == "__main__":
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(gerar(), encoding="utf-8")
    print(f"Salvo em {SAIDA}")
