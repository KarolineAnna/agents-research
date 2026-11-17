"""Servidor local: API + site estático.

Rodar:  python -m indicadores_b3   →   http://127.0.0.1:8080
"""
import logging
import math
import re
import time

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from indicadores_b3 import __version__, config
from indicadores_b3.agents import llm, orquestrador, redator, relatorio
from indicadores_b3.analytics import dcf, demonstracoes, historico_preco, rendafixa, valuation_rapido
from indicadores_b3.analytics.indicadores import calcular, catalogo_json
from indicadores_b3.data import comunicados, futuros, lista, opcoes, setores
from indicadores_b3.data.fontes import cdi_atual
from indicadores_b3.ml import modelos
from indicadores_b3.portfolio import montar
from indicadores_b3.portfolio.carteira import carteira
from indicadores_b3.quality import acertos, checagens
from indicadores_b3.rag import armazem, avaliacao, coleta
from indicadores_b3.rag.agente import AgenteDocumentos

log = logging.getLogger(__name__)
app = FastAPI(title="Indicadores B3", version=__version__,
              description="API local do site: indicadores, balanços, valuation, carteiras, modelos e agentes de pesquisa.")


@app.middleware("http")
async def sem_cache_no_site(request, call_next):
    """HTML/CSS/JS sempre revalidados: depois de atualizar o projeto, o navegador não mistura arquivo novo com antigo."""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/api/versao")
def versao():
    return {"versao": __version__}
_cache: dict[str, tuple[float, dict]] = {}
TTL = 900  # 15 min: o preço muda durante o pregão; os balanços já ficam em cache de disco


