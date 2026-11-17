"""Avaliação (evals) do RAG: mede a busca e as respostas com números, para comparar versões e provedores.

1. Busca (sem rótulo manual): sorteia trechos do índice e cria, para cada um, uma pergunta que só ele responde.
   - com IA: o modelo escreve a pergunta com outras palavras (testa se a busca entende significado);
   - sem IA: a consulta são as palavras mais raras do trecho (teste mais fácil, só para referência).
   Métricas: recall@1/3/5 (o trecho certo — ou outro da mesma página — veio entre os k primeiros) e MRR
   (média de 1/posição), para BM25, semântica e híbrida.
2. Respostas: perguntas escritas por você em data/evals/perguntas.jsonl, uma por linha:
     {"id": "itub-jcp", "ticker": "ITUB4", "pergunta": "...", "deve_conter": ["JCP"], "sem_resposta": false}
   Métricas: respostas aprovadas pelo validador, aprovadas na 1ª tentativa, rascunhos barrados (alucinação
   pega pelo validador), resposta contém o esperado, recusa correta (perguntas sem resposta), tempo e tokens.
Cada execução fica salva em data/evals/execucoes/ para o histórico e a comparação.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from datetime import datetime

from indicadores_b3 import config
from indicadores_b3.agents import llm
from indicadores_b3.rag import armazem
from indicadores_b3.rag.agente import NAO_ACHOU, AgenteDocumentos

PASTA = config.DATA_DIR / "evals"
EXECUCOES = PASTA / "execucoes"
PERGUNTAS = PASTA / "perguntas.jsonl"
CACHE_SINT = PASTA / "perguntas_sinteticas.json"
EXEMPLO = [
    {"id": "trap-futuro", "ticker": None, "pergunta": "Qual será o lucro da empresa em 2035, segundo os comunicados?",
     "deve_conter": [], "sem_resposta": True},
    {"id": "geral-dividendos", "ticker": None, "pergunta": "Algum comunicado fala de dividendos ou juros sobre capital próprio? Quais valores e datas?",
     "deve_conter": [], "sem_resposta": False},
    {"id": "geral-recompra", "ticker": None, "pergunta": "Existe programa de recompra de ações? Quantas ações e qual o prazo?",
     "deve_conter": [], "sem_resposta": False},
]

PROMPT_PERGUNTA = """Leia o trecho de um comunicado de empresa e escreva UMA pergunta, em português, que este trecho responde.
Regras: não copie frases do trecho, use outras palavras; a pergunta deve fazer sentido sozinha (cite a empresa ou o assunto);
responda só com a pergunta.

