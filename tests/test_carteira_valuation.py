"""Gráfico de preço, cara/barata e agente de carteira, com dados sintéticos (sem internet)."""
import json

import numpy as np
import pandas as pd
import pytest

from indicadores_b3.agents import carteira_agente as ca
from indicadores_b3.agents import redator
from indicadores_b3.analytics import historico_preco as hp
from indicadores_b3.analytics import valuation_rapido as vr

IDX = pd.bdate_range("2016-01-04", "2026-10-30")


def _serie(mu, sig, seed, idx=IDX):
    r = np.random.default_rng(seed).normal(mu / 252, sig / np.sqrt(252), len(idx))
    return pd.Series(np.cumprod(1 + r) * 10, index=idx)


# ---------- gráfico de preço ----------
def test_historico_preco_estatisticas_e_reducao():
    fech = _serie(0.1, 0.25, 1)
    div = pd.Series(0.0, index=IDX)
    div.iloc[::126] = 0.2
    total = fech * (1 + (div > 0) * 0.01).cumprod()

    def baixar(simbolo, periodo):
        base = _serie(0.08, 0.2, 9) if simbolo == "^BVSP" else fech
        return pd.DataFrame({"Close": base, "Adj Close": total if simbolo != "^BVSP" else base, "Dividends": div if simbolo != "^BVSP" else 0.0})
    r = hp.historico("PETR4", "10y", baixar_fn=baixar)
    s = r["estatisticas"]
    assert r["semanal"] and len(r["datas"]) <= hp.MAX_PONTOS + 1 and r["datas"][-1] == "2026-10-30"
    assert s["variacao_preco"] == pytest.approx((fech.iloc[-1] / fech.iloc[0] - 1) * 100)
    assert s["retorno_total"] > s["variacao_preco"]  # proventos somam
    assert s["drawdown_max"] < 0 and s["minima"] <= s["maxima"]
    assert r["total_base100"][0] == 100 and r["ibov_base100"][0] == 100
    assert sum(r["proventos_por_ano"].values()) == pytest.approx(div.sum())
    with pytest.raises(ValueError):
        hp.historico("BTC", "5y", baixar_fn=baixar)


# ---------- cara ou barata ----------
def test_leitura_e_limiar():
    assert vr.leitura(-20) == "barata" and vr.leitura(20) == "cara" and vr.leitura(10) == "justa"
    assert vr.leitura(30, invertido=True) == "barata" and vr.leitura(None) is None


def test_multiplos_historicos_sem_quantidade_de_acoes():
    idx = pd.bdate_range("2023-01-02", "2026-10-30")
    fech = pd.Series(np.linspace(10, 20, len(idx)), index=idx)
    atual = {"pl_mult": 10.0, "pvp": 2.0, "lucro": 200.0, "pl": 1000.0}
    contabil = {2024: {"lucro": 100.0, "pl": 800.0, "documento": "DFP 2024"}, 2025: {"lucro": -5.0, "pl": 900.0, "documento": "DFP 2025"}}
    h = {x["ano"]: x for x in vr.multiplos_historicos(atual, contabil, fech)}
    p24 = fech[fech.index <= "2024-12-31"].iloc[-1]
    # P/L(2024) = 10 × (p24/20) × (200/100); P/VP(2024) = 2 × (p24/20) × (1000/800)
    assert h[2024]["p_l"] == pytest.approx(10 * p24 / 20 * 2)
    assert h[2024]["p_vp"] == pytest.approx(2 * p24 / 20 * 1.25)
    assert h[2025]["p_l"] is None  # prejuízo: P/L não se aplica


def test_dcf_por_acao_igual_gordon_sem_crescimento_extra():
    # crescimento igual a g nos dois estágios e sem meio de ano = perpetuidade de Gordon
    v = vr.dcf_por_acao(100, 12, 4, 4, 0, 10, anos=5, anos2=5, meio=False)
    assert v == pytest.approx(100 * 1.04 / (0.12 - 0.04) / 10, rel=1e-9)
    assert vr.dcf_por_acao(100, 3, 4, 4, 0, 10) is None


