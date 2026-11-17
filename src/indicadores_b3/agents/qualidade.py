"""Agente de qualidade de dados: investiga os problemas que as checagens automáticas apontam num ticker.

Gratuito: usa o mesmo núcleo e os mesmos provedores do agente de pesquisa (Gemini/Groq grátis ou Ollama local).
Ferramentas: linhas brutas da CVM, campos do yfinance e o rastreio do cálculo. A IA classifica cada problema em
``dado_real`` (estranho, mas correto), ``erro_fonte`` (CVM/yfinance com dado faltando ou errado) ou ``erro_calculo``.

Uso: ``python -m indicadores_b3.agents.qualidade PETR4 ITUB4``
"""
from __future__ import annotations

import json
import re
import sys

from indicadores_b3.agents.nucleo import AgenteFerramentas, Ferramenta
from indicadores_b3.analytics.indicadores import calcular
from indicadores_b3.data.fundamentos import demonstrativo, mapa_tickers
from indicadores_b3.quality.qualidade import checar

SISTEMA = """Você é analista de qualidade de dados de indicadores fundamentalistas da B3, em português.
Recebe indicadores calculados a partir de ITR/DFP da CVM e os problemas apontados por checagens automáticas.
Para cada problema, investigue com as ferramentas e classifique a causa provável:
- dado_real (o valor é estranho mas correto: prejuízo, empresa alavancada, banco com plano de contas próprio)
- erro_fonte (CVM ou yfinance com dado faltando ou errado)
- erro_calculo (conta errada, escala, units, ações em milhares, plano de contas diferente)
Use as ferramentas antes de concluir. Não invente valores: cite as contas e os números que as ferramentas mostraram.
Responda APENAS com um JSON: [{"campo", "regra", "causa", "evidencia", "acao_sugerida"}]."""

CAUSAS = {"dado_real", "erro_fonte", "erro_calculo"}


def contas_cvm(ticker: str, demonstrativo_: str = "DRE_con", prefixo_conta: str = "") -> dict:
    cnpj = mapa_tickers().get(ticker.upper())
    if not cnpj:
        return {"erro": f"{ticker} não está no cadastro da CVM"}
    df = demonstrativo(demonstrativo_, cnpj)
    if "CD_CONTA" in df and prefixo_conta:
        df = df[df.CD_CONTA.str.startswith(prefixo_conta)]
    cols = [c for c in ["FONTE", "DT_REFER", "ORDEM_EXERC", "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL", "ESCALA_MOEDA",
                        "QT_ACAO_TOTAL_CAP_INTEGR", "QT_ACAO_TOTAL_TESOURO"] if c in df]
    return {"linhas": df[cols or list(df.columns)].tail(60).astype(str).to_dict("records")}


def dados_yfinance(ticker: str, campos: list[str]) -> dict:
    import yfinance as yf

    info = yf.Ticker(f"{ticker.upper()}.SA").info or {}
    return {c: info.get(c) for c in campos}


def validar_json(texto: str) -> list[str]:
    m = re.search(r"\[.*\]", texto, re.S)
    if not m:
        return ["a resposta precisa ser uma lista JSON"]
    try:
        itens = json.loads(m.group(0))
    except ValueError as e:
        return [f"JSON inválido ({e})"]
    erros = [f"item {i} sem campo {k}" for i, it in enumerate(itens) for k in ("campo", "regra", "causa", "evidencia") if k not in it]
    erros += [f"causa inválida no item {i}: {it.get('causa')}" for i, it in enumerate(itens) if it.get("causa") not in CAUSAS]
    return erros


def investigar(ticker: str) -> dict:
    r = calcular(ticker)
    problemas = [p for p in checar(r) if p.get("severidade") != "info"]
    if not problemas:
        return {"ticker": ticker, "problemas": [], "diagnostico": [], "passos": []}
    ferramentas = [
        Ferramenta("contas_cvm", "Linhas brutas de um demonstrativo da CVM do ticker, filtrando por prefixo de conta.", contas_cvm,
                   {"type": "object", "properties": {
                       "ticker": {"type": "string"},
                       "demonstrativo_": {"type": "string", "enum": ["DRE_con", "BPA_con", "BPP_con", "DVA_con", "composicao_capital"]},
                       "prefixo_conta": {"type": "string", "description": "ex.: '3.11' ou '2.03'. Vazio = todas."}},
                    "required": ["ticker", "demonstrativo_"]}),
        Ferramenta("dados_yfinance", "Campos do yfinance (info) para comparar, ex.: trailingPE, priceToBook, sharesOutstanding.",
                   dados_yfinance, {"type": "object", "properties": {"ticker": {"type": "string"},
                                                                     "campos": {"type": "array", "items": {"type": "string"}}},
                                    "required": ["ticker", "campos"]}),
        Ferramenta("rastreio", "Como cada valor de base do ticker foi calculado (contas, documentos, notas).",
                   lambda campo: {"campo": campo, **(r.get("rastreio") or {}).get(campo, {"erro": "campo inexistente"})},
                   {"type": "object", "properties": {"campo": {"type": "string"}}, "required": ["campo"]}),
    ]
    pedido = json.dumps({"ticker": ticker, "valores": r["valores"], "problemas": problemas}, ensure_ascii=False, default=str)
    res = AgenteFerramentas(SISTEMA, ferramentas, validar_json, max_passos=10).rodar(pedido)
    diag = json.loads(re.search(r"\[.*\]", res.texto, re.S).group(0)) if res.texto else []
    return {"ticker": ticker, "problemas": problemas, "diagnostico": diag, **res.to_dict()}


if __name__ == "__main__":
    for tk in sys.argv[1:] or ["PETR4"]:
        print(json.dumps(investigar(tk.upper()), ensure_ascii=False, indent=2, default=str))
