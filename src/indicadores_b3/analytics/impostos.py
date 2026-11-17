"""Regras de imposto de renda (pessoa física, Brasil) usadas na aba "Com impostos".

Conferido em out/2026. Regras tributárias mudam: revise esta tabela quando houver lei nova
e confirme sua situação com um contador. Este módulo é uma SIMPLIFICAÇÃO para estudo.

Fontes consultadas (resumos, não substituem a lei):
- Lei 15.270/2025 (dividendos, IRPFM): https://normas.leg.br/?urn=urn:lex:br:federal:lei:2025-11-26;15270
- LC 224/2025 (JCP 17,5%): https://www.mayerbrown.com/pt/insights/publications/2025/12/complementary-law-no-224-2025-reduction-of-tax-incentives
- MP 1.303/2025 perdeu a validade em out/2025 (não está em vigor)
"""
import math

REGRAS = {
    "acao": {
        "nome": "Ação",
        "ganho": 15.0, "isencao": "vendas de ações até R$ 20 mil no mês",
        "proventos": 0.0,
        "base_legal": "Lei 11.033/2004, art. 2º (15%) e art. 3º, I (isenção de vendas até R$ 20 mil/mês)",
        "nota": "Dividendos isentos até R$ 50 mil/mês por empresa (acima disso, 10% retido — Lei 15.270/2025). "
                "JCP tem 17,5% retido na fonte (LC 224/2025), mas o yfinance não separa dividendo de JCP, "
                "então os proventos foram tratados como dividendos isentos.",
    },
    "fii": {
        "nome": "FII",
        "ganho": 20.0, "isencao": None,
        "proventos": 0.0,
        "base_legal": "Lei 8.668/1993, art. 18 (20% sobre o ganho); Lei 11.033/2004, art. 3º, III (rendimentos isentos)",
        "nota": "Rendimentos isentos para pessoa física se o fundo e o cotista cumprirem as condições da lei "
                "(negociação em bolsa, número mínimo de cotistas e participação abaixo de 10%).",
    },
    "etf": {
        "nome": "ETF / outro ativo da B3",
        "ganho": 15.0, "isencao": None,
        "proventos": 0.0,
        "base_legal": "IN RFB 1.585/2015 (ETF de renda variável: 15%, sem a isenção de R$ 20 mil)",
        "nota": "Vale para ETFs de renda variável. ETFs de renda fixa e BDRs têm regras próprias.",
    },
    "cripto": {
        "nome": "Criptomoeda",
        "ganho": 15.0, "isencao": "vendas de cripto até R$ 35 mil no mês (corretora nacional)",
        "proventos": 0.0,
        "base_legal": "Lei 8.981/1995, art. 21 (15% a 22,5%, progressiva); IN RFB 1.888/2019",
        "nota": "15% vale para ganhos até R$ 5 milhões; acima disso a alíquota sobe até 22,5%. "
                "Em corretoras no exterior: 15% anual, sem isenção mensal (Lei 14.754/2023).",
    },
    "commodity": {
        "nome": "Ouro (contrato futuro)",
        "ganho": 15.0, "isencao": None,
        "proventos": 0.0,
        "base_legal": "Lei 11.033/2004, art. 2º (mercados futuros: 15%)",
        "nota": "O GC=F é negociado nos EUA e serve aqui como referência de preço. Na B3, o acesso a ouro "
                "costuma ser via ETF (ex.: GOLD11), que segue a regra de ETF.",
    },
    "moeda": {
        "nome": "Dólar (espécie)",
        "ganho": 15.0, "isencao": "vendas de moeda estrangeira em espécie até US$ 5 mil no ano",
        "proventos": 0.0,
        "base_legal": "MP 2.158-35/2001, art. 24 (ganho em moeda estrangeira em espécie)",
        "nota": "Considera dólar em espécie. Conta em dólar e fundos cambiais têm outras regras.",
    },
}

# Renda fixa (CDI, CDB, Tesouro): tabela regressiva sobre o rendimento — Lei 11.033/2004, art. 1º
TABELA_REGRESSIVA = [(180, 22.5), (360, 20.0), (720, 17.5), (math.inf, 15.0)]
BASE_LEGAL_RF = "Lei 11.033/2004, art. 1º (tabela regressiva: 22,5% até 180 dias … 15% acima de 720 dias)"


def aliquota_renda_fixa(dias: int) -> float:
    return next(a for limite, a in TABELA_REGRESSIVA if dias <= limite)


def regra(classe_fiscal: str, dentro_isencao: bool) -> dict:
    r = dict(REGRAS[classe_fiscal])
    r["ganho_aplicado"] = 0.0 if (dentro_isencao and r["isencao"]) else r["ganho"]
    r["isento"] = r["ganho_aplicado"] == 0.0
    return r


def regra_tesouro(dias: int) -> dict:
    """Tesouro Direto segue a tabela regressiva da renda fixa, pelo tempo que você fica no título."""
    a = aliquota_renda_fixa(dias)
    return {"nome": "Tesouro Direto", "ganho": a, "ganho_aplicado": a, "isencao": None, "isento": False,
            "proventos": a, "base_legal": BASE_LEGAL_RF,
            "nota": f"Alíquota de {a:.1f}% para {dias} dias de aplicação. Há também taxa de custódia da B3 "
                    "(0,20% a.a., com isenção parcial no Tesouro Selic), não considerada aqui.".replace(".", ",", 1)}
