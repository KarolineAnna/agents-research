
"""Análise de renda fixa: títulos do Tesouro Direto, curvas de juros e inflação implícita.

Precificação (convenção do Tesouro/ANBIMA, base 252 dias úteis):
  PU = Σ fluxoᵢ ÷ (1 + taxa)^(duᵢ/252)
  - Prefixado (LTN): um fluxo de R$ 1.000 no vencimento
  - Prefixado com juros semestrais (NTN-F): cupom de 10% a.a. (4,8809% ao semestre) sobre R$ 1.000
  - IPCA+ (NTN-B Principal): 100% do VNA no vencimento (preço calculado em % do VNA)
  - IPCA+ com juros semestrais (NTN-B): cupom de 6% a.a. (2,9563% ao semestre) sobre o VNA
  - Selic (LFT): pós-fixado; o risco de juros é só o do ágio/deságio
  - Renda+ e Educa+: fluxos mensais especiais, fora desta análise por enquanto

Cupons: a cada 6 meses, contando para trás a partir do vencimento.
Dias úteis: calendário de feriados nacionais (fixos + Carnaval, Sexta-feira Santa e Corpus Christi).
O PU calculado é comparado com o PU publicado pelo Tesouro, para conferência.
"""
from datetime import date, timedelta
from functools import cache, lru_cache

import numpy as np
import pandas as pd

from indicadores_b3.data import futuros, tesouro
from indicadores_b3.data.fontes import erro_amigavel

CUPOM_NTNF = 1.10 ** 0.5 - 1   # 4,8809% ao semestre
CUPOM_NTNB = 1.06 ** 0.5 - 1   # 2,9563% ao semestre


# ---------- calendário ----------
def pascoa(ano: int) -> date:
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


@cache
def feriados(ano: int) -> tuple:
    p = pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    if ano >= 2024:
        fixos.append((11, 20))  # Consciência Negra, feriado nacional desde 2024
    moveis = [p - timedelta(days=48), p - timedelta(days=47), p - timedelta(days=2), p + timedelta(days=60)]
    return tuple(sorted([date(ano, m, d) for m, d in fixos] + moveis))


def todos_feriados(d1: date, d2: date) -> list:
    return [f for a in range(d1.year, d2.year + 1) for f in feriados(a)]


@lru_cache(maxsize=200_000)
def du(d1: date, d2: date) -> int:
    """Dias úteis entre d1 (inclusive) e d2 (exclusive)."""
    return int(np.busday_count(d1, d2, holidays=todos_feriados(d1, d2)))


def proximo_util(d: date) -> date:
    fer = set(feriados(d.year))
    while d.weekday() >= 5 or d in fer:
        d += timedelta(days=1)
    return d


# ---------- fluxos e métricas ----------
def datas_cupom(venc: date, base: date) -> list[date]:
    datas, d = [], venc
    while d > base:
        datas.append(d)
        d = (pd.Timestamp(d) - pd.DateOffset(months=6)).date()
    return sorted(datas)


def fluxos(sigla: str, venc: date, base: date) -> tuple[list[dict], str]:
    if sigla == "PRE":
        return [{"data": venc, "valor": 1000.0, "tipo": "principal"}], "R$"
    if sigla == "IPCA":
        return [{"data": venc, "valor": 100.0, "tipo": "principal"}], "% do VNA"
    if sigla in ("PREJS", "IPCAJS"):
        cup = 1000 * CUPOM_NTNF if sigla == "PREJS" else 100 * CUPOM_NTNB
        principal = 1000.0 if sigla == "PREJS" else 100.0
        out = [{"data": d, "valor": cup, "tipo": "cupom"} for d in datas_cupom(venc, base)]
        out[-1] = {"data": venc, "valor": cup + principal, "tipo": "cupom + principal"}
        return out, "R$" if sigla == "PREJS" else "% do VNA"
    return [], ""


