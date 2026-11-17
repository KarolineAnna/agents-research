"""Catálogos de indicadores, um por tipo de ativo.

Cada indicador é um registro com: fórmula, entradas, cálculo e textos didáticos.
O site lê estes catálogos e monta os cards sozinho.

Tipos:
  acao     -> fundamentos da CVM (ITR/DFP)          catálogo ACAO
  fii      -> informe mensal de FII da CVM          catálogo FII
  mercado  -> ETF, BDR, cripto, ouro, dólar         catálogo MERCADO (só preço)

Para adicionar um indicador: crie um Indicador(...) no catálogo do tipo.
As entradas podem ser números de base (BASE_* abaixo) ou indicadores que
aparecem ANTES na mesma lista.
"""
from collections.abc import Callable
from dataclasses import dataclass, field

from indicadores_b3.data import fii, fundamentos, tesouro
from indicadores_b3.data.ativos import anualizar, identificar, metricas_mercado
from indicadores_b3.data.fontes import coingecko_brl, historico_yf, proventos_12m, rastro


def div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


@dataclass
class Indicador:
    id: str
    sigla: str
    nome: str
    categoria: str
    unidade: str              # "R$", "R$/ação", "x", "%"
    formula: str              # texto exibido, ex.: "Preço ÷ LPA"
    entradas: list[str]       # ids usados no cálculo
    calc: Callable[[dict], float | None] = field(repr=False)
    o_que_e: str = ""
    como_ler: str = ""
    cuidados: str = ""


