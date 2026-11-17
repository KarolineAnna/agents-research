"""Cara ou barata? Três lentes independentes, cada uma com a sua conta à mostra.

1. Contra a própria história: P/L e P/VP de hoje contra a mediana dos fins de ano anteriores (DFP da CVM).
   O múltiplo de cada fim de ano é reconstruído a partir do múltiplo de hoje, sem depender da quantidade de ações:
       P/L(ano)  = P/L(hoje)  × [preço(fim do ano) ÷ preço(hoje)] × [lucro 12m(hoje) ÷ lucro(ano)]
       P/VP(ano) = P/VP(hoje) × [preço(fim do ano) ÷ preço(hoje)] × [PL(hoje) ÷ PL(fim do ano)]
   O preço é o fechamento ajustado só por desdobramentos (sem proventos). Supõe a mesma quantidade de ações:
   recompras e emissões grandes distorcem a comparação.
2. Contra os pares do setor (cadastro da CVM, mais negociadas primeiro): múltiplo de hoje contra a mediana dos pares.
3. Preço justo:
   - empresas em geral: DCF do fluxo da firma com as premissas padrão da aba Balanços → DCF
     (crescimento 5% por 5 anos convergindo para g = 3,5%, WACC com Ke de mercado, meio do ano, três cenários);
   - bancos: P/VP justificado (ROE − g) ÷ (Ke − g), o mesmo cálculo do Research.
Regra de leitura (a mesma do Research): diferença acima de 15% para um lado = barata ou cara; dentro de 15% = no preço.
Nada aqui é recomendação: P/L baixo pode ser lucro no pico (cíclicas) e o mercado pode estar certo.
"""
from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import pandas as pd

from indicadores_b3.analytics import historico_preco
from indicadores_b3.data import fundamentos as f

LIMIAR = 15.0  # %
ANOS_HIST = 7
NOMES = {"barata": "Barata", "justa": "No preço", "cara": "Cara"}


def leitura(diferenca_pct: float | None, invertido: bool = False) -> str | None:
    """Múltiplo: abaixo da referência = barata. Potencial de preço justo (invertido): acima = barata."""
    if diferenca_pct is None:
        return None
    d = -diferenca_pct if invertido else diferenca_pct
    return "barata" if d < -LIMIAR else "cara" if d > LIMIAR else "justa"


def _dif(atual, ref):
    return None if atual is None or ref in (None, 0) else (atual / ref - 1) * 100


# ---------- 1. história própria ----------
def _dfp(sufixo: str, ano: int, cnpj: str) -> pd.DataFrame:
    df = f.ler_csv("DFP", ano, sufixo, cnpj)
    if df.empty:
        return df
    df = df.copy()
    df["VERSAO"] = df["VERSAO"].astype(int)
    df = df[df["VERSAO"] == df["VERSAO"].max()]
    mult = df["ESCALA_MOEDA"].str.upper().eq("MIL").map({True: 1000, False: 1})
    df["VL"] = df["VL_CONTA"].astype(float) * mult
    return df


def _valor(df: pd.DataFrame, contas: list[str], ordem: str, resultado: bool) -> float | None:
    tot = 0.0
    for c in contas:
        d = df[df.ORDEM_EXERC.str.startswith(ordem) & (df.CD_CONTA == c)]
        if d.empty:
            return None
        if resultado:  # acumulado do exercício (não o trimestre)
            d = d[d.DT_INI_EXERC == d.DT_INI_EXERC.min()]
        tot += float(d.VL.iloc[0])
    return tot


