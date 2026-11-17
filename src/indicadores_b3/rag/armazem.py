"""Armazém do RAG: documentos, páginas e trechos em SQLite, com busca híbrida.

Busca híbrida = duas buscas independentes combinadas por Reciprocal Rank Fusion (RRF):
  - BM25 (palavras): ótimo para nomes, siglas e números ("JCP", "R$ 1,2 bilhão", "4.966");
  - embeddings (significado): acha "recompra de ações" quando o texto diz "aquisição de ações de própria emissão".
Sem provedor de embeddings configurado, a busca usa só o BM25 — e o painel de avaliação mostra a diferença.

Tabelas: documentos (metadados do IPE da CVM), paginas (texto de cada página), trechos (pedaços indexados)
e embeddings (vetores por trecho e por modelo, para não pagar/gastar cota duas vezes).
"""
from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from indicadores_b3 import config

DB = config.DATA_DIR / "documentos.db"
TAM_TRECHO = 900      # caracteres por trecho
SOBREPOSICAO = 150    # para uma frase cortada no meio aparecer inteira em algum trecho
RRF_K = 60            # constante usual do Reciprocal Rank Fusion

STOP = set("""a o e é de da do das dos em no na nos nas um uma uns umas por para com sem sob sobre entre até ao aos à às
que se não ou mas como mais menos muito muita seu sua seus suas ele ela eles elas isso isto esse essa este esta
foi foram ser será são está estão ter tem têm há pelo pela pelos pelas qual quais quando onde já também
companhia sociedade s.a sa""".split())

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY, protocolo TEXT UNIQUE, ticker TEXT, cnpj TEXT, empresa TEXT, data_entrega TEXT,
  data_referencia TEXT, categoria TEXT, tipo TEXT, especie TEXT, assunto TEXT, url TEXT, paginas INTEGER,
  sha256 TEXT, status TEXT, indexado_em TEXT DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS paginas (doc_id INTEGER, pagina INTEGER, texto TEXT, PRIMARY KEY (doc_id, pagina));
