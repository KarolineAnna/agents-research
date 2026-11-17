"""Dados de base para o DCF (fluxo de caixa descontado), com rastreio.

Fluxo de caixa livre (FCL) a partir da Demonstração dos Fluxos de Caixa (DFC) da CVM, com os ajustes que
analistas fazem para não superestimar o caixa:
    FCL contábil = Caixa das operações (6.01) + Caixa dos investimentos (6.02)
    FCL ajustado = FCL contábil
                 − pagamentos de arrendamento (IFRS 16: aluguel de lojas/CDs vai para "financiamento", mas é custo operacional)
                 − pagamentos a fornecedores via convênio / risco sacado (a compra de mercadoria é operacional, mesmo
                   quando o banco paga o fornecedor e a empresa quita o banco depois)
Sem esses ajustes, varejistas como o Magazine Luiza aparecem com caixa operacional várias vezes maior que o real.

Conferência independente, pelo resultado: FCFF ≈ EBIT × (1 − IR) + depreciação − investimentos.

Os cálculos do DCF (projeção, desconto, perpetuidade) são feitos na página, para você mexer
nas premissas e ver o efeito na hora. Este módulo só entrega os números reais e de onde vieram.
"""
import statistics
from functools import lru_cache

import pandas as pd

from indicadores_b3.data import fundamentos as f
from indicadores_b3.data.fontes import cdi_atual, comp, historico_yf, rastro, url_yahoo

ERP_PADRAO = 5.0   # prêmio de risco de ações (% a.a.), premissa editável
IR_PADRAO = 34.0   # IR + CSLL (%), alíquota nominal das empresas no lucro real


def beta_semanal(simbolo: str) -> dict:
    """β contra o Ibovespa com retornos semanais de 2 anos (convenção comum de provedores de mercado)."""
    try:
        a, m = historico_yf(simbolo, "2y"), historico_yf("^BVSP", "2y")
        if a.empty or m.empty:
            raise ValueError("o yfinance não retornou o histórico de preços")
        df = pd.concat([a.rename("a"), m.rename("m")], axis=1).dropna().resample("W-FRI").last().pct_change().dropna()
        if len(df) < 40:
            raise ValueError("histórico curto")
        beta = float(df["a"].cov(df["m"]) / df["m"].var())
        r2 = float(df["a"].corr(df["m"]) ** 2)
    except Exception as e:  # noqa: BLE001
        return rastro(None, [], f"Não consegui calcular o beta ({e}). Informe um valor.")
    return rastro(beta, [comp("+", "Regressão contra o Ibovespa", {
        "fonte": "yfinance", "documento": f"{simbolo} e ^BVSP", "url": url_yahoo(simbolo),
        "data_ref": df.index[-1].strftime("%Y-%m-%d"), "periodo": f"{len(df)} semanas",
        "conta": "β = Cov(ativo, Ibov) ÷ Var(Ibov)", "descricao": f"retornos semanais · R² {r2:.2f}", "valor": beta})],
        f"Retornos semanais de 2 anos ({len(df)} semanas), R² = {r2:.2f}. Provedores como Bloomberg usam convenções parecidas "
        "(2 anos semanais ou 5 anos mensais) e costumam ajustar o beta para perto de 1 (β ajustado = 0,67·β + 0,33).")


def dados_wacc(cnpj: str, simbolo: str) -> dict:
    """Insumos do WACC, cada um com fonte. A conta é feita na página."""
    from indicadores_b3.portfolio import premissas
    out = {"erp": ERP_PADRAO, "ir": IR_PADRAO, "beta": beta_semanal(simbolo)}
    try:
        m = premissas.mercado(10.0)
        out["rf"] = {**m["juro_pre"], "nota": "Juro prefixado longo do Tesouro (≈10 anos): a referência de taxa livre de risco em reais "
                                             "para avaliar empresas. " + (m["juro_pre"].get("nota") or "")}
    except Exception as e:  # noqa: BLE001
        out["rf"] = rastro(None, [], f"Curva do Tesouro indisponível ({e}).")
    out["mercado_usd"] = dados_ke_mercado()
    dre = f.demonstrativo("DRE_con", cnpj)
    out["despesa_fin"] = f.ttm(dre, "3.06.02") if not dre.empty else rastro(None, [], "DRE não encontrada.")
    return out


