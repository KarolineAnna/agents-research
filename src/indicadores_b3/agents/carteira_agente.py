"""Agente de carteira: por que a carteira ficou abaixo (ou acima) do Ibovespa e o que mudar para melhorar.

Duas partes:
1. Diagnóstico (código, sem IA, cada número com id): resultado contra Ibovespa e CDI, quem somou e quem tirou
   (efeito = peso × [soma dos retornos diários do ativo − soma dos do Ibovespa]), setores, risco e concentração.
2. Investigação (agente de IA + laboratorio.py): o período é dividido em treino (60%) e reserva (40%). O agente vê só o
   diagnóstico do treino, formula hipóteses (cortar quem puxou, trocar por par do setor, diversificar, BOVA11...),
   testa cada uma nas 3 janelas do treino, descarta as ruins e manda até 3 para a confirmação na reserva, que ele
   nunca viu. O código impõe as regras: renda fixa fixa, peso máximo, ativos novos, número de testes, uma confirmação.
   O texto final passa pelo validador (números só das ferramentas, e só depois da confirmação).
Sem IA, as regras fixas (pesos iguais, inverso do risco, limite por ativo, sem o pior, metade em BOVA11) viram as
hipóteses e passam pelo mesmo laboratório.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from indicadores_b3.agents import estilo, redator
from indicadores_b3.agents.fatos import Dossie
from indicadores_b3.agents.nucleo import AgenteFerramentas, Ferramenta

DU = 252
RF_ID = "RENDA FIXA (CDI)"
LIMITE_PESO = 25.0
CDI_PADRAO = 14.0


# ---------- dados ----------
def _series(ativos: list[str], periodo: str, serie_fn=None, ibov_fn=None):
    from indicadores_b3.portfolio import carteira as cart
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    pegar = serie_fn or (lambda t: cart._serie(t, periodo, hoje)[0])
    px = pd.DataFrame({t: pegar(t) for t in ativos})
    ib = (ibov_fn or (lambda: cart._ibov(periodo, hoje)))()
    if ib is None or len(ib) == 0:
        raise LookupError("O Ibovespa (^BVSP) não veio do yfinance: sem ele não há comparação.")
    px["_IBOV"] = ib
    px = px.dropna()
    ret = px.pct_change().dropna()
    if len(ret) < 120:
        raise ValueError("Poucos dias em comum entre os ativos e o Ibovespa (menos de 120): use um período maior.")
    return ret


def _cdi(rf_pct):
    if rf_pct is not None:
        return float(rf_pct), "informado"
    try:
        from indicadores_b3.data.fontes import cdi_atual
        return float(cdi_atual()["valor"]), "Banco Central, SGS 4389"
    except Exception:  # noqa: BLE001
        return CDI_PADRAO, "premissa (Banco Central indisponível)"


def _setor(t: str) -> str:
    if t == RF_ID:
        return "Renda fixa"
    try:
        from indicadores_b3.data import setores
        return setores.setor_de(t).get("setor") or "Outros (ETF, FII, BDR…)"
    except Exception:  # noqa: BLE001
        return "Sem setor"


def _metricas(rp: pd.Series, rm: pd.Series, rf: float) -> dict:
    serie = (1 + rp).cumprod()
    anos = len(rp) / DU
    vol = float(rp.std() * np.sqrt(DU))
    ret_aa = float(serie.iloc[-1] ** (1 / anos) - 1) if anos > 0 else None
    beta = float(rp.cov(rm) / rm.var()) if rm.var() > 0 else None
    return {"retorno": float(serie.iloc[-1] - 1) * 100, "retorno_aa": None if ret_aa is None else ret_aa * 100,
            "vol": vol * 100, "drawdown": float((serie / serie.cummax() - 1).min()) * 100,
            "sharpe": (ret_aa - rf) / vol if vol > 0 and ret_aa is not None else None,
            "beta": beta, "correlacao": float(rp.corr(rm)),
            "tracking_error": float((rp - rm).std() * np.sqrt(DU)) * 100}


def _normalizar(pesos: dict[str, float]) -> dict[str, float]:
    pesos = {k.strip().upper() if k != RF_ID else k: float(v) for k, v in pesos.items() if v and float(v) > 0}
    tot = sum(pesos.values())
    if tot <= 0:
        raise ValueError("Informe os pesos da carteira.")
    return {k: v / tot * 100 for k, v in pesos.items()}


# ---------- regras de ajuste (a renda fixa fica sempre no mesmo peso) ----------
def _redistribuir(pesos_risco: dict[str, float], total: float) -> dict[str, float]:
    s = sum(pesos_risco.values())
    return {k: v / s * total for k, v in pesos_risco.items()} if s > 0 else {}


def _limitar(pesos: dict[str, float], limite: float, total: float) -> dict[str, float]:
    p = dict(pesos)
    for _ in range(20):
        acima = {k for k, v in p.items() if v > limite + 1e-9}
        if not acima:
            break
        sobra = sum(p[k] - limite for k in acima)
        livres = {k: v for k, v in p.items() if k not in acima and v < limite}
        for k in acima:
            p[k] = limite
        if not livres:
            break
        s = sum(livres.values())
        for k, v in livres.items():
            p[k] = v + sobra * v / s
    return p


def regras(pesos: dict[str, float], ret_treino: pd.DataFrame) -> dict[str, tuple[str, dict[str, float]]]:
    """{id: (descrição, pesos)} decididos SÓ com os dados de treino."""
    rf_w = pesos.get(RF_ID, 0.0)
    risco = {k: v for k, v in pesos.items() if k != RF_ID}
    total = 100 - rf_w
    out = {"atual": ("Carteira atual", pesos)}
    if len(risco) >= 2:
        out["iguais"] = ("Pesos iguais entre os ativos de risco", {**{k: total / len(risco) for k in risco}, **({RF_ID: rf_w} if rf_w else {})})
        vol = ret_treino[list(risco)].std()
        inv = {k: 1 / float(vol[k]) for k in risco if vol[k] > 0}
        out["inverso_risco"] = ("Peso pelo inverso da volatilidade (ativo mais arriscado pesa menos)",
                                {**_redistribuir(inv, total), **({RF_ID: rf_w} if rf_w else {})})
        if max(risco.values()) > LIMITE_PESO and len(risco) * LIMITE_PESO >= total:
            out["limite"] = (f"Nenhum ativo acima de {LIMITE_PESO:.0f}% da carteira",
                             {**_limitar(risco, LIMITE_PESO, total), **({RF_ID: rf_w} if rf_w else {})})
        ib = float(ret_treino["_IBOV"].sum())
        efeitos = {k: v / 100 * (float(ret_treino[k].sum()) - ib) for k, v in risco.items()}
        pior = min(efeitos, key=efeitos.get)
        if efeitos[pior] < 0:
            out["sem_pior"] = (f"Sem {pior}, o que mais puxou para baixo na 1ª metade",
                               {**_redistribuir({k: v for k, v in risco.items() if k != pior}, total), **({RF_ID: rf_w} if rf_w else {})})
    if risco:
        meio = {k: v / 2 for k, v in risco.items()}
        meio["_IBOV"] = total / 2
        out["meio_ibov"] = ("Metade da parte em ações no próprio Ibovespa (BOVA11)", {**meio, **({RF_ID: rf_w} if rf_w else {})})
    return out


def _retorno_carteira(pesos: dict[str, float], ret: pd.DataFrame, rf_dia: float) -> pd.Series:
    rp = pd.Series(0.0, index=ret.index)
    for k, w in pesos.items():
        rp += w / 100 * (rf_dia if k == RF_ID else ret[k])
    return rp


# ---------- diagnóstico (ferramenta principal) ----------
def diagnosticar(pesos: dict[str, float], periodo: str = "3y", rf_pct: float | None = None, serie_fn=None, ibov_fn=None,
                 setor_fn=None, prefixo: str = "C", ret: pd.DataFrame | None = None,
                 assunto: str = "Carteira contra o Ibovespa") -> Dossie:
    """ret (opcional): retornos diários já carregados (colunas = ativos + _IBOV), para diagnosticar só um trecho do período."""
    pesos = _normalizar(pesos)
    ativos = [k for k in pesos if k != RF_ID]
    if not ativos:
        raise ValueError("A carteira só tem renda fixa: não há o que comparar com o Ibovespa.")
    if ret is None:
        ret = _series(ativos, periodo, serie_fn, ibov_fn)
    cdi, cdi_fonte = _cdi(rf_pct)
    rf, rf_dia = cdi / 100, (1 + cdi / 100) ** (1 / DU) - 1
    rm = ret["_IBOV"]
    rp = _retorno_carteira(pesos, ret, rf_dia)
    mc, mi = _metricas(rp, rm, rf), _metricas(rm, rm, rf)
    setor_de = setor_fn or _setor

    D = Dossie("Agente de carteira", prefixo, assunto)
    ini, fim = ret.index[0].strftime("%Y-%m-%d"), ret.index[-1].strftime("%Y-%m-%d")
    D.extras.update({"inicio": ini, "fim": fim, "dias": len(ret), "periodo": periodo, "pesos": pesos})
    yf = {"fonte": "yfinance", "documento": "preços diários (Close ajustado por proventos)", "data_ref": fim,
          "periodo": f"{ini} a {fim}", "url": "https://finance.yahoo.com/quote/%5EBVSP"}

    S = "Resultado no período"
    c_ret = D.calc("Retorno da carteira no período", mc["retorno"], "%", "produto de (1 + retorno diário da carteira) − 1", [], S)
    i_ret = D.fato("Retorno do Ibovespa no período", mi["retorno"], "%", yf, S)
    cdi_id = D.fato("CDI usado (ao ano)", cdi, "% a.a.", {"fonte": cdi_fonte, "documento": "SGS 4389", "data_ref": fim}, S)
    cdi_per = D.calc("CDI no período", ((1 + rf_dia) ** len(ret) - 1) * 100, "%", "(1 + CDI ao dia) ^ dias − 1", [cdi_id], S)
    dif = D.calc("Diferença da carteira contra o Ibovespa", mc["retorno"] - mi["retorno"], "p.p.", "retorno da carteira − retorno do Ibovespa", [c_ret, i_ret], S)
    c_aa = D.calc("Retorno da carteira ao ano", mc["retorno_aa"], "% a.a.", "anualizado pelos dias úteis", [c_ret], S)
    i_aa = D.calc("Retorno do Ibovespa ao ano", mi["retorno_aa"], "% a.a.", "anualizado pelos dias úteis", [i_ret], S)

    S = "Quem somou e quem tirou"
    soma_ib = float(rm.sum())
    linhas = []
    for k, w in sorted(pesos.items(), key=lambda kv: -kv[1]):
        soma = rf_dia * len(ret) if k == RF_ID else float(ret[k].sum())
        acum = ((1 + rf_dia) ** len(ret) - 1) if k == RF_ID else float((1 + ret[k]).prod() - 1)
        efeito = w / 100 * (soma - soma_ib) * 100
        pid = D.premissa(f"Peso de {k}", w, "%", "informado por você (normalizado para somar 100%)", S)
        rid = D.calc(f"Retorno de {k} no período", acum * 100, "%", "produto de (1 + retorno diário) − 1", [], S)
        eid = D.calc(f"Efeito de {k} contra o Ibovespa", efeito, "p.p.",
                     "peso × (soma dos retornos diários do ativo − soma dos do Ibovespa)", [pid, rid, i_ret], S)
        linhas.append({"ticker": k, "setor": setor_de(k), "peso": w, "retorno": acum * 100, "efeito": efeito, "ids": [pid, rid, eid]})
    D.extras["atribuicao"] = linhas
    setores: dict[str, dict] = {}
    for x in linhas:
        s = setores.setdefault(x["setor"], {"setor": x["setor"], "peso": 0.0, "efeito": 0.0, "ativos": []})
        s["peso"] += x["peso"]
        s["efeito"] += x["efeito"]
        s["ativos"].append(x["ticker"])
    S = "Por setor"
    for s in sorted(setores.values(), key=lambda s: s["efeito"]):
        s["id_peso"] = D.calc(f"Peso do setor {s['setor']}", s["peso"], "%", "soma dos pesos dos ativos do setor", [], S)
        s["id_efeito"] = D.calc(f"Efeito do setor {s['setor']} contra o Ibovespa", s["efeito"], "p.p.", "soma dos efeitos dos ativos do setor", [], S)
    D.extras["setores"] = sorted(setores.values(), key=lambda s: s["efeito"])

    S = "Risco"
    ids_r = {
        "vol_c": D.calc("Volatilidade da carteira ao ano", mc["vol"], "% a.a.", "desvio-padrão diário × raiz(252)", [], S),
        "vol_i": D.calc("Volatilidade do Ibovespa ao ano", mi["vol"], "% a.a.", "desvio-padrão diário × raiz(252)", [], S),
        "beta": D.calc("Beta da carteira contra o Ibovespa", mc["beta"], "", "cov(carteira, Ibovespa) ÷ var(Ibovespa)", [], S),
        "corr": D.calc("Correlação com o Ibovespa", mc["correlacao"], "", "correlação dos retornos diários", [], S),
        "te": D.calc("Tracking error ao ano", mc["tracking_error"], "% a.a.", "desvio-padrão de (carteira − Ibovespa) × raiz(252)", [], S),
        "dd_c": D.calc("Maior queda da carteira", mc["drawdown"], "%", "pior queda do topo ao fundo", [], S),
        "dd_i": D.calc("Maior queda do Ibovespa", mi["drawdown"], "%", "pior queda do topo ao fundo", [], S),
        "sh_c": D.calc("Sharpe da carteira", mc["sharpe"], "", "(retorno ao ano − CDI) ÷ volatilidade", [c_aa, cdi_id], S),
        "sh_i": D.calc("Sharpe do Ibovespa", mi["sharpe"], "", "(retorno ao ano − CDI) ÷ volatilidade", [i_aa, cdi_id], S),
    }
    risco = {k: v for k, v in pesos.items() if k != RF_ID}
    n_ef = 1 / sum((v / 100) ** 2 for v in risco.values()) if risco else None
    maior = max(risco, key=risco.get)
    ids_r["n_ef"] = D.calc("Número efetivo de ativos de risco", n_ef, "", "1 ÷ soma dos pesos² (só a parte em ações)", [], S)
    ids_r["maior"] = D.calc(f"Maior peso ({maior})", risco[maior], "%", "maior peso entre os ativos de risco", [], S)
    D.extras["risco"] = ids_r

    # ---------- testes fora da amostra ----------
    S = "Testes de ajuste"
    meio = len(ret) // 2
    treino, teste = ret.iloc[:meio], ret.iloc[meio:]
    ib_teste = float((1 + teste["_IBOV"]).prod() - 1) * 100
    ib_t = D.calc("Ibovespa na 2ª metade do período", ib_teste, "%", "produto de (1 + retorno diário) − 1 na 2ª metade", [], S)
    D.premissa("Limite de peso por ativo nos testes", LIMITE_PESO, "%", "regra comum de diversificação; só entra se algum ativo passar dele", S)
    D.extras["teste_inicio"] = teste.index[0].strftime("%Y-%m-%d")
    testes = []
    for rid, (desc, w) in regras(pesos, treino).items():
        rp_t = _retorno_carteira({k: v for k, v in w.items()}, teste, rf_dia)
        m_t = _metricas(rp_t, teste["_IBOV"], rf)
        rp_full = _retorno_carteira(w, ret, rf_dia)
        r_full = float((1 + rp_full).prod() - 1) * 100
        x = {"id": rid, "descricao": desc, "pesos": {("BOVA11" if k == "_IBOV" else k): v for k, v in w.items()},
             "ret_teste": m_t["retorno"], "vol_teste": m_t["vol"], "dd_teste": m_t["drawdown"], "sharpe_teste": m_t["sharpe"],
             "ret_total": r_full}
        x["ids"] = [D.estimativa(f"Teste '{desc}': retorno na 2ª metade", m_t["retorno"], "%", "regra decidida na 1ª metade, medida na 2ª", [ib_t], S),
                    D.estimativa(f"Teste '{desc}': volatilidade na 2ª metade", m_t["vol"], "% a.a.", "desvio-padrão diário × raiz(252)", [], S),
                    D.estimativa(f"Teste '{desc}': maior queda na 2ª metade", m_t["drawdown"], "%", "pior queda do topo ao fundo", [], S),
                    D.estimativa(f"Teste '{desc}': diferença contra o Ibovespa na 2ª metade", m_t["retorno"] - ib_teste, "p.p.", "retorno − Ibovespa", [ib_t], S)]
        testes.append(x)
    D.extras["testes"] = testes

    # ---------- leituras (inferências a partir dos números) ----------
    neg = sorted([x for x in linhas if x["efeito"] < 0], key=lambda x: x["efeito"])
    if neg:
        p = neg[0]
        D.leitura(f"{p['ticker']} foi o que mais tirou da carteira contra o Ibovespa ({redator.fmt(p['efeito'], 'p.p.')}).", p["ids"])
    rf_lin = next((x for x in linhas if x["ticker"] == RF_ID), None)
    if rf_lin and rf_lin["efeito"] < 0:
        D.leitura(f"A renda fixa rendeu menos que o Ibovespa no período e respondeu por {redator.fmt(rf_lin['efeito'], 'p.p.')} da diferença. "
                  "É o preço de ter menos risco, não um erro de escolha.", rf_lin["ids"])
    if mc["beta"] is not None and mc["beta"] < 0.8 and mi["retorno"] > 0:
        D.leitura(f"Com beta de {redator.br(mc['beta'], 2)}, a carteira anda menos que o Ibovespa: em período de alta, tende a ficar para trás.", [ids_r["beta"]])
    if risco[maior] > 35 or (n_ef and n_ef < 4):
        D.alerta("atencao", f"Carteira concentrada: {maior} pesa {redator.fmt(risco[maior], '%')} e o número efetivo de ativos é {redator.br(n_ef, 2)}.",
                 [ids_r["maior"], ids_r["n_ef"]])
    melhor = max(testes, key=lambda x: x["ret_teste"])
    atual = next(x for x in testes if x["id"] == "atual")
    if melhor["id"] != "atual" and melhor["ret_teste"] > atual["ret_teste"]:
        D.leitura(f"No teste fora da amostra, a regra '{melhor['descricao']}' rendeu {redator.fmt(melhor['ret_teste'], '%')} na 2ª metade, "
                  f"contra {redator.fmt(atual['ret_teste'], '%')} da carteira atual. Um único período não prova que vai se repetir.",
                  [melhor["ids"][0], atual["ids"][0]])
    D.extras["resumo"] = {"dif": dif, "c_ret": c_ret, "i_ret": i_ret, "cdi_per": cdi_per}
    return D


# ---------- texto por regras (sem IA) ----------
def texto_regras(d: dict) -> dict:
    it = {x["id"]: x for x in d["itens"]}

    def v(i, u=None):
        x = it.get(i)
        return f"{redator.fmt(x['valor'], u or x.get('unidade'))} [{i}]" if x else "n/d"
    r = d["extras"]["resumo"]
    acima = (it.get(r["dif"]) or {}).get("valor", 0) >= 0
    diag = (f"A carteira rendeu {v(r['c_ret'])} no período, contra {v(r['i_ret'])} do Ibovespa e {v(r['cdi_per'])} do CDI. "
            f"Diferença: {v(r['dif'])}, {'acima' if acima else 'abaixo'} do índice.")
    at = d["extras"]["atribuicao"]
    piores = [x for x in sorted(at, key=lambda x: x["efeito"]) if x["efeito"] < 0][:3]
    melhores = [x for x in sorted(at, key=lambda x: -x["efeito"]) if x["efeito"] > 0][:2]
    quem = "\n".join([f"- {x['ticker']}: peso {v(x['ids'][0])}, retorno {v(x['ids'][1])}, efeito {v(x['ids'][2])}." for x in piores]
                     + [f"- A favor: {x['ticker']}, efeito {v(x['ids'][2])}." for x in melhores])
    R = d["extras"]["risco"]
    riscos = "\n".join([f"- Volatilidade de {v(R['vol_c'])} contra {v(R['vol_i'])} do Ibovespa; beta {v(R['beta'])}.",
                        f"- Maior queda de {v(R['dd_c'])} contra {v(R['dd_i'])} do Ibovespa.",
                        f"- Número efetivo de ativos de risco: {v(R['n_ef'])}; maior peso {v(R['maior'])}."]
                       + [f"- {a['texto']}" for a in d["alertas"]])
    ts = sorted(d["extras"]["testes"], key=lambda x: -x["ret_teste"])
    testar = "\n".join(f"- {x['descricao']}: {v(x['ids'][0])} na 2ª metade, diferença contra o Ibovespa {v(x['ids'][3])}, maior queda {v(x['ids'][2])}."
                       for x in ts)
    leit = " ".join(l["texto"] for l in d["leituras"])
    return {k: estilo.texto(s) for k, s in {
        "diagnostico": diag, "quem": quem, "riscos": riscos, "testar": testar,
        "leitura": "Opinião: " + (leit or "sem um fator único; a diferença vem da soma de vários ativos."),
        "limitacoes": "- O passado não garante o futuro: os testes usam um único período.\n"
                      "- Preços do yfinance (fonte não oficial), ajustados por proventos.\n"
                      "- Custos de corretagem, impostos e o desvio do BOVA11 contra o índice não entram na conta."}.items()}


# ---------- agente com IA ----------
SECOES_CARTEIRA = {"diagnostico": "diagnostico", "quem puxou": "quem", "quem somou": "quem", "quem mais pesou": "quem",
                   "hipoteses": "hipoteses", "o que foi testado": "hipoteses", "confirmacao": "confirmacao", "o que passou": "confirmacao",
                   "riscos": "riscos", "leitura final": "leitura", "leitura": "leitura", "limitacoes": "limitacoes"}

SISTEMA = """Você é um gestor de carteiras no Brasil, escrevendo em português para uma pessoa física que está estudando investimentos.
Ela montou uma carteira e quer saber por que ficou abaixo (ou acima) do Ibovespa e o que pode mudar para melhorar.
Seu trabalho é INVESTIGAR como um analista: formular hipóteses, testar, descartar as ruins e confirmar as boas.

