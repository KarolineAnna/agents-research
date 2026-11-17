"""Testes dos modelos de ML/estatística com dados sintéticos (sem internet, determinísticos)."""
import numpy as np
import pandas as pd
import pytest

from indicadores_b3.ml import carteira_robusta as cr
from indicadores_b3.ml.volatilidade import avaliar_garch


def _retornos(n=700, k=4, seed=7):
    rng = np.random.default_rng(seed)
    mu = np.array([0.0004, 0.0003, 0.0002, 0.0005])[:k]
    a = rng.normal(0, 0.01, (k, k))
    cov = a @ a.T / k + np.eye(k) * 1e-4
    r = rng.multivariate_normal(mu, cov, n)
    return pd.DataFrame(r, index=pd.bdate_range("2020-01-01", periods=n), columns=[f"A{i}" for i in range(k)])


def test_pesos_validos_em_todos_os_metodos():
    ret = _retornos()
    out = cr.avaliar(ret, rf=0.10, peso_max=0.6, janela=252, rebal=21, n_boot=20)
    for m, pesos in out["atual"].items():
        w = np.array(list(pesos.values()))
        assert w.sum() == pytest.approx(100, abs=0.1), m
        assert (w >= -1e-6).all(), m
        if m not in ("iguais", "hrp"):
            assert (w <= 60 + 1e-4).all(), m


def test_hrp_soma_um_e_positivo():
    w = cr._hrp(_retornos().values)
    assert w.sum() == pytest.approx(1) and (w > 0).all()


def test_walk_forward_nao_olha_o_futuro():
    """Mudar os últimos dias não pode alterar o resultado fora da amostra dos dias anteriores."""
    ret = _retornos()
    a = cr.avaliar(ret, rf=0.10, n_boot=5)
    ret2 = ret.copy()
    ret2.iloc[-40:] = ret2.iloc[-40:] * -3
    b = cr.avaliar(ret2, rf=0.10, n_boot=5)
    corte = len(a["datas"]) - 40 - 21  # o último bloco antes da mudança
    for m in cr.METODOS:
        assert a["backtest"][m]["curva"][:corte] == b["backtest"][m]["curva"][:corte], m


def test_reprodutivel_com_semente():
    ret = _retornos()
    a = cr.avaliar(ret, rf=0.1, n_boot=15, seed=1)
    b = cr.avaliar(ret, rf=0.1, n_boot=15, seed=1)
    assert a["estabilidade"] == b["estabilidade"]


def test_historico_curto_e_recusado():
    with pytest.raises(ValueError):
        cr.avaliar(_retornos(n=200), rf=0.1)


def test_garch_recupera_parametros_de_processo_garch():
    pytest.importorskip("arch")
    rng = np.random.default_rng(3)
    n, w, a, b = 3000, 0.05, 0.10, 0.85
    var, r = w / (1 - a - b), np.empty(n)
    for t in range(n):
        r[t] = np.sqrt(var) * rng.standard_normal()
        var = w + a * r[t] ** 2 + b * var
    s = pd.Series(r, index=pd.bdate_range("2012-01-02", periods=n))
    out = avaliar_garch(s, fracao_teste=0.25)
    assert out["parametros"]["alpha"] == pytest.approx(a, abs=0.04)
    assert out["parametros"]["beta"] == pytest.approx(b, abs=0.06)
    assert out["teste"]["vencedor_qlike"] == "garch"  # num processo GARCH de verdade, o GARCH tem de ganhar


def test_resultado_nao_depende_do_layout_na_memoria():
    """Mesmo histórico, um DataFrame contíguo e outro não: antes dava curvas diferentes (~1e-9 nos pesos)."""
    ret = _retornos()
    f = pd.DataFrame(np.asfortranarray(ret.values), index=ret.index, columns=ret.columns)
    a, b = cr.avaliar(ret, rf=0.10, n_boot=5), cr.avaliar(f, rf=0.10, n_boot=5)
    for m in cr.METODOS:
        assert a["backtest"][m]["curva"] == b["backtest"][m]["curva"], m