TRECHO:
{t}"""


def _salvar(res: dict) -> dict:
    EXECUCOES.mkdir(parents=True, exist_ok=True)
    res["id"] = f"{res['tipo']}_{datetime.now():%Y%m%d_%H%M%S}"
    (EXECUCOES / f"{res['id']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return res


def execucoes() -> list[dict]:
    if not EXECUCOES.exists():
        return []
    out = []
    for p in sorted(EXECUCOES.glob("*.json"), reverse=True)[:50]:
        r = json.loads(p.read_text(encoding="utf-8"))
        r.pop("detalhes", None)
        out.append(r)
    return out


# ---------------- 1. busca ----------------
def _consulta_palavras(texto: str, idf: dict, n: int = 6, rng=None) -> str:
    ts = list(dict.fromkeys(armazem.tokens(texto)))
    ts.sort(key=lambda w: -idf.get(w, 0))
    escolhidas = ts[:n]
    (rng or random).shuffle(escolhidas)
    return " ".join(escolhidas)


def _perguntas_ia(amostra: list[dict], prov: tuple[str, str]) -> dict[str, str]:
    cache = json.loads(CACHE_SINT.read_text(encoding="utf-8")) if CACHE_SINT.exists() else {}
    for t in amostra:
        h = hashlib.sha1(t["texto"].encode()).hexdigest()
        if h in cache:
            continue
        msg = llm.conversar(prov[0], prov[1], [{"role": "user", "content": PROMPT_PERGUNTA.format(t=t["texto"][:1500])}], [])
        cache[h] = (msg.get("content") or "").strip().split("\n")[0][:300]
    PASTA.mkdir(parents=True, exist_ok=True)
    CACHE_SINT.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return {t["texto"]: cache[hashlib.sha1(t["texto"].encode()).hexdigest()] for t in amostra}


def avaliar_busca(n: int = 40, k: int = 5, usar_ia: bool = True, seed: int = 42, db=None) -> dict:
    ts = [t for t in armazem.trechos(db) if len(t["texto"]) > 120]
    if len(ts) < 3:
        raise ValueError("Poucos trechos indexados para avaliar. Indexe alguns documentos primeiro.")
    rng = random.Random(seed)
    amostra = rng.sample(ts, min(n, len(ts)))
    idx, _ = armazem._indice_bm25(str(db) if db else "padrao")
    total = len(idx.docs)
    idf = {w: math.log(1 + (total - d + 0.5) / (d + 0.5)) for w, d in idx.df.items()}

    geracao, perguntas = "palavras-chave (sem IA)", None
    provs = llm.disponiveis() if usar_ia else []
    if provs:
        try:
            perguntas = _perguntas_ia(amostra, provs[0])
            geracao = f"IA: {provs[0][0]} · {provs[0][1]}"
        except llm.ErroProvedor as e:
            geracao = f"palavras-chave (IA indisponível: {e})"
    consultas = [perguntas[t["texto"]] if perguntas else _consulta_palavras(t["texto"], idf, rng=rng) for t in amostra]

    emb = llm.provedor_embedding()
    vetores, modelo = None, None
    if emb:
        armazem.garantir_embeddings(emb, db)
        try:
            vetores = llm.embeddings(emb[0], emb[1], consultas)
            modelo = f"{emb[0]}:{emb[1]}"
        except llm.ErroProvedor:
            vetores = None
    modos = ["bm25"] + (["semantico", "hibrido"] if vetores else [])
    met = {m: {"acertos": {1: 0, 3: 0, k: 0}, "rr": 0.0} for m in modos}
    detalhes = []
    for i, (t, q) in enumerate(zip(amostra, consultas, strict=True)):
        linha = {"pergunta": q, "esperado": f"[D{t['doc_id']} p{t['pagina']}]", "posicoes": {}}
        for m in modos:
            rs = armazem.buscar(q, k=10, modo=m, vetor_consulta=vetores[i] if vetores else None, modelo_emb=modelo, db=db)
            pos = next((j + 1 for j, r in enumerate(rs) if r["id"] == t["id"] or (r["doc_id"], r["pagina"]) == (t["doc_id"], t["pagina"])), None)
            linha["posicoes"][m] = pos
            if pos:
                met[m]["rr"] += 1 / pos
                for kk in met[m]["acertos"]:
                    met[m]["acertos"][kk] += pos <= kk
        detalhes.append(linha)
    nq = len(amostra)
    resumo = {m: {**{f"recall@{kk}": round(v / nq * 100, 1) for kk, v in d["acertos"].items()}, "mrr": round(d["rr"] / nq, 3)}
              for m, d in met.items()}
    return _salvar({"tipo": "busca", "quando": datetime.now().strftime("%Y-%m-%d %H:%M"), "n": nq, "k": k, "geracao": geracao,
                    "embeddings": modelo, "modos": resumo, "detalhes": detalhes,
                    "falhas": [d for d in detalhes if not d["posicoes"].get(modos[-1])][:10],
                    "trechos_no_indice": total})


# ---------------- 2. respostas ----------------
def carregar_perguntas() -> list[dict]:
    if not PERGUNTAS.exists():
        PASTA.mkdir(parents=True, exist_ok=True)
        PERGUNTAS.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in EXEMPLO) + "\n", encoding="utf-8")
    out = []
    for n, linha in enumerate(PERGUNTAS.read_text(encoding="utf-8").splitlines(), start=1):
        if linha.strip() and not linha.lstrip().startswith("//"):
            try:
                out.append(json.loads(linha))
            except ValueError as e:
                raise ValueError(f"perguntas.jsonl, linha {n}: JSON inválido ({e})") from e
    return out


def avaliar_respostas(provedor: str | None = None, limite: int | None = None, db=None) -> dict:
    perguntas = carregar_perguntas()[:limite]
    provs = [p for p in llm.disponiveis() if provedor in (None, p[0])]
    if not provs:
        raise ValueError(f"Provedor {provedor or 'de IA'} não configurado.")
    detalhes, t0 = [], time.time()
    for q in perguntas:
        ini = time.time()
        try:
            r = AgenteDocumentos(q.get("ticker"), db).perguntar(q["pergunta"], provedores=provs if provedor else None)
        except llm.ErroProvedor as e:
            detalhes.append({"id": q.get("id"), "erro": str(e)})
            continue
        texto = r["texto"] or ""
        barrados = sum(1 for p in r["passos"] if p["tipo"] == "rascunho" and "problemas: nenhum" not in p["texto"])
        esperado = q.get("deve_conter") or []
        detalhes.append({
            "id": q.get("id"), "pergunta": q["pergunta"], "concluiu": r["texto"] is not None,
            "primeira": r["texto"] is not None and r["metricas"]["correcoes"] == 0, "rascunhos_barrados": barrados,
            "contem": (all(armazem.sem_acento(e.lower()) in armazem.sem_acento(texto.lower()) for e in esperado) if esperado else None),
            "recusa_correta": (bool(NAO_ACHOU.search(texto)) if q.get("sem_resposta") else None),
            "citacoes": len(r["citacoes"]), "segundos": round(time.time() - ini, 1), "tokens": r["metricas"]["tokens"],
            "provedores": r["provedores"], "resposta": texto[:1500]})
    ok = [d for d in detalhes if "erro" not in d]
    pct = lambda xs: round(sum(xs) / len(xs) * 100, 1) if xs else None  # noqa: E731
    resumo = {
        "perguntas": len(perguntas), "executadas": len(ok), "erros": len(detalhes) - len(ok),
        "aprovadas_pelo_validador_%": pct([d["concluiu"] for d in ok]),
        "aprovadas_na_1a_tentativa_%": pct([d["primeira"] for d in ok]),
        "rascunhos_barrados": sum(d["rascunhos_barrados"] for d in ok),
        "contem_esperado_%": pct([d["contem"] for d in ok if d["contem"] is not None]),
        "recusa_correta_%": pct([d["recusa_correta"] for d in ok if d["recusa_correta"] is not None]),
        "citacoes_por_resposta": round(sum(d["citacoes"] for d in ok) / len(ok), 2) if ok else None,
        "segundos_por_pergunta": round(sum(d["segundos"] for d in ok) / len(ok), 1) if ok else None,
        "tokens": sum(int(d["tokens"].get("prompt_tokens", 0)) + int(d["tokens"].get("completion_tokens", 0)) for d in ok),
    }
    usados = sorted({p for d in ok for p in d["provedores"]})
    return _salvar({"tipo": "respostas", "quando": datetime.now().strftime("%Y-%m-%d %H:%M"), "provedor": ", ".join(usados) or provedor,
                    "resumo": resumo, "detalhes": detalhes, "segundos_total": round(time.time() - t0, 1),
                    "arquivo": str(PERGUNTAS)})