O PERÍODO É DIVIDIDO COMO EM MACHINE LEARNING
- Treino (60% iniciais, em 3 janelas): é o que você enxerga. diagnostico_treino e testar_carteira usam só ele.
- Reserva (40% finais, em 2 janelas): fica escondida. Você escolhe até 3 testes e chama confirmar_propostas UMA vez.
  Só a reserva diz se uma proposta funciona. Bom no treino e ruim na reserva = a ideia não se sustenta.

COMO TRABALHAR
1. Chame diagnostico_treino. Veja quem puxou para baixo, concentração, risco e setores.
2. Formule hipóteses concretas a partir do que viu. Exemplos: reduzir o ativo que mais tirou; trocar por um par do mesmo setor
   (use buscar_substitutos e, se quiser, cara_ou_barata); diversificar setores; pôr parte em BOVA11; equilibrar o risco.
3. Teste cada hipótese com testar_carteira (pesos completos dos ativos de risco + motivo em uma frase). Leia o resultado e ajuste:
   se uma ideia perdeu nas janelas, descarte ou refine. Faça pelo menos 4 testes diferentes.
4. Escolha até 3 testes que venceram a carteira atual na maioria das janelas do treino e chame confirmar_propostas.
5. Depois da confirmação, responda sem chamar ferramentas.

