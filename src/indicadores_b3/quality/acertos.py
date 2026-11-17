"""Histórico de acertos: o software guarda cada conclusão que tira e, meses depois, confere se ela se confirmou.

O que é registrado (automaticamente, no máximo uma vez por ativo por dia):
- "cara_ou_barata": o veredito da aba Indicadores (barata, no preço, cara ou sinais mistos);
- "research": a leitura do Research pelo potencial do preço justo (regra de ±15%);
- "carteira": as propostas que o agente de carteira mandou para a confirmação (aprovada, inconclusiva, reprovada)
  e a carteira atual daquele dia.
Como cada conclusão é conferida, a 3, 6 e 12 meses da data:
- ações: retorno total (com proventos) da ação MENOS o do Ibovespa no mesmo intervalo (excesso);
  "barata" acerta se bateu o Ibovespa; "cara" acerta se ficou atrás; "no preço" não conta acerto, só o excesso médio;
- carteira: retorno da proposta MENOS o da carteira atual (com os pesos daquele dia), daquela data em diante.
  "aprovada" acerta se rendeu mais que a atual; "reprovada" acerta se rendeu menos.
Para não inflar a conta, cada ativo conta uma vez por mês e por origem (a primeira conclusão do mês).
A comparação honesta é com a TAXA BASE: se 55% de todas as ações acompanhadas bateram o Ibovespa, um "barata"
que acerta 55% não sabe nada. O que mostra valor é a diferença entre os grupos (barata − cara).
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import date, datetime

import pandas as pd

from indicadores_b3 import config

HORIZONTES = {"3m": 91, "6m": 182, "12m": 365}  # dias corridos
RF_ID = "RENDA FIXA (CDI)"
GRUPOS = {"barata": "Barata", "justa": "No preço", "cara": "Cara", "mista": "Sinais mistos",
          "aprovada": "Aprovada", "inconclusiva": "Inconclusiva", "reprovada": "Reprovada"}


def _db(caminho=None) -> sqlite3.Connection:
    p = caminho or (config.DATA_DIR / "previsoes.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.execute("""CREATE TABLE IF NOT EXISTS previsoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, origem TEXT NOT NULL, alvo TEXT NOT NULL,
        previsao TEXT NOT NULL, preco REAL, detalhes TEXT, criado_em TEXT NOT NULL,
        UNIQUE (data, origem, alvo))""")
    return c


def registrar(origem: str, alvo: str, previsao: str | None, detalhes: dict | None = None, preco: float | None = None,
              dia: str | None = None, db=None) -> bool:
    """Guarda uma conclusão. Devolve False se já havia uma igual no mesmo dia (ou se não há previsão)."""
    if not previsao:
        return False
    dia = dia or date.today().isoformat()
    with _db(db) as c:
        cur = c.execute("INSERT OR IGNORE INTO previsoes (data, origem, alvo, previsao, preco, detalhes, criado_em) VALUES (?,?,?,?,?,?,?)",
                        (dia, origem, alvo, previsao, preco, json.dumps(detalhes or {}, ensure_ascii=False, default=str),
                         datetime.now().isoformat(timespec="seconds")))
        return cur.rowcount > 0


def leitura_potencial(pot: float | None) -> str | None:
    if pot is None:
        return None
    return "barata" if pot > 15 else "cara" if pot < -15 else "justa"


# ---------- registros a partir das telas ----------
def registrar_valuation(r: dict, db=None) -> bool:
    return registrar("cara_ou_barata", r["ticker"], r.get("veredito"),
                     {"lentes": [{"id": x["id"], "leitura": x["leitura"], "diferenca": x["diferenca"]} for x in r.get("lentes", [])],
                      "texto": r.get("texto")}, r.get("preco"), db=db)


def registrar_research(res: dict, db=None) -> bool:
    inv = res.get("investment") or {}
    item = next((x for x in inv.get("itens", []) if x["nome"] == "Potencial ponderado"), None)
    pot = item["valor"] if item else None
    return registrar("research", res["ticker"], leitura_potencial(pot), {"potencial": pot, "relatorio": res.get("id")}, db=db)


def registrar_carteira(r: dict, db=None) -> int:
    """Uma linha por proposta confirmada (alvo = carteira + número do teste)."""
    lab = r.get("laboratorio") or {}
    atual = r.get("pesos") or {}
    chave = ",".join(f"{k}:{round(v, 1)}" for k, v in sorted(atual.items()))
    cdi = next((x["valor"] for x in (r.get("diagnostico") or {}).get("itens", []) if x["nome"] == "CDI usado (ao ano)"), None)
    n = 0
    for c in lab.get("confirmacao") or []:
        n += registrar("carteira", f"{chave}#{c['numero']}", c["status"],
                       {"atual": atual, "proposta": c["pesos"], "motivo": c.get("motivo"), "cdi": cdi,
                        "modo": r.get("modo")}, db=db)
    return n


# ---------- conferência ----------
def _precos_padrao(simbolo: str) -> pd.Series:
    from indicadores_b3.analytics import historico_preco
    df = historico_preco.baixar(simbolo, "5y")
    col = "Adj Close" if "Adj Close" in df else "Close"
    return df[col].dropna().astype(float) if not df.empty else pd.Series(dtype=float)


def _ret(s: pd.Series, ini: pd.Timestamp, fim: pd.Timestamp) -> float | None:
    if s.empty:  # sem preço (fonte fora do ar): a previsão fica "sem dados"
        return None
    a, b = s[s.index <= ini], s[s.index <= fim]
    if a.empty or b.empty or b.index[-1] <= a.index[-1]:
        return None
    return (float(b.iloc[-1]) / float(a.iloc[-1]) - 1) * 100


def _ret_carteira(pesos: dict, ini, fim, precos, cdi) -> float | None:
    """Retorno com rebalanceamento diário nos pesos dados (mesma conta das outras abas)."""
    series = {}
    for k in pesos:
        if k == RF_ID:
            continue
        s = precos("^BVSP" if k in ("_IBOV", "BOVA11") else f"{k}.SA")
        if s.empty:
            return None
        series[k] = s
    df = pd.DataFrame(series)
    df = df[(df.index >= ini - pd.Timedelta(days=10)) & (df.index <= fim)].ffill().dropna()
    df = df[df.index >= df.index[df.index <= ini][-1]] if (df.index <= ini).any() else df.iloc[0:0]
    if len(df) < 2:
        return None
    r = df.pct_change().dropna()
    rf_dia = (1 + (cdi or 0) / 100) ** (1 / 252) - 1
    rp = sum(w / 100 * (rf_dia if k == RF_ID else r[k]) for k, w in pesos.items())
    if not isinstance(rp, pd.Series):
        return None
    return float((1 + rp).prod() - 1) * 100


def conferir(linha: dict, hoje: date, precos) -> dict:
    """Resultado de uma previsão em cada horizonte: pendente (com a data em que fica pronta) ou o excesso e o acerto."""
    ini = pd.Timestamp(linha["data"])
    out = {}
    for h, dias in HORIZONTES.items():
        fim = ini + pd.Timedelta(days=dias)
        if fim.date() > hoje:
            out[h] = {"status": "pendente", "pronto_em": fim.strftime("%Y-%m-%d")}
            continue
        if linha["origem"] == "carteira":
            d = linha["detalhes"]
            rp, ra = _ret_carteira(d["proposta"], ini, fim, precos, d.get("cdi")), _ret_carteira(d["atual"], ini, fim, precos, d.get("cdi"))
            exc = None if rp is None or ra is None else rp - ra
        else:
            ra_, ib = _ret(precos(f"{linha['alvo']}.SA"), ini, fim), _ret(precos("^BVSP"), ini, fim)
            exc = None if ra_ is None or ib is None else ra_ - ib
        if exc is None:
            out[h] = {"status": "sem_dados"}
            continue
        p = linha["previsao"]
        acerto = (exc > 0 if p in ("barata", "aprovada") else exc < 0 if p in ("cara", "reprovada") else None)
        out[h] = {"status": "conferida", "excesso": exc, "acerto": acerto}
    return out


def _uma_por_mes(linhas: list[dict]) -> list[dict]:
    vistos, out = set(), []
    for l in sorted(linhas, key=lambda x: x["data"]):
        chave = (l["origem"], l["alvo"], l["data"][:7])
        if chave not in vistos:
            vistos.add(chave)
            out.append(l)
    return out


def painel(hoje: date | None = None, precos=None, db=None) -> dict:
    hoje = hoje or date.today()
    cache: dict[str, pd.Series] = {}
    buscar = precos or _precos_padrao

    def px(simbolo):
        if simbolo not in cache:
            try:
                cache[simbolo] = buscar(simbolo)
            except Exception:  # noqa: BLE001 — sem preço, a previsão fica "sem dados"
                cache[simbolo] = pd.Series(dtype=float)
        return cache[simbolo]

    with _db(db) as c:
        c.row_factory = sqlite3.Row
        todas = [dict(r) for r in c.execute("SELECT * FROM previsoes ORDER BY data DESC, id DESC")]
    for l in todas:
        l["detalhes"] = json.loads(l["detalhes"] or "{}")
    contadas = _uma_por_mes(todas)
    for l in contadas:
        l["resultado"] = conferir(l, hoje, px)

    resumo = {}
    for origem in ("cara_ou_barata", "research", "carteira"):
        ls = [l for l in contadas if l["origem"] == origem]
        por_h = {}
        for h in HORIZONTES:
            conf = [l for l in ls if l["resultado"][h]["status"] == "conferida"]
            grupos = {}
            for g in GRUPOS:
                xs = [l["resultado"][h] for l in conf if l["previsao"] == g]
                if xs:
                    acertos = [x["acerto"] for x in xs if x["acerto"] is not None]
                    grupos[g] = {"n": len(xs), "excesso_medio": statistics.mean(x["excesso"] for x in xs),
                                 "taxa_acerto": (sum(acertos) / len(acertos) * 100) if acertos else None}
            base = [l["resultado"][h]["excesso"] for l in conf]
            positivos = (sum(1 for x in base if x > 0) / len(base) * 100) if base else None
            alto, baixo = ("barata", "cara") if origem != "carteira" else ("aprovada", "reprovada")
            spread = (grupos[alto]["excesso_medio"] - grupos[baixo]["excesso_medio"]) if alto in grupos and baixo in grupos else None
            por_h[h] = {"conferidas": len(conf), "pendentes": sum(1 for l in ls if l["resultado"][h]["status"] == "pendente"),
                        "grupos": grupos, "taxa_base": positivos, "diferenca_grupos": spread}
        proxima = min((l["resultado"][h]["pronto_em"] for l in ls for h in HORIZONTES if l["resultado"][h]["status"] == "pendente"), default=None)
        resumo[origem] = {"previsoes": len(ls), "horizontes": por_h, "proxima_conferencia": proxima}
    recentes = [{k: l[k] for k in ("id", "data", "origem", "alvo", "previsao", "preco", "resultado")} |
                {"motivo": l["detalhes"].get("motivo"), "texto": l["detalhes"].get("texto")} for l in contadas[:200]]
    return {"hoje": hoje.isoformat(), "total_registros": len(todas), "contadas": len(contadas), "resumo": resumo,
            "previsoes": sorted(recentes, key=lambda x: x["data"], reverse=True), "horizontes": list(HORIZONTES), "grupos": GRUPOS}
