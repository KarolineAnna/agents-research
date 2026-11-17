"""Conferência de ponta a ponta com dados reais: ``python -m indicadores_b3.conferir`` (ou ``conferir.bat``).

Roda cada fonte e cada função do site com dados de verdade (CVM, B3, Tesouro, Banco Central, yfinance) e mostra
uma lista de "funcionou / falhou e por quê". O resultado fica salvo em data/conferencia.txt e data/conferencia.json.
Opções: --ia também testa a IA configurada (gasta algumas chamadas do limite gratuito); --rapido pula os testes lentos.
Na primeira vez demora (baixa arquivos da CVM); depois usa o cache.
"""
from __future__ import annotations

import json
import platform
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as Esgotado
from datetime import datetime

from indicadores_b3 import config

LIMITE_S = 240  # tempo máximo de cada verificação
ACAO, BANCO = "WEGE3", "ITUB4"
CARTEIRA = {"PETR4": 30, "WEGE3": 25, "ITUB4": 25, "RENDA FIXA (CDI)": 20}


def _br(v, casas=2):
    return "n/d" if v is None else f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- verificações: cada uma devolve um texto curto com o que viu; erro = falhou ----------
def v_ambiente():
    import importlib.metadata as md
    faltam = []
    for p in ("pandas", "numpy", "scipy", "sklearn", "yfinance", "fastapi", "uvicorn", "requests", "pypdf", "pdfplumber", "arch"):
        try:
            __import__(p)
        except ImportError:
            faltam.append(p)
    if faltam:
        raise RuntimeError(f"bibliotecas faltando: {', '.join(faltam)}. Rode: python -m pip install -e .")
    return f"Python {platform.python_version()} · yfinance {md.version('yfinance')} · dados em {config.DATA_DIR}"


def v_cvm():
    from indicadores_b3.data import fundamentos as f
    m = f.mapa_tickers()
    if len(m) < 300:
        raise RuntimeError(f"cadastro da CVM com só {len(m)} tickers")
    return f"{len(m)} tickers no cadastro (FCA)"


def v_yfinance():
    from indicadores_b3.data.fontes import historico_yf
    s, ib = historico_yf(f"{ACAO}.SA", "1mo"), historico_yf("^BVSP", "1mo")
    if s.empty or ib.empty:
        raise RuntimeError("o yfinance não devolveu preços (pode ser bloqueio temporário do Yahoo)")
    return f"{ACAO} R$ {_br(float(s.iloc[-1]))} e Ibovespa {_br(float(ib.iloc[-1]), 0)} em {s.index[-1]:%d/%m/%Y}"


def v_bcb():
    from indicadores_b3.data.fontes import cdi_atual
    c = cdi_atual()
    return f"CDI {_br(c['valor'])}% a.a. em {c['componentes'][0]['data_ref']}"


def v_tesouro_precos():
    from indicadores_b3.analytics import rendafixa
    t = rendafixa.titulos()
    return f"{len(t['titulos'])} títulos, data base {t['data_base']}"


def v_tesouro_venda():
    from indicadores_b3.data import tesouro
    v = tesouro.a_venda()
    if not v["ok"]:
        raise RuntimeError(f"não baixou as vendas do Tesouro Direto: {v.get('erro')}")
    return f"{len(v['codigos'])} títulos à venda (vendas até {v['ate']})"


def v_mercado_eua():
    from indicadores_b3.analytics import dcf
    m = dcf.dados_ke_mercado()
    usados = [k for k, x in m.items() if isinstance(x, dict) and not x.get("premissa")]
    padrao = [k for k, x in m.items() if isinstance(x, dict) and x.get("premissa")]
    txt = f"da fonte: {', '.join(usados) or 'nenhum'}"
    if padrao:
        txt += f" · no valor padrão (fonte não respondeu): {', '.join(padrao)}"
    return txt


def v_indicadores():
    from indicadores_b3.analytics.indicadores import calcular
    out = []
    for t in (ACAO, BANCO):
        r = calcular(t)
        v = {i["id"]: i["valor"] for i in r["indicadores"]}
        if v.get("pl") is None or v.get("pvp") is None:
            raise RuntimeError(f"{t}: P/L ou P/VP não calculado")
        out.append(f"{t} P/L {_br(v['pl'])}x P/VP {_br(v['pvp'])}x (balanço {r['balanco_ref']})")
    return " · ".join(out)


