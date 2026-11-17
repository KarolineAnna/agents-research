"""RAG de comunicados: extração, índice, busca híbrida, validador de citações, agente e avaliação (sem internet)."""
from pathlib import Path

import numpy as np
import pytest

from indicadores_b3.agents import llm
from indicadores_b3.rag import agente as rag_agente
from indicadores_b3.rag import armazem, avaliacao
from indicadores_b3.rag.coleta import _pdf_de, extrair_paginas

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Armazém temporário com os dois PDFs de exemplo; sem provedores de IA."""
    db = tmp_path / "docs.db"
    monkeypatch.setattr(llm, "provedor_embedding", lambda: None)
    ids = {}
    for nome, prot, assunto in (("fato_relevante_jcp.pdf", "P1", "JCP e recompra"), ("comunicado_debentures.pdf", "P2", "Debêntures")):
        paginas = extrair_paginas((FIX / nome).read_bytes())
        ids[prot] = armazem.salvar_documento({"protocolo": prot, "ticker": "BEXM4", "assunto": assunto, "categoria": "Fato Relevante",
                                              "data_entrega": "2026-10-01", "status": "ok"}, paginas, db=db)
    armazem._indice_bm25.cache_clear()
    return db, ids


def test_extracao_por_pagina_e_pdf_dentro_de_zip():
    ps = extrair_paginas((FIX / "fato_relevante_jcp.pdf").read_bytes())
    assert len(ps) == 3 and "R$ 0,35 por ação" in ps[0] and "18 meses" in ps[2]
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.pdf", (FIX / "comunicado_debentures.pdf").read_bytes())
    assert _pdf_de(buf.getvalue())[:4] == b"%PDF" and _pdf_de(b"<html>erro</html>") is None


def test_fatiar_com_sobreposicao():
    txt = ". ".join(f"Frase número {i} sobre o assunto" for i in range(120))
    partes = armazem.fatiar(txt, tam=300, sobra=60)
    assert all(len(p) <= 300 for p in partes) and len(partes) > 5
    assert partes[0][-20:] in txt and any(partes[i][-30:][:10] in partes[i + 1] for i in range(len(partes) - 1))


def test_bm25_acha_a_pagina_certa(base):
    db, ids = base
    r = armazem.buscar("programa de recompra prazo de 18 meses", k=3, modo="bm25", db=db)
    assert (r[0]["doc_id"], r[0]["pagina"]) == (ids["P1"], 3)
    r = armazem.buscar("debêntures CDI", k=1, modo="bm25", db=db)
    assert r[0]["doc_id"] == ids["P2"]


def test_rrf_combina_rankings():
    assert armazem.rrf([1, 2, 3], [3, 2, 1])[:2] in ([2, 1], [2, 3], [1, 3], [3, 1])
    assert armazem.rrf([1, 2], [2, 9])[0] == 2  # aparece bem nas duas listas


def test_busca_semantica_e_hibrida_com_vetores_falsos(base, monkeypatch):
    db, ids = base
    ts = armazem.trechos(db)
    vet = {t["id"]: (np.eye(8)[i % 8] + 0.01) for i, t in enumerate(ts)}
    monkeypatch.setattr(llm, "embeddings", lambda p, m, textos, **k: [vet[next(t["id"] for t in ts if t["texto"] == x)].tolist() for x in textos])
    armazem.garantir_embeddings(("ollama", "falso"), db)
    alvo = ts[-1]
    r = armazem.buscar("qualquer coisa", k=2, modo="semantico", vetor_consulta=vet[alvo["id"]], modelo_emb="ollama:falso", db=db)
    assert r[0]["id"] == alvo["id"] and r[0]["metodo"] == "semântico"
    h = armazem.buscar("debêntures", k=3, modo="hibrido", vetor_consulta=vet[alvo["id"]], modelo_emb="ollama:falso", db=db)
    assert h[0]["metodo"] == "híbrido" and {x["doc_id"] for x in h} == set(ids.values())


def _vistos(db, ids):
    return {(ids["P1"], 1): armazem.pagina(ids["P1"], 1, db), (ids["P1"], 2): armazem.pagina(ids["P1"], 2, db),
            (ids["P2"], 1): armazem.pagina(ids["P2"], 1, db)}


def test_validador_de_citacoes(base):
    db, ids = base
    v, a, b = _vistos(db, ids), ids["P1"], ids["P2"]
    bom = f'JCP de R$ 0,35 por ação [D{a} p1], pagos em 15/12/2026 [D{a} p2]; IR de 17,5% [D{a} p2]. Debêntures de R$ 1,5 bilhão [D{b} p1].'
    assert rag_agente.validar_citacoes(bom, v) == []
    assert rag_agente.validar_citacoes("JCP de R$ 0,35 [D99 p1]", v)[0].startswith("cita páginas que não foram lidas")
    assert "aspas" in rag_agente.validar_citacoes(f'Diz "o banco vai dobrar o lucro no ano" [D{a} p1]', v)[0]
    assert "0,40" in rag_agente.validar_citacoes(f"JCP de R$ 0,40 por ação [D{a} p1]", v)[0]
    assert "nenhuma citação" in rag_agente.validar_citacoes("O JCP é de R$ 0,35.", v)[0]
    assert rag_agente.validar_citacoes("Não encontrei essa informação nos documentos.", v) == []
    # escala: 3.850.000.000,00 na página aceita "R$ 3,85 bilhões"
    assert rag_agente.validar_citacoes(f"Total de R$ 3,85 bilhões [D{a} p1].", v) == []


def _roteiro(monkeypatch, respostas):
    def falso(p, m, msgs, tools, **_):
        return respostas.pop(0)
    monkeypatch.setattr(llm, "conversar", falso)
    monkeypatch.setattr(llm, "disponiveis", lambda: [("teste", "m")])


def test_agente_busca_cita_e_corrige_numero_inventado(base, monkeypatch):
    db, ids = base
    a = ids["P1"]
    chamada = {"id": "1", "type": "function", "function": {"name": "buscar", "arguments": '{"pergunta": "juros sobre capital próprio valor"}'}}
    _roteiro(monkeypatch, [{"content": "", "tool_calls": [chamada]},
                           {"content": f"O JCP é de R$ 0,50 por ação [D{a} p1]."},
                           {"content": f"O JCP é de R$ 0,35 por ação [D{a} p1]."}])
    r = rag_agente.AgenteDocumentos("BEXM4", db).perguntar("Qual o JCP por ação?")
    assert r["texto"].endswith(f"[D{a} p1].") and r["metricas"]["correcoes"] == 1
    assert r["citacoes"][0]["doc_id"] == a and "0,35" in r["citacoes"][0]["texto"]


def test_avaliacao_de_busca_sem_ia(base, monkeypatch, tmp_path):
    db, _ = base
    for nome, val in (("PASTA", tmp_path), ("EXECUCOES", tmp_path / "ex"), ("CACHE_SINT", tmp_path / "s.json")):
        monkeypatch.setattr(avaliacao, nome, val)
    r = avaliacao.avaliar_busca(n=10, usar_ia=False, db=db)
    assert r["geracao"].startswith("palavras-chave") and r["n"] >= 1
    assert r["modos"]["bm25"]["recall@5"] >= 50 and 0 < r["modos"]["bm25"]["mrr"] <= 1
    assert avaliacao.execucoes()[0]["id"] == r["id"]


def test_avaliacao_de_respostas(base, monkeypatch, tmp_path):
    db, ids = base
    perg = tmp_path / "perguntas.jsonl"
    perg.write_text('{"id": "jcp", "ticker": "BEXM4", "pergunta": "Qual o JCP?", "deve_conter": ["0,35"]}\n'
                    '{"id": "trap", "ticker": "BEXM4", "pergunta": "Lucro em 2035?", "sem_resposta": true}\n', encoding="utf-8")
    for nome, val in (("PASTA", tmp_path), ("EXECUCOES", tmp_path / "ex"), ("PERGUNTAS", perg)):
        monkeypatch.setattr(avaliacao, nome, val)
    a = ids["P1"]
    busca = {"id": "1", "type": "function", "function": {"name": "buscar", "arguments": '{"pergunta": "juros capital próprio"}'}}
    _roteiro(monkeypatch, [{"content": "", "tool_calls": [busca]}, {"content": f"R$ 0,35 por ação [D{a} p1]."},
                           {"content": "", "tool_calls": [busca]}, {"content": "Não encontrei essa informação."}])
    r = avaliacao.avaliar_respostas(db=db)
    s = r["resumo"]
    assert s["executadas"] == 2 and s["aprovadas_pelo_validador_%"] == 100.0
    assert s["contem_esperado_%"] == 100.0 and s["recusa_correta_%"] == 100.0