ACAO: list[Indicador] = [
    # ---------------- Por ação ----------------
    Indicador(
        id="lpa", sigla="LPA", nome="Lucro por ação", categoria="Por ação", unidade="R$/ação",
        formula="Lucro dos controladores (12m) ÷ Ações em circulação",
        entradas=["lucro_contr", "acoes"],
        calc=lambda v: div(v["lucro_contr"], v["acoes"]),
        o_que_e="Quanto do lucro dos últimos 12 meses cabe a cada ação.",
        como_ler="Sozinho diz pouco; é a base do P/L. O mais útil é ver se cresce ao longo do tempo.",
        cuidados="Usa ações em circulação (sem as da tesouraria). Para units (ex.: TAEE11), uma unit "
                 "tem várias ações, então o LPA por unit é diferente.",
    ),
    Indicador(
        id="vpa", sigla="VPA", nome="Valor patrimonial por ação", categoria="Por ação", unidade="R$/ação",
        formula="Patrimônio líquido dos controladores ÷ Ações em circulação",
        entradas=["pl_contr", "acoes"],
        calc=lambda v: div(v["pl_contr"], v["acoes"]),
        o_que_e="O valor contábil de cada ação: quanto sobraria por ação se a empresa vendesse "
                "os ativos e pagasse as dívidas pelo valor do balanço.",
        como_ler="É a base do P/VP.",
        cuidados="Valor contábil não é valor de mercado: marcas, tecnologia e carteira de clientes "
                 "quase nunca aparecem no patrimônio.",
    ),
    # ---------------- Valuation ----------------
    Indicador(
        id="pl", sigla="P/L", nome="Preço / Lucro", categoria="Valuation", unidade="x",
        formula="Preço ÷ LPA",
        entradas=["preco", "lpa"],
        calc=lambda v: div(v["preco"], v["lpa"]),
        o_que_e="Quantos anos do lucro atual seriam necessários para 'pagar' o preço da ação.",
        como_ler="Mais baixo = mais barato em relação ao lucro. Mas P/L baixo pode significar que o "
                 "mercado espera queda do lucro. Compare com empresas do mesmo setor e com o "
                 "histórico da própria empresa.",
        cuidados="Negativo = a empresa teve prejuízo, não dá para interpretar. Em empresas cíclicas "
                 "(commodities, siderurgia) o P/L costuma ficar mais baixo justamente no pico do lucro.",
    ),
    Indicador(
        id="pvp", sigla="P/VP", nome="Preço / Valor patrimonial", categoria="Valuation", unidade="x",
        formula="Preço ÷ VPA",
        entradas=["preco", "vpa"],
        calc=lambda v: div(v["preco"], v["vpa"]),
        o_que_e="Quanto o mercado paga por cada R$ 1 de patrimônio contábil.",
        como_ler="Abaixo de 1: o mercado paga menos que o valor contábil. Relação útil: "
                 "P/VP = P/L × ROE. Uma empresa com ROE alto 'merece' P/VP alto.",
        cuidados="Empresas de tecnologia e serviços têm poucos ativos físicos, então P/VP alto é "
                 "normal. É mais usado para bancos e empresas intensivas em capital.",
    ),
    Indicador(
        id="dy", sigla="DY", nome="Dividend yield (12m)", categoria="Valuation", unidade="%",
        formula="Proventos por ação (12m) ÷ Preço × 100",
        entradas=["proventos_12m", "preco"],
        calc=lambda v: div(v["proventos_12m"] * 100 if v["proventos_12m"] is not None else None, v["preco"]),
        o_que_e="Quanto a ação pagou em dividendos e JCP nos últimos 12 meses, em % do preço atual.",
        como_ler="Funciona como o 'rendimento' em proventos. Compare com a taxa de juros e com o "
                 "histórico da empresa.",
        cuidados="Um dividendo extraordinário infla o DY de um ano só. Os proventos vêm do yfinance, "
                 "que às vezes atrasa ou mistura JCP bruto e líquido.",
    ),
    # ---------------- Rentabilidade ----------------
    Indicador(
        id="roe", sigla="ROE", nome="Retorno sobre o patrimônio", categoria="Rentabilidade", unidade="%",
        formula="Lucro dos controladores (12m) ÷ Patrimônio líquido dos controladores × 100",
        entradas=["lucro_contr", "pl_contr"],
        calc=lambda v: div(v["lucro_contr"] * 100 if v["lucro_contr"] is not None else None, v["pl_contr"]),
        o_que_e="Quanto de lucro a empresa gera para cada R$ 100 do capital dos sócios.",
        como_ler="Quanto maior, mais eficiente no uso do capital. Vale comparar com o custo do "
                 "dinheiro (ex.: a Selic): ROE abaixo disso é sinal de alerta.",
        cuidados="Dívida alta aumenta o ROE (o patrimônio é menor). Patrimônio pequeno ou negativo "
                 "distorce tudo. Aqui usamos o PL do fim do período; o mais preciso seria a média.",
    ),
    Indicador(
        id="margem_liq", sigla="Margem líq.", nome="Margem líquida", categoria="Rentabilidade", unidade="%",
        formula="Lucro líquido total (12m) ÷ Receita líquida (12m) × 100",
        entradas=["lucro_total", "receita"],
        calc=lambda v: div(v["lucro_total"] * 100 if v["lucro_total"] is not None else None, v["receita"]),
        o_que_e="Quanto sobra de lucro para cada R$ 100 vendidos.",
        como_ler="Compare apenas dentro do mesmo setor: varejo tem margens baixas, software e "
                 "energia costumam ter margens altas.",
        cuidados="Eventos não recorrentes (venda de ativo, multa, impairment) mexem muito na margem "
                 "de um período.",
    ),
    # ---------------- Endividamento ----------------
    Indicador(
        id="ebitda", sigla="EBITDA", nome="EBITDA (12m)", categoria="Endividamento", unidade="R$",
        formula="EBIT + Depreciação e amortização",
        entradas=["ebit", "depreciacao"],
        calc=lambda v: v["ebit"] + v["depreciacao"] if None not in (v["ebit"], v["depreciacao"]) else None,
        o_que_e="Lucro operacional antes de juros, impostos, depreciação e amortização. É uma "
                "aproximação da geração de caixa da operação.",
        como_ler="Usado como base para medir endividamento e para comparar empresas com estruturas "
                 "de dívida diferentes.",
        cuidados="Ignora investimentos (capex), juros e impostos, que são saídas de caixa reais. "
                 "Não existe para bancos.",
    ),
    Indicador(
        id="divida_liq", sigla="Dív. líq.", nome="Dívida líquida", categoria="Endividamento", unidade="R$",
        formula="Dívida bruta − Caixa e aplicações",
        entradas=["divida_bruta", "caixa"],
        calc=lambda v: v["divida_bruta"] - v["caixa"],
        o_que_e="Quanto a empresa deve depois de descontar o dinheiro que já tem em caixa.",
        como_ler="Negativa = caixa líquido (a empresa tem mais dinheiro do que dívida).",
        cuidados="Não inclui arrendamentos (aluguéis contabilizados pelo IFRS 16) nem outras "
                 "obrigações fora de 'empréstimos e financiamentos'.",
    ),
    Indicador(
        id="dl_ebitda", sigla="Dív.Líq/EBITDA", nome="Alavancagem", categoria="Endividamento", unidade="x",
        formula="Dívida líquida ÷ EBITDA",
        entradas=["divida_liq", "ebitda"],
        calc=lambda v: div(v["divida_liq"], v["ebitda"]),
        o_que_e="Quantos anos de EBITDA seriam necessários para quitar a dívida líquida.",
        como_ler="Até ~2x costuma ser confortável; acima de ~3x acende alerta. Negativo = caixa líquido.",
        cuidados="Setores com receita previsível (energia, saneamento) suportam alavancagem maior. "
                 "Não se aplica a bancos.",
    ),
]