CREATE TABLE IF NOT EXISTS trechos (id INTEGER PRIMARY KEY, doc_id INTEGER, pagina INTEGER, ordem INTEGER, texto TEXT);
CREATE INDEX IF NOT EXISTS ix_trechos_doc ON trechos(doc_id);
CREATE TABLE IF NOT EXISTS embeddings (trecho_id INTEGER, modelo TEXT, vetor BLOB, PRIMARY KEY (trecho_id, modelo));
"""


def conectar(db=None) -> sqlite3.Connection:
    db = Path(db) if db else DB
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


# ---------------- texto ----------------
def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokens(texto: str) -> list[str]:
    t = sem_acento(texto.lower())
    return [w for w in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", t) if len(w) > 1 and w not in STOP]


def limpar_pagina(texto: str) -> str:
    texto = texto.replace("­", "").replace("\r", "\n")
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)  # hifenização no fim da linha
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def fatiar(texto: str, tam: int = TAM_TRECHO, sobra: int = SOBREPOSICAO) -> list[str]:
    """Divide em trechos de ~tam caracteres, preferindo cortar em fim de parágrafo/frase, com sobreposição."""
    texto = texto.strip()
    if len(texto) <= tam:
        return [texto] if texto else []
    out, ini = [], 0
    while ini < len(texto):
        fim = min(ini + tam, len(texto))
        if fim < len(texto):
            corte = max(texto.rfind("\n\n", ini + tam // 2, fim), texto.rfind(". ", ini + tam // 2, fim))
            if corte > ini:
                fim = corte + 1
        out.append(texto[ini:fim].strip())
        if fim >= len(texto):
            break
        ini = max(fim - sobra, ini + 1)
    return [t for t in out if t]


# ---------------- gravação ----------------
def salvar_documento(meta: dict, paginas: list[str], tabelas: list[list[str]] | None = None, db=None) -> int:
    """Grava (ou regrava) um documento com suas páginas e trechos. Devolve o id.
    tabelas[i]: trechos de tabela da página i (rag/tabelas.py). Viram trechos próprios e são anexados ao texto da página,
    para o validador conferir os números contra a mesma página que o agente citou."""
    with closing(conectar(db)) as con, con:
        cur = con.execute("SELECT id FROM documentos WHERE protocolo = ?", (meta["protocolo"],)).fetchone()
        if cur:
            doc_id = cur["id"]
            con.execute("DELETE FROM paginas WHERE doc_id = ?", (doc_id,))
            ids = [r[0] for r in con.execute("SELECT id FROM trechos WHERE doc_id = ?", (doc_id,))]
            con.executemany("DELETE FROM embeddings WHERE trecho_id = ?", [(i,) for i in ids])
            con.execute("DELETE FROM trechos WHERE doc_id = ?", (doc_id,))
        campos = ["protocolo", "ticker", "cnpj", "empresa", "data_entrega", "data_referencia", "categoria", "tipo",
                  "especie", "assunto", "url", "sha256", "status"]
        valores = [meta.get(c) for c in campos] + [len(paginas)]
        if cur:
            con.execute(f"UPDATE documentos SET {', '.join(c + ' = ?' for c in campos)}, paginas = ?, "
                        "indexado_em = datetime('now','localtime') WHERE id = ?", valores + [doc_id])
        else:
            doc_id = con.execute(f"INSERT INTO documentos ({', '.join(campos)}, paginas) VALUES ({', '.join('?' * (len(campos) + 1))})",
                                 valores).lastrowid
        for n, txt in enumerate(paginas, start=1):
            tabs = (tabelas[n - 1] if tabelas and n - 1 < len(tabelas) else []) or []
            completo = txt + ("\n\nTabelas desta página, linha a linha:\n" + "\n".join(tabs) if tabs else "")
            con.execute("INSERT INTO paginas VALUES (?, ?, ?)", (doc_id, n, completo))
            pedacos = fatiar(txt) + [f"Tabela · {t}" for t in tabs]
            for o, tr in enumerate(pedacos):
                con.execute("INSERT INTO trechos (doc_id, pagina, ordem, texto) VALUES (?, ?, ?, ?)", (doc_id, n, o, tr))
    _indice_bm25.cache_clear()
    return doc_id


def documentos(ticker: str | None = None, db=None) -> list[dict]:
    with closing(conectar(db)) as con:
        sql, args = "SELECT * FROM documentos", []
        if ticker:
            sql, args = sql + " WHERE ticker = ?", [ticker.upper()]
        return [dict(r) for r in con.execute(sql + " ORDER BY data_entrega DESC, id DESC", args)]


def pagina(doc_id: int, n: int, db=None) -> str | None:
    with closing(conectar(db)) as con:
        r = con.execute("SELECT texto FROM paginas WHERE doc_id = ? AND pagina = ?", (doc_id, n)).fetchone()
        return r["texto"] if r else None


def trechos(db=None, doc_ids: list[int] | None = None) -> list[dict]:
    with closing(conectar(db)) as con:
        sql = ("SELECT t.id, t.doc_id, t.pagina, t.ordem, t.texto, d.ticker, d.categoria, d.assunto, d.data_entrega "
               "FROM trechos t JOIN documentos d ON d.id = t.doc_id")
        if doc_ids:
            sql += f" WHERE t.doc_id IN ({', '.join('?' * len(doc_ids))})"
        return [dict(r) for r in con.execute(sql + " ORDER BY t.id", doc_ids or [])]


def estatisticas(db=None) -> dict:
    with closing(conectar(db)) as con:
        q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
        return {"documentos": q("SELECT COUNT(*) FROM documentos"), "paginas": q("SELECT COUNT(*) FROM paginas"),
                "trechos": q("SELECT COUNT(*) FROM trechos"),
                "embeddings": {r["modelo"]: r["n"] for r in con.execute("SELECT modelo, COUNT(*) n FROM embeddings GROUP BY modelo")},
                "empresas": [r[0] for r in con.execute("SELECT DISTINCT ticker FROM documentos ORDER BY 1")]}


# ---------------- BM25 ----------------
@dataclass
class IndiceBM25:
    ids: list[int]
    docs: list[Counter]
    tam: np.ndarray
    df: Counter
    k1: float = 1.5
    b: float = 0.75

    def pontuar(self, consulta: str) -> np.ndarray:
        q = tokens(consulta)
        n, media = len(self.ids), (self.tam.mean() if len(self.tam) else 1.0)
        s = np.zeros(n)
        for termo in set(q):
            df = self.df.get(termo, 0)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = np.array([d.get(termo, 0) for d in self.docs], dtype=float)
            s += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.tam / media))
        return s


@lru_cache(maxsize=4)
def _indice_bm25(db_key: str) -> tuple[IndiceBM25, dict[int, dict]]:
    ts = trechos(db_key if db_key != "padrao" else None)
    docs = [Counter(tokens(t["texto"])) for t in ts]
    df = Counter(term for d in docs for term in d)
    return IndiceBM25([t["id"] for t in ts], docs, np.array([sum(d.values()) for d in docs], dtype=float), df), {t["id"]: t for t in ts}


# ---------------- embeddings ----------------
def _para_blob(v) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def garantir_embeddings(provedor: tuple[str, str] | None = None, db=None) -> dict:
    """Calcula os embeddings que faltam para o modelo escolhido. Devolve {modelo, novos, erro?}."""
    from indicadores_b3.agents import llm
    prov = provedor or llm.provedor_embedding()
    if not prov:
        return {"modelo": None, "novos": 0, "aviso": "Nenhum provedor de embeddings: busca só por palavras (BM25)."}
    p, modelo = prov
    chave = f"{p}:{modelo}"
    with closing(conectar(db)) as con:
        faltam = con.execute("SELECT t.id, t.texto FROM trechos t LEFT JOIN embeddings e ON e.trecho_id = t.id AND e.modelo = ? "
                             "WHERE e.trecho_id IS NULL", (chave,)).fetchall()
    if not faltam:
        return {"modelo": chave, "novos": 0}
    try:
        vetores = llm.embeddings(p, modelo, [r["texto"] for r in faltam])
    except llm.ErroProvedor as e:
        return {"modelo": chave, "novos": 0, "erro": str(e)}
    with closing(conectar(db)) as con, con:
        con.executemany("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)",
                        [(r["id"], chave, _para_blob(v)) for r, v in zip(faltam, vetores, strict=True)])
    return {"modelo": chave, "novos": len(faltam)}


def _matriz(modelo: str, db=None) -> tuple[list[int], np.ndarray]:
    with closing(conectar(db)) as con:
        linhas = con.execute("SELECT trecho_id, vetor FROM embeddings WHERE modelo = ? ORDER BY trecho_id", (modelo,)).fetchall()
    if not linhas:
        return [], np.zeros((0, 0))
    m = np.vstack([np.frombuffer(r["vetor"], dtype=np.float32) for r in linhas])
    m = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)
    return [r["trecho_id"] for r in linhas], m


# ---------------- busca ----------------
def _ranking(ids: list[int], scores: np.ndarray, permitido: set[int] | None) -> list[int]:
    ordem = np.argsort(-scores, kind="stable")
    return [ids[i] for i in ordem if scores[i] > 0 and (permitido is None or ids[i] in permitido)]


def rrf(*rankings: list[int], k: int = RRF_K) -> list[int]:
    """Reciprocal Rank Fusion: soma 1/(k + posição) de cada lista; robusto a escalas de nota diferentes."""
    nota: dict[int, float] = {}
    for rk in rankings:
        for pos, i in enumerate(rk):
            nota[i] = nota.get(i, 0.0) + 1.0 / (k + pos + 1)
    return sorted(nota, key=lambda i: -nota[i])


def buscar(consulta: str, k: int = 6, ticker: str | None = None, doc_id: int | None = None, modo: str = "hibrido",
           vetor_consulta=None, modelo_emb: str | None = None, db=None) -> list[dict]:
    """modo: 'bm25', 'semantico' ou 'hibrido'. Devolve trechos com doc_id, pagina, texto e as posições em cada busca."""
    idx, por_id = _indice_bm25(str(db) if db else "padrao")
    if not idx.ids:
        return []
    permitido = {i for i, t in por_id.items() if (not ticker or t["ticker"] == ticker.upper()) and (not doc_id or t["doc_id"] == doc_id)}
    r_bm25 = _ranking(idx.ids, idx.pontuar(consulta), permitido) if modo in ("bm25", "hibrido") else []
    r_sem: list[int] = []
    if modo in ("semantico", "hibrido"):
        if modelo_emb is None or vetor_consulta is None:
            from indicadores_b3.agents import llm
            prov = llm.provedor_embedding()
            if prov:
                modelo_emb = f"{prov[0]}:{prov[1]}"
                try:
                    vetor_consulta = llm.embeddings(prov[0], prov[1], [consulta])[0]
                except llm.ErroProvedor:
                    vetor_consulta = None
        if vetor_consulta is not None and modelo_emb:
            ids, m = _matriz(modelo_emb, db)
            if ids:
                q = np.asarray(vetor_consulta, dtype=np.float32)
                r_sem = _ranking(ids, m @ (q / max(np.linalg.norm(q), 1e-12)) + 1.0, permitido)  # +1: cosseno vira positivo
    final = rrf(r_bm25, r_sem) if (r_bm25 and r_sem) else (r_bm25 or r_sem)
    pos_b = {i: p + 1 for p, i in enumerate(r_bm25)}
    pos_s = {i: p + 1 for p, i in enumerate(r_sem)}
    return [{**por_id[i], "pos_bm25": pos_b.get(i), "pos_semantica": pos_s.get(i),
             "metodo": "híbrido" if r_sem and r_bm25 else ("semântico" if r_sem else "palavras (BM25)")} for i in final[:k]]