def v_grafico():
    from indicadores_b3.analytics import historico_preco
    r = historico_preco.historico(ACAO, "5y")
    s = r["estatisticas"]
    if len(r["datas"]) < 200:
        raise RuntimeError(f"só {len(r['datas'])} pontos em 5 anos")
    return (f"{len(r['datas'])} pontos · retorno com proventos {_br(s['retorno_total'], 1)}% · Ibovespa {_br(s.get('ibov_retorno'), 1)}% · "
            f"{len(r['proventos'])} proventos")


def v_cara_barata():
    from indicadores_b3.analytics import valuation_rapido
    out = []
    for t in (ACAO, BANCO):
        r = valuation_rapido.avaliar(t)
        lidas = [x["id"] for x in r["lentes"] if x["leitura"]]
        out.append(f"{t}: {r['veredito'] or 'sem leitura'} ({len(lidas)} de 3 lentes; {len(r['historico'])} fins de ano; "
                   f"{len([p for p in r['pares']['pares'] if not p.get('erro')])} pares)")
        if len(lidas) < 2:
            raise RuntimeError("; ".join(out) + " · menos de 2 lentes com dados")
    return " · ".join(out)


def v_dcf():
    from indicadores_b3.analytics import dcf, valuation_rapido
    d = dcf.dados_dcf(ACAO)
    cr = d.get("crescimento_receita") or {}
    pj = valuation_rapido.preco_justo_dcf(d)
    return (f"FCL 12m R$ {_br(d['rastreio']['fcl']['valor'] / 1e9, 1)} bi · preço justo padrão R$ {_br(pj.get('valor'))} · "
            f"Monte Carlo: desvio do crescimento {'de ' + _br(cr.get('desvio'), 1) + ' pontos (' + str(cr.get('n')) + ' anos)' if cr.get('desvio') else 'sem histórico, usa 3 pontos'}")


def v_carteira():
    from indicadores_b3.portfolio import montar
    r = montar.montar(list(k for k in CARTEIRA if not k.startswith("RENDA")), "3y", modelo="blocos", bootstrap=False)
    m = r["metricas"]
    return f"retorno esperado {_br(m['retorno'], 1)}% · volatilidade {_br(m['volatilidade'], 1)}% · {len(r['alocacao'])} posições"


def v_agente_carteira():
    from indicadores_b3.agents import carteira_agente
    r = carteira_agente.rodar(CARTEIRA, "3y", usar_ia=False)
    lab = r["laboratorio"]
    if not lab["testes"] or not lab["confirmacao"]:
        raise RuntimeError("o laboratório não testou nem confirmou nenhuma hipótese")
    st = ", ".join(f"teste {c['numero']} {c['status']}" for c in lab["confirmacao"])
    return f"{len(lab['testes'])} hipóteses · confirmação: {st}"


def v_research():
    from indicadores_b3.agents import orquestrador
    r = orquestrador.rodar(BANCO, usar_ia=False, salvar=False)
    pot = next((x["valor"] for x in (r.get("investment") or {}).get("itens", []) if x["nome"] == "Potencial ponderado"), None)
    if "—" in r["markdown"] or "–" in r["markdown"]:
        raise RuntimeError("o relatório tem travessão")
    return f"relatório de {len(r['markdown'])} caracteres · potencial ponderado {_br(pot, 1)}%"


def v_saude():
    from indicadores_b3.ml import modelos
    from indicadores_b3.quality import checagens
    s = checagens.rodar(online=False)
    a = modelos.anomalias(ACAO)
    return f"checagens: {s['resumo']} · anomalias {ACAO}: {a.get('n_empresas')} companhias comparadas"


def v_acertos():
    from indicadores_b3.quality import acertos
    p = acertos.painel()
    return f"{p['total_registros']} conclusões registradas ({p['contadas']} contadas)"


def v_documentos():
    from indicadores_b3.rag import armazem
    docs = armazem.documentos()
    return f"{len(docs)} documentos indexados"