CRP_PADRAO = 2.5   # risco-país (% a.a.) se o Ipeadata não responder — premissa declarada
PI_US_PADRAO = 2.3  # inflação de longo prazo dos EUA (% a.a.) se o FRED não responder


def _ou_premissa(func, padrao: float, nota: str, conv=lambda v: v) -> dict:
    try:
        x = func()
        v = conv(x["valor"])
        idade = (pd.Timestamp.now() - pd.Timestamp(x["data_ref"])).days
        aviso = f" Dado de {idade} dias atrás: confira se a série continua sendo atualizada." if idade > 60 else ""
        return rastro(v, [comp("+", x.get("descricao", ""), {**x, "valor": v})], nota + aviso)
    except Exception as e:  # noqa: BLE001 — sem internet ou série encerrada
        return {**rastro(padrao, [], f"{nota} Fonte indisponível ({type(e).__name__}); usada a premissa de {padrao:.1f}% — edite se quiser."),
                "premissa": True}


def dados_ke_mercado() -> dict:
    return _ke_mercado_do_dia(pd.Timestamp.now().strftime("%Y-%m-%d"))


@lru_cache(maxsize=4)
def _ke_mercado_do_dia(hoje: str) -> dict:
    """Insumos do Ke "padrão de mercado": juro americano + risco-país, em dólar, convertido para reais pela inflação.
    Ke(R$) = (1 + rf EUA + risco-país + β × prêmio) × (1 + inflação Brasil) ÷ (1 + inflação EUA) − 1"""
    from concurrent.futures import ThreadPoolExecutor

    from indicadores_b3.agents import fontes_publicas as fp
    ano = pd.Timestamp.now().year + 3
    tarefas = {  # em paralelo: as quatro consultas juntas levam o tempo da mais lenta
        "rf_us": (lambda: fp.fred("DGS10", hoje), 4.3, "Juro do Tesouro americano de 10 anos (FRED).", lambda v: v),
        "crp": (lambda: fp.ipea_ultimo("JPM366_EMBI366", hoje), CRP_PADRAO,
                "Risco-país (EMBI+ Brasil), convertido de pontos-base para % a.a.", lambda v: v / 100),
        "pi_us": (lambda: fp.fred("T10YIE", hoje), PI_US_PADRAO, "Inflação implícita dos EUA em 10 anos (FRED, breakeven).", lambda v: v),
        "pi_br": (lambda: fp.focus("IPCA", ano, hoje), 3.5,
                  f"Expectativa de inflação de longo prazo (Focus, IPCA {ano}). Na falta dela, 3,5%: meta de 3% mais a "
                  "folga histórica. A inflação implícita nos títulos é maior porque embute um prêmio de risco.", lambda v: v),
    }
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut = {k: ex.submit(_ou_premissa, f, padrao, nota, conv) for k, (f, padrao, nota, conv) in tarefas.items()}
        return {k: v.result() for k, v in fut.items()}


def _dfc(cnpj: str) -> pd.DataFrame:
    for sufixo in ("DFC_MI_con", "DFC_MD_con"):  # cada empresa usa um dos dois métodos
        df = f.demonstrativo(sufixo, cnpj)
        if not df.empty:
            return df
    return pd.DataFrame()


def crescimento_receita(cnpj: str, anos: int = 8) -> dict:
    """Crescimento anual da receita líquida (DRE 3.01) nos DFPs da CVM. Serve ao Monte Carlo: a DISPERSÃO do crescimento
    histórico mede a incerteza da premissa de crescimento (o fluxo de caixa oscila demais para isso)."""
    from indicadores_b3.analytics.valuation_rapido import _dfp, _valor
    receita: dict[int, float] = {}
    for arq in range(f.ANO - 1, f.ANO - anos - 1, -2):  # cada DFP traz o ano e o anterior
        try:
            dre = _dfp("DRE_con", arq, cnpj)
        except Exception:  # noqa: BLE001 — ano sem arquivo: segue com os outros
            continue
        if dre.empty:
            continue
        for ordem, ano in (("ÚLT", arq), ("PEN", arq - 1)):
            v = _valor(dre, ["3.01"], ordem, True)
            if v and ano not in receita:
                receita[ano] = v
    anos_ok = sorted(receita)
    serie = [{"ano": a, "receita": receita[a], "cresc": (receita[a] / receita[a - 1] - 1) * 100 if a - 1 in receita and receita[a - 1] > 0 else None}
             for a in anos_ok]
    cs = [x["cresc"] for x in serie if x["cresc"] is not None]
    return {"anos": serie, "n": len(cs), "media": statistics.mean(cs) if cs else None,
            "desvio": statistics.stdev(cs) if len(cs) >= 3 else None,
            "fonte": "CVM · DFP · DRE 3.01 (receita líquida)"}


