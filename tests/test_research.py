"""Testes do Research (3 agentes): fórmulas, validador de números e rastreabilidade.

Os testes de fórmula não precisam de internet. O teste com o Itaú usa os arquivos da CVM/B3 em cache
e é pulado se eles ainda não foram baixados.
"""
import pytest

from indicadores_b3.agents import investment, redator
from indicadores_b3.agents.fatos import Dossie, decimal_br


def _fin(roe=20.0, vpa=10.0, preco=15.0, pvp=1.5):
    D = Dossie("Financial Analyst", "F", "Banco Teste (TEST4)")
    D.extras.update({"ticker": "TEST4", "tipo": "banco", "ref": "2026-06-30"})
    D.calc("ROE", roe, "%", "lucro ÷ PL", [])
    D.calc("VPA (valor patrimonial por ação)", vpa, "R$", "PL ÷ ações", [])
    D.fato("Preço", preco, "R$", {"fonte": "B3", "data_ref": "2026-10-30"})
    D.calc("P/VP", pvp, "x", "Preço ÷ VPA", [])
    return D.to_dict()


def _mkt(rf=12.0, inf=4.0):
    D = Dossie("Market Research Analyst", "M", "Macro")
    D.fato("Juro prefixado em 5 anos", rf, "% a.a.", {"fonte": "Tesouro Nacional"})
    D.fato("Inflação implícita em 5 anos", inf, "% a.a.", {"fonte": "Tesouro Nacional"})
    return D.to_dict()


def _val(d, nome):
    return next(x["valor"] for x in d["itens"] if x["nome"] == nome)


def test_valuation_banco_formulas():
    inv = investment.analisar(_fin(), {}, _mkt()).to_dict()
    ke = _val(inv, "Ke (CAPM)")
    g = _val(inv, "g (crescimento nominal na perpetuidade)")
    assert ke == pytest.approx(12 + 1 * 5)
    assert g == pytest.approx((1.04 * 1.01 - 1) * 100)
    assert _val(inv, "P/VP justo — base") == pytest.approx((20 - g) / (ke - g))
    assert _val(inv, "Preço justo — base") == pytest.approx((20 - g) / (ke - g) * 10)
    # ROE implícito e Ke implícito são as duas inversões da mesma fórmula
    assert _val(inv, "ROE sustentável implícito no preço") == pytest.approx(g + 1.5 * (ke - g))
    ke_i = _val(inv, "Ke implícito no preço")
    assert (20 - g) / (ke_i - g) == pytest.approx(1.5)
    pond = sum(investment.PESOS[c] * _val(inv, f"Preço justo — {c}") for c in investment.PESOS)
    assert _val(inv, "Preço justo ponderado pelos cenários") == pytest.approx(pond)


def test_valuation_recusa_ke_menor_que_g():
    inv = investment.analisar(_fin(), {}, _mkt(rf=2.0, inf=9.0), {"erp": 1.0}).to_dict()
    assert any(a["nivel"] == "erro" for a in inv["alertas"])
    assert not any(x["nome"].startswith("Preço justo") for x in inv["itens"])


def test_toda_estimativa_aponta_para_insumos_existentes():
    inv = investment.analisar(_fin(), {"PAR3": _fin(roe=12, pvp=0.8)}, _mkt()).to_dict()
    ids = {x["id"] for x in inv["itens"]}
    for x in inv["itens"]:
        if x["tipo"] in ("calculado", "estimativa"):
            assert set(x["insumos"]) <= ids, x["nome"]
        if x["tipo"] == "fato":
            assert x["fonte"]["fonte"], x["nome"]
        if x["tipo"] == "premissa":
            assert x["nota"], x["nome"]


