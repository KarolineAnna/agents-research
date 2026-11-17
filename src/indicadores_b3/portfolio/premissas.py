"""Premissas de retorno por "blocos" (Capital Market Assumptions) e Black-Litterman.

É assim que gestoras, bancos e fundos de pensão estimam retorno esperado para alocação:
cada classe de ativo tem o retorno decomposto em blocos observáveis hoje, em vez da média do passado.

Blocos usados (horizonte H anos, retornos nominais em R$, ao ano):
  Renda fixa (Tesouro)     taxa do título hoje (IPCA+: taxa real + inflação implícita no prazo)
  Renda fixa (CDI)         taxa prefixada do Tesouro no prazo H (o mercado embute nela o CDI esperado)
  Ações (Grinold-Kroner)   dividend yield + inflação esperada + crescimento real do lucro − diluição + reprecificação
  FII                      dividend yield + inflação esperada (aluguéis reajustados por índice de preços)
  ETF de ações             juro prefixado no prazo + prêmio de risco de ações
  Dólar                    paridade de juros: (1 + juro BR) ÷ (1 + juro EUA) − 1
  Ouro                     inflação dos EUA (ouro ≈ reserva de valor real) + variação esperada do dólar
  Cripto                   sem âncora de fluxo de caixa: juro prefixado + prêmio que VOCÊ definir (padrão 0)

Inflação esperada = inflação implícita (prefixado ÷ IPCA+) da curva do Tesouro no prazo H.
Juro dos EUA = Treasury de 5 anos (^FVX, yfinance).

Black-Litterman (He & Litterman, 1999): parte de um retorno de referência (prior) e mistura com
as suas visões, ponderando pela confiança. O artigo original usa o retorno implícito de equilíbrio
como referência; aqui a referência são as premissas por blocos acima, que já são uma visão de mercado
(prática comum em alocação multiclasse). Fórmula:
  μ_BL = [(τΣ)⁻¹ + Pᵀ Ω⁻¹ P]⁻¹ · [(τΣ)⁻¹ π + Pᵀ Ω⁻¹ Q]
  Ω_k  = (1 − c_k) / c_k · p_k (τΣ) p_kᵀ        (confiança c_k entre 0 e 1, à la Idzorek)
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from indicadores_b3.analytics import rendafixa
from indicadores_b3.data import tesouro
from indicadores_b3.data.ativos import identificar
from indicadores_b3.data.fontes import comp, historico_yf, proventos_12m, rastro, url_yahoo

PADROES = {
    "horizonte": 5.0,          # anos
    "crescimento_real": 2.0,   # % a.a., crescimento real do lucro (≈ PIB potencial)
    "diluicao": 0.0,           # % a.a., emissão líquida de ações
    "repreco": 0.0,            # % a.a., mudança esperada de múltiplo (P/L)
    "premio_acoes": 4.0,       # % a.a. sobre o juro prefixado, para ETFs de ações
    "inflacao_eua": 2.5,       # % a.a.
    "premio_cripto": 0.0,      # % a.a. sobre o juro prefixado
}
TAU = 0.05
CONFIANCA = {"baixa": 0.25, "media": 0.5, "alta": 0.75}


def _hoje() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d")


@lru_cache(maxsize=4)
def _curvas(dia: str) -> dict:
    tt = rendafixa.titulos()
    return {"titulos": tt, "curvas": rendafixa.curvas(tt)}


def _no_prazo(pontos: list[dict], campo: str, anos: float) -> float | None:
    xs, ys = rendafixa.media_por_prazo([(p["anos"], p[campo]) for p in pontos])
    if not xs:
        return None
    return float(np.interp(min(max(anos, xs[0]), xs[-1]), xs, ys))  # fora da curva: usa a ponta mais próxima


@lru_cache(maxsize=4)
def _juro_eua(dia: str) -> tuple[float | None, str]:
    try:
        s = historico_yf("^FVX", "1mo")
        if not s.empty:
            return float(s.iloc[-1]), s.index[-1].strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        pass
    return None, ""


def mercado(H: float) -> dict:
    """Premissas de mercado comuns a todos os ativos, com fonte."""
    d = _curvas(_hoje())
    c, base = d["curvas"], d["titulos"]["data_base"]
    pre = _no_prazo(c["pre"], "taxa", H)
    inf = _no_prazo(c["implicita"], "inflacao", H)
    eua, d_eua = _juro_eua(_hoje())
    td = {"fonte": "Tesouro Nacional", "documento": "precotaxatesourodireto.csv", "url": tesouro.PAGINA,
          "data_ref": base, "periodo": f"curva em {base}, interpolada em {H:g} anos"}
    return {
        "juro_pre": rastro(pre, [comp("+", "Taxa prefixada do Tesouro no prazo", {**td, "conta": "Taxa Compra Manha",
                           "descricao": "Curva prefixada (LTN/NTN-F)", "valor": pre})],
                           "O juro prefixado embute o CDI que o mercado espera, em média, até esse prazo (mais um pequeno prêmio de prazo)."),
        "inflacao": rastro(inf, [comp("+", "Inflação implícita no prazo", {**td, "conta": "prefixado ÷ IPCA+",
                           "descricao": "(1 + prefixado) ÷ (1 + IPCA+) − 1", "valor": inf})],
                           "A inflação que o mercado embute nos preços dos títulos. Inclui um prêmio de risco de inflação."),
        "juro_eua": rastro(eua if eua is not None else 4.0, [comp("+", "Treasury de 5 anos", {
                           "fonte": "yfinance" if eua is not None else "premissa", "documento": "^FVX", "url": url_yahoo("^FVX"),
                           "data_ref": d_eua, "periodo": "último fechamento", "conta": "Close",
                           "descricao": "Rendimento do título do Tesouro americano de 5 anos (% a.a.)",
                           "valor": eua if eua is not None else 4.0})],
                           "" if eua is not None else "Sem resposta do yfinance; usado 4% a.a."),
    }


def _dy(info: dict, preco: float) -> tuple[float, dict]:
    p = proventos_12m(info["simbolo"])
    v = (p["valor"] or 0.0) / preco * 100 if preco else 0.0
    return v, p


def bloco_ativo(t: str, preco: float, H: float, m: dict, g: dict, classe_fiscal: str | None = None) -> dict:
    """Retorno esperado de um ativo por blocos: {valor, metodo, blocos:[{nome, valor, fonte}], nota, aviso}."""
    a = identificar(t)
    pre, inf, us = m["juro_pre"]["valor"], m["inflacao"]["valor"], m["juro_eua"]["valor"]
    blocos, aviso = [], ""

    def b(nome, valor, origem, editavel=None):
        blocos.append({"nome": nome, "valor": valor, "origem": origem, "editavel": editavel})

    if a["classe"] == "tesouro":
        linha = next((x for x in _curvas(_hoje())["titulos"]["titulos"] if x["codigo"] == a["ticker"]), None)
        if linha is None:
            raise LookupError(f"{t} não está no arquivo do Tesouro.")
        if linha["sigla"] in ("IPCA", "IPCAJS", "RENDA", "EDUCA"):  # siglas de tesouro.SIGLAS
            inf_t = _no_prazo(_curvas(_hoje())["curvas"]["implicita"], "inflacao", linha["anos"])
            b("Taxa real do título", linha["taxa"], "Tesouro Nacional")
            b(f"Inflação implícita em {linha['anos']:.1f} anos", inf_t, "curva do Tesouro")
            v = ((1 + linha["taxa"] / 100) * (1 + inf_t / 100) - 1) * 100
            metodo = "IPCA+: taxa real + inflação implícita no prazo do título"
        elif linha["sigla"] == "SELIC":
            b("Juro prefixado no prazo (CDI esperado)", _no_prazo(_curvas(_hoje())["curvas"]["pre"], "taxa", linha["anos"]), "curva do Tesouro")
            b("Ágio/deságio do título", linha["taxa"], "Tesouro Nacional")
            v = ((1 + blocos[0]["valor"] / 100) * (1 + linha["taxa"] / 100) - 1) * 100
            metodo = "Selic: CDI esperado no prazo + ágio/deságio"
        else:
            b("Taxa prefixada do título", linha["taxa"], "Tesouro Nacional")
            v = linha["taxa"]
            metodo = "Prefixado: a própria taxa (é o retorno até o vencimento)"
        nota = "Levando até o vencimento, a taxa de hoje é o retorno; vendendo antes, há marcação a mercado."
    elif a["classe"] == "b3" and classe_fiscal == "fii":
        dy, _ = _dy(a, preco)
        b("Dividend yield (12 meses)", dy, "yfinance · proventos ÷ preço")
        b("Inflação esperada (reajuste dos aluguéis)", inf, "curva do Tesouro")
        v = ((1 + dy / 100) * (1 + inf / 100) - 1) * 100
        metodo = "FII: rendimento + reajuste dos aluguéis pela inflação"
        nota = "Supõe aluguéis corrigidos pela inflação e vacância estável. FIIs de papel (CRI) seguem o indexador dos títulos."
        if dy == 0:
            aviso = "Sem proventos nos últimos 12 meses no yfinance: confira o rendimento."
    elif a["classe"] == "b3" and classe_fiscal == "acao":
        dy, _ = _dy(a, preco)
        b("Dividend yield (12 meses)", dy, "yfinance · proventos ÷ preço")
        b("Inflação esperada", inf, "curva do Tesouro")
        b("Crescimento real do lucro", g["crescimento_real"], "premissa", "crescimento_real")
        b("Diluição (emissão de ações)", -g["diluicao"], "premissa", "diluicao")
        b("Reprecificação (mudança de múltiplo)", g["repreco"], "premissa", "repreco")
        v = dy + inf + g["crescimento_real"] - g["diluicao"] + g["repreco"]
        metodo = "Ação: Grinold-Kroner"
        nota = "Retorno = renda (dividendos) + crescimento nominal do lucro + mudança de múltiplo. Empresas que reinvestem muito (DY baixo) costumam crescer mais: ajuste o crescimento real."
        if dy > 15:
            aviso = f"Dividend yield de {dy:.1f}% parece extraordinário (provento não recorrente?). Considere sobrescrever."
    elif a["classe"] == "b3":  # ETF ou outro
        b("Juro prefixado no prazo", pre, "curva do Tesouro")
        b("Prêmio de risco de ações", g["premio_acoes"], "premissa", "premio_acoes")
        v = ((1 + pre / 100) * (1 + g["premio_acoes"] / 100) - 1) * 100
        metodo = "ETF de ações: juro prefixado + prêmio de risco de ações"
        nota = "Para ETFs de renda fixa ou internacionais (ex.: IVVB11), sobrescreva com a premissa adequada."
    elif a["classe"] == "moeda":
        dep = ((1 + pre / 100) / (1 + us / 100) - 1) * 100
        b("Juro prefixado no Brasil", pre, "curva do Tesouro")
        b("Juro nos EUA (Treasury 5 anos)", -us, "yfinance ^FVX")
        v = dep
        metodo = "Dólar: paridade de juros (o real tende a perder valor na diferença de juros)"
        nota = "É o 'carry': quem fica em dólar abre mão do juro brasileiro mais alto. Na prática o câmbio desvia muito disso no curto prazo."
    elif a["classe"] == "commodity":
        dep = ((1 + pre / 100) / (1 + us / 100) - 1) * 100
        b("Inflação dos EUA (ouro ≈ reserva de valor)", g["inflacao_eua"], "premissa", "inflacao_eua")
        b("Variação esperada do dólar (paridade de juros)", dep, "curva do Tesouro e ^FVX")
        v = ((1 + g["inflacao_eua"] / 100) * (1 + dep / 100) - 1) * 100
        metodo = "Ouro: inflação dos EUA + variação esperada do dólar"
        nota = "O ouro não gera fluxo de caixa; a premissa usual é preservar o poder de compra no longo prazo."
    elif a["classe"] == "cripto":
        b("Juro prefixado no prazo", pre, "curva do Tesouro")
        b("Prêmio de cripto (sua premissa)", g["premio_cripto"], "premissa", "premio_cripto")
        v = ((1 + pre / 100) * (1 + g["premio_cripto"] / 100) - 1) * 100
        metodo = "Cripto: sem âncora de fluxo de caixa"
        nota = "Não há dividendos nem lucros para ancorar a estimativa; qualquer número é uma opinião."
        aviso = "Premissa sem fundamento observável: defina o prêmio ou use uma visão no Black-Litterman."
    else:
        raise ValueError(f"Sem premissa por blocos para {t}.")
    return {"ticker": a["ticker"], "valor": float(v), "metodo": metodo, "blocos": blocos, "nota": nota, "aviso": aviso}


def premissas(tickers: list[str], precos: dict, classes: dict, globais: dict | None = None,
              sobrescritas: dict | None = None) -> dict:
    g = {**PADROES, **{k: float(v) for k, v in (globais or {}).items() if k in PADROES and v is not None}}
    H = g["horizonte"]
    m = mercado(H)
    if m["juro_pre"]["valor"] is None or m["inflacao"]["valor"] is None:
        raise LookupError("Não consegui montar a curva do Tesouro para as premissas.")
    ativos = []
    for t in tickers:
        try:
            r = bloco_ativo(t, precos.get(t), H, m, g, classes.get(t))
        except Exception as e:  # noqa: BLE001
            r = {"ticker": t, "valor": None, "metodo": "—", "blocos": [], "nota": "", "aviso": f"Sem premissa: {e}"}
        r["calculado"] = r["valor"]
        s = (sobrescritas or {}).get(t)
        if s is not None and s != "":
            r["valor"], r["sobrescrito"] = float(s), True
        ativos.append(r)
    return {"globais": g, "mercado": m, "ativos": ativos, "rf_bloco": m["juro_pre"]["valor"]}


# ---------- Black-Litterman ----------
def black_litterman(prior: np.ndarray, cov: np.ndarray, nomes: list[str], visoes: list[dict], tau: float = TAU) -> dict:
    """prior e cov anuais (frações). visoes: [{tipo: abs|rel, a, b?, q (% a.a.), confianca: baixa|media|alta}]."""
    n = len(nomes)
    idx = {t: i for i, t in enumerate(nomes)}
    P, Q, conf, usadas = [], [], [], []
    for v in visoes or []:
        a = str(v.get("a", "")).upper()
        if a not in idx or v.get("q") in (None, ""):
            continue
        p = np.zeros(n)
        p[idx[a]] = 1
        if v.get("tipo") == "rel":
            b = str(v.get("b", "")).upper()
            if b not in idx or b == a:
                continue
            p[idx[b]] = -1
        P.append(p)
        Q.append(float(v["q"]) / 100)
        conf.append(CONFIANCA.get(v.get("confianca"), 0.5))
        usadas.append({**v, "a": a, "b": v.get("b", "").upper() if v.get("tipo") == "rel" else None,
                       "prior": float(p @ prior * 100)})
    if not P:
        return {"posterior": prior, "visoes": []}
    P, Q, c = np.array(P), np.array(Q), np.array(conf)
    tS = tau * cov
    omega = np.diag([(1 - ck) / ck * float(pk @ tS @ pk) + 1e-12 for pk, ck in zip(P, c)])
    tSi = np.linalg.pinv(tS)
    Oi = np.linalg.inv(omega)
    post = np.linalg.pinv(tSi + P.T @ Oi @ P) @ (tSi @ prior + P.T @ Oi @ Q)
    for u, p in zip(usadas, P):
        u["posterior"] = float(p @ post * 100)
    return {"posterior": post, "visoes": usadas}
