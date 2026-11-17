"""Histórico de acertos: registro, deduplicação e conferência contra o Ibovespa (sem internet)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from indicadores_b3.quality import acertos as ac

IDX = pd.bdate_range("2025-01-01", "2026-10-30")


def _precos(simbolo):
    # GANHA3 sobe 30% ao ano, PERDE3 cai 10%, Ibovespa sobe 10%
    taxa = {"GANHA3.SA": 0.30, "PERDE3.SA": -0.10, "^BVSP": 0.10, "MEIO3.SA": 0.10}[simbolo]
    t = np.arange(len(IDX)) / 252
    return pd.Series((1 + taxa) ** t * 10, index=IDX)


def test_registro_uma_vez_por_dia(tmp_path):
    db = tmp_path / "p.db"
    assert ac.registrar("cara_ou_barata", "GANHA3", "barata", dia="2025-02-03", db=db)
    assert not ac.registrar("cara_ou_barata", "GANHA3", "cara", dia="2025-02-03", db=db)  # mesmo dia: ignora
    assert not ac.registrar("cara_ou_barata", "GANHA3", None, db=db)


def test_painel_confere_acertos_erros_e_pendentes(tmp_path):
    db = tmp_path / "p.db"
    ac.registrar("cara_ou_barata", "GANHA3", "barata", dia="2025-02-03", db=db)   # acerta (bateu o Ibov)
    ac.registrar("cara_ou_barata", "GANHA3", "barata", dia="2025-02-20", db=db)   # mesmo mês: não conta de novo
    ac.registrar("cara_ou_barata", "PERDE3", "barata", dia="2025-02-03", db=db)   # erra
    ac.registrar("cara_ou_barata", "PERDE3", "cara", dia="2025-03-03", db=db)     # acerta (ficou atrás)
    ac.registrar("cara_ou_barata", "MEIO3", "justa", dia="2025-03-03", db=db)     # não conta acerto
    ac.registrar("cara_ou_barata", "GANHA3", "cara", dia="2026-10-01", db=db)     # ainda pendente
    p = ac.painel(hoje=date(2026, 10, 30), precos=_precos, db=db)
    r = p["resumo"]["cara_ou_barata"]
    assert p["contadas"] == 5 and r["previsoes"] == 5
    h = r["horizontes"]["6m"]
    assert h["conferidas"] == 4 and h["pendentes"] == 1
    assert h["grupos"]["barata"]["n"] == 2 and h["grupos"]["barata"]["taxa_acerto"] == pytest.approx(50)
    assert h["grupos"]["cara"]["taxa_acerto"] == pytest.approx(100) and h["grupos"]["justa"]["taxa_acerto"] is None
    assert h["grupos"]["justa"]["excesso_medio"] == pytest.approx(0, abs=0.5)
    assert h["diferenca_grupos"] > 0 and h["taxa_base"] == pytest.approx(25)
    pend = next(x for x in p["previsoes"] if x["data"] == "2026-10-01")
    assert pend["resultado"]["3m"]["status"] == "pendente" and pend["resultado"]["3m"]["pronto_em"] == "2026-12-31"


def test_carteira_compara_com_a_atual(tmp_path):
    db = tmp_path / "p.db"
    r = {"pesos": {"PERDE3": 80.0, ac.RF_ID: 20.0}, "modo": "regras",
         "diagnostico": {"itens": [{"nome": "CDI usado (ao ano)", "valor": 14.0}]},
         "laboratorio": {"confirmacao": [{"numero": 2, "status": "aprovada", "pesos": {"GANHA3": 80.0, ac.RF_ID: 20.0}, "motivo": "troca"},
                                         {"numero": 3, "status": "reprovada", "pesos": {"BOVA11": 80.0, ac.RF_ID: 20.0}, "motivo": "índice"}]}}
    assert ac.registrar_carteira(r, db=db) == 2
    p = ac.painel(hoje=date.today(), precos=_precos, db=db)
    h = p["resumo"]["carteira"]["horizontes"]["3m"]
    if h["conferidas"]:  # registrado hoje: ainda pendente
        pytest.fail("previsão de hoje não deveria estar conferida")
    out = ac.conferir({"origem": "carteira", "data": "2025-02-03", "previsao": "aprovada",
                       "detalhes": {"atual": r["pesos"], "proposta": {"GANHA3": 80.0, ac.RF_ID: 20.0}, "cdi": 14.0}}, date(2026, 10, 30), _precos)
    assert out["12m"]["status"] == "conferida" and out["12m"]["excesso"] > 0 and out["12m"]["acerto"] is True
    out2 = ac.conferir({"origem": "carteira", "data": "2025-02-03", "previsao": "reprovada",
                        "detalhes": {"atual": r["pesos"], "proposta": {"BOVA11": 80.0, ac.RF_ID: 20.0}, "cdi": 14.0}}, date(2026, 10, 30), _precos)
    assert out2["6m"]["acerto"] is False  # o índice rendeu mais que PERDE3: reprovar foi um erro


def test_sem_preco_fica_sem_dados(tmp_path):
    db = tmp_path / "p.db"
    ac.registrar("cara_ou_barata", "GANHA3", "barata", dia="2025-02-03", db=db)
    p = ac.painel(hoje=date(2026, 10, 30), precos=lambda s: pd.Series(dtype=float), db=db)
    assert p["previsoes"][0]["resultado"]["6m"]["status"] == "sem_dados"