FII_CAT: list[Indicador] = [
    Indicador(
        id="pvp", sigla="P/VP", nome="Preço / Valor patrimonial da cota", categoria="Valuation", unidade="x",
        formula="Preço da cota ÷ Valor patrimonial por cota",
        entradas=["preco", "vp_cota"],
        calc=lambda v: div(v["preco"], v["vp_cota"]),
        o_que_e="Quanto o mercado paga por cada R$ 1 de patrimônio do fundo (imóveis, recebíveis, caixa).",
        como_ler="Abaixo de 1: a cota está mais barata que o patrimônio informado. Acima de 1: o mercado "
                 "paga um prêmio, por exemplo por gestão ou qualidade dos imóveis.",
        cuidados="O valor patrimonial depende de laudos de avaliação dos imóveis, que podem estar "
                 "desatualizados. O informe mensal é entregue com algumas semanas de atraso.",
    ),
    Indicador(
        id="dy", sigla="DY", nome="Dividend yield (12m, sobre o preço)", categoria="Rendimento", unidade="%",
        formula="Rendimentos por cota (12m) ÷ Preço da cota × 100",
        entradas=["proventos_12m", "preco"],
        calc=lambda v: div(v["proventos_12m"] * 100, v["preco"]),
        o_que_e="Quanto o fundo distribuiu nos últimos 12 meses, em % do preço que você pagaria hoje.",
        como_ler="É o rendimento de quem compra agora. Compare com o CDI e com o histórico do próprio fundo.",
        cuidados="Rendimentos de FII variam mês a mês. Um mês extraordinário (venda de imóvel) infla o número.",
    ),
    Indicador(
        id="dy_pat", sigla="DY patr.", nome="Dividend yield patrimonial (12m)", categoria="Rendimento", unidade="%",
        formula="Soma do DY mensal informado à CVM (12 informes)",
        entradas=["dy_patrimonial_12m"],
        calc=lambda v: v["dy_patrimonial_12m"],
        o_que_e="O rendimento distribuído em relação ao patrimônio do fundo, como o administrador informa à CVM.",
        como_ler="Compare com o DY sobre o preço: se o DY de mercado é maior, a cota está abaixo do "
                 "valor patrimonial (P/VP < 1), e vice-versa.",
        cuidados="É a soma simples dos 12 meses, não composta.",
    ),
    Indicador(
        id="patrimonio", sigla="PL", nome="Patrimônio líquido", categoria="Tamanho", unidade="R$",
        formula="Patrimônio líquido (informe mensal)",
        entradas=["pl"],
        calc=lambda v: v["pl"],
        o_que_e="O tamanho do fundo: valor de todos os ativos menos as obrigações.",
        como_ler="Fundos maiores costumam ter mais imóveis (mais diversificação) e mais liquidez.",
        cuidados="Tamanho sozinho não diz nada sobre retorno.",
    ),
    Indicador(
        id="n_cotistas", sigla="Cotistas", nome="Número de cotistas", categoria="Tamanho", unidade="qtd",
        formula="Número de cotistas (informe mensal)",
        entradas=["cotistas"],
        calc=lambda v: v["cotistas"],
        o_que_e="Quantas pessoas e instituições têm cotas do fundo.",
        como_ler="Também é uma das condições legais para a isenção de IR dos rendimentos para pessoa física.",
        cuidados="Confira as condições de isenção vigentes com um contador.",
    ),
]