REGRAS QUE O SISTEMA IMPÕE (se violar, a ferramenta devolve erro)
- A renda fixa fica no peso que a pessoa escolheu. Nunca proponha mudar a renda fixa.
- Peso máximo de 40% por ativo (ou o maior peso que a carteira já tem, se for maior), no máximo 3 ativos novos por proposta, até 12 testes, uma única confirmação.

REGRAS DE NÚMEROS
- Use SOMENTE números que apareceram nas ferramentas, exatamente como lá, com o id entre colchetes: 12,3% [E4].
- Não faça contas novas nem invente notícias, eventos ou projeções.
- Só diga que uma proposta "funcionou" se o status na confirmação for "aprovada".

FORMATO (Markdown, até 400 palavras), com estes títulos e nesta ordem:
## Diagnóstico
2 ou 3 frases sobre o treino: quanto a carteira rendeu contra o Ibovespa e o motivo principal.
## O que foi testado
Até 5 itens: cada hipótese, o motivo e o resultado no treino (inclusive as que falharam).
## O que passou na confirmação
Um item por proposta confirmada, com o status (aprovada, inconclusiva ou reprovada) e o número da reserva.
## Riscos
Até 3 itens.
## Leitura final
Começando por "Opinião:", 1 ou 2 frases. Não recomende comprar ou vender: diga o que os testes sugerem e o grau de confiança.
## Limitações
Até 2 itens.