def v_relatorios_ri():
    from indicadores_b3.rag import armazem, coleta
    r = coleta.indexar_ri(BANCO, 1)
    if not r["documentos"]:
        raise RuntimeError(f"nenhum relatório de RI baixado: {r['falhas'][:1]}")
    d = r["documentos"][0]
    hits = armazem.buscar("índice de Basileia", k=3, ticker=BANCO, doc_id=d["id"], modo="bm25")
    tab = [h for h in hits if h["texto"].startswith("Tabela ·")]
    return (f"{d.get('tipo')}: {d.get('assunto')} ({d.get('data_entrega')}, {d.get('paginas')} páginas) · "
            f"busca 'índice de Basileia': {tab[0]['texto'][:120] if tab else 'nenhuma linha de tabela (confira o PDF)'}")


def v_ia():
    from indicadores_b3.agents import llm
    provs = llm.disponiveis()
    if not provs:
        raise RuntimeError("nenhuma IA configurada (Research → Configurar IA gratuita)")
    p, m = provs[0]
    r = llm.conversar(p, m, [{"role": "user", "content": "Responda só: ok"}], [])
    return f"{p} · {m} respondeu: {(r.get('content') or '').strip()[:30]!r} · reservas: {', '.join(f'{a}:{b}' for a, b in provs[1:]) or 'nenhuma'}"


VERIFICACOES = [
    ("Ambiente", v_ambiente, False), ("CVM: cadastro", v_cvm, False), ("yfinance: preços", v_yfinance, False),
    ("Banco Central: CDI", v_bcb, False), ("Tesouro: preços", v_tesouro_precos, False), ("Tesouro: títulos à venda", v_tesouro_venda, False),
    ("Juros e inflação EUA, risco-país", v_mercado_eua, False), ("Indicadores (empresa e banco)", v_indicadores, False),
    ("Gráfico de preço", v_grafico, False), ("Cara ou barata", v_cara_barata, True), ("DCF e Monte Carlo", v_dcf, False),
    ("Carteira eficiente", v_carteira, True), ("Agente de carteira (sem IA)", v_agente_carteira, True),
    ("Research (regras fixas)", v_research, True), ("Saúde dos dados", v_saude, True), ("Histórico de acertos", v_acertos, False),
    ("Documentos (RAG)", v_documentos, False), ("Relatórios de RI (tabelas)", v_relatorios_ri, True),
]


def rodar(ia: bool = False, rapido: bool = False) -> list[dict]:
    lista = VERIFICACOES + ([("IA gratuita", v_ia, False)] if ia else [])
    out = []
    with ThreadPoolExecutor(max_workers=1) as ex:
        for nome, f, lento in lista:
            if rapido and lento:
                out.append({"nome": nome, "ok": None, "detalhe": "pulado (--rapido)", "s": 0})
                continue
            print(f"… {nome}", end="", flush=True)
            t0 = time.time()
            fut = ex.submit(f)
            try:
                det, ok = fut.result(timeout=LIMITE_S), True
            except Esgotado:
                det, ok = f"passou de {LIMITE_S} s sem terminar", False
            except Exception as e:  # noqa: BLE001
                det, ok = f"{type(e).__name__}: {e}"[:400], False
                det += " | " + traceback.format_exc().strip().splitlines()[-3].strip()[:200]
            s = round(time.time() - t0, 1)
            out.append({"nome": nome, "ok": ok, "detalhe": det, "s": s})
            print(f"\r{'OK  ' if ok else 'ERRO'} {nome} ({s} s): {det}")
    return out


def main() -> None:
    args = set(sys.argv[1:])
    config.garantir_pastas()
    print(f"Conferência do Indicadores B3 · {datetime.now():%d/%m/%Y %H:%M}\n")
    res = rodar(ia="--ia" in args, rapido="--rapido" in args)
    ok = sum(1 for r in res if r["ok"]), sum(1 for r in res if r["ok"] is False)
    linhas = [f"{'OK  ' if r['ok'] else 'ERRO' if r['ok'] is False else '--  '} {r['nome']} ({r['s']} s): {r['detalhe']}" for r in res]
    resumo = f"\n{ok[0]} funcionaram, {ok[1]} falharam."
    txt = f"Conferência · {datetime.now():%Y-%m-%d %H:%M} · {platform.platform()}\n" + "\n".join(linhas) + resumo + "\n"
    (config.DATA_DIR / "conferencia.txt").write_text(txt, encoding="utf-8")
    (config.DATA_DIR / "conferencia.json").write_text(json.dumps({"quando": datetime.now().isoformat(), "resultados": res},
                                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(resumo)
    print(f"Resultado salvo em {config.DATA_DIR / 'conferencia.txt'}")


if __name__ == "__main__":
    main()
