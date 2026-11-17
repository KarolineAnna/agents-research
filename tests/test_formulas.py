"""Testes das fórmulas, sem depender de internet nem de arquivos baixados."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from indicadores_b3.analytics import impostos
from indicadores_b3.analytics import rendafixa as rf
from indicadores_b3.data import lista
from indicadores_b3.portfolio import carteira


def test_feriados_2026():
    f = set(rf.feriados(2026))
    for d in [date(2026, 2, 16), date(2026, 2, 17),   # Carnaval
              date(2026, 4, 3),                        # Sexta-feira Santa (Páscoa em 05/04)
              date(2026, 6, 4),                        # Corpus Christi
              date(2026, 11, 20), date(2026, 11, 2), date(2026, 12, 25)]:
        assert d in f, d


def test_dias_uteis_pula_feriado_e_fim_de_semana():
    # 30/10/2026 é sexta; 02/11 é feriado → só 30/10 e 03/11 são úteis até 04/11 (exclusive)
    assert rf.du(date(2026, 10, 30), date(2026, 11, 4)) == 2
    assert rf.proximo_util(date(2026, 10, 31)) == date(2026, 11, 3)


# ---------- títulos ----------
def test_prefixado_preco_e_duration():
    base = date(2026, 11, 3)
    fl, un = rf.fluxos("PRE", date(2028, 1, 1), base)
    a = rf.analisar(fl, 14.0, base)
    du = rf.du(base, rf.proximo_util(date(2028, 1, 1)))
    assert un == "R$"
    assert a["pu"] == pytest.approx(1000 / 1.14 ** (du / 252))
    assert a["duration_macaulay"] == pytest.approx(du / 252)          # sem cupom: duration = prazo
    assert a["duration_modificada"] == pytest.approx(du / 252 / 1.14)


def test_cupons_semestrais():
    assert rf.CUPOM_NTNF == pytest.approx(0.048809, abs=1e-6)
    assert rf.CUPOM_NTNB == pytest.approx(0.029563, abs=1e-6)
    fl, _ = rf.fluxos("PREJS", date(2035, 1, 1), date(2026, 11, 3))
    assert all(f["data"].month in (1, 7) for f in fl)
    assert fl[-1]["valor"] == pytest.approx(1000 + 1000 * rf.CUPOM_NTNF)


def test_titulo_com_cupom_tem_duration_menor_que_prazo():
    base = date(2026, 11, 3)
    fl, _ = rf.fluxos("PREJS", date(2035, 1, 1), base)
    a = rf.analisar(fl, 13.0, base)
    assert a["duration_macaulay"] < fl[-1]["anos"] if "anos" in fl[-1] else a["fluxos"][-1]["anos"]


def test_dv01_e_convexidade_positivos():
    base = date(2026, 11, 3)
    fl, _ = rf.fluxos("PRE", date(2035, 1, 1), base)
    a = rf.analisar(fl, 13.0, base)
    assert a["dv01"] < 0 and a["convexidade"] > 0


# ---------- impostos ----------
@pytest.mark.parametrize("dias,aliq", [(1, 22.5), (180, 22.5), (181, 20), (360, 20), (361, 17.5),
                                       (720, 17.5), (721, 15), (5000, 15)])
def test_tabela_regressiva(dias, aliq):
    assert impostos.aliquota_renda_fixa(dias) == aliq


def test_iof_regressivo():
    assert rf._iof(1) == 96 and rf._iof(29) == 3 and rf._iof(30) == 0 and rf._iof(400) == 0


# ---------- carteira ----------
def test_markowitz_pesos_somam_100_e_respeitam_maximo():
    rng = np.random.default_rng(1)
    ret = rng.normal(0.0005, 0.01, (500, 4)) + rng.normal(0, 0.005, (500, 1))
    mu, cov = ret.mean(0) * 252, np.cov(ret.T) * 252
    r = carteira.otimizar(list("ABCD"), mu, cov, 0.10, 0.4)
    for c in (r["max_sharpe"], r["min_var"]):
        pesos = np.array(list(c["pesos"].values())) / 100
        assert pesos.sum() == pytest.approx(1, abs=1e-4)
        assert pesos.max() <= 0.4 + 1e-4 and pesos.min() >= -1e-6


def test_capm_beta_do_proprio_mercado_e_1(monkeypatch):
    idx = pd.bdate_range("2024-01-01", periods=300)
    rng = np.random.default_rng(2)
    m = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, 300)), index=idx)
    monkeypatch.setattr(carteira, "_ibov", lambda periodo, dia: m)
    rm = m.pct_change().dropna()
    ret = pd.DataFrame({"MERC": rm, "DOBRO": 2 * rm, "NADA": rng.normal(0, 0.01, len(rm))}, index=rm.index)
    c = carteira.capm(ret, "1y", "x", 0.10, 15.0)
    b = {a["ticker"]: a for a in c["ativos"]}
    assert b["MERC"]["beta"] == pytest.approx(1) and b["MERC"]["alfa"] == pytest.approx(0, abs=1e-9)
    assert b["DOBRO"]["beta"] == pytest.approx(2)
    assert b["MERC"]["retorno_capm"] == pytest.approx(15.0)          # β=1 → E[Rm]
    assert abs(b["NADA"]["beta"]) < 0.3


# ---------- lista de ativos ----------
@pytest.mark.parametrize("tk,ok", [("PETR4", True), ("TAEE11", True), ("EMBJ3", True), ("PETRK300", False),
                                   ("HGLG11", True), ("AB", False)])
def test_formato_de_ticker(tk, ok):
    # o formato aceita FII (11), por isso a lista também filtra pela espécie (ON/PN/UNT) no COTAHIST
    assert bool(pd.Series([tk]).str.fullmatch(lista.TICKER_ACAO).iloc[0]) is ok


def test_dcf_tira_arrendamento_e_convenio_do_fcl():
    """Varejista: 'Pagamento de fornecedores - convênio' e arrendamentos ficam no financiamento, mas são operacionais."""
    import pandas as pd

    from indicadores_b3.analytics import dcf

    linhas = [("6.03.04", "Pagamento de Arrendamento Mercantil", -400.0), ("6.03.05", "Pagamento de fornecedores - convênio", -13000.0),
              ("6.03.06", "Pagamento de Juros sobre Arrendamento", -300.0), ("6.03.01", "Captação de Empréstimos", 2000.0)]
    df = pd.DataFrame([{"FONTE": "DFP", "DT_REFER": "2025-12-31", "ORDEM_EXERC": "ÚLTIMO", "DT_INI_EXERC": "2025-01-01",
                        "DT_FIM_EXERC": "2025-12-31", "CD_CONTA": c, "DS_CONTA": d, "VL": v, "VL_CONTA": v} for c, d, v in linhas])
    norm = dcf._ajustes_normalizados(df)
    tot = norm.groupby("CD_CONTA").VL.sum().to_dict()
    assert tot == {"arrendamento": -700.0, "fornecedores": -13000.0}


def test_ke_mercado_sem_internet_usa_premissas_declaradas(monkeypatch):
    from indicadores_b3.agents import fontes_publicas as fp
    from indicadores_b3.analytics import dcf

    def falha(*a, **k):
        raise ConnectionError("sem internet")
    for nome in ("fred", "ipea_ultimo", "focus"):
        monkeypatch.setattr(fp, nome, falha)
    dcf._ke_mercado_do_dia.cache_clear()
    m = dcf._ke_mercado_do_dia("2099-01-01")
    assert {k: v["valor"] for k, v in m.items()} == {"rf_us": 4.3, "crp": dcf.CRP_PADRAO, "pi_us": dcf.PI_US_PADRAO, "pi_br": 3.5}
    assert all(v.get("premissa") and "premissa" in v["nota"] for v in m.values())
    # Ke em reais pela paridade de inflação: (1 + 4,3% + 2,5% + 1 × 5%) × 1,035 ÷ 1,023 − 1 ≈ 13,1%
    ke = ((1 + (4.3 + 2.5 + 5) / 100) * 1.035 / 1.023 - 1) * 100
    assert round(ke, 1) == 13.1


def test_titulos_a_venda_pelas_vendas_recentes():
    import pandas as pd

    from indicadores_b3.data import tesouro
    df = pd.DataFrame({
        "Tipo Titulo": ["Tesouro IPCA+", "Tesouro Selic", "Tesouro Prefixado", "Tesouro Educa+"],
        "Vencimento do Titulo": ["15/05/2035", "01/03/2031", "01/01/2027", "15/12/2040"],
        "Data Venda": ["28/10/2026", "30/10/2026", "01/09/2026", "20/10/2026"],  # o prefixado 2027 parou de vender
        "PU": ["2500,0", "20000,0", "900,0", "2000,0"], "Quantidade": ["1", "1", "1", "1"], "Valor": ["1", "1", "1", "1"]})
    cods, ult = tesouro.codigos_vendidos(df)
    assert ult == pd.Timestamp("2026-10-30")
    assert cods == {"TD-IPCA-20350515", "TD-SELIC-20310301", "TD-EDUCA-20401215"}


def test_chave_de_preco_renova_a_cada_15_min_so_no_pregao():
    from datetime import datetime, timedelta, timezone

    from indicadores_b3.data.fontes import chave_preco
    br = timezone(timedelta(hours=-3))
    seg = lambda h, m: datetime(2026, 11, 9, h, m, tzinfo=br)  # noqa: E731 — 09/11/2026 é segunda-feira
    assert chave_preco(seg(11, 7)) == "2026-11-09 11:00"
    assert chave_preco(seg(11, 16)) == "2026-11-09 11:15"          # 15 min depois: chave nova, preço novo
    assert chave_preco(seg(9, 30)) == chave_preco(seg(19, 0)) == "2026-11-09"  # fora do pregão: uma por dia
    assert chave_preco(datetime(2026, 11, 8, 12, 0, tzinfo=br)) == "2026-11-08"  # domingo