def contas_do_ano(dre: pd.DataFrame, bpp: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    """(lucro dos controladores, PL consolidado, não controladores) no plano de contas do documento."""
    from indicadores_b3.agents import financial as fin
    if fin.eh_banco(dre):
        lucro = fin.achar(dre, fin.BANCO_DRE["lucro_controladores"], "3", 4) or fin.achar(dre, fin.BANCO_DRE["lucro_total"], "3", 2)[-1:]
        pl = fin.achar(bpp, fin.BANCO_BP["pl_consolidado"], "2", 2)
        nc = fin.achar(bpp, fin.BANCO_BP["nao_controladores"], pl[0], 3) if pl else []
        return lucro, pl, nc
    codigos = set(dre.CD_CONTA)
    lucro = ["3.11.01"] if "3.11.01" in codigos else ["3.11"]
    nc = sorted(set(bpp[bpp.CD_CONTA.str.startswith("2.03.") & bpp.DS_CONTA.str.contains("Não Controladores", case=False, na=False)].CD_CONTA))[:1]
    return lucro, ["2.03"], nc


def contabil_por_ano(cnpj: str, ano_atual: int | None = None, anos: int = ANOS_HIST) -> dict[int, dict]:
    """{ano: {lucro, pl, documento}} dos fins de exercício. Cada DFP traz o ano e o anterior, então basta um arquivo a cada dois anos."""
    ano_atual = ano_atual or f.ANO
    out: dict[int, dict] = {}
    for arq in range(ano_atual - 1, ano_atual - anos - 1, -2):
        dre, bpp = _dfp("DRE_con", arq, cnpj), _dfp("BPP_con", arq, cnpj)
        if dre.empty or bpp.empty:
            continue
        try:
            lucro_c, pl_c, nc_c = contas_do_ano(dre, bpp)
        except (IndexError, KeyError):
            continue
        for ordem, ano in (("ÚLT", arq), ("PEN", arq - 1)):
            if ano in out:
                continue
            lucro, pl = _valor(dre, lucro_c, ordem, True), _valor(bpp, pl_c, ordem, False)
            menos = _valor(bpp, nc_c, ordem, False) if nc_c else 0.0
            if lucro is None or pl is None:
                continue
            out[ano] = {"lucro": lucro, "pl": pl - (menos or 0.0),
                        "documento": f"DFP {arq} ({'exercício' if ordem == 'ÚLT' else 'coluna do ano anterior'})",
                        "contas": {"lucro": lucro_c, "pl": pl_c, "nao_controladores": nc_c}}
    return dict(sorted(out.items()))


def multiplos_historicos(atual: dict, contabil: dict[int, dict], fechamento: pd.Series) -> list[dict]:
    """atual = {preco, pl_mult, pvp, lucro, pl}. fechamento: série diária ajustada só por desdobramentos."""
    if fechamento.empty:
        return []
    p_hoje = float(fechamento.iloc[-1])
    linhas = []
    for ano, c in contabil.items():
        s = fechamento[fechamento.index <= pd.Timestamp(f"{ano}-12-31")]
        if s.empty or s.index[-1] < pd.Timestamp(f"{ano}-12-01"):
            continue  # sem preço no fim daquele ano (ação listada depois)
        p_ano = float(s.iloc[-1])
        fator = p_ano / p_hoje
        pl_ano = (atual["pl_mult"] * fator * atual["lucro"] / c["lucro"]
                  if atual.get("pl_mult") and atual.get("lucro") and c["lucro"] > 0 else None)
        pvp_ano = (atual["pvp"] * fator * atual["pl"] / c["pl"]
                   if atual.get("pvp") and atual.get("pl") and c["pl"] > 0 else None)
        linhas.append({"ano": ano, "data_preco": s.index[-1].strftime("%Y-%m-%d"), "preco": p_ano,
                       "lucro": c["lucro"], "pl": c["pl"], "p_l": pl_ano if pl_ano and pl_ano > 0 else None,
                       "p_vp": pvp_ano, "documento": c["documento"]})
    return linhas


def _qtd(n: int, um: str, varios: str) -> str:
    return f"mediana de {n} {um if n == 1 else varios}"


def _mediana(xs):
    xs = [x for x in xs if x is not None and x > 0]
    return statistics.median(xs) if xs else None


# ---------- 2. pares ----------
def multiplos_pares(ticker: str, n: int = 5, calcular=None) -> dict:
    from indicadores_b3.analytics import indicadores
    from indicadores_b3.data import setores
    calc = calcular or indicadores.calcular
    info = setores.pares(ticker, n)
    tks = [p["ticker"] for p in info.get("pares", [])]

    def um(t):
        try:
            r = calc(t)
            v = {i["id"]: i["valor"] for i in r["indicadores"]}
            return {"ticker": t, "empresa": r.get("empresa"), "p_l": v.get("pl"), "p_vp": v.get("pvp")}
        except Exception as e:  # noqa: BLE001 — um par sem dados não derruba o resto
            return {"ticker": t, "erro": str(e)[:160]}

    with ThreadPoolExecutor(max_workers=4) as ex:
        linhas = list(ex.map(um, tks))
    return {"criterio": info.get("criterio"), "setor": info.get("setor"), "pares": linhas,
            "mediana_p_l": _mediana([x.get("p_l") for x in linhas]), "mediana_p_vp": _mediana([x.get("p_vp") for x in linhas])}


# ---------- 3. preço justo ----------
PREM_DCF = {"cresc": 5.0, "g": 3.5, "anos": 5, "anos2": 5, "meio": True,
            "cen": {"pessimista": (-3, 1.5, -0.5, 25), "base": (0, 0, 0, 50), "otimista": (3, -1, 0.5, 25)}}


def wacc_padrao(d: dict) -> dict:
    """Mesmo cálculo de iniciarWACC/calcWACC (dcf.js) com os insumos padrão: β ajustado, Ke de mercado, Kd implícito."""
    w, R = d.get("wacc") or {}, d["rastreio"]
    D = R["divida_bruta"]["valor"] or 0
    desp = abs((w.get("despesa_fin") or {}).get("valor") or 0)
    rf = (w.get("rf") or {}).get("valor") or ((d.get("cdi") or {}).get("valor") or 13)
    kd = desp / D * 100 if D > 0 and desp > 0 else rf + 2
    if kd > 30 or kd < 5:
        kd = rf + 2
    beta_bruto = (w.get("beta") or {}).get("valor") or 1.0
    beta = 0.67 * beta_bruto + 0.33
    erp, ir = w.get("erp") or 5.0, w.get("ir") or 34.0
    mu = w.get("mercado_usd") or {}

    def v(k, padrao):
        return (mu.get(k) or {}).get("valor") or padrao
    if mu.get("rf_us"):
        ke_usd = v("rf_us", 4.3) + v("crp", 2.5) + beta * erp
        ke = ((1 + ke_usd / 100) * (1 + v("pi_br", 3.5) / 100) / (1 + v("pi_us", 2.3) / 100) - 1) * 100
        metodo = "Ke de mercado (Treasury + risco-país + β × prêmio, convertido para reais)"
    else:
        ke = rf + beta * erp
        metodo = "Ke local (juro brasileiro + β × prêmio)"
    E = (R["preco"]["valor"] or 0) * (R["acoes"]["valor"] or 0)
    pe = E / (E + D) if E + D > 0 else 1
    return {"ke": ke, "kd_liq": kd * (1 - ir / 100), "beta": beta, "peso_acoes": pe,
            "wacc": pe * ke + (1 - pe) * kd * (1 - ir / 100), "metodo_ke": metodo}


def dcf_por_acao(fcl0: float, r: float, g: float, cresc: float, divida_liq: float, acoes: float,
                 anos: int = 5, anos2: int = 5, meio: bool = True) -> float | None:
    """Mesma conta de calcularDCF (dcf.js), fluxo da firma."""
    if r <= g or not acoes:
        return None
    r_, g_ = r / 100, g / 100
    fcl, soma, n = fcl0, 0.0, anos + anos2
    for t in range(1, n + 1):
        c = cresc if t <= anos else cresc + (g - cresc) * (t - anos) / (anos2 + 1)
        fcl *= 1 + c / 100
        soma += fcl / (1 + r_) ** (t - (0.5 if meio else 0))
    terminal = fcl * (1 + g_) / (r_ - g_)
    vp_term = terminal / (1 + r_) ** (n - (0.5 if meio else 0))
    return (soma + vp_term - divida_liq) / acoes


def preco_justo_dcf(d: dict) -> dict:
    R = d["rastreio"]
    fcl0 = (R.get("fcl") or {}).get("valor")
    preco = R["preco"]["valor"]
    if fcl0 is None or fcl0 <= 0:
        return {"metodo": "DCF", "valor": None,
                "nota": "Fluxo de caixa livre dos últimos 12 meses negativo ou indisponível: o DCF padrão não se aplica. "
                        "Use a aba Balanços → DCF com outra base (média dos anos ou pelo resultado)."}
    w = wacc_padrao(d)
    dl = (R["divida_bruta"]["valor"] or 0) - (R["caixa"]["valor"] or 0)
    cen = []
    for nome, (dc, dr, dg, peso) in PREM_DCF["cen"].items():
        r, g, c = w["wacc"] + dr, PREM_DCF["g"] + dg, PREM_DCF["cresc"] + dc
        cen.append({"nome": nome, "peso": peso, "cresc": c, "r": r, "g": g,
                    "por_acao": dcf_por_acao(fcl0, r, g, c, dl, R["acoes"]["valor"], PREM_DCF["anos"], PREM_DCF["anos2"], PREM_DCF["meio"])})
    val = [c for c in cen if c["por_acao"] is not None]
    pond = sum(c["peso"] * c["por_acao"] for c in val) / sum(c["peso"] for c in val) if val else None
    return {"metodo": "DCF (fluxo da firma, premissas padrão)", "valor": pond, "preco": preco,
            "potencial": _dif(pond, preco), "cenarios": cen, "wacc": w, "fcl": fcl0, "divida_liquida": dl,
            "nota": (f"WACC {w['wacc']:.1f}% ({w['metodo_ke']}); crescimento de {PREM_DCF['cresc']:.0f}% ao ano por "
                     f"{PREM_DCF['anos']} anos, convergindo para g = {PREM_DCF['g']:.1f}%.").replace(".", ",").replace("%,", "%.").rstrip(",") +
                    " Premissas padrão: empresas que crescem rápido costumam valer mais que isso. Ajuste em Balanços → DCF."}


def preco_justo_banco(ticker: str) -> dict:
    from indicadores_b3.agents import financial, investment, market
    fin = financial.analisar(ticker).to_dict()
    mkt = market.analisar(ticker).to_dict()
    inv = investment.analisar(fin, {}, mkt).to_dict()
    item = {x["nome"]: x for x in inv["itens"]}
    pj = next((v for k, v in item.items() if k.startswith("Preço justo ponderado")), None)
    pot = next((v for k, v in item.items() if k.startswith("Potencial ponderado")), None)
    cen = [{"nome": k.split("— ")[-1], "valor": v["valor"]} for k, v in item.items() if k.startswith("Preço justo — ")]
    return {"metodo": "P/VP justificado (ROE − g) ÷ (Ke − g)", "valor": pj and pj["valor"],
            "potencial": pot and pot["valor"], "cenarios": cen,
            "nota": "Mesmo cálculo do Research (três cenários de ROE e Ke). Os detalhes e as premissas ficam no Research."}


# ---------- tudo junto ----------
@lru_cache(maxsize=32)
def _avaliar_dia(ticker: str, chave: str) -> dict:
    return _avaliar(ticker)


def avaliar(ticker: str, **testes) -> dict:
    """Refeito a cada 15 minutos durante o pregão (o preço muda) e uma vez por dia fora dele.
    Os balanços antigos e os dos pares ficam no cache de disco da CVM, então refazer é rápido. Os parâmetros de teste ignoram o cache."""
    from indicadores_b3.data.fontes import chave_preco
    if testes:
        return _avaliar(ticker, **testes)
    return _avaliar_dia(ticker.strip().upper(), chave_preco())


def _avaliar(ticker: str, calcular=None, dcf_fn=None, precos_fn=None, banco_fn=None, pares_fn=None) -> dict:
    """Junta as três lentes. Os parâmetros *_fn existem para os testes (sem internet)."""
    from indicadores_b3.analytics import dcf, indicadores
    t = ticker.strip().upper()
    calc = calcular or indicadores.calcular
    base = calc(t)
    if base.get("tipo") != "acao":
        raise ValueError("A leitura cara/barata usa balanços da CVM: só vale para ações de companhias abertas.")
    ind = {i["id"]: i["valor"] for i in base["indicadores"]}
    val = base["valores"]
    banco = bool(base.get("banco"))
    atual = {"preco": val.get("preco"), "pl_mult": ind.get("pl"), "pvp": ind.get("pvp"),
             "lucro": val.get("lucro_contr"), "pl": val.get("pl_contr")}
    avisos: list[str] = []

    # 1. história
    hist: list[dict] = []
    try:
        cnpj = f.mapa_tickers().get(t)
        contabil = contabil_por_ano(cnpj) if cnpj else {}
        precos = (precos_fn or (lambda s: historico_preco.baixar(s, "10y")))(f"{t}.SA")
        fech = precos["Close"].dropna().astype(float) if not precos.empty and "Close" in precos else pd.Series(dtype=float)
        hist = multiplos_historicos(atual, contabil, fech)
    except Exception as e:  # noqa: BLE001
        avisos.append(f"Histórico próprio indisponível: {str(e)[:160]}")
    med_pl_h, med_pvp_h = _mediana([h["p_l"] for h in hist]), _mediana([h["p_vp"] for h in hist])

    # 2. pares
    try:
        pares = (pares_fn or (lambda x: multiplos_pares(x, calcular=calcular)))(t)
    except Exception as e:  # noqa: BLE001
        pares, _ = {"pares": [], "mediana_p_l": None, "mediana_p_vp": None}, avisos.append(f"Pares indisponíveis: {str(e)[:160]}")

    # 3. preço justo
    try:
        justo = (banco_fn or preco_justo_banco)(t) if banco else preco_justo_dcf((dcf_fn or dcf.dados_dcf)(t))
    except Exception as e:  # noqa: BLE001
        justo = {"metodo": "P/VP justificado" if banco else "DCF", "valor": None, "nota": f"Não calculado: {str(e)[:160]}"}

    # para bancos o múltiplo principal é o P/VP; para os demais, o P/L (com o P/VP de apoio)
    principal = "p_vp" if banco else "p_l"
    lentes = []

    def lente(id_, nome, atual_v, ref, rotulo_ref, detalhe):
        dif = _dif(atual_v, ref)
        lentes.append({"id": id_, "nome": nome, "atual": atual_v, "referencia": ref, "rotulo_ref": rotulo_ref,
                       "diferenca": dif, "leitura": leitura(dif), "detalhe": detalhe})

    sig = "P/VP" if principal == "p_vp" else "P/L"
    atual_p = atual["pvp"] if principal == "p_vp" else atual["pl_mult"]
    if atual_p is not None and atual_p <= 0:
        atual_p = None
        avisos.append("P/L negativo (prejuízo nos últimos 12 meses): a comparação por P/L não se aplica.")
    lente("historia", f"{sig} contra a própria história", atual_p, med_pvp_h if principal == "p_vp" else med_pl_h,
          _qtd(len([h for h in hist if h[principal]]), "fim de ano", "fins de ano"), "Fins de exercício (DFP) com o preço do último pregão de cada ano.")
    lente("pares", f"{sig} contra os pares do setor", atual_p, pares.get(f"mediana_{principal}"),
          _qtd(len([p for p in pares.get("pares", []) if p.get(principal)]), "par", "pares"), pares.get("criterio") or "")
    pot = justo.get("potencial")
    lentes.append({"id": "justo", "nome": f"Preço contra o preço justo ({justo.get('metodo')})", "atual": atual["preco"],
                   "referencia": justo.get("valor"), "rotulo_ref": "preço justo ponderado", "diferenca": pot,
                   "leitura": leitura(pot, invertido=True), "detalhe": justo.get("nota", "")})

    lidas = [x["leitura"] for x in lentes if x["leitura"]]
    if not lidas:
        veredito, texto = None, "Sem dados suficientes para uma leitura."
    elif len(set(lidas)) == 1:
        veredito = lidas[0]
        texto = f"As {len(lidas)} lentes disponíveis concordam: {NOMES[veredito].lower()}."
    else:
        cont = {k: lidas.count(k) for k in NOMES}
        maior = max(cont, key=cont.get)
        veredito = maior if cont[maior] > len(lidas) / 2 else "mista"
        texto = ("Sinais mistos: " + ", ".join(f"{NOMES[k].lower()} em {v}" for k, v in cont.items() if v)
                 + (f". Maioria: {NOMES[maior].lower()}." if veredito != "mista" else "."))
    return {"ticker": t, "empresa": base.get("empresa"), "banco": banco, "preco": atual["preco"],
            "multiplos": {"p_l": atual["pl_mult"], "p_vp": atual["pvp"]}, "principal": principal,
            "veredito": veredito, "texto": texto, "lentes": lentes, "historico": hist,
            "mediana_hist": {"p_l": med_pl_h, "p_vp": med_pvp_h}, "pares": pares, "preco_justo": justo,
            "avisos": avisos, "limiar": LIMIAR,
            "regra": f"Regra do projeto (escolhida, não vem de estudo): diferença acima de {LIMIAR:.0f}% contra a referência = cara (ou barata, se abaixo); dentro de {LIMIAR:.0f}% = no preço. "
                     "Não é recomendação: múltiplo baixo pode ser lucro no pico (empresas cíclicas) e o mercado pode ter razão.",
            "balanco_ref": base.get("balanco_ref")}