def limpar(o):
    """NaN/inf não existem em JSON."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: limpar(v) for k, v in o.items()}
    if isinstance(o, list):
        return [limpar(v) for v in o]
    return o


@app.get("/api/catalogo")
def catalogo():
    return catalogo_json()


@app.get("/api/empresa/{ticker}")
def empresa(ticker: str):
    ticker = ticker.strip().upper()
    hit = _cache.get(ticker)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        dados = limpar(calcular(ticker))
    except (LookupError, ValueError, KeyError) as e:
        raise HTTPException(404, str(e)) from e
    _cache[ticker] = (time.time(), dados)
    return dados


@app.get("/api/carteira")
def api_carteira(tickers: str, periodo: str = "3y", rf: float | None = None, peso_max: float = 100.0,
                 horizonte: float = 2.0, isencao: bool = False, modelo: str = "historico",
                 mercado: float | None = None):
    try:
        return limpar(carteira(tickers.split(","), periodo, rf, peso_max, horizonte, isencao, modelo, mercado))
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/carteira/diagnostico")
def api_carteira_diagnostico(p: dict = Body(...)):
    """p: {pesos: {ticker: %}, periodo: "3y", ia: bool}. A renda fixa entra como "RENDA FIXA (CDI)"."""
    from indicadores_b3.agents import carteira_agente
    try:
        r = carteira_agente.rodar(p.get("pesos") or {}, p.get("periodo", "3y"), bool(p.get("ia", True)))
    except (ValueError, LookupError, KeyError, llm.ErroProvedor) as e:
        raise HTTPException(400, str(e)) from e
    _registrar(acertos.registrar_carteira, r)
    return limpar(r)


@app.post("/api/carteira/montar")
def api_carteira_montar(p: dict = Body(...)):
    try:
        return limpar(montar.montar(
            p.get("tickers", []), p.get("periodo", "3y"), p.get("rf"), p.get("modelo", "historico"), p.get("mercado"),
            p.get("cov", "ledoit"), p.get("objetivo", "max_sharpe"), p.get("alvo"), p.get("limites") or {},
            bool(p.get("com_rf", True)), float(p.get("rf_min", 0)), float(p.get("rf_max", 100)),
            float(p.get("valor", 10000)), bool(p.get("bootstrap", True)),
            p.get("globais"), p.get("sobrescritas"), p.get("visoes")))
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/carteira/premissas")
def api_carteira_premissas(p: dict = Body(...)):
    try:
        return limpar(montar.calcular_premissas(p.get("tickers", []), p.get("periodo", "3y"),
                                                p.get("globais"), p.get("sobrescritas")))
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/cdi")
def api_cdi():
    try:
        return limpar(cdi_atual())
    except Exception as e:
        raise HTTPException(502, f"Não consegui consultar o Banco Central: {e}") from e


@app.get("/api/lista/{classe}")
def api_lista(classe: str):
    try:
        return limpar(lista.listar(classe))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/preco/{ticker}")
def api_preco(ticker: str, periodo: str = "5y"):
    try:
        return limpar(historico_preco.historico(ticker, periodo))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/valuation/{ticker}")
def api_valuation(ticker: str):
    try:
        r = valuation_rapido.avaliar(ticker)
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e
    _registrar(acertos.registrar_valuation, r)
    return limpar(r)


def _registrar(func, r):
    """Guarda a conclusão para o Histórico de acertos; falha aqui nunca derruba a resposta."""
    try:
        func(r)
    except Exception:  # noqa: BLE001
        log.exception("não consegui registrar a previsão")


@app.get("/api/acertos")
def api_acertos():
    return limpar(acertos.painel())


@app.get("/api/dcf/{ticker}")
def api_dcf(ticker: str):
    try:
        return limpar(dcf.dados_dcf(ticker))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/demonstracoes/{ticker}")
def api_demonstracoes(ticker: str):
    try:
        return limpar(demonstracoes.demonstracoes(ticker))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/opcoes/{ticker}")
def api_opcoes(ticker: str):
    try:
        return limpar(opcoes.grade(ticker))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/futuros")
def api_futuros():
    return limpar(futuros.dados(int(time.time() // 3600)))


@app.get("/api/modelos/carteira")
def api_modelos_carteira(tickers: str, periodo: str = "5y", peso_max: float = 100.0, janela: int = 252, rebal: int = 21):
    try:
        return limpar(modelos.carteira_robusta(tickers.split(","), periodo, peso_max, janela, rebal))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/modelos/garch/{ticker}")
def api_modelos_garch(ticker: str, periodo: str = "5y"):
    try:
        return limpar(modelos.garch(ticker, periodo))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/saude/empresa/{ticker}")
def api_saude_empresa(ticker: str):
    """Checagens determinísticas dos indicadores de uma empresa (faixas plausíveis, divergência com o yfinance, balanço velho)."""
    from indicadores_b3.quality.qualidade import checar
    try:
        r = calcular(ticker)
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e
    return limpar({"ticker": r["ticker"], "empresa": r.get("empresa"), "problemas": checar(r)})


@app.post("/api/saude/agente/{ticker}")
def api_saude_agente(ticker: str):
    """Agente de qualidade: investiga cada problema e classifica em dado real, erro da fonte ou erro de cálculo."""
    from indicadores_b3.agents import qualidade
    try:
        return limpar(qualidade.investigar(ticker.strip().upper()))
    except (ValueError, LookupError, KeyError, llm.ErroProvedor) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/saude/anomalias/{ticker}")
def api_saude_anomalias(ticker: str):
    try:
        return limpar(modelos.anomalias(ticker))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/rendafixa")
def api_rendafixa():
    try:
        return limpar(rendafixa.dados())
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/saude")
def api_saude(online: bool = False):
    return limpar(checagens.rodar(online=online))


@app.get("/api/rendafixa/simular/{codigo}")
def api_rendafixa_simular(codigo: str, valor: float = 1000.0, venda: str | None = None, taxa_saida: float | None = None,
                          ipca: float | None = None, selic: float | None = None, custodia: float = 0.20):
    try:
        return limpar(rendafixa.simular(codigo, valor, venda, taxa_saida, ipca, selic, custodia))
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/rendafixa/historico/{codigo}")
def api_rendafixa_hist(codigo: str):
    try:
        return limpar(rendafixa.historico(codigo))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/comunicados")
def api_comunicados(tickers: str, categorias: str = ""):
    try:
        cats = [c for c in categorias.split("|") if c] or None
        return limpar(comunicados.listar(tickers.split(","), cats))
    except (ValueError, LookupError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


# ---------------- Research (3 agentes) ----------------
@app.post("/api/research/{ticker}")
def api_research(ticker: str, p: dict = Body(default={})):
    """p: {agentes: [financial, market, investment], pares: [...], premissas: {...}, ia: bool}"""
    try:
        if p.get("modo") == "agente":
            r = orquestrador.rodar_agente(ticker, p.get("pares"))
        else:
            r = orquestrador.rodar(ticker, p.get("agentes") or orquestrador.AGENTES, p.get("pares"),
                                   p.get("premissas"), bool(p.get("ia", True)))
    except (ValueError, LookupError, KeyError, llm.ErroProvedor) as e:
        raise HTTPException(400, str(e)) from e
    _registrar(acertos.registrar_research, r)
    return limpar(r)


@app.get("/api/research-ia")
def api_research_ia():
    return llm.status()


@app.post("/api/research-ia")
def api_research_ia_salvar(p: dict = Body(...)):
    """p: {ordem: [...], chaves: {gemini: "...", groq: "..."}} — salvo em config_ia.json, só no seu computador."""
    llm.salvar_config(p.get("ordem"), p.get("chaves"), p.get("modelos"))
    return llm.status()


@app.get("/api/research-ia/testar")
def api_research_ia_testar():
    out = []
    for prov, modelo in llm.disponiveis():
        try:
            r = llm.conversar(prov, modelo, [{"role": "user", "content": "Responda só: ok"}], [], timeout=30)
            out.append({"provedor": prov, "modelo": modelo, "ok": True, "resposta": (r.get("content") or "")[:40]})
        except llm.ErroProvedor as e:
            out.append({"provedor": prov, "modelo": modelo, "ok": False, "resposta": str(e)[:200]})
    return {"resultados": out}


@app.get("/api/setor/{ticker}")
def api_setor(ticker: str, n: int = 4):
    """Setor do ticker e pares sugeridos (mesmo setor, mais negociados primeiro)."""
    return limpar({**setores.setor_de(ticker), "sugestao": setores.pares(ticker, n)})


# ---------------- Documentos (RAG dos comunicados da CVM) ----------------
@app.get("/api/docs")
def api_docs(ticker: str | None = None):
    return limpar({"documentos": armazem.documentos(ticker), "estatisticas": armazem.estatisticas()})


@app.post("/api/docs/indexar")
def api_docs_indexar(p: dict = Body(...)):
    """p: {tickers: [...], categorias: [...] | null, por_empresa: 10}. Baixa os PDFs da CVM e indexa."""
    tickers = [t.strip().upper() for t in p.get("tickers") or [] if t.strip()]
    if not tickers:
        raise HTTPException(400, "Informe pelo menos um ticker.")
    try:
        r = coleta.indexar(tickers, p.get("categorias") or None, int(p.get("por_empresa", 10)), embeddings=not p.get("ri"))
        if p.get("ri"):  # relatórios de resultados (MD&A, press-release, apresentação) com as tabelas linha a linha
            ri = [coleta.indexar_ri(t, 2, embeddings=False) for t in tickers]
            r["ri"] = {"documentos": [d for x in ri for d in x["documentos"]], "falhas": [f for x in ri for f in x["falhas"]]}
            r["embeddings"] = armazem.garantir_embeddings()
        return limpar(r)
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/docs/{doc_id}/pagina/{n}")
def api_docs_pagina(doc_id: int, n: int):
    t = armazem.pagina(doc_id, n)
    if t is None:
        raise HTTPException(404, "Página não encontrada.")
    return {"doc_id": doc_id, "pagina": n, "texto": t}


@app.post("/api/docs/perguntar")
def api_docs_perguntar(p: dict = Body(...)):
    if not (p.get("pergunta") or "").strip():
        raise HTTPException(400, "Escreva a pergunta.")
    try:
        return limpar(AgenteDocumentos(p.get("ticker") or None).perguntar(p["pergunta"].strip()))
    except llm.ErroProvedor as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/docs/avaliacoes")
def api_docs_avaliacoes():
    return limpar({"execucoes": avaliacao.execucoes(), "arquivo_perguntas": str(avaliacao.PERGUNTAS),
                   "perguntas": len(avaliacao.carregar_perguntas())})


@app.post("/api/docs/avaliar/{tipo}")
def api_docs_avaliar(tipo: str, p: dict = Body(default={})):
    try:
        if tipo == "busca":
            return limpar(avaliacao.avaliar_busca(int(p.get("n", 40)), usar_ia=bool(p.get("usar_ia", True))))
        if tipo == "respostas":
            return limpar(avaliacao.avaliar_respostas(p.get("provedor") or None, p.get("limite")))
    except (ValueError, llm.ErroProvedor) as e:
        raise HTTPException(400, str(e)) from e
    raise HTTPException(404, "Use busca ou respostas.")


@app.get("/api/research")
def api_research_lista():
    return {"relatorios": orquestrador.listar(), "ia": redator.ollama_disponivel()}


@app.delete("/api/research/relatorio/{rid}")
def api_research_excluir(rid: str):
    if not orquestrador.excluir(rid):
        raise HTTPException(404, "Relatório não encontrado.")
    return {"ok": True}


@app.post("/api/research/relatorios/limpar")  # dois segmentos: não colide com POST /api/research/{ticker}
def api_research_limpar(p: dict = Body(default={})):
    """Mantém só os N relatórios mais recentes de cada empresa (padrão: 1)."""
    return {"apagados": orquestrador.limpar_antigos(p.get("manter", 1))}


@app.get("/api/research/relatorio/{rid}.md", response_class=PlainTextResponse)
def api_research_md(rid: str):
    r = orquestrador.carregar(rid)
    if not r:
        raise HTTPException(404, "Relatório não encontrado.")
    return PlainTextResponse(r["markdown"], headers={"Content-Disposition": f'attachment; filename="{rid}.md"'})


@app.get("/api/research/relatorio/{rid}.html", response_class=HTMLResponse)
def api_research_html(rid: str):
    r = orquestrador.carregar(rid)
    if not r:
        raise HTTPException(404, "Relatório não encontrado.")
    return relatorio.para_html(r["markdown"], f"Research {r['ticker']}")


@app.get("/api/research/relatorio/{rid}")
def api_research_carregar(rid: str):
    r = orquestrador.carregar(rid)
    if not r:
        raise HTTPException(404, "Relatório não encontrado.")
    return limpar(r)


# ---------- Abas privadas (pasta extras/, fora do GitHub) ----------
EXTRAS_DIR = config.STATIC_DIR.parents[1] / "extras"
TEM_EXTRAS = (EXTRAS_DIR / "rotas.py").exists()
if TEM_EXTRAS:
    from indicadores_b3.extras.rotas import rotas as _rotas_extras
    app.include_router(_rotas_extras)
    app.mount("/extras", StaticFiles(directory=EXTRAS_DIR / "static"), name="extras")


def _blocos_extras() -> dict[str, str]:
    if not TEM_EXTRAS:
        return {}
    txt = (EXTRAS_DIR / "static" / "abas.html").read_text(encoding="utf-8")
    return dict(re.findall(r"<!--bloco:([\w-]+)-->\n(.*?)<!--/bloco-->", txt, re.S))


def _versao_estaticos() -> str:
    """Muda sempre que um CSS/JS muda: o navegador é obrigado a baixar a versão nova (sem Ctrl+F5)."""
    pastas = [config.STATIC_DIR] + ([EXTRAS_DIR / "static"] if TEM_EXTRAS else [])
    return str(int(max(f.stat().st_mtime for d in pastas for f in d.iterdir() if f.suffix in (".js", ".css", ".html"))))


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def pagina_inicial():
    v = _versao_estaticos()
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    blocos = _blocos_extras()
    html = re.sub(r"<!--extras:([\w-]+)-->\n?", lambda m: blocos.get(m.group(1), ""), html)
    html = re.sub(r'(href|src)="([\w./-]+\.(?:css|js))"', lambda m: f'{m.group(1)}="{m.group(2)}?v={v}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORTA)