def analisar(fl: list[dict], taxa_pct: float, base: date) -> dict:
    y = taxa_pct / 100
    linhas, pu, soma_t, soma_conv = [], 0.0, 0.0, 0.0
    for f in fl:
        pag = proximo_util(f["data"])
        d = du(base, pag)
        t = d / 252
        fator = (1 + y) ** t
        vp = f["valor"] / fator
        pu += vp
        soma_t += t * vp
        soma_conv += t * (t + 1) * vp
        linhas.append({"data": pag.isoformat(), "du": d, "anos": t, "valor": f["valor"], "tipo": f["tipo"],
                       "fator": fator, "vp": vp})
    for l in linhas:
        l["peso"] = l["vp"] / pu
    mac = soma_t / pu
    pu_mais = sum(l["valor"] / (1 + y + 0.0001) ** l["anos"] for l in linhas)
    return {"fluxos": linhas, "pu": pu, "duration_macaulay": mac, "duration_modificada": mac / (1 + y),
            "convexidade": soma_conv / (pu * (1 + y) ** 2), "dv01": pu_mais - pu}


# ---------- títulos ----------
NOMES_SIGLA = {v: k for k, v in tesouro.SIGLAS.items()}


def titulos() -> dict:
    df = tesouro.tabela()
    ult = df[df["base"] == df["base"].max()].sort_values(["Tipo Titulo", "vencimento"])
    base = ult["base"].iloc[0].date()
    # Os preços do Tesouro são para liquidação no dia útil seguinte à data base: os dias úteis
    # contam a partir daí (conferido contra o PU publicado: diferença cai de ~0,05% para ~0,001%).
    liq = proximo_util(base + timedelta(days=1))
    venda = tesouro.a_venda()
    itens = []
    for _, r in ult.iterrows():
        sigla, venc, taxa = r["sigla"], r["vencimento"].date(), float(r["Taxa Compra Manha"])
        item = {"codigo": r["codigo"], "tipo": r["Tipo Titulo"], "sigla": sigla, "vencimento": venc.isoformat(),
                "taxa": taxa, "pu_publicado": float(r["PU Compra Manha"]), "anos": (venc - base).days / 365.25,
                "suportado": sigla in ("PRE", "PREJS", "IPCA", "IPCAJS", "SELIC"),
                "a_venda": (r["codigo"] in venda["codigos"]) if venda["ok"] else None}
        fl, unidade = fluxos(sigla, venc, liq)
        if fl:
            a = analisar(fl, taxa, liq)
            item.update({"unidade": unidade, **a})
            if unidade == "R$":
                item["diferenca_pu"] = (a["pu"] / item["pu_publicado"] - 1) * 100
            else:  # IPCA+: o PU publicado = cotação × VNA → VNA implícito
                item["vna_implicito"] = item["pu_publicado"] / (a["pu"] / 100)
                item["dv01_reais"] = a["dv01"] / 100 * item["vna_implicito"]
        elif sigla == "SELIC":
            d = du(liq, proximo_util(venc))
            item.update({"unidade": "R$", "duration_macaulay": d / 252, "duration_modificada": None, "fluxos": [],
                         "nota": "Pós-fixado: o valor acompanha a Selic, então quase não sofre com a alta dos juros. "
                                 "A taxa mostrada é o ágio/deságio sobre a Selic; só ela gera marcação a mercado."})
        itens.append(item)
    venda_info = {"ok": venda["ok"], "url": venda["url"], "erro": venda.get("erro"), "nota": venda.get("nota"), "ate": venda.get("ate"),
                  "n_venda": sum(1 for i in itens if i["a_venda"]) if venda["ok"] else None}
    return {"data_base": base.isoformat(), "liquidacao": liq.isoformat(), "fonte": {"url": tesouro.URL, "pagina": tesouro.PAGINA},
            "venda": venda_info, "titulos": itens}


def interp(x, xs, ys):
    if not xs:
        return None
    return float(np.interp(x, xs, ys)) if xs[0] <= x <= xs[-1] else None


