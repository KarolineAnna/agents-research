"""Robustez do núcleo de agentes e do cliente de IA (tudo simulado, sem internet)."""
import json

import pytest

from indicadores_b3.agents import llm
from indicadores_b3.agents.nucleo import AgenteFerramentas, Ferramenta
from indicadores_b3.agents.qualidade import validar_json


def chamada(i, nome, args="{}"):
    return {"id": str(i), "type": "function", "function": {"name": nome, "arguments": args}}


def _agente(roteiro, monkeypatch, provs=(("p1", "m1"),), **kw):
    vistos = []

    def falso(p, m, msgs, tools, **_):
        vistos.append((p, msgs[-1]))
        item = roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm, "conversar", falso)
    contador = {"n": 0}

    def soma(a: int, b: int):
        contador["n"] += 1
        return {"total": a + b}

    def quebra():
        raise RuntimeError("falhou lá dentro")

    ferr = [Ferramenta("soma", "soma dois números", soma, {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}),
            Ferramenta("quebra", "sempre falha", quebra)]
    return AgenteFerramentas("sistema", ferr, provedores=list(provs), **kw), vistos, contador


def test_ferramenta_com_erro_invalida_ou_inexistente_nao_derruba(monkeypatch):
    roteiro = [{"content": "", "tool_calls": [chamada(1, "quebra"), chamada(2, "nao_existe"), chamada(3, "soma", "{a:1")]},
               {"content": "pronto"}]
    ag, vistos, _ = _agente(roteiro, monkeypatch)
    r = ag.rodar("faça")
    assert r.texto == "pronto"
    erros = [p["resumo"] for p in r.passos if p["tipo"] == "ferramenta"]
    assert "RuntimeError" in erros[0] and "desconhecida" in erros[1] and "inválidos" in erros[2]


def test_chamada_repetida_reaproveita_resultado(monkeypatch):
    roteiro = [{"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":2}')]},
               {"content": "", "tool_calls": [chamada(2, "soma", '{"b":2,"a":1}')]},
               {"content": "3"}]
    ag, _, cont = _agente(roteiro, monkeypatch)
    r = ag.rodar("x")
    assert cont["n"] == 1 and "reaproveitado" in r.passos[1]["resumo"]


def test_troca_de_provedor_quando_um_falha(monkeypatch):
    roteiro = [llm.ErroProvedor("p1: limite gratuito atingido (429)"), {"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":1}')]},
               {"content": "2"}]
    ag, vistos, _ = _agente(roteiro, monkeypatch, provs=(("p1", "m1"), ("p2", "m2")))
    r = ag.rodar("x")
    assert r.texto == "2" and r.provedores == ["p2 · m2"] and vistos[1][0] == "p2"


def test_exige_investigacao_e_limite_de_passos(monkeypatch):
    roteiro = [{"content": "chute sem investigar"}] + \
              [{"content": "", "tool_calls": [chamada(i, "soma", json.dumps({"a": i, "b": 0}))]} for i in range(3)] + [{"content": "fim"}]
    ag, vistos, _ = _agente(roteiro, monkeypatch, max_passos=3)
    r = ag.rodar("x")
    assert r.texto == "fim" and r.metricas["chamadas_ferramenta"] == 3
    assert any("sem investigar" in p["texto"] for p in r.passos if p["tipo"] == "info")
    assert any("Limite" in p["texto"] for p in r.passos if p["tipo"] == "info")


def test_validador_reprova_e_descarta(monkeypatch):
    roteiro = [{"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":1}')]}, {"content": "ruim"}, {"content": "ruim de novo"}]
    ag, _, _ = _agente(roteiro, monkeypatch, validar=lambda t: ["está ruim"] if "ruim" in t else [], max_correcoes=1)
    r = ag.rodar("x")
    assert r.texto is None and r.metricas["correcoes"] == 1


def test_llm_tenta_de_novo_no_429_e_desiste_no_401(monkeypatch):
    class Resp:
        def __init__(self, code, corpo=None, headers=None):
            self.status_code, self._c, self.headers, self.text = code, corpo, headers or {}, "x"

        def json(self):
            return self._c

    seq = [Resp(429, headers={"Retry-After": "1"}), Resp(503), Resp(200, {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 5}})]
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: seq.pop(0))
    esperas = []
    out = llm.conversar("ollama", "m", [], [], dormir=esperas.append)
    assert out["content"] == "ok" and out["_uso"]["prompt_tokens"] == 5 and esperas == [1.0, 6]
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: Resp(401))
    with pytest.raises(llm.ErroProvedor) as e:
        llm.conversar("ollama", "m", [], [], dormir=esperas.append)
    assert e.value.transitorio is False


