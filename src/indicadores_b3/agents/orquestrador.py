"""Orquestrador: roda os agentes na ordem certa, passa os dossiês adiante e salva o resultado.

Fluxo:
  1. Financial Analyst  → dossiê da empresa (e dos pares, para comparação)
  2. Market Research    → dossiê de macro, juros, notícias
  3. Investment Research→ consolida 1 e 2, compara pares, valuation, cenários, tese
  4. Redator            → texto (regras fixas ou IA local opcional), sempre validado
  5. Relatório          → Markdown + HTML em data/research_out/
Python puro, sem serviços pagos. Cada agente pode rodar sozinho.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from indicadores_b3 import config
from indicadores_b3.agents import estilo, financial, investment, market, redator, relatorio

PASTA = config.RELATORIOS_DIR
AGENTES = ("financial", "market", "investment")


def _limpo(t: str) -> str:
    t = (t or "").upper().strip()
    if not re.fullmatch(r"[A-Z0-9]{4,6}\d{0,2}", t):
        raise ValueError(f"Ticker inválido: {t!r}")
    return t


def rodar_agente(ticker: str, pares: list[str] | None = None, salvar: bool = True) -> dict:
    """Modo agente: a IA (gratuita, ver llm.py) decide quais ferramentas usar e escreve a análise; números validados."""
    from indicadores_b3.agents import agente
    t = _limpo(ticker)
    ag = agente.Agente(t, [_limpo(p) for p in pares] if pares is not None else None)
    saida = ag.rodar()
    res = {"ticker": t, "modo": "agente", "agentes": [k for k, d in (("financial", ag.fin), ("market", ag.mkt), ("investment", ag.inv)) if d],
           "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "financial": ag.fin, "market": ag.mkt, "investment": ag.inv,
           "pares": {p: {"assunto": d["assunto"], "ref": d["extras"].get("ref")} for p, d in ag.pares_brutos.items()},
           "pares_dossies": ag.pares, "passos": saida["passos"], "metricas_agente": saida.get("metricas"),
           "documentos_ri": ag.documentos_usados()}
    if saida["texto"]:
        regras = redator.texto_modelo(ag.fin, ag.mkt, ag.inv)
        do_agente = estilo.secoes(saida["texto"])
        res["redacao"] = {"modo": "agente", "modelo": ", ".join(saida["provedores"]), "resumo": estilo.texto(saida["texto"]),
                          "secoes": {**regras, **{k: v for k, v in do_agente.items() if v}}, "rejeitados": []}
    else:
        red = redator.redigir(ag.fin, ag.mkt, ag.inv, usar_ia=False)
        so_erro = not any(x["tipo"] == "rascunho" for x in saida["passos"])
        red["aviso"] = ("A IA não respondeu (" + next((x["texto"] for x in reversed(saida["passos"]) if x["tipo"] == "erro"), "sem resposta")
                        + "); texto gerado por regras fixas. Tente de novo em alguns minutos ou cadastre o Groq como reserva."
                        if so_erro else "O agente não terminou uma análise válida (veja o registro); texto gerado por regras fixas.")
        res["redacao"] = red
    res["markdown"] = relatorio.montar(res)
    res["log"] = [f"{x['tipo']}: " + (f"{x['nome']}({json.dumps(x['args'], ensure_ascii=False)}) → {x['resumo']}" if x["tipo"] == "ferramenta" else x["texto"])
                  for x in saida["passos"]]
    if salvar:
        _salvar(res)
    return res


def _salvar(res: dict):
    PASTA.mkdir(parents=True, exist_ok=True)
    nome = f"{res['ticker']}_{datetime.now():%Y%m%d_%H%M%S}"
    (PASTA / f"{nome}.json").write_text(json.dumps(res, ensure_ascii=False, default=str), encoding="utf-8")
    (PASTA / f"{nome}.md").write_text(res["markdown"], encoding="utf-8")
    res["id"] = nome


def rodar(ticker: str, agentes=AGENTES, pares: list[str] | None = None, premissas: dict | None = None,
          usar_ia: bool = True, salvar: bool = True) -> dict:
    t = _limpo(ticker)
    agentes = [a for a in AGENTES if a in set(agentes)] or list(AGENTES)
    log, res = [], {"ticker": t, "agentes": agentes, "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M")}

    def passo(msg):
        log.append(f"{datetime.now():%H:%M:%S} {msg}")

    precisa_fin = "financial" in agentes or "investment" in agentes
    fin = None
    if precisa_fin:
        passo(f"Financial Analyst: lendo CVM e preço de {t}")
        fin = financial.analisar(t).to_dict()
    tipo = (fin or {}).get("extras", {}).get("tipo", "geral")
    if "financial" in agentes:
        res["financial"] = fin

    mkt = None
    if "market" in agentes or "investment" in agentes:
        passo("Market Research Analyst: macro, curva de juros, comunicados")
        mkt = market.analisar(t, tipo).to_dict()
        if "market" in agentes:
            res["market"] = mkt

    if "investment" in agentes:
        if pares:
            lista = [_limpo(p) for p in pares]
        else:  # sem pares informados: mesmo setor na CVM, mais negociados primeiro
            from indicadores_b3.data import setores
            sug = setores.pares(t)
            lista = [p["ticker"] for p in sug["pares"]]
            res["pares_criterio"] = sug.get("criterio")
            passo(f"Pares sugeridos pelo setor ({sug.get('criterio')}): {', '.join(lista) or 'nenhum'}")
        lista = [p for p in lista if p != t]
        dp = {}
        for p in lista:
            passo(f"Financial Analyst: par {p}")
            try:
                dp[p] = financial.analisar(p).to_dict()
            except Exception as e:  # um par com problema não derruba a análise
                passo(f"  par {p} ignorado: {type(e).__name__}: {e}")
        res["pares"] = {p: {"assunto": d["assunto"], "ref": d["extras"].get("ref")} for p, d in dp.items()}
        passo("Investment Research Analyst: pares, valuation, cenários, tese")
        res["investment"] = investment.analisar(fin, dp, mkt, premissas).to_dict()

    passo("Redator: texto e validação dos números")
    res["redacao"] = redator.redigir(res.get("financial"), res.get("market"), res.get("investment"), usar_ia)
    res["markdown"] = relatorio.montar(res)
    res["log"] = log
    if salvar:
        _salvar(res)
        passo(f"Salvo em data/research_out/{res['id']}.md")
    return res


_RID = re.compile(r"[A-Z0-9]+_\d{8}_\d{6}")
_RESUMOS: dict[str, tuple[float, dict]] = {}  # id -> (mtime, resumo): evita reler o JSON inteiro a cada listagem


def _resumo(p) -> dict:
    """Empresa, modo, autor do texto e potencial de um relatório salvo (lido uma vez e guardado em memória)."""
    mt = p.stat().st_mtime
    if p.stem in _RESUMOS and _RESUMOS[p.stem][0] == mt:
        return _RESUMOS[p.stem][1]
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        r = {}
    itens = {x["nome"]: x for x in (r.get("investment") or {}).get("itens", [])}
    pot = next((itens[n] for n in ("Potencial ponderado", "Potencial — base", "Potencial (base)") if n in itens), None)
    red = r.get("redacao") or {}
    res = {"empresa": (r.get("financial") or r.get("investment") or {}).get("assunto"),
           "modo": r.get("modo") or "regras", "autor": red.get("modelo") if red.get("modo") in ("agente", "ia") else "regras fixas",
           "potencial": pot.get("valor") if pot else None, "aviso": bool(red.get("aviso"))}
    _RESUMOS[p.stem] = (mt, res)
    return res


def listar() -> list[dict]:
    if not PASTA.exists():
        return []
    out = []
    for p in sorted(PASTA.glob("*.json"), key=lambda x: x.stem.partition("_")[2], reverse=True):
        if not _RID.fullmatch(p.stem):
            continue
        t, _, resto = p.stem.partition("_")
        out.append({"id": p.stem, "ticker": t, "quando": datetime.strptime(resto, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M"),
                    **_resumo(p)})
    return out


def carregar(rid: str) -> dict | None:
    if not _RID.fullmatch(rid or ""):
        return None
    p = PASTA / f"{rid}.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text(encoding="utf-8"))
    r["id"] = rid  # o JSON é gravado antes de ganhar o id; sem isso, os botões de baixar somem ao reabrir
    return r


def excluir(rid: str) -> bool:
    """Apaga o relatório (.json e .md). O Histórico de acertos guarda a conclusão à parte e não é afetado."""
    if not _RID.fullmatch(rid or ""):
        return False
    achou = False
    for ext in (".json", ".md"):
        p = PASTA / f"{rid}{ext}"
        if p.exists():
            p.unlink()
            achou = True
    _RESUMOS.pop(rid, None)
    return achou


def limpar_antigos(manter: int = 1) -> list[str]:
    """Mantém só os ``manter`` relatórios mais recentes de cada empresa; devolve os ids apagados."""
    manter = max(1, int(manter))
    vistos: dict[str, int] = {}
    apagados = []
    for r in listar():  # já vem do mais recente para o mais antigo
        vistos[r["ticker"]] = vistos.get(r["ticker"], 0) + 1
        if vistos[r["ticker"]] > manter and excluir(r["id"]):
            apagados.append(r["id"])
    return apagados


if __name__ == "__main__":
    import sys
    r = rodar(sys.argv[1] if len(sys.argv) > 1 else "ITUB4")
    print("\n".join(r["log"]))