def historico_anual(df: pd.DataFrame, conta: str) -> list[dict]:
    """Valores anuais (DFP) da conta, com a linha da CVM de cada ano."""
    out = []
    for ref in sorted(df[df.FONTE == "DFP"].DT_REFER.unique()):
        r = f.linha_acumulada(df, "DFP", ref, "ÚLT", conta)
        if r is not None:
            out.append({"ano": ref[:4], "valor": float(r.VL), "linha": f.linha_cvm(r)})
    return out


AJUSTES_FIN = {  # linhas de "financiamento" (6.03) que, em substância, são operacionais
    "arrendamento": (r"^(?!.*(?:fornecedor|conv[êe]nio|risco sacado)).*(?:arrendamento|loca[çc][ãa]o|lease|direito de uso)",
                     "Pagamentos de arrendamento (IFRS 16)"),
    "fornecedores": (r"fornecedor|conv[êe]nio|risco sacado|forfait|confirming", "Pagamentos a fornecedores via convênio/risco sacado"),
}


def _ajustes_normalizados(dfc: pd.DataFrame) -> pd.DataFrame:
    """As linhas de ajuste achadas pela DESCRIÇÃO em cada documento (o código muda entre DFP e ITR da mesma empresa)."""
    from indicadores_b3.agents.financial import normalizar
    return normalizar(dfc, {k: (rx, "6.03", 4, None) for k, (rx, _) in AJUSTES_FIN.items()})


def _ajuste_ttm(norm: pd.DataFrame, chave: str) -> dict:
    if norm.empty or chave not in set(norm.CD_CONTA):
        return rastro(0.0, [], "Nenhuma linha encontrada.")
    from indicadores_b3.agents.financial import ttm_c
    r = ttm_c(norm, chave)
    if r["valor"] is not None:
        return r
    anual = historico_anual(norm, chave)  # a linha não existe em algum trimestre: usa o último ano fechado
    if anual:
        a = anual[-1]
        return rastro(a["valor"], [comp("+", f"Ano fechado de {a['ano']} (DFP)", a["linha"])],
                      "Sem os trimestres para somar 12 meses: usado o último ano fechado.")
    return rastro(0.0, [], "Faltam períodos para somar 12 meses.")


def _fcff_resultado(base: dict, fci: dict, ir: float = IR_PADRAO) -> dict:
    r = base["rastreio"]
    ebit, da = r.get("ebit") or {}, r.get("depreciacao") or {}
    if ebit.get("valor") is None or da.get("valor") is None or fci.get("valor") is None:
        return rastro(None, [], "Faltam EBIT, depreciação ou investimentos para a conferência pelo resultado.")
    v = ebit["valor"] * (1 - ir / 100) + da["valor"] + fci["valor"]
    return rastro(v, [{**c, "papel": "EBIT · " + c.get("papel", "")} for c in ebit.get("componentes", [])]
                  + [{**c, "papel": "Depreciação · " + c.get("papel", "")} for c in da.get("componentes", [])]
                  + [{**c, "papel": "Investimentos · " + c.get("papel", "")} for c in fci.get("componentes", [])],
                  f"FCFF pelo resultado = EBIT × (1 − {ir:.0f}%) + depreciação e amortização + investimentos (negativo). "
                  "Ignora a variação do capital de giro; serve para conferir se o FCL da DFC é plausível.")