def curvas(dados_titulos: dict) -> dict:
    T = dados_titulos["titulos"]
    pre = sorted([(t["anos"], t["taxa"], t["codigo"]) for t in T if t["sigla"] in ("PRE", "PREJS")])
    real = sorted([(t["anos"], t["taxa"], t["codigo"]) for t in T if t["sigla"] in ("IPCA", "IPCAJS")])
    xs, ys = [p[0] for p in pre], [p[1] for p in pre]
    implicita = []
    for anos, taxa_real, cod in real:
        tp = interp(anos, xs, ys)
        if tp is not None:
            implicita.append({"anos": anos, "codigo": cod, "pre": tp, "real": taxa_real,
                              "inflacao": ((1 + tp / 100) / (1 + taxa_real / 100) - 1) * 100})
    try:
        di = futuros.curva_di(int(pd.Timestamp.now().timestamp() // 3600))
    except Exception as e:
        di = {"erro": erro_amigavel(e)}
    return {"pre": [{"anos": a, "taxa": t, "codigo": c} for a, t, c in pre],
            "real": [{"anos": a, "taxa": t, "codigo": c} for a, t, c in real],
            "implicita": implicita, "di": di}


def historico(codigo: str, anos: int = 3) -> dict:
    t = tesouro.titulo(codigo)
    t = t[t["base"] >= t["base"].max() - pd.DateOffset(years=anos)]
    return {"codigo": codigo.upper(), "nome": tesouro.nome(codigo),
            "datas": t["base"].dt.strftime("%Y-%m-%d").tolist(),
            "taxa": [None if pd.isna(x) else round(float(x), 4) for x in t["Taxa Compra Manha"]],
            "pu": [None if pd.isna(x) else round(float(x), 2) for x in t["PU Base Manha"]],
            "fonte": tesouro.URL}


def dados() -> dict:
    tt = titulos()
    return {**tt, "curvas": curvas(tt)}


# ---------- simulador de investimento ----------
IOF_REGRESSIVO = [96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50,
                  46, 43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3]  # % do rendimento, dias 1 a 29
BASE_LEGAL_IOF = "Decreto 6.306/2007, anexo (IOF regressivo sobre o rendimento nos primeiros 30 dias)"
SERIE_IPCA, SERIE_SELIC_META = 433, 432


@lru_cache(maxsize=4)
def _premissas_bc(dia: str) -> dict:
    """IPCA acumulado em 12 meses e meta Selic, do SGS do Banco Central (para as projeções)."""
    from indicadores_b3.data.fontes import sgs
    fim = pd.Timestamp(dia)
    out = {}
    try:
        s, url = sgs(SERIE_IPCA, fim - pd.DateOffset(months=14), fim)
        s = s.iloc[-12:]
        out["ipca"] = {"valor": float(((1 + s / 100).prod() - 1) * 100), "url": url,
                       "descricao": f"IPCA acumulado em 12 meses até {s.index[-1]:%m/%Y} (SGS {SERIE_IPCA})"}
    except Exception as e:  # noqa: BLE001
        out["ipca"] = {"valor": None, "erro": erro_amigavel(e)}
    try:
        s, url = sgs(SERIE_SELIC_META, fim - pd.Timedelta(days=60), fim)
        out["selic"] = {"valor": float(s.iloc[-1]), "url": url,
                        "descricao": f"Meta Selic em {s.index[-1]:%d/%m/%Y} (SGS {SERIE_SELIC_META})"}
    except Exception as e:  # noqa: BLE001
        out["selic"] = {"valor": None, "erro": erro_amigavel(e)}
    return out


def premissas_bc() -> dict:
    return _premissas_bc(pd.Timestamp.now().strftime("%Y-%m-%d"))


def _iof(dias: int) -> float:
    return IOF_REGRESSIVO[dias - 1] if 1 <= dias < 30 else 0.0


def simular(codigo: str, valor: float, data_venda: str | None = None, taxa_saida: float | None = None,
            ipca: float | None = None, selic: float | None = None, custodia: float = 0.20) -> dict:
    """Quanto você recebe, líquido, investindo `valor` hoje no título e vendendo em `data_venda`.

    Modelo: o indexador (VNA) cresce pela premissa de IPCA/Selic; na venda antes do vencimento, o preço é
    recalculado com a `taxa_saida` (marcação a mercado). Cupons líquidos são reinvestidos à taxa do
    próprio título (IPCA+: taxa real + IPCA projetado) até a saída, e o ganho do reinvestimento paga IR.
    """
    from indicadores_b3.analytics.impostos import BASE_LEGAL_RF, aliquota_renda_fixa
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")
    dados_t = titulos()
    t = next((x for x in dados_t["titulos"] if x["codigo"] == codigo.upper()), None)
    if not t:
        raise LookupError(f"Título {codigo} não encontrado no arquivo do Tesouro.")
    sigla = t["sigla"]
    if sigla not in ("PRE", "PREJS", "IPCA", "IPCAJS", "SELIC"):
        raise ValueError(f"{t['tipo']} paga fluxos mensais especiais e ainda não entra no simulador.")
    # compra liquidada no dia útil seguinte à data base dos preços
    base, venc = date.fromisoformat(dados_t["liquidacao"]), date.fromisoformat(t["vencimento"])
    venda = min(date.fromisoformat(data_venda), venc) if data_venda else venc
    if venda <= base:
        raise ValueError("A data de venda precisa ser depois da data base dos preços.")
    ate_venc = venda >= venc

    pb = premissas_bc()
    usado = {}
    if sigla in ("IPCA", "IPCAJS"):
        if ipca is None:
            ipca = pb["ipca"]["valor"]
            if ipca is None:
                raise LookupError("Não consegui o IPCA no Banco Central; informe a inflação esperada.")
            usado["ipca"] = {**pb["ipca"], "origem": "Banco Central"}
        else:
            usado["ipca"] = {"valor": ipca, "origem": "informado"}
    if sigla == "SELIC":
        if selic is None:
            selic = pb["selic"]["valor"]
            if selic is None:
                raise LookupError("Não consegui a Selic no Banco Central; informe a Selic esperada.")
            usado["selic"] = {**pb["selic"], "origem": "Banco Central"}
        else:
            usado["selic"] = {"valor": selic, "origem": "informado"}
    taxa0 = t["taxa"]
    y_e = (taxa0 if taxa_saida is None else taxa_saida) / 100

    # multiplicador do indexador (VNA) ao longo do tempo
    if sigla == "SELIC":
        vna0 = t["pu_publicado"] * (1 + taxa0 / 100) ** (du(base, proximo_util(venc)) / 252)
        fl = [{"data": proximo_util(venc).isoformat(), "valor": 1.0, "tipo": "principal"}]
        mult = lambda anos: vna0 * (1 + selic / 100) ** anos  # noqa: E731
    elif sigla in ("IPCA", "IPCAJS"):
        fl = t["fluxos"]
        mult = lambda anos: t["vna_implicito"] / 100 * (1 + ipca / 100) ** anos  # noqa: E731
    else:
        fl = t["fluxos"]
        mult = lambda anos: 1.0  # noqa: E731

    qtd = valor / t["pu_publicado"]
    taxa_reinv = (1 + taxa0 / 100) * (1 + ipca / 100) - 1 if sigla == "IPCAJS" else taxa0 / 100
    anos_venda = du(base, venda) / 252

    def resultado(dv: date, detalhar: bool) -> dict:
        a_v = du(base, dv) / 252
        dias = (dv - base).days
        cupons, ir_cupons = [], 0.0
        for f in fl:
            dp = date.fromisoformat(f["data"])
            if dp <= dv and f["tipo"] != "principal":
                bruto = qtd * f["valor"] * mult(f["anos"]) if "anos" in f else 0.0
                if f["tipo"] == "cupom + principal":  # separa o principal do cupom
                    princ = 1000.0 if sigla == "PREJS" else 100.0
                    bruto = qtd * (f["valor"] - princ) * mult(f["anos"])
                aliq = aliquota_renda_fixa((dp - base).days)
                ir = bruto * aliq / 100
                ir_cupons += ir
                liq = bruto - ir
                # reinveste o cupom líquido à taxa do próprio título até a saída; o ganho do reinvestimento paga IR
                fator = (1 + taxa_reinv) ** (du(dp, dv) / 252) if dv > dp else 1.0
                g = liq * (fator - 1)
                ir_r = g * aliquota_renda_fixa((dv - dp).days) / 100 if g > 0 else 0.0
                cupons.append({"data": f["data"], "bruto": bruto, "aliquota": aliq, "ir": ir, "liquido": liq,
                               "reinvestido": liq + g - ir_r, "ir_reinvestimento": ir_r})
        if dv >= venc:
            princ = 1000.0 if sigla in ("PRE", "PREJS") else (100.0 if sigla in ("IPCA", "IPCAJS") else 1.0)
            preco = princ * mult(du(base, proximo_util(venc)) / 252)
        else:
            rest = [f for f in fl if date.fromisoformat(f["data"]) > dv]
            m = mult(a_v)
            preco = sum(f["valor"] * m / (1 + y_e) ** (du(dv, date.fromisoformat(f["data"])) / 252) for f in rest)
        venda_bruta = qtd * preco
        custo_custodia = valor * custodia / 100 * (dias / 365)
        ganho = venda_bruta - valor
        base_ir = max(0.0, ganho - custo_custodia)
        iof = base_ir * _iof(dias) / 100
        aliq = aliquota_renda_fixa(dias)
        ir = (base_ir - iof) * aliq / 100
        liquido_venda = venda_bruta - custo_custodia - iof - ir
        total = liquido_venda + sum(c["reinvestido"] for c in cupons)
        anos_cal = dias / 365.25
        r = {"data": dv.isoformat(), "dias": dias, "preco_unitario": preco, "venda_bruta": venda_bruta,
             "ganho_bruto": ganho, "custodia": custo_custodia, "iof": iof, "iof_pct": _iof(dias),
             "aliquota_ir": aliq, "ir": ir, "cupons_liquidos": sum(c["liquido"] for c in cupons),
             "ir_cupons": ir_cupons, "cupons_reinvestidos": sum(c["reinvestido"] for c in cupons),
             "ir_reinvestimento": sum(c["ir_reinvestimento"] for c in cupons), "liquido_total": total,
             "rent_liquida": (total / valor - 1) * 100,
             "rent_liquida_aa": ((total / valor) ** (1 / anos_cal) - 1) * 100 if anos_cal > 0 and total > 0 else None}
        if detalhar:
            r["cupons"] = cupons
        return r

    final = resultado(venda, True)
    # curva: valor líquido se vender em cada mês até a data escolhida (mesmas premissas)
    curva, d = [], base
    while True:
        d = (pd.Timestamp(d) + pd.DateOffset(months=1)).date()
        if d >= venda:
            break
        curva.append(resultado(d, False))
    curva.append({k: final[k] for k in ("data", "liquido_total", "rent_liquida")})

    return {
        "titulo": {k: t.get(k) for k in ("codigo", "tipo", "sigla", "vencimento", "taxa", "pu_publicado", "unidade")},
        "data_base": dados_t["data_base"], "liquidacao": base.isoformat(), "data_venda": venda.isoformat(), "ate_vencimento": ate_venc,
        "valor": valor, "quantidade": qtd, "taxa_saida": y_e * 100, "anos_uteis": anos_venda,
        "custodia_pct": custodia, "taxa_reinvestimento": taxa_reinv * 100, "premissas": usado, "resultado": final,
        "curva": [{"data": c["data"], "liquido": c["liquido_total"], "rent": c["rent_liquida"]} for c in curva],
        "fonte": dados_t["fonte"], "base_legal": {"ir": BASE_LEGAL_RF, "iof": BASE_LEGAL_IOF},
    }
