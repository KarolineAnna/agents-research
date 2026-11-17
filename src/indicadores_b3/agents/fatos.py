"""Dossiê: o "caderno" de cada agente, onde cada número tem id, tipo, fonte, data e fórmula.

Tipos de item:
  fato       número lido de uma fonte (CVM, Banco Central, B3…) — com documento, conta e data
  calculado  número derivado de outros por uma fórmula — guarda a fórmula e os ids usados
  premissa   valor escolhido (por você ou pelo modelo), com justificativa
  estimativa resultado de um modelo (valuation, cenário) — depende de premissas
Além disso: ausentes (dados que não foram encontrados), alertas e leituras (inferências/opiniões).
"""
from __future__ import annotations

import math
import re
from datetime import datetime


class Dossie:
    def __init__(self, agente: str, prefixo: str, assunto: str):
        self.agente, self.prefixo, self.assunto = agente, prefixo, assunto
        self.itens: list[dict] = []
        self.ausentes: list[dict] = []
        self.alertas: list[dict] = []
        self.leituras: list[dict] = []
        self.secoes: dict[str, list[str]] = {}
        self.extras: dict = {}
        self.gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---------- itens ----------
    def _add(self, item: dict, secao: str | None) -> str:
        item["id"] = f"{self.prefixo}{len(self.itens) + 1}"
        v = item.get("valor")
        if v is not None and (not isinstance(v, int | float) or not math.isfinite(v)):
            item["valor"] = None
        self.itens.append(item)
        if secao:
            self.secoes.setdefault(secao, []).append(item["id"])
        return item["id"]

    def fato(self, nome, valor, unidade, fonte: dict, secao=None, nota="") -> str | None:
        """fonte: {fonte, documento, url, data_ref, periodo, conta, descricao} (formato do rastreio do site)."""
        if valor is None:
            self.ausente(nome, f"Não encontrado em {fonte.get('fonte', 'fonte')} · {fonte.get('documento', '')}".strip(" ·"))
            return None
        return self._add({"tipo": "fato", "nome": nome, "valor": float(valor), "unidade": unidade,
                          "fonte": {k: fonte.get(k) for k in ("fonte", "documento", "url", "data_ref", "periodo", "conta", "descricao")},
                          "nota": nota}, secao)

    def fato_rastro(self, nome, rastro: dict, unidade, secao=None) -> str | None:
        """Converte um 'rastro' do site (valor + componentes CVM) num fato."""
        if not rastro or rastro.get("valor") is None:
            self.ausente(nome, (rastro or {}).get("nota") or "Não encontrado nas fontes.")
            return None
        comps = rastro.get("componentes") or []
        c0 = comps[0] if comps else {}
        datas = sorted({c.get("data_ref") for c in comps if c.get("data_ref")})
        fonte = {**c0, "data_ref": datas[-1] if datas else c0.get("data_ref"),
                 "conta": " · ".join(f"{c.get('sinal', '+')}{c.get('conta')}" for c in comps) if len(comps) > 1 else c0.get("conta")}
        i = self.fato(nome, rastro["valor"], unidade, fonte, secao, rastro.get("nota", ""))
        if i:
            self.get(i)["componentes"] = [{k: c.get(k) for k in ("papel", "sinal", "fonte", "documento", "url", "data_ref",
                                                                  "periodo", "conta", "descricao", "valor")} for c in comps]
        return i

    def calc(self, nome, valor, unidade, formula, insumos: list, secao=None, nota="") -> str | None:
        if any(i is None for i in insumos) or valor is None:
            faltam = [n for n in insumos if n is None]
            self.ausente(nome, f"Faltam dados para calcular ({formula})." if faltam else "Cálculo indefinido (divisão por zero?).")
            return None
        return self._add({"tipo": "calculado", "nome": nome, "valor": float(valor), "unidade": unidade,
                          "formula": formula, "insumos": insumos, "nota": nota}, secao)

    def premissa(self, nome, valor, unidade, justificativa, secao=None) -> str:
        return self._add({"tipo": "premissa", "nome": nome, "valor": float(valor), "unidade": unidade,
                          "nota": justificativa}, secao)

    def estimativa(self, nome, valor, unidade, formula, insumos: list, secao=None, nota="") -> str | None:
        i = self.calc(nome, valor, unidade, formula, insumos, secao, nota)
        if i:
            self.get(i)["tipo"] = "estimativa"
        return i

    def ausente(self, nome, motivo, fonte_sugerida=""):
        self.ausentes.append({"nome": nome, "motivo": motivo, "fonte_sugerida": fonte_sugerida})

    def alerta(self, nivel, texto, ids=()):
        self.alertas.append({"nivel": nivel, "texto": decimal_br(texto), "ids": [i for i in ids if i]})

    def leitura(self, texto, ids=(), tipo="inferência"):
        """Interpretação baseada nos números (não é fato). tipo: inferência | opinião"""
        self.leituras.append({"tipo": tipo, "texto": decimal_br(texto), "ids": [i for i in ids if i]})

    # ---------- acesso ----------
    def get(self, i):
        return next((x for x in self.itens if x["id"] == i), None)

    def v(self, i):
        x = self.get(i) if i else None
        return None if x is None else x["valor"]

    def to_dict(self) -> dict:
        return {"agente": self.agente, "assunto": self.assunto, "gerado_em": self.gerado_em, "itens": self.itens,
                "secoes": self.secoes, "ausentes": self.ausentes, "alertas": self.alertas, "leituras": self.leituras,
                "extras": self.extras}


def decimal_br(texto: str) -> str:
    """Troca o ponto decimal das f-strings (9.1%) pela vírgula (9,1%). Não mexe em datas nem em ids."""
    return re.sub(r"(?<=\d)\.(?=\d{1,2}(?!\d))", ",", texto)  # 9.1 → 9,1; 4.966 e 1.000 ficam


def div(a, b):
    return None if a is None or b in (None, 0) else a / b


def vezes(a, k):
    return None if a is None else a * k