MERCADO: list[Indicador] = [
    Indicador(
        id="ret_12m", sigla="Retorno 12m", nome="Retorno nos últimos 12 meses", categoria="Desempenho", unidade="%",
        formula="(Preço atual ÷ Preço de 12 meses atrás − 1) × 100",
        entradas=["preco", "preco_12m"],
        calc=lambda v: (div(v["preco"], v["preco_12m"]) - 1) * 100 if div(v["preco"], v["preco_12m"]) else None,
        o_que_e="Quanto o preço em reais variou em um ano.",
        como_ler="Para ativos da B3 o preço é ajustado por proventos, então já inclui o que foi distribuído.",
        cuidados="Para cripto, ouro e dólar, o retorno em reais mistura a variação do ativo com a do câmbio.",
    ),
    Indicador(
        id="vol_12m", sigla="Volatilidade", nome="Volatilidade anual (12m)", categoria="Risco", unidade="%",
        formula="Desvio-padrão diário × √(retornos por ano) × 100",
        entradas=["desvio_diario", "obs_ano"],
        calc=lambda v: anualizar(v["desvio_diario"], v["obs_ano"]) * 100,
        o_que_e="O quanto o preço oscila. É a medida de risco usada na carteira de Markowitz.",
        como_ler="Ações costumam ficar entre 20% e 40% ao ano; cripto frequentemente passa de 50%.",
        cuidados="Volatilidade passada não garante a futura, e ela não mede o risco de perdas raras e grandes.",
    ),
    Indicador(
        id="dy", sigla="DY", nome="Dividend yield (12m)", categoria="Desempenho", unidade="%",
        formula="Proventos (12m) ÷ Preço × 100",
        entradas=["proventos_12m", "preco"],
        calc=lambda v: div(v["proventos_12m"] * 100, v["preco"]),
        o_que_e="Quanto o ativo distribuiu nos últimos 12 meses, em % do preço.",
        como_ler="A maioria dos ETFs brasileiros reinveste os proventos e fica em 0%. Cripto, ouro e dólar não pagam.",
        cuidados="Os proventos vêm do yfinance.",
    ),
]