def dados_dcf(ticker: str) -> dict:
    base = f.dados_base(ticker)
    if base.get("banco"):
        raise LookupError(f"{base['ticker']} é um banco: caixa e dívida são a própria operação, e o DCF de fluxo de caixa livre não se aplica. "
                          "Use a aba Research, que avalia bancos pelo P/VP justificado (ROE, custo de capital e crescimento).")
    cnpj = f.mapa_tickers()[base["ticker"]]
    dfc = _dfc(cnpj)
    if dfc.empty:
        raise LookupError(f"{ticker}: Demonstração dos Fluxos de Caixa não encontrada na CVM.")

    fco, fci = f.ttm(dfc, "6.01"), f.ttm(dfc, "6.02")
    if fco["valor"] is None or fci["valor"] is None:
        raise LookupError(f"{ticker}: contas 6.01/6.02 não encontradas na DFC.")
    fcl_contabil = {"valor": fco["valor"] + fci["valor"],
                    "componentes": [{**c, "papel": "Operações · " + c["papel"]} for c in fco["componentes"]]
                                   + [{**c, "papel": "Investimentos · " + c["papel"]} for c in fci["componentes"]],
                    "nota": "FCL contábil = caixa gerado pelas operações + caixa usado em investimentos (12 meses). " + fco["nota"]}
    norm_aj = _ajustes_normalizados(dfc)
    ajustes = {}
    for k in AJUSTES_FIN:
        r = _ajuste_ttm(norm_aj, k)
        ajustes[k] = {**r, "rotulo": AJUSTES_FIN[k][1],
                      "contas": list(dict.fromkeys(f"{(c.get('documento') or '').split(' ·')[0]} {c.get('conta')}".strip()
                                                   for c in r["componentes"] if c.get("conta")))}
    total_aj = sum(a["valor"] or 0 for a in ajustes.values())
    fcl = {"valor": fcl_contabil["valor"] + total_aj,
           "componentes": fcl_contabil["componentes"] + [{**c, "papel": f"{a['rotulo']} · " + c["papel"]}
                                                          for a in ajustes.values() for c in a["componentes"]],
           "nota": "FCL ajustado = FCL contábil − arrendamentos − pagamentos a fornecedores via convênio (linhas de financiamento "
                   "que, em substância, são custo da operação)." if total_aj else "Sem linhas de arrendamento ou convênio na DFC: FCL = FCL contábil."}
    alertas = []
    var_giro = f.ttm(dfc, "6.01.02")
    if var_giro["valor"] is not None and fco["valor"] and abs(var_giro["valor"]) > 0.5 * abs(fco["valor"]):
        alertas.append(f"A variação de capital de giro (6.01.02) responde por {abs(var_giro['valor']) / abs(fco['valor']) * 100:.0f}% do caixa "
                       "das operações: o FCL de 12 meses pode estar distorcido. Compare com a conferência pelo resultado.")

    hist_fco, hist_fci = historico_anual(dfc, "6.01"), historico_anual(dfc, "6.02")
    anos = sorted({h["ano"] for h in hist_fco} & {h["ano"] for h in hist_fci})
    historico = [{"ano": a,
                  "fco": next(h["valor"] for h in hist_fco if h["ano"] == a),
                  "fci": next(h["valor"] for h in hist_fci if h["ano"] == a)} for a in anos]
    aj_anual = {k: historico_anual(norm_aj, k) if not norm_aj.empty and k in set(norm_aj.CD_CONTA) else [] for k in AJUSTES_FIN}
    for h in historico:
        h["fcl_contabil"] = h["fco"] + h["fci"]
        h["ajustes"] = sum(x["valor"] for xs in aj_anual.values() for x in xs if x["ano"] == h["ano"])
        h["fcl"] = h["fcl_contabil"] + h["ajustes"]

    try:
        cdi = cdi_atual()
    except Exception:
        cdi = None

    r = base["rastreio"]
    simbolo = f"{base['ticker']}.SA"
    return {
        "wacc": dados_wacc(cnpj, simbolo),
        "ticker": base["ticker"], "empresa": base["empresa"], "balanco_ref": base["balanco_ref"],
        "rastreio": {
            "fco": fco, "fci": fci, "fcl_contabil": fcl_contabil, "fcl": fcl,
            "fcff_resultado": _fcff_resultado(base, fci),
            "divida_bruta": r["divida_bruta"], "caixa": r["caixa"],
            "acoes": r["acoes"], "preco": r["preco"],
        },
        "ajustes": [{"chave": k, "rotulo": a["rotulo"], "valor": a["valor"], "contas": a["contas"]} for k, a in ajustes.items()],
        "alertas": alertas,
        "historico": historico,
        "crescimento_receita": crescimento_receita(cnpj),
        "cdi": cdi,
    }