def test_validador_aceita_numeros_dos_dossies_e_rejeita_inventados():
    fin, mkt = _fin(), _mkt()
    inv = investment.analisar(fin, {}, mkt).to_dict()
    ds = [fin, mkt, inv]
    bom = redator.texto_modelo(fin, mkt, inv)
    assert redator.validar(" ".join(bom.values()), ds) == []
    assert redator.validar("ROE de 20,0% [F1] em 2026, 3 cenários", ds) == []
    assert redator.validar("ROE de 31,7% e preço-alvo de R$ 55,00", ds) == ["31,7%", "R$ 55,00"]
    # número que existe, mas com outra unidade, não passa: VPA é R$ 10,00, não 10,0%
    assert redator.validar("crescimento de 10,0%", ds) == ["10,0%"]


def test_decimal_br_nao_estraga_milhares_nem_normas():
    assert decimal_br("cresceu 9.1% (+1.18 p.p.)") == "cresceu 9,1% (+1,18 p.p.)"
    assert decimal_br("Resolução CMN 4.966 e 1.000 ações") == "Resolução CMN 4.966 e 1.000 ações"


def test_itau_com_dados_em_cache():
    from indicadores_b3.agents import financial
    try:
        fin = financial.analisar("ITUB4").to_dict()
    except Exception as e:  # arquivos ainda não baixados / sem internet
        pytest.skip(f"Dados do Itaú indisponíveis: {e}")
    assert fin["extras"]["tipo"] == "banco"
    roe = next((x for x in fin["itens"] if x["nome"] == "ROE"), None)
    assert roe and 5 < roe["valor"] < 40, "ROE do Itaú fora de uma faixa plausível"
    for x in fin["itens"]:
        if x["tipo"] == "fato":
            assert x["fonte"]["fonte"] and x["fonte"]["data_ref"], x["nome"]


def test_agente_usa_ferramentas_e_rejeita_numero_inventado(monkeypatch):
    """Modelo de mentira com roteiro fixo: chama ferramentas, inventa um número, é corrigido."""
    from indicadores_b3.agents import agente, llm
    mkt = _mkt()
    monkeypatch.setattr(agente.financial, "analisar", lambda t: type("D", (), {"to_dict": lambda s: _fin() if t == "TEST4" else _fin(roe=12, pvp=0.8)})())
    monkeypatch.setattr(agente.market, "analisar", lambda t, tipo: type("D", (), {"to_dict": lambda s: mkt})())
    chamada = lambda i, n, a="{}": {"id": i, "type": "function", "function": {"name": n, "arguments": a}}  # noqa: E731
    roteiro = [
        {"content": None, "tool_calls": [chamada("1", "analise_financeira", '{"ticker":"TEST4"}'), chamada("2", "analise_financeira", '{"ticker":"PAR3"}')]},
        {"content": None, "tool_calls": [chamada("3", "valuation")]},
        {"content": "## Resumo\nROE de 20,0% [F1] e preço-alvo de R$ 99,00."},
        {"content": "## Resumo\nROE de 20,0% [F1] contra 12,0% [PAR3.F1]."},
    ]
    monkeypatch.setattr(llm, "disponiveis", lambda: [("teste", "modelo")])
    monkeypatch.setattr(llm, "conversar", lambda *a, **k: roteiro.pop(0))
    ag = agente.Agente("TEST4", ["PAR3"])
    out = ag.rodar()
    assert out["texto"].endswith("12,0% [PAR3.F1].")
    assert [p["nome"] for p in out["passos"] if p["tipo"] == "ferramenta"] == ["analise_financeira", "analise_financeira", "valuation"]
    assert any("R$ 99,00" in p["texto"] for p in out["passos"] if p["tipo"] == "rascunho")
    assert ag.inv is not None and ag.pares["PAR3"]["itens"][0]["id"] == "PAR3.F1"