TESOURO_CAT: list[Indicador] = [
    Indicador(
        id="taxa", sigla="Taxa", nome="Taxa de compra hoje", categoria="Rendimento", unidade="%",
        formula="Taxa Compra Manha (arquivo do Tesouro)",
        entradas=["taxa_compra"],
        calc=lambda v: v["taxa_compra"],
        o_que_e="O rendimento anual contratado por quem compra hoje e fica até o vencimento.",
        como_ler="No Tesouro Selic é um adicional sobre a Selic; no IPCA+ é o ganho acima da inflação; "
                 "no Prefixado é a taxa total. Compare títulos do mesmo tipo.",
        cuidados="Só é garantida se você ficar até o vencimento. Vendendo antes, vale o preço de mercado do dia.",
    ),
    Indicador(
        id="anos", sigla="Prazo", nome="Anos até o vencimento", categoria="Rendimento", unidade="anos",
        formula="(Data de vencimento − Data base) ÷ 365,25",
        entradas=["anos_vencimento"],
        calc=lambda v: v["anos_vencimento"],
        o_que_e="Quanto tempo falta para o Tesouro devolver o dinheiro.",
        como_ler="Prazos longos oscilam mais de preço quando os juros mudam.",
        cuidados="Títulos com juros semestrais devolvem parte do dinheiro antes do vencimento.",
    ),
    Indicador(
        id="ret_12m", sigla="Retorno 12m", nome="Retorno de mercado em 12 meses", categoria="Desempenho", unidade="%",
        formula="(Preço de mercado hoje ÷ Preço de 12 meses atrás − 1) × 100",
        entradas=["preco", "preco_12m"],
        calc=lambda v: (div(v["preco"], v["preco_12m"]) - 1) * 100 if div(v["preco"], v["preco_12m"]) else None,
        o_que_e="Quanto o título rendeu para quem comprou há um ano e venderia hoje.",
        como_ler="Pode ser bem diferente da taxa contratada, porque inclui a marcação a mercado.",
        cuidados="Em títulos com juros semestrais, o preço cai quando o cupom é pago; o retorno aqui não soma o cupom.",
    ),
    Indicador(
        id="vol_12m", sigla="Volatilidade", nome="Volatilidade anual do preço (12m)", categoria="Desempenho", unidade="%",
        formula="Desvio-padrão diário × √(dias com preço no ano) × 100",
        entradas=["desvio_diario", "obs_ano"],
        calc=lambda v: anualizar(v["desvio_diario"], v["obs_ano"]) * 100,
        o_que_e="O quanto o preço de mercado do título oscila.",
        como_ler="Tesouro Selic quase não oscila; IPCA+ e Prefixados longos podem oscilar como ações.",
        cuidados="Só importa se você pretende vender antes do vencimento.",
    ),
]

BASE_FII = {
    "preco":              ("Preço da cota", "yfinance — fechamento mais recente", "R$/cota"),
    "proventos_12m":      ("Rendimentos por cota (12m)", "yfinance — data-ex nos últimos 12 meses", "R$/cota"),
    "vp_cota":            ("Valor patrimonial por cota", "CVM · informe mensal de FII", "R$/cota"),
    "pl":                 ("Patrimônio líquido", "CVM · informe mensal de FII", "R$"),
    "cotas":              ("Cotas emitidas", "CVM · informe mensal de FII", "qtd"),
    "cotistas":           ("Número de cotistas", "CVM · informe mensal de FII", "qtd"),
    "dy_patrimonial_12m": ("DY patrimonial (soma 12m)", "CVM · informe mensal de FII", "%"),
}
BASE_MERCADO = {
    "preco":         ("Preço atual (R$)", "yfinance (+ PTAX do Banco Central se cotado em US$)", "R$"),
    "preco_12m":     ("Preço de 12 meses atrás (R$)", "yfinance (+ PTAX)", "R$"),
    "desvio_diario": ("Desvio-padrão diário", "cálculo sobre a série de preços", "decimal"),
    "obs_ano":       ("Retornos diários em 1 ano", "contagem na série de preços", "dias"),
    "proventos_12m": ("Proventos (12m)", "yfinance", "R$"),
}
BASE_TESOURO = {
    "taxa_compra":     ("Taxa de compra (% a.a.)", "Tesouro Nacional · precotaxatesourodireto.csv", "%"),
    "pu_compra":       ("Preço de compra (R$)", "Tesouro Nacional · precotaxatesourodireto.csv", "R$/cota"),
    "preco":           ("Preço de mercado (R$)", "Tesouro Nacional · PU Base Manha", "R$/cota"),
    "preco_12m":       ("Preço de mercado há 12 meses (R$)", "Tesouro Nacional · PU Base Manha", "R$/cota"),
    "anos_vencimento": ("Anos até o vencimento", "Tesouro Nacional · Data Vencimento", "anos"),
    "desvio_diario":   ("Desvio-padrão diário", "cálculo sobre o PU Base Manha", "decimal"),
    "obs_ano":         ("Dias com preço em 1 ano", "contagem no arquivo", "dias"),
}
BASE_ACAO = {k: (n, f, {"preco": "R$/ação", "proventos_12m": "R$/ação", "acoes": "qtd"}.get(k, "R$"))
             for k, (n, f) in fundamentos.BASE.items()}