ESTILO: frases curtas. Não use travessão (— ou –), linhas separadoras (---), tabelas ou negrito em frases inteiras."""


def _compacto(d: dict) -> dict:
    fora = set(d["secoes"].get("Testes de ajuste", []))  # os testes antigos (metades) não entram: quem testa agora é o agente
    return {"assunto": d["assunto"], "periodo": f"{d['extras']['inicio']} a {d['extras']['fim']}",
            "itens": [{"id": x["id"], "nome": x["nome"], "valor": redator.fmt(x["valor"], x.get("unidade")), "tipo": x["tipo"]}
                      for x in d["itens"] if x["valor"] is not None and x["id"] not in fora],
            "alertas": [a["texto"] for a in d["alertas"]], "leituras": [l["texto"] for l in d["leituras"] if "fora da amostra" not in l["texto"]]}


def texto_lab(lab_resumo: dict) -> dict:
    """Seções 'O que foi testado' e 'O que passou na confirmação' montadas pelo código (usadas sem IA e como reserva)."""
    nomes = {"aprovada": "aprovada", "inconclusiva": "inconclusiva", "reprovada": "reprovada"}
    hip = "\n".join(f"- Teste {t['numero']}: {t['motivo'] or 'sem motivo'}. Venceu a atual em {t['vitorias']} de 3 janelas do treino, "
                    f"diferença média de {redator.fmt(t['dif_media'], 'p.p.')} [{t['ids']['dif']}]." for t in lab_resumo["testes"])
    conf = "\n".join(f"- Teste {c['numero']}: {nomes[c['status']]}. Na reserva, {redator.fmt(c['dif'], 'p.p.')} [{c['ids']['dif']}] contra a "
                     f"carteira atual e {redator.fmt(c['dif_ibov'], 'p.p.')} [{c['ids']['dif_ib']}] contra o Ibovespa."
                     for c in (lab_resumo["confirmacao"] or []))
    return {"hipoteses": estilo.texto(hip or "- Nenhuma hipótese foi testada."), "confirmacao": estilo.texto(conf or "- Nada foi confirmado.")}


class AgenteCarteira:
    def __init__(self, pesos: dict[str, float], periodo: str = "3y", rf_pct: float | None = None, serie_fn=None, ibov_fn=None,
                 setor_fn=None, valuation_fn=None, pares_fn=None):
        from indicadores_b3.agents.laboratorio import Laboratorio
        self.pesos, self.periodo = _normalizar(pesos), periodo
        self._val_fn, self._pares_fn = valuation_fn, pares_fn
        ativos = [k for k in self.pesos if k != RF_ID]
        if not ativos:
            raise ValueError("A carteira só tem renda fixa: não há o que comparar com o Ibovespa.")
        from indicadores_b3.portfolio import carteira as cart
        hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
        pegar = serie_fn or (lambda t: cart._serie(t, periodo, hoje)[0])
        ret = _series(ativos, periodo, pegar, ibov_fn)
        self.cdi, _ = _cdi(rf_pct)
        self.lab = Laboratorio(self.pesos, ret, self.cdi, carregar=pegar)
        kw = {"rf_pct": self.cdi, "setor_fn": setor_fn}
        self.diag = diagnosticar(self.pesos, periodo, ret=ret, **kw).to_dict()
        self.diag_treino = diagnosticar(self.pesos, periodo, ret=self.lab.treino[list(ret.columns)], prefixo="T",
                                        assunto="Carteira no período de treino", **kw).to_dict()
        self.vals: dict[str, dict] = {}

    # ---------- ferramentas ----------
    def diagnostico_treino(self):
        out = _compacto(self.diag_treino)
        out["periodos"] = self.lab.periodos()
        out["pesos_atuais"] = {_nome(k): redator.br(v, 1) + "%" for k, v in self.pesos.items()}
        return out

    def testar_carteira(self, pesos: dict, motivo: str = ""):
        return self.lab.testar(pesos, motivo)

    def confirmar_propostas(self, testes: list):
        return self.lab.confirmar(testes)

    def buscar_substitutos(self, ticker: str, quantidade: int = 5):
        from indicadores_b3.data import setores
        r = (self._pares_fn or setores.pares)(ticker.strip().upper(), max(1, min(int(quantidade), 8)))
        return {"ticker": r.get("ticker"), "setor": r.get("setor"), "criterio": r.get("criterio"),
                "empresas": [{"ticker": p["ticker"], "empresa": p.get("empresa")} for p in r.get("pares", [])],
                "fonte": "CVM · FCA (setor declarado); ordem por volume negociado na B3"}

    def cara_ou_barata(self, ticker: str):
        t = ticker.strip().upper()
        if t not in self.vals:
            from indicadores_b3.analytics import valuation_rapido
            r = (self._val_fn or valuation_rapido.avaliar)(t)
            D = Dossie("Cara ou barata", f"{t}.V", f"{t}: cara ou barata")
            for l in r["lentes"]:
                u = "R$" if l["id"] == "justo" else "x"
                a = D.calc(f"{l['nome']}: hoje", l["atual"], u, "", [])
                b = D.calc(f"{l['nome']}: referência ({l['rotulo_ref']})", l["referencia"], u, "", [])
                D.calc(f"{l['nome']}: diferença", l["diferenca"], "%", "hoje ÷ referência − 1", [a, b])
            D.extras["veredito"] = r["veredito"]
            D.extras["texto"] = r["texto"]
            self.vals[t] = D.to_dict()
        d = self.vals[t]
        return {"ticker": t, "leitura": d["extras"]["texto"], "veredito": d["extras"]["veredito"],
                "itens": [{"id": x["id"], "nome": x["nome"], "valor": redator.fmt(x["valor"], x["unidade"])} for x in d["itens"] if x["valor"] is not None],
                "aviso": "Leitura de hoje: usa preços atuais, não ajuda a explicar o passado."}

    def detalhe_item(self, id: str):
        for d in self.dossies():
            for x in d.get("itens", []):
                if x["id"] == id:
                    return {k: x.get(k) for k in ("id", "nome", "tipo", "formula", "nota") if x.get(k)} | {"valor": redator.fmt(x["valor"], x.get("unidade"))}
        return {"erro": f"id {id} não encontrado"}

    def dossies(self) -> list[dict]:
        return [self.diag_treino, self.lab.D.to_dict(), self.diag, *self.vals.values()]

    def _validar(self, texto: str) -> list[str]:
        if not self.lab.testes:
            return ["Você ainda não testou nenhuma hipótese. Use testar_carteira (pelo menos 4 testes) antes de escrever."]
        if self.lab.confirmacao is None:
            return ["Falta a confirmação: escolha até 3 testes e chame confirmar_propostas antes de escrever."]
        ruins = redator.validar(texto, self.dossies())
        return [f"números que não vieram das ferramentas: {', '.join(ruins)}. Use só números exatamente como as ferramentas devolveram, com o id ao lado"] if ruins else []

    def ferramentas(self) -> list[Ferramenta]:
        obj = lambda props, req: {"type": "object", "properties": props, "required": req}  # noqa: E731
        return [
            Ferramenta("diagnostico_treino", "Diagnóstico da carteira só no período de treino: resultado contra Ibovespa e CDI, quem somou e quem tirou, setores e risco.",
                       self.diagnostico_treino, resumo=lambda r: r.get("assunto", "ok")),
            Ferramenta("testar_carteira", "Testa uma proposta de pesos nas 3 janelas do treino contra a carteira atual. Envie só os ativos de risco; a renda fixa é mantida.",
                       self.testar_carteira, obj({"pesos": {"type": "object", "description": 'ex.: {"PETR4": 30, "WEGE3": 25, "BOVA11": 25}',
                                                             "additionalProperties": {"type": "number"}},
                                                  "motivo": {"type": "string", "description": "a hipótese em uma frase"}}, ["pesos", "motivo"]),
                       resumo=lambda r: f"teste {r.get('teste')}: venceu em {r.get('venceu_a_atual_em')}, média {r.get('diferenca_media_por_janela')}"),
            Ferramenta("confirmar_propostas", "Mede até 3 testes na reserva (dias que você não viu). Só pode ser chamada uma vez.",
                       self.confirmar_propostas, obj({"testes": {"type": "array", "items": {"type": "integer"}}}, ["testes"]),
                       resumo=lambda r: ", ".join(f"teste {x['teste']}: {x['status']}" for x in r.get("resultados", []))),
            Ferramenta("buscar_substitutos", "Empresas do mesmo setor de uma ação (cadastro da CVM), mais negociadas primeiro.",
                       self.buscar_substitutos, obj({"ticker": {"type": "string"}, "quantidade": {"type": "integer"}}, ["ticker"]),
                       resumo=lambda r: f"{r.get('setor')}: {', '.join(e['ticker'] for e in r.get('empresas', []))}"),
            Ferramenta("cara_ou_barata", "Se uma ação está cara ou barata hoje: múltiplo contra a própria história, contra os pares e preço justo.",
                       self.cara_ou_barata, obj({"ticker": {"type": "string"}}, ["ticker"]), resumo=lambda r: r.get("leitura", "ok")),
            Ferramenta("detalhe_item", "Detalhe de um número pelo id (fórmula).", self.detalhe_item, obj({"id": {"type": "string"}}, ["id"]),
                       resumo=lambda r: r.get("nome", "ok")),
        ]

    # ---------- sem IA: as regras fixas viram hipóteses e passam pelo mesmo laboratório ----------
    def hipoteses_padrao(self):
        for rid, (desc, w) in regras(self.pesos, self.lab.treino).items():
            if rid == "atual" or len(self.lab.testes) >= 6:
                continue
            try:
                self.lab.testar({("BOVA11" if k == "_IBOV" else k): v for k, v in w.items() if k != RF_ID}, desc)
            except ValueError:
                continue  # regra que fura os limites (ex.: peso acima de 40%) fica de fora

    def rodar(self, usar_ia: bool = True) -> dict:
        passos, provs, texto = [], [], None
        if usar_ia:
            from indicadores_b3.agents import llm
            if llm.disponiveis():
                pesos_txt = ", ".join(f"{_nome(k)} {redator.br(v, 1)}%" for k, v in self.pesos.items())
                nucleo = AgenteFerramentas(SISTEMA, self.ferramentas(), self._validar, max_passos=18, max_correcoes=2, orcamento_s=360,
                                           podar=True)
                r = nucleo.rodar(f"Carteira: {pesos_txt}. Período: {self.periodo}. Data de hoje: {datetime.now():%Y-%m-%d}.")
                passos, provs, texto = r.passos, r.provedores, r.texto
        if not self.lab.testes:
            self.hipoteses_padrao()
        if self.lab.confirmacao is None and self.lab.testes:
            self.lab.confirmar(self.lab.melhores())
        lab = self.lab.resumo()
        base = {**texto_regras(self.diag), **texto_lab(lab)}
        base.pop("testar", None)
        aviso = None
        if texto:
            do_agente = estilo.secoes(texto, SECOES_CARTEIRA)
            secoes, modo = {**base, **{k: v for k, v in do_agente.items() if v and k in base}}, "agente"
        else:
            secoes, modo = base, "regras"
            if usar_ia and passos:
                aviso = ("A IA não respondeu (" + next((x["texto"] for x in reversed(passos) if x["tipo"] == "erro"), "sem resposta") + "); texto por regras fixas."
                         if not any(x["tipo"] == "rascunho" for x in passos) else "O agente não terminou um texto válido; texto por regras fixas.")
        return {"gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "modo": modo, "provedores": provs, "aviso": aviso,
                "secoes": secoes, "diagnostico": self.diag, "diagnostico_treino": self.diag_treino, "laboratorio": lab,
                "laboratorio_dossie": self.lab.D.to_dict(), "cara_ou_barata": self.vals, "passos": passos,
                "pesos": self.pesos, "periodo": self.periodo}


def _nome(t: str) -> str:
    return "BOVA11" if t == "_IBOV" else t


def rodar(pesos: dict[str, float], periodo: str = "3y", usar_ia: bool = True) -> dict:
    return json.loads(json.dumps(AgenteCarteira(pesos, periodo).rodar(usar_ia), default=str))