def test_agente_empacado_perde_so_a_frase_com_numero_inventado(monkeypatch):
    """Com o validador de verdade: o modelo insiste num preço-alvo inventado; só essa frase sai, o resto é aprovado."""
    from indicadores_b3.agents import agente, llm
    mkt = _mkt()
    monkeypatch.setattr(agente.financial, "analisar", lambda t: type("D", (), {"to_dict": lambda s: _fin() if t == "TEST4" else _fin(roe=12, pvp=0.8)})())
    monkeypatch.setattr(agente.market, "analisar", lambda t, tipo: type("D", (), {"to_dict": lambda s: mkt})())
    chamada = lambda i, n, a="{}": {"id": i, "type": "function", "function": {"name": n, "arguments": a}}  # noqa: E731
    texto = ("## Resumo\nROE de 20,0% [F1], acima dos pares. O preço-alvo é R$ 99,00. Nos pares o ROE é 12,0% [PAR3.F1].\n"
             "## Riscos\n- Juros altos pesam no custo de capital.")
    roteiro = [
        {"content": None, "tool_calls": [chamada("1", "analise_financeira", '{"ticker":"TEST4"}'), chamada("2", "analise_financeira", '{"ticker":"PAR3"}')]},
        {"content": None, "tool_calls": [chamada("3", "valuation")]},
        {"content": texto}, {"content": texto},
    ]
    monkeypatch.setattr(llm, "disponiveis", lambda: [("teste", "modelo")])
    monkeypatch.setattr(llm, "conversar", lambda *a, **k: roteiro.pop(0))
    out = agente.Agente("TEST4", ["PAR3"]).rodar()
    assert out["texto"] == ("## Resumo\nROE de 20,0% [F1], acima dos pares. Nos pares o ROE é 12,0% [PAR3.F1].\n"
                            "## Riscos\n- Juros altos pesam no custo de capital.")
    assert not roteiro  # não pediu uma 3ª reescrita


def test_valuation_banco_roe_abaixo_de_g_nao_da_preco_negativo():
    """Caso real (BBAS3, nov/2026): ROE 5,9% < g 8,1% dava P/VP justo negativo e potencial de −147%."""
    inv = investment.analisar(_fin(roe=5.9, vpa=32.6, preco=15.1, pvp=0.463), {}, _mkt(rf=15.3, inf=7.0)).to_dict()
    ke = _val(inv, "Ke (CAPM)")
    for c in ("pessimista", "base", "otimista"):
        assert _val(inv, f"P/VP justo — {c}") > 0, c
        assert _val(inv, f"Potencial — {c}") > -100, c
    # sem crescimento quando ROE < Ke: P/VP = ROE ÷ Ke
    assert _val(inv, "P/VP justo — base") == pytest.approx(5.9 / ke)
    assert any("crescimento zero" in a["texto"] for a in inv["alertas"])
    # com P/VP < 1, as leituras implícitas também usam crescimento zero e ficam coerentes
    assert _val(inv, "Ke implícito no preço") == pytest.approx(5.9 / 0.463)
    assert _val(inv, "ROE sustentável implícito no preço") == pytest.approx(0.463 * ke)
    assert all(p is None or p >= 0 for linha in inv["extras"]["sensibilidade"]["precos"] for p in linha)


def test_valuation_banco_com_prejuizo_vira_ausente():
    inv = investment.analisar(_fin(roe=2.0, pvp=0.5, preco=5.0), {}, _mkt()).to_dict()  # pessimista: 2 − 4 = −2%
    assert not any(x["nome"] == "Preço justo — pessimista" for x in inv["itens"])
    assert any(a["nome"] == "Preço justo — pessimista" for a in inv["ausentes"])
    assert not any(x["nome"] == "Potencial ponderado" for x in inv["itens"])  # ponderado só com os 3 cenários


def test_pvp_justo_continuo_em_roe_igual_ke():
    g = 5.0
    abaixo, acima = investment._pvp_justo(17.0 - 1e-9, 17.0, g), investment._pvp_justo(17.0, 17.0, g)
    assert abaixo[0] == pytest.approx(1.0) and acima[0] == pytest.approx(1.0)
    assert investment._pvp_justo(-1.0, 17.0, g) is None