TIPOS = {
    "acao":    {"nome": "Ações", "catalogo": ACAO, "base": BASE_ACAO},
    "fii":     {"nome": "Fundos imobiliários", "catalogo": FII_CAT, "base": BASE_FII},
    "tesouro": {"nome": "Renda fixa — Tesouro Direto", "catalogo": TESOURO_CAT, "base": BASE_TESOURO},
    "mercado": {"nome": "ETFs, cripto, ouro e moedas", "catalogo": MERCADO, "base": BASE_MERCADO},
}
NOME_CLASSE = {"b3": "ETF / outro ativo da B3", "cripto": "Criptomoeda", "commodity": "Commodity", "moeda": "Moeda"}


# ---------- Coleta por tipo ----------
def tipo_de(ticker: str) -> tuple[str, dict]:
    a = identificar(ticker)
    if a["classe"] == "tesouro":
        return "tesouro", a
    if a["classe"] == "b3":
        if a["ticker"] in fundamentos.mapa_tickers():
            return "acao", a
        if fii.buscar(a["ticker"]):
            return "fii", a
    return "mercado", a


def coletar_acao(a: dict) -> dict:
    d = fundamentos.dados_base(a["ticker"])
    from indicadores_b3.data import setores
    try:
        st = setores.setor_de(a["ticker"])
    except Exception:  # noqa: BLE001
        st = {}
    rotulo = st.get("setor") or ("Banco" if d.get("banco") else None)
    return {**d, "subtipo": f"Ação · {rotulo}" if rotulo else "Ação", "setor": st, "avisos": d.get("avisos", [])}


def coletar_fii(a: dict) -> dict:
    cvm = fii.dados_cvm(a["ticker"])
    preco, prov = fundamentos.rastro_yfinance(fundamentos.yf.Ticker(a["simbolo"]), a["simbolo"])
    r = {"preco": preco, "proventos_12m": prov, **cvm["rastreio"]}

    avisos = []
    vp, cotas, pl = r["vp_cota"]["valor"], r["cotas"]["valor"], r["pl"]["valor"]
    if vp and cotas and pl:
        dif = abs(vp * cotas - pl) / pl
        if dif > 0.01:
            avisos.append(f"Inconsistência no informe: VP por cota × cotas difere {_br(dif * 100, 1)}% do patrimônio líquido.")
    return {"ticker": a["ticker"], "empresa": cvm["cadastro"]["nome"] or a["ticker"], "subtipo": "FII",
            "balanco_ref": cvm["data_ref"], "rastreio": r, "avisos": avisos,
            "valores": {k: x["valor"] for k, x in r.items()}}


def conferir_cambio(ptax: float) -> str | None:
    s = historico_yf("BRL=X", "5d")
    if s.empty:
        return None
    dif = abs(float(s.iloc[-1]) - ptax) / ptax
    if dif > 0.02:
        return (f"A PTAX (R$ {_br(ptax, 4)}) difere {_br(dif * 100, 1)}% do câmbio do Yahoo (BRL=X, R$ {_br(float(s.iloc[-1]), 4)}). "
                f"Confira as duas fontes.")
    return None


