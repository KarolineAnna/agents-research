"""Fachada dos modelos usados na aba "Modelos" (mantida para compatibilidade da API).

Regra do projeto: todo modelo é comparado a uma referência simples e avaliado FORA DA AMOSTRA.
Se não ganhar da referência, a página mostra isso. (O Monte Carlo do DCF roda na página, em static/dcf.js; as anomalias contábeis aparecem na Saúde dos dados.)
"""
from indicadores_b3.ml.carteira_robusta import METODOS, avaliar, carteira_robusta
from indicadores_b3.ml.pares import RAZOES, anomalias, identidades
from indicadores_b3.ml.volatilidade import avaliar_garch, garch

__all__ = ["METODOS", "RAZOES", "anomalias", "avaliar", "avaliar_garch", "carteira_robusta", "garch", "identidades"]
