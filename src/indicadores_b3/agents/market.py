"""Agente 2 — Market Research Analyst: ambiente macroeconômico, juros, câmbio, cenário externo e notícias.

Coleta (fontes_publicas.py): Selic, IPCA, câmbio, desemprego e atividade (Banco Central/IBGE via SGS),
expectativas do Focus, curva de juros e inflação implícita (Tesouro), juros/inflação dos EUA e petróleo (FRED),
fatos relevantes e comunicados da empresa (CVM/IPE).
Depois aplica leituras setoriais por regras explícitas (cada uma cita os números que usa).
"""
from __future__ import annotations

import pandas as pd

from indicadores_b3.agents import fontes_publicas as fp
from indicadores_b3.agents.fatos import Dossie


def _tenta(D: Dossie, nome, func, unidade, secao, *args):
    try:
        x = func(*args)
        i = D.fato(nome, x["valor"], unidade, x, secao)
        if i and x.get("anterior"):
            D.get(i)["anterior"] = x["anterior"]
        return i
    except Exception as e:  # noqa: BLE001
        D.ausente(nome, f"Fonte indisponível agora ({type(e).__name__}).", str(getattr(func, "__name__", "")))
        return None


def analisar(ticker: str | None = None, tipo: str = "geral") -> Dossie:
    D = Dossie("Market Research Analyst", "M", "Ambiente macroeconômico" + (f" · {ticker}" if ticker else ""))
    hoje = pd.Timestamp.now()
    dia = hoje.strftime("%Y-%m-%d")
    ano = hoje.year

    S = "Brasil · juros, inflação e atividade"
    selic = _tenta(D, "Selic (meta)", fp.sgs_ultimo, "% a.a.", S, 432, dia)
    ipca = _tenta(D, "IPCA em 12 meses", fp.sgs_ultimo, "%", S, 13522, dia)
    _tenta(D, "Dólar (PTAX)", fp.sgs_ultimo, "R$/US$", S, 1, dia)
    desoc = _tenta(D, "Taxa de desocupação", fp.sgs_ultimo, "%", S, 24369, dia)
    ibc = _tenta(D, "IBC-Br (atividade)", fp.sgs_ultimo, "índice", S, 24363, dia)
    if ibc and D.get(ibc).get("anterior"):
        a = D.get(ibc)["anterior"]
        D.calc("Atividade em 12 meses (IBC-Br)", (D.v(ibc) / a["valor"] - 1) * 100, "%",
               f"IBC-Br atual ÷ IBC-Br de {a['data_ref'][:7]} − 1", [ibc], S)

    S = "Expectativas de mercado (Focus)"
    f_ipca = _tenta(D, f"IPCA esperado para {ano + 1}", fp.focus, "%", S, "IPCA", ano + 1, dia)
    f_selic = _tenta(D, f"Selic esperada no fim de {ano + 1}", fp.focus, "% a.a.", S, "Selic", ano + 1, dia)
    f_pib = _tenta(D, f"PIB esperado para {ano + 1}", fp.focus, "%", S, "PIB Total", ano + 1, dia)
    _tenta(D, f"Câmbio esperado no fim de {ano + 1}", fp.focus, "R$/US$", S, "Câmbio", ano + 1, dia)

    S = "Curva de juros (Tesouro)"
    pre1 = pre5 = None
    try:
        from indicadores_b3.portfolio import premissas
        for H, nome in ((1, "1 ano"), (5, "5 anos")):
            m = premissas.mercado(float(H))
            c = m["juro_pre"]["componentes"][0]
            i = D.fato(f"Juro prefixado em {nome}", m["juro_pre"]["valor"], "% a.a.", c, S)
            if H == 1:
                pre1 = i
            else:
                pre5 = i
                D.fato("Inflação implícita em 5 anos", m["inflacao"]["valor"], "% a.a.", m["inflacao"]["componentes"][0], S)
    except Exception as e:  # noqa: BLE001
        D.ausente("Curva de juros do Tesouro", f"Indisponível ({type(e).__name__}).")
    if pre1 and pre5:
        D.calc("Inclinação da curva (5 anos menos 1 ano)", D.v(pre5) - D.v(pre1), "p.p.", "juro prefixado 5 anos − 1 ano", [pre5, pre1], S)
    if selic and (f_ipca or ipca):
        base = f_ipca or ipca
        D.calc("Juro real (Selic ÷ inflação esperada)", ((1 + D.v(selic) / 100) / (1 + D.v(base) / 100) - 1) * 100, "% a.a.",
               "(1 + Selic) ÷ (1 + IPCA esperado) − 1", [selic, base], S)

    S = "Cenário externo"
    us10 = _tenta(D, "Juro dos EUA de 10 anos", fp.fred, "% a.a.", S, "DGS10", dia)
    _tenta(D, "Fed Funds", fp.fred, "% a.a.", S, "FEDFUNDS", dia)
    _tenta(D, "Inflação dos EUA em 12 meses", fp.fred, "%", S, "CPIAUCSL", dia)
    _tenta(D, "Petróleo Brent", fp.fred, "US$/barril", S, "DCOILBRENTEU", dia)

    # comunicados da empresa (CVM/IPE). Manchetes gerais de economia (RSS da Agência Brasil e do IBGE) saíram:
    # não eram filtradas pela empresa e traziam notícias do dia sem relação com ela, para a tela e para o modelo.
    noticias = []
    if ticker:
        try:
            from indicadores_b3.data import comunicados
            r = comunicados.listar([ticker], None, 8)
            noticias += [{"titulo": f"{i.get('categoria', '')}: {i.get('assunto', '')}".strip(": "), "url": i.get("link") or i.get("url"),
                          "data": i.get("data_entrega") or i.get("data"), "fonte": "CVM · IPE"} for i in r.get("itens", [])]
        except Exception as e:  # noqa: BLE001
            D.ausente("Fatos relevantes da empresa (CVM)", f"Indisponível ({type(e).__name__}).")
    D.extras["noticias"] = noticias
    D.extras["aviso_noticias"] = "Comunicados entregues pela empresa à CVM (sistema IPE), com título e link para o documento."

    _leituras(D, tipo, selic, ipca, f_ipca, f_selic, desoc, pre1, pre5, us10, f_pib)
    return D