def coletar_mercado(a: dict) -> dict:
    m = metricas_mercado(a["ticker"])
    r = dict(m["rastreio"])
    if a["classe"] == "b3":
        r["proventos_12m"] = proventos_12m(a["simbolo"])
    else:
        r["proventos_12m"] = rastro(0.0, [], "Este ativo não distribui proventos.")

    avisos = []
    preco = r["preco"]["valor"]
    if a["classe"] == "cripto":
        cg = coingecko_brl(a["ticker"])
        if cg:
            dif = abs(cg["valor"] - preco) / cg["valor"]
            msg = (f"Conferência com CoinGecko ({cg['data']}): R$ {_br(cg['valor'])} — diferença de {_br(dif * 100, 1)}% "
                   f"para o preço calculado (Yahoo em US$ × PTAX).")
            avisos.append(msg if dif > 0.05 else None)
            r["preco"]["componentes"].append({
                "sinal": "≈", "papel": "Conferência (não entra no cálculo)", "fonte": "CoinGecko",
                "documento": "simple/price", "url": cg["url"], "data_ref": cg["data"][:10],
                "periodo": cg["data"], "conta": "brl", "descricao": f"Preço de {a['ticker']} em reais",
                "valor": cg["valor"]})
    if a["classe"] == "moeda":
        avisos.append(conferir_cambio(preco))

    return {"ticker": a["ticker"], "empresa": a["nome"], "subtipo": NOME_CLASSE[a["classe"]],
            "balanco_ref": r["preco"]["componentes"][0]["data_ref"], "rastreio": r,
            "avisos": [x for x in avisos if x], "valores": {k: x["valor"] for k, x in r.items()}}


def _br(v: float, d: int = 2) -> str:
    """Número no formato brasileiro: 1.234,56"""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def coletar_tesouro(a: dict) -> dict:
    d = tesouro.dados(a["ticker"])
    return {**d, "subtipo": "Tesouro Direto", "avisos": [],
            "valores": {k: x["valor"] for k, x in d["rastreio"].items()}}


COLETA = {"acao": coletar_acao, "fii": coletar_fii, "mercado": coletar_mercado, "tesouro": coletar_tesouro}


def calcular(ticker: str) -> dict:
    """Identifica o tipo, coleta os dados de base e calcula o catálogo na ordem."""
    tipo, a = tipo_de(ticker)
    base = COLETA[tipo](a)
    v = dict(base["valores"])
    resultados = []
    for ind in TIPOS[tipo]["catalogo"]:
        try:
            valor = ind.calc(v) if all(v.get(e) is not None for e in ind.entradas) else None
        except (TypeError, ZeroDivisionError):
            valor = None
        v[ind.id] = valor
        resultados.append({"id": ind.id, "valor": valor, "entradas": {e: v.get(e) for e in ind.entradas}})
    return {**base, "tipo": tipo, "indicadores": resultados}


def catalogo_json() -> dict:
    """Metadados (sem as funções de cálculo) para o front-end."""
    campos = ("id", "sigla", "nome", "categoria", "unidade", "formula", "entradas", "o_que_e", "como_ler", "cuidados")
    tipos = {}
    for k, t in TIPOS.items():
        rotulos = {b: {"nome": n, "fonte": f, "unidade": u} for b, (n, f, u) in t["base"].items()}
        rotulos.update({i.id: {"nome": i.sigla, "fonte": f"Indicador · {i.formula}", "unidade": i.unidade}
                        for i in t["catalogo"]})
        tipos[k] = {
            "nome": t["nome"],
            "categorias": list(dict.fromkeys(i.categoria for i in t["catalogo"])),
            "indicadores": [{c: getattr(i, c) for c in campos} for i in t["catalogo"]],
            "rotulos": rotulos,
        }
    return {"tipos": tipos}
