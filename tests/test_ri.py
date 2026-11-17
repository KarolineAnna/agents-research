"""Relatórios de RI: tabelas linha a linha, busca que acha o número com o período e o Research citando a página."""
from pathlib import Path

import pytest

from indicadores_b3.agents import agente as research
from indicadores_b3.agents import llm
from indicadores_b3.rag import armazem, coleta, tabelas

FIX = Path(__file__).parent / "fixtures" / "relatorio_gerencial.pdf"


def test_linhas_de_tabela_ligam_rotulo_periodo_e_valor():
    txt = ("Qualidade do crédito\nIndicador 3T26 2T26 3T25\nÍndice de inadimplência acima de 90 dias 1,9% 2,0% 2,2%\n"
           "Índice de cobertura (NPL 90) 215% 210% 205%\nO texto corrido com 7,4% não é tabela.\n"
           "Resultado\nItem 2025 2024\nReceita líquida R$ 40,8 bi R$ 38,0 bi")
    ls = tabelas.linhas_de_tabela(txt)
    assert ls[0] == "Qualidade do crédito | Índice de inadimplência acima de 90 dias | 3T26: 1,9% | 2T26: 2,0% | 3T25: 2,2%"
    assert ls[1].startswith("Qualidade do crédito | Índice de cobertura (NPL 90) | 3T26: 215%")
    assert ls[2] == "Resultado | Receita líquida | 2025: R$ 40,8 bi | 2024: R$ 38,0 bi"
    assert len(ls) == 3  # a frase com 7,4% não vira linha de tabela


def test_pdf_real_vira_trechos_de_tabela():
    paginas, tabs = coleta.extrair(FIX.read_bytes())
    assert len(paginas) == 2
    assert any("Índice de Basileia | 3T26: 15,8% | 2T26: 15,6%" in t for t in tabs[1])


@pytest.fixture
def base_ri(tmp_path, monkeypatch):
    db = tmp_path / "docs.db"
    monkeypatch.setattr(armazem, "DB", db)
    monkeypatch.setattr(llm, "provedor_embedding", lambda: None)
    paginas, tabs = coleta.extrair(FIX.read_bytes())
    doc = armazem.salvar_documento({"protocolo": "RI1", "ticker": "BEXM4", "categoria": "Dados Econômico-Financeiros",
                                    "tipo": "Relatório de Análise Gerencial", "assunto": "Análise Gerencial da Operação",
                                    "data_entrega": "2026-11-04", "url": "https://exemplo/ri.pdf", "status": "ok"}, paginas, tabs)
    armazem._indice_bm25.cache_clear()
    monkeypatch.setattr(coleta, "indexar_ri", lambda t, *a, **k: {"documentos": [{**armazem.documentos(t)[0]}], "falhas": []})
    return doc


def test_busca_traz_a_linha_da_tabela_com_o_periodo(base_ri):
    r = armazem.buscar("índice de Basileia", k=3, ticker="BEXM4", modo="bm25")
    assert r[0]["texto"].startswith("Tabela · Capital | Índice de Basileia | 3T26: 15,8%")
    assert "Tabelas desta página" in armazem.pagina(base_ri, 2)


def test_research_cita_o_relatorio_e_o_validador_confere(base_ri):
    ag = research.Agente("BEXM4")
    r = ag.relatorios_ri("índice de Basileia")
    assert r["resultados"][0]["cite_como"] == f"[D{base_ri} p2]"
    assert ag._validar(f"O índice de Basileia ficou em 15,8% [D{base_ri} p2] no 3T26.") == []
    erro = ag._validar(f"O índice de Basileia ficou em 16,9% [D{base_ri} p2].")
    assert erro and "16,9" in erro[0]
    erro = ag._validar(f"O índice de Basileia ficou em 15,8% [D{base_ri} p9].")  # página não lida
    assert erro and "não foram lidas" in erro[0]
    usados = ag.documentos_usados()
    assert usados[0]["paginas_lidas"] and usados[0]["url"].startswith("https://")
