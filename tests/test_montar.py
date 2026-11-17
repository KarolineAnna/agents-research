"""Testes do "Montar minha carteira" (montar.py), sem internet."""
import numpy as np
import pandas as pd
import pytest

from indicadores_b3.portfolio import montar

RNG = np.random.default_rng(10)
MU = np.array([0.20, 0.12, 0.30, 0.149])           # último = renda fixa
COV = np.diag([0.25, 0.15, 0.6, 0.0]) ** 2
COV[0, 1] = COV[1, 0] = 0.25 * 0.15 * 0.3 * 0.25 * 0.15 / (0.25 * 0.15)  # correlação moderada
RF = 0.149


def _ok(w, lo, hi):
    assert w.sum() == pytest.approx(1, abs=1e-6)
    assert np.all(w >= np.array(lo) - 1e-6) and np.all(w <= np.array(hi) + 1e-6)


def test_risco_alvo_respeita_a_volatilidade():
    lo, hi = [0, 0, 0, 0], [1, 1, 0.05, 1]
    w = montar.otimizar(MU, COV, RF, lo, hi, "vol_alvo", 8)
    _ok(w, lo, hi)
    assert np.sqrt(w @ COV @ w) <= 0.08 + 1e-4
    assert w[2] <= 0.05 + 1e-6                     # limite do ativo mais arriscado


def test_retorno_alvo_chega_no_retorno():
    lo, hi = [0, 0, 0, 0], [1, 1, 1, 1]
    w = montar.otimizar(MU, COV, RF, lo, hi, "ret_alvo", 20)
    _ok(w, lo, hi)
    assert w @ MU >= 0.20 - 1e-4


def test_minimos_sao_respeitados_e_rf_fixa_no_sharpe():
    lo, hi = [0.1, 0.1, 0, 0.2], [1, 1, 1, 1]
    w = montar.otimizar(MU, COV, RF, lo, hi, "max_sharpe", fixar_rf=(3, 0.2))
    _ok(w, lo, hi)
    assert w[3] == pytest.approx(0.2, abs=1e-6)


def test_alvo_impossivel_da_erro_claro():
    with pytest.raises(ValueError, match="risco de até"):
        montar.otimizar(MU[:3], COV[:3, :3], RF, [0, 0, 0], [1, 1, 1], "vol_alvo", 1)
    with pytest.raises(ValueError, match="100%"):
        montar.otimizar(MU, COV, RF, [0.5, 0.5, 0.5, 0], [1, 1, 1, 1], "min_risco")


def test_lista_de_compras_inteiras_e_soma_o_valor():
    idx = pd.bdate_range("2026-01-01", periods=3)
    px = pd.DataFrame({"PETR4": [30.0, 31, 32.5], "TD-SELIC-20290301": [16000, 16010, 16020.0],
                       "BTC": [500000, 505000, 510000.0]}, index=idx)
    info = {"PETR4": {"classe": "b3", "nome": "PETR4"}, "TD-SELIC-20290301": {"classe": "tesouro", "nome": "Selic"},
            "BTC": {"classe": "cripto", "nome": "BTC"}}
    nomes = ["PETR4", "TD-SELIC-20290301", "BTC", montar.RF_ID]
    itens = montar.lista_compras(np.array([0.4, 0.3, 0.1, 0.2]), nomes, px, info, 10000)
    q = {i["ticker"]: i for i in itens}
    assert q["PETR4"]["quantidade"] == int(q["PETR4"]["quantidade"])
    assert round(q["TD-SELIC-20290301"]["quantidade"] * 100) == q["TD-SELIC-20290301"]["quantidade"] * 100
    assert sum(i["valor"] for i in itens) == pytest.approx(10000)
    assert all(i["valor"] >= -1e-9 for i in itens)
    assert abs(q["PETR4"]["valor"] - 4000) <= 32.5 / 2 + 1e-9  # a quantidade inteira mais próxima do alvo


# ---------- Black-Litterman ----------
from indicadores_b3.portfolio import premissas  # noqa: E402


def test_bl_sem_visoes_devolve_as_premissas():
    prior = np.array([0.12, 0.15, 0.10])
    cov = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.0], [0.0, 0.0, 0.02]])
    r = premissas.black_litterman(prior, cov, ["A", "B", "C"], [])
    assert r["posterior"] == pytest.approx(prior)


def test_bl_visao_move_na_direcao_e_confianca_pesa():
    prior = np.array([0.12, 0.15, 0.10])
    cov = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.0], [0.0, 0.0, 0.02]])
    vis = lambda c: [{"tipo": "rel", "a": "A", "b": "B", "q": 5, "confianca": c}]  # noqa: E731
    baixa = premissas.black_litterman(prior, cov, ["A", "B", "C"], vis("baixa"))["posterior"]
    alta = premissas.black_litterman(prior, cov, ["A", "B", "C"], vis("alta"))["posterior"]
    d0, db, da = prior[0] - prior[1], baixa[0] - baixa[1], alta[0] - alta[1]
    assert d0 < db < da < 0.05 + 1e-9          # vai de −3 p.p. em direção a +5 p.p., mais com confiança alta
    assert baixa[2] == pytest.approx(prior[2], abs=1e-9)   # ativo não correlacionado não se move


def test_bl_visao_absoluta_com_confianca_quase_total():
    prior = np.array([0.12, 0.15])
    cov = np.array([[0.04, 0.0], [0.0, 0.09]])
    old = premissas.CONFIANCA["alta"]
    premissas.CONFIANCA["alta"] = 0.9999
    try:
        r = premissas.black_litterman(prior, cov, ["A", "B"], [{"tipo": "abs", "a": "A", "q": 20, "confianca": "alta"}])
    finally:
        premissas.CONFIANCA["alta"] = old
    assert r["posterior"][0] == pytest.approx(0.20, abs=1e-3)