def test_avaliar_junta_as_tres_lentes(monkeypatch):
    base = {"tipo": "acao", "empresa": "X", "banco": False, "valores": {"preco": 20.0, "lucro_contr": 200.0, "pl_contr": 1000.0},
            "indicadores": [{"id": "pl", "valor": 15.0}, {"id": "pvp", "valor": 3.0}]}
    idx = pd.bdate_range("2019-01-02", "2026-10-30")
    precos = pd.DataFrame({"Close": np.full(len(idx), 20.0)}, index=idx)
    monkeypatch.setattr(vr, "contabil_por_ano", lambda cnpj, *a, **k: {a_: {"lucro": 200.0, "pl": 1000.0, "documento": "DFP"} for a_ in range(2019, 2026)})
    monkeypatch.setattr(vr.f, "mapa_tickers", lambda: {"XPTO3": "1"})
    if True:
        r = vr.avaliar("XPTO3", calcular=lambda t: base, precos_fn=lambda s: precos,
                       pares_fn=lambda t: {"pares": [{"ticker": "A", "p_l": 10.0, "p_vp": 2.0}], "mediana_p_l": 10.0, "mediana_p_vp": 2.0},
                       dcf_fn=lambda t: {"rastreio": {"fcl": {"valor": 1.0}, "preco": {"valor": 20.0}, "acoes": {"valor": 10.0},
                                                      "divida_bruta": {"valor": 0.0}, "caixa": {"valor": 0.0}}, "wacc": {}})
    lentes = {x["id"]: x for x in r["lentes"]}
    assert lentes["historia"]["leitura"] == "justa"   # mesmo múltiplo todo ano
    assert lentes["pares"]["leitura"] == "cara"       # 15x contra 10x
    assert lentes["justo"]["leitura"] == "cara"       # FCL minúsculo: preço justo bem abaixo do preço
    assert r["veredito"] == "cara" and "mistos" in r["texto"]


# ---------- agente de carteira ----------
def _diag(pesos):
    idx = pd.bdate_range("2023-11-01", "2026-10-30")
    S = {"AAAA3": _serie(0.25, 0.3, 1, idx), "BBBB3": _serie(-0.3, 0.5, 2, idx), "CCCC3": _serie(0.1, 0.25, 3, idx),
         "DDDD3": _serie(0.05, 0.2, 4, idx)}
    ib = _serie(0.12, 0.2, 0, idx)
    return ca.diagnosticar(pesos, "3y", rf_pct=14.0, serie_fn=lambda t: S[t], ibov_fn=lambda: ib, setor_fn=lambda t: "Setor " + t[0]).to_dict()


def test_diagnostico_atribuicao_soma_a_diferenca_e_renda_fixa_fixa():
    pesos = {"AAAA3": 40, "BBBB3": 20, "CCCC3": 10, "DDDD3": 10, ca.RF_ID: 20}
    d = _diag(pesos)
    at = d["extras"]["atribuicao"]
    assert sum(x["peso"] for x in at) == pytest.approx(100)
    # soma dos efeitos = soma dos retornos diários da carteira − do Ibovespa (identidade exata)
    assert sum(x["efeito"] for x in at) == pytest.approx(sum(x["efeito"] for x in d["extras"]["setores"]))
    for t in d["extras"]["testes"]:
        assert t["pesos"].get(ca.RF_ID) == pytest.approx(20)          # o agente nunca mexe na renda fixa
        assert sum(t["pesos"].values()) == pytest.approx(100)
    lim = next((t for t in d["extras"]["testes"] if t["id"] == "limite"), None)
    assert lim and max(v for k, v in lim["pesos"].items() if k != ca.RF_ID) <= ca.LIMITE_PESO + 1e-6
    txt = ca.texto_regras(d)
    assert set(txt) == {"diagnostico", "quem", "riscos", "testar", "leitura", "limitacoes"}
    assert redator.validar(" ".join(txt.values()), [d]) == []
    assert not any(c in " ".join(txt.values()) for c in "—–")


def test_regras_decididas_so_com_o_treino():
    idx = pd.bdate_range("2024-01-01", periods=200)
    treino = pd.DataFrame({"AAAA3": np.r_[[-0.01] * 100, [0.05] * 100][:100], "BBBB3": [0.001] * 100, "_IBOV": [0.0] * 100}, index=idx[:100])
    rs = ca.regras({"AAAA3": 50, "BBBB3": 50}, treino)
    assert "AAAA3" not in rs["sem_pior"][1] and rs["sem_pior"][1]["BBBB3"] == pytest.approx(100)


def _agente():
    idx = pd.bdate_range("2023-11-01", "2026-10-30")
    S = {"AAAA3": _serie(0.25, 0.3, 1, idx), "BBBB3": _serie(-0.3, 0.5, 2, idx), "CCCC3": _serie(0.1, 0.25, 3, idx),
         "EEEE3": _serie(0.2, 0.25, 5, idx)}
    ib = _serie(0.12, 0.2, 0, idx)
    return ca.AgenteCarteira({"AAAA3": 40, "BBBB3": 30, "CCCC3": 10, ca.RF_ID: 20}, "3y", rf_pct=14.0, serie_fn=lambda t: S[t],
                             ibov_fn=lambda: ib, setor_fn=lambda t: "Setor", pares_fn=lambda t, n: {"ticker": t, "setor": "X", "pares": [{"ticker": "EEEE3"}]})