def test_validador_do_agente_de_qualidade():
    ok = '[{"campo": "pl", "regra": "fora_da_faixa", "causa": "dado_real", "evidencia": "prejuízo em 3.11"}]'
    assert validar_json("Resultado:\n" + ok) == []
    assert validar_json('[{"campo": "pl", "regra": "x", "causa": "talvez", "evidencia": "-"}]')
    assert validar_json("sem json")


def test_503_espera_mais_e_gemini_tem_modelos_reserva(monkeypatch):
    class Resp:
        def __init__(self, code, corpo=None):
            self.status_code, self._c, self.headers, self.text = code, corpo, {}, "x"

        def json(self):
            return self._c

    seq = [Resp(503), Resp(503), Resp(503)]
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: seq.pop(0))
    esperas = []
    with pytest.raises(llm.ErroProvedor) as e:
        llm.conversar("ollama", "m", [], [], dormir=esperas.append)
    # sobrecarga: só 2 tentativas (uma espera de 3 s), para o agente passar logo ao próximo modelo
    assert esperas == [3] and len(seq) == 1 and "sobrecarregado" in str(e.value) and e.value.transitorio
    assert llm._reservas_gemini(["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.8-flash-lite"]) == \
        ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.5-flash"]


def test_tempo_esgotado_passa_ao_proximo_sem_insistir(monkeypatch):
    chamadas = []

    def lento(*a, **k):
        chamadas.append(k["timeout"])
        raise llm.requests.Timeout("parado")
    monkeypatch.setattr(llm.requests, "post", lento)
    with pytest.raises(llm.ErroProvedor) as e:
        llm.conversar("gemini", "g", [], [], dormir=lambda s: None)
    assert chamadas == [llm.TIMEOUT_PADRAO] and "não respondeu em 60 s" in str(e.value)
    chamadas.clear()
    with pytest.raises(llm.ErroProvedor):
        llm.conversar("ollama", "m", [], [], dormir=lambda s: None)
    assert chamadas == [240]  # o Ollama roda no PC: espera mais


def _valida_numero(t):
    return ["número 49 sem fonte"] if "49" in t else []


def test_modelo_empacado_tem_so_a_frase_reprovada_retirada(monkeypatch):
    texto = "## Tese\nA receita cresceu [F1]. A margem é de 49 pontos. O caixa é forte [F2].\n- Risco de juros [M1]."
    roteiro = [{"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":1}')]}, {"content": texto}, {"content": texto}]
    ag, _, _ = _agente(roteiro, monkeypatch, validar=_valida_numero, max_correcoes=2, podar=True)
    r = ag.rodar("x")
    assert r.texto == "## Tese\nA receita cresceu [F1]. O caixa é forte [F2].\n- Risco de juros [M1]."
    assert r.metricas["correcoes"] == 1  # a 2ª reprovação igual já poda: não gasta a 3ª chamada
    assert any("frase(s)" in p.get("texto", "") for p in r.passos)


def test_poda_nao_salva_texto_que_perderia_metade(monkeypatch):
    ruim = "O lucro é 49. A margem é 49. Fim."
    roteiro = [{"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":1}')]}, {"content": ruim}, {"content": ruim}, {"content": ruim}]
    ag, _, _ = _agente(roteiro, monkeypatch, validar=_valida_numero, max_correcoes=2, podar=True)
    assert ag.rodar("x").texto is None


def test_sem_poda_o_comportamento_antigo_continua(monkeypatch):
    texto = "A receita cresceu. A margem é de 49 pontos. O caixa é forte."
    roteiro = [{"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":1}')]}, {"content": texto}, {"content": texto}, {"content": texto}]
    ag, _, _ = _agente(roteiro, monkeypatch, validar=_valida_numero, max_correcoes=2)
    assert ag.rodar("x").texto is None


def test_metricas_mostram_tempo_de_cada_chamada_a_ia(monkeypatch):
    roteiro = [llm.ErroProvedor("p1 (m1): servidor sobrecarregado (503)"),
               {"content": "", "tool_calls": [chamada(1, "soma", '{"a":1,"b":1}')]}, {"content": "pronto"}]
    ag, _, _ = _agente(roteiro, monkeypatch, provs=(("p1", "m1"), ("p2", "m2")))
    m = ag.rodar("x").metricas
    assert [(c["provedor"], c["ok"]) for c in m["chamadas_ia"]] == [("p1 · m1", False), ("p2 · m2", True), ("p2 · m2", True)]
    assert m["segundos_ia"] >= 0 and "segundos_ferramentas" in m