def _leituras(D: Dossie, tipo, selic, ipca, f_ipca, f_selic, desoc, pre1, pre5, us10, f_pib):
    """Leituras por regras explícitas. São inferências (não fatos) e citam os números usados."""
    v = D.v
    juro_real = next((x["id"] for x in D.itens if x["nome"].startswith("Juro real")), None)
    inclin = next((x["id"] for x in D.itens if x["nome"].startswith("Inclinação")), None)
    if juro_real and v(juro_real) is not None:
        nivel = "muito restritivo" if v(juro_real) > 7 else "restritivo" if v(juro_real) > 4.5 else "neutro ou estimulativo"
        D.leitura(f"Juro real de {v(juro_real):.1f}% a.a.: política monetária {nivel} "
                  "(referências usuais de juro neutro no Brasil ficam entre 4,5% e 5,5% reais).", [juro_real])
    if selic and f_selic:
        dif = v(f_selic) - v(selic)
        D.leitura(f"O mercado espera a Selic {'abaixo' if dif < 0 else 'acima'} da atual no fim do próximo ano "
                  f"({v(f_selic):.2f}% contra {v(selic):.2f}%): ciclo de {'cortes' if dif < -0.25 else 'altas' if dif > 0.25 else 'estabilidade'}.",
                  [selic, f_selic])
    if inclin and v(inclin) is not None:
        D.leitura(f"Curva prefixada {'positivamente inclinada' if v(inclin) > 0.25 else 'invertida' if v(inclin) < -0.25 else 'praticamente plana'} "
                  f"({v(inclin):+.2f} p.p. entre 1 e 5 anos).", [inclin])
    if tipo == "banco":
        if juro_real and v(juro_real) and v(juro_real) > 6:
            D.leitura("Para bancos: juro real alto encarece o crédito e tende a elevar a inadimplência com defasagem de 2 a 4 trimestres; "
                      "por outro lado, sustenta a margem com recursos próprios aplicados a juros altos.", [juro_real])
        if selic and f_selic and v(f_selic) < v(selic) - 0.25:
            D.leitura("Para bancos: um ciclo de cortes costuma aliviar a inadimplência e estimular a demanda por crédito, "
                      "mas reduz o ganho com a parcela da carteira e do caixa remunerada pela Selic.", [selic, f_selic])
        if desoc and v(desoc) is not None:
            D.leitura(f"Desemprego de {v(desoc):.1f}%: {'baixo para o padrão histórico brasileiro, o que favorece a qualidade do crédito a pessoas físicas' if v(desoc) < 8 else 'elevado, o que pressiona a inadimplência de pessoas físicas'}.",
                      [desoc])
    else:
        if juro_real and v(juro_real) and v(juro_real) > 6:
            D.leitura("Juro real alto aumenta a taxa de desconto e o custo da dívida das empresas, pesando sobre múltiplos e investimentos.", [juro_real])
    if us10 and v(us10) is not None and v(us10) > 4.5:
        D.leitura(f"Juro americano de 10 anos em {v(us10):.2f}%: juros altos lá fora tendem a reduzir o fluxo para emergentes.", [us10])