def test_laboratorio_impoe_as_regras_e_esconde_a_reserva():
    ag = _agente()
    lab = ag.lab
    assert lab.treino.index[-1] < lab.reserva.index[0] and len(lab.jt) == 3 and len(lab.jr) == 2
    with pytest.raises(ValueError, match="renda fixa"):
        lab.testar({"AAAA3": 50, "RENDA FIXA": 50}, "mexe na RF")
    with pytest.raises(ValueError, match="Peso máximo"):
        lab.testar({"AAAA3": 90, "CCCC3": 10}, "concentra")
    with pytest.raises(ValueError, match="testes"):
        lab.confirmar([1])  # nada testado ainda
    r = lab.testar({"AAAA3": 40, "CCCC3": 20, "EEEE3": 20}, "troca BBBB3 por EEEE3 (ativo fora da carteira)")
    assert r["trocas"] == {"entra": ["EEEE3"], "sai": ["BBBB3"]}
    t = lab.testes[0]
    assert t["_pesos"][ca.RF_ID] == pytest.approx(20) and sum(t["_pesos"].values()) == pytest.approx(100)
    assert "reserva" not in str(r).replace("a reserva decide", "")  # o teste não devolve nada da reserva
    lab.testar({"AAAA3": 40, "BOVA11": 40}, "metade no índice")
    c = lab.confirmar([1, 2])
    assert {x["status"] for x in lab.confirmacao} <= {"aprovada", "inconclusiva", "reprovada"} and len(c["resultados"]) == 2
    with pytest.raises(ValueError):
        lab.testar({"AAAA3": 40, "CCCC3": 40}, "depois de ver a reserva")
    with pytest.raises(ValueError):
        lab.confirmar([1])


def test_agente_sem_ia_usa_as_regras_como_hipoteses():
    r = _agente().rodar(usar_ia=False)
    lab = r["laboratorio"]
    assert r["modo"] == "regras" and len(lab["testes"]) >= 3 and lab["confirmacao"]
    assert {"diagnostico", "quem", "hipoteses", "confirmacao", "riscos", "leitura", "limitacoes"} <= set(r["secoes"])
    txt = " ".join(r["secoes"].values())
    assert redator.validar(txt, [r["diagnostico"], r["laboratorio_dossie"]]) == []
    assert not any(ch in txt for ch in "—–")


def test_agente_investiga_com_ia_falsa(monkeypatch):
    from indicadores_b3.agents import llm
    ag = _agente()
    tc = lambda i, n, a: {"id": i, "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}  # noqa: E731
    estado = {"n": 0}

    def falso(p, m, msgs, tools, **k):
        estado["n"] += 1
        n = estado["n"]
        if n == 1:
            return {"content": "", "tool_calls": [tc("1", "diagnostico_treino", {})]}
        if n == 2:
            return {"content": "Escrevendo já."}  # tenta escrever sem testar: o validador barra
        if n == 3:
            return {"content": "", "tool_calls": [tc("2", "testar_carteira", {"pesos": {"AAAA3": 40, "CCCC3": 40}, "motivo": "sem BBBB3"}),
                                                  tc("3", "testar_carteira", {"pesos": {"AAAA3": 40, "EEEE3": 40}, "motivo": "troca por par"}),
                                                  tc("4", "testar_carteira", {"pesos": {"AAAA3": 90}, "motivo": "concentra"})]}
        if n == 4:
            return {"content": "", "tool_calls": [tc("5", "confirmar_propostas", {"testes": [1, 2]})]}
        st = ag.lab.confirmacao[0]
        it = {x["id"]: x for x in ag.lab.D.itens}
        i = st["ids"]["dif"]
        return {"content": f"## Diagnóstico\nTeste.\n## O que passou na confirmação\n- Teste 1 — {st['status']}: {redator.fmt(it[i]['valor'], 'p.p.')} [{i}].\n"
                           "## Leitura final\nOpinião: teste."}
    monkeypatch.setattr(llm, "conversar", falso)
    monkeypatch.setattr(llm, "disponiveis", lambda: [("teste", "m")])
    r = ag.rodar()
    assert r["modo"] == "agente" and len(r["laboratorio"]["testes"]) == 2          # o de 90% foi recusado pelo código
    assert any(p["tipo"] == "ferramenta" and "erro" in p.get("resumo", "") or "Peso máximo" in p.get("resumo", "") for p in r["passos"])
    assert any(p["tipo"] == "rascunho" and "problemas: nenhum" not in p["texto"] for p in r["passos"])  # barrado antes de testar
    assert "—" not in r["secoes"]["confirmacao"] and r["secoes"]["hipoteses"]
