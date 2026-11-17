"""Laboratório da carteira: onde o agente formula e testa hipóteses sem "colar" do futuro.

O período é dividido como num modelo de machine learning:
    |---------------- treino (60%) ----------------|------ reserva (40%) ------|
      janela 1   |   janela 2   |   janela 3          janela 4   |   janela 5
- O agente só enxerga o TREINO: o diagnóstico que ele recebe e os testes que ele roda (testar_carteira) usam só
  essas três janelas. Ele pode testar quantas hipóteses couberem no limite.
- A RESERVA fica escondida até o fim. O agente escolhe no máximo 3 propostas e chama confirmar_propostas UMA vez;
  só então elas são medidas nos dias que ele nunca viu. É a reserva que decide se a proposta foi aprovada.
Regras que o código impõe (o agente não consegue furar): renda fixa no peso que você escolheu, peso máximo por ativo,
no máximo 3 ativos novos, número limitado de testes e uma única confirmação.
Critério de aprovação (fixo, decidido antes): render mais que a carteira atual na reserva inteira E nas duas janelas
da reserva, sem volatilidade mais de 20% maior. Rendeu mais no total mas perdeu numa janela = inconclusiva.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicadores_b3.agents import redator
from indicadores_b3.agents.fatos import Dossie

DU = 252
RF_ID = "RENDA FIXA (CDI)"
PARTE_TREINO = 0.6
JANELAS_TREINO, JANELAS_RESERVA = 3, 2
MAX_TESTES, MAX_NOVOS, MAX_CONFIRMAR = 12, 3, 3
PESO_MAX = 40.0
FOLGA_VOL = 1.2
APELIDOS_RF = {"RENDA FIXA (CDI)", "RENDA FIXA", "CDI", "RF", "TESOURO SELIC"}


def _janelas(df: pd.DataFrame, n: int) -> list[pd.DataFrame]:
    partes = np.array_split(np.arange(len(df)), n)
    return [df.iloc[p] for p in partes if len(p)]


def _acum(r: pd.Series) -> float:
    return float((1 + r).prod() - 1) * 100


def _vol(r: pd.Series) -> float:
    return float(r.std() * np.sqrt(DU)) * 100


def _queda(r: pd.Series) -> float:
    s = (1 + r).cumprod()
    return float((s / s.cummax() - 1).min()) * 100


class Laboratorio:
    def __init__(self, pesos: dict[str, float], ret: pd.DataFrame, rf_pct: float, carregar=None):
        """pesos já normalizados (somam 100); ret: retornos diários com as colunas dos ativos e _IBOV;
        carregar(ticker) -> série de preços, para testar ativos que não estão na carteira."""
        self.atual = dict(pesos)
        self.rf_w = pesos.get(RF_ID, 0.0)
        # carteira de 2 ativos já tem 50% em cada: o limite nunca fica abaixo do maior peso atual
        self.peso_max = max(PESO_MAX, max((v for k, v in pesos.items() if k != RF_ID), default=0.0))
        self.ret = ret.copy()
        self.rf_dia = (1 + rf_pct / 100) ** (1 / DU) - 1
        self._carregar = carregar
        corte = int(len(ret) * PARTE_TREINO)
        self.treino, self.reserva = ret.iloc[:corte], ret.iloc[corte:]
        self.jt, self.jr = _janelas(self.treino, JANELAS_TREINO), _janelas(self.reserva, JANELAS_RESERVA)
        self.D = Dossie("Laboratório da carteira", "E", "Hipóteses testadas")
        self.testes: list[dict] = []
        self.confirmacao: list[dict] | None = None

    # ---------- períodos ----------
    def periodos(self) -> dict:
        d = lambda x: x.index[0].strftime("%Y-%m-%d")  # noqa: E731
        f = lambda x: x.index[-1].strftime("%Y-%m-%d")  # noqa: E731
        return {"treino": f"{d(self.treino)} a {f(self.treino)}", "reserva": f"{d(self.reserva)} a {f(self.reserva)}",
                "janelas_treino": [f"{d(j)} a {f(j)}" for j in self.jt], "janelas_reserva": [f"{d(j)} a {f(j)}" for j in self.jr]}

    # ---------- pesos ----------
    def _coluna(self, t: str) -> str:
        if t in self.ret:
            return t
        if not self._carregar:
            raise ValueError(f"{t} não está na carteira e não há como carregar o preço dele.")
        px = self._carregar(t)
        r = px.reindex(self.ret.index.union(px.index)).sort_index().ffill().pct_change().reindex(self.ret.index)
        falta = float(r.isna().mean())
        if falta > 0.05:
            raise ValueError(f"{t} não tem histórico em {falta:.0%} dos dias do período: não dá para comparar.")
        self.ret[t] = r.fillna(0.0)
        corte = len(self.treino)
        self.treino, self.reserva = self.ret.iloc[:corte], self.ret.iloc[corte:]
        self.jt, self.jr = _janelas(self.treino, JANELAS_TREINO), _janelas(self.reserva, JANELAS_RESERVA)
        return t

    def preparar(self, pesos: dict) -> dict[str, float]:
        """Confere e normaliza uma proposta. Erros voltam para o agente como texto (ValueError)."""
        if not isinstance(pesos, dict) or not pesos:
            raise ValueError('Envie os pesos como objeto, ex.: {"PETR4": 30, "WEGE3": 30}.')
        risco, rf_pedido = {}, None
        for k, v in pesos.items():
            t = str(k).strip().upper()
            v = float(v)
            if v < 0:
                raise ValueError("Pesos negativos não são permitidos (sem venda a descoberto).")
            if t in APELIDOS_RF:
                rf_pedido = v
                continue
            if v > 0:
                chave = "_IBOV" if t == "BOVA11" else self._coluna(t)
                risco[chave] = risco.get(chave, 0) + v
        if rf_pedido is not None and abs(rf_pedido - self.rf_w) > 0.5:
            raise ValueError(f"A renda fixa é decisão da pessoa e fica em {redator.br(self.rf_w, 1)}%. Não mude esse peso.")
        if not risco:
            raise ValueError("A proposta precisa ter pelo menos um ativo de risco.")
        total, s = 100 - self.rf_w, sum(risco.values())
        out = {k: v / s * total for k, v in risco.items()}
        acima = [self.nome(k) for k, v in out.items() if v > self.peso_max + 1e-6]
        if acima:
            raise ValueError(f"Peso máximo por ativo é {redator.br(self.peso_max, 1)}% da carteira: {', '.join(acima)} passou disso.")
        novos = [k for k in out if k not in self.atual]
        if len(novos) > MAX_NOVOS:
            raise ValueError(f"No máximo {MAX_NOVOS} ativos novos por proposta (vieram {len(novos)}).")
        if self.rf_w:
            out[RF_ID] = self.rf_w
        return out

    def retorno(self, pesos: dict[str, float], df: pd.DataFrame) -> pd.Series:
        rp = pd.Series(0.0, index=df.index)
        for k, w in pesos.items():
            rp += w / 100 * (self.rf_dia if k == RF_ID else df[k])
        return rp

    @staticmethod
    def nome(t: str) -> str:
        return "BOVA11" if t == "_IBOV" else t

    def trocas(self, pesos: dict[str, float]) -> dict:
        entra = [self.nome(k) for k in pesos if k not in self.atual]
        sai = [k for k in self.atual if k not in pesos]
        return {"entra": entra, "sai": sai}

    # ---------- ferramentas ----------
    def testar(self, pesos: dict, motivo: str = "") -> dict:
        if self.confirmacao is not None:
            raise ValueError("A confirmação já foi feita: não dá para testar depois de ver a reserva.")
        if len(self.testes) >= MAX_TESTES:
            raise ValueError(f"Limite de {MAX_TESTES} testes atingido. Escolha as melhores e chame confirmar_propostas.")
        w = self.preparar(pesos)
        n = len(self.testes) + 1
        S = f"Teste {n}"
        jan = []
        for i, j in enumerate(self.jt, start=1):
            rp, ra = _acum(self.retorno(w, j)), _acum(self.retorno(self.atual, j))
            jan.append({"janela": i, "proposta": rp, "atual": ra, "ibov": _acum(j["_IBOV"]), "diferenca": rp - ra})
        rp_t, ra_t = self.retorno(w, self.treino), self.retorno(self.atual, self.treino)
        vit = sum(1 for x in jan if x["diferenca"] > 0)
        dif_media = float(np.mean([x["diferenca"] for x in jan]))
        D = self.D
        ids = {
            "ret": D.estimativa(f"Teste {n}: retorno no treino", _acum(rp_t), "%", "produto de (1 + retorno diário) − 1 no treino", [], S),
            "atual": D.estimativa(f"Teste {n}: retorno da carteira atual no treino", _acum(ra_t), "%", "mesma conta com os pesos atuais", [], S),
            "dif": D.estimativa(f"Teste {n}: diferença média contra a atual por janela", dif_media, "p.p.", "média das 3 janelas de (proposta − atual)", [], S),
            "vol": D.estimativa(f"Teste {n}: volatilidade no treino", _vol(rp_t), "% a.a.", "desvio-padrão diário × raiz(252)", [], S),
            "vol_atual": D.estimativa(f"Teste {n}: volatilidade da atual no treino", _vol(ra_t), "% a.a.", "desvio-padrão diário × raiz(252)", [], S),
            "queda": D.estimativa(f"Teste {n}: maior queda no treino", _queda(rp_t), "%", "pior queda do topo ao fundo", [], S),
        }
        for x in jan:
            x["id"] = D.estimativa(f"Teste {n}: diferença na janela {x['janela']} do treino", x["diferenca"], "p.p.", "proposta − atual", [], S)
        t = {"numero": n, "motivo": (motivo or "").strip()[:300], "pesos": {self.nome(k): v for k, v in w.items()}, "_pesos": w,
             "trocas": self.trocas(w), "janelas": jan, "vitorias": vit, "dif_media": dif_media,
             "ret": _acum(rp_t), "ret_atual": _acum(ra_t), "vol": _vol(rp_t), "vol_atual": _vol(ra_t), "queda": _queda(rp_t), "ids": ids}
        self.testes.append(t)
        it = {x["id"]: x for x in D.itens}
        f = lambda i: f"{redator.fmt(it[i]['valor'], it[i]['unidade'])} [{i}]" if i in it else "n/d"  # noqa: E731
        return {"teste": n, "pesos": {k: redator.br(v, 1) + "%" for k, v in t["pesos"].items()}, "trocas": t["trocas"],
                "venceu_a_atual_em": f"{vit} de {len(jan)} janelas do treino",
                "diferenca_media_por_janela": f(ids["dif"]), "retorno_no_treino": f(ids["ret"]), "atual_no_treino": f(ids["atual"]),
                "volatilidade": f(ids["vol"]), "volatilidade_atual": f(ids["vol_atual"]), "maior_queda": f(ids["queda"]),
                "janelas": [{"janela": x["janela"], "diferenca": f(x["id"])} for x in jan],
                "testes_restantes": MAX_TESTES - len(self.testes),
                "lembrete": "Resultado só no treino. Bom no treino ainda não é prova: a reserva decide."}

    def confirmar(self, testes: list[int]) -> dict:
        if self.confirmacao is not None:
            raise ValueError("A confirmação só pode ser feita uma vez.")
        nums = list(dict.fromkeys(int(x) for x in (testes or [])))[:MAX_CONFIRMAR]
        escolhidos = [t for t in self.testes if t["numero"] in nums]
        if not escolhidos:
            raise ValueError(f"Informe os números de até {MAX_CONFIRMAR} testes já feitos (ex.: [2, 5]).")
        S = "Confirmação na reserva"
        D = self.D
        ra = self.retorno(self.atual, self.reserva)
        ib = _acum(self.reserva["_IBOV"])
        id_atual = D.estimativa("Carteira atual na reserva", _acum(ra), "%", "produto de (1 + retorno diário) − 1 na reserva", [], S)
        id_ib = D.estimativa("Ibovespa na reserva", ib, "%", "produto de (1 + retorno diário) − 1 na reserva", [], S)
        out = []
        for t in escolhidos:
            w, n = t["_pesos"], t["numero"]
            rp = self.retorno(w, self.reserva)
            jan = [{"janela": i, "diferenca": _acum(self.retorno(w, j)) - _acum(self.retorno(self.atual, j))} for i, j in enumerate(self.jr, start=1)]
            dif = _acum(rp) - _acum(ra)
            vol, vol_a = _vol(rp), _vol(ra)
            todas = all(x["diferenca"] > 0 for x in jan)
            status = ("aprovada" if dif > 0 and todas and vol <= vol_a * FOLGA_VOL else
                      "inconclusiva" if dif > 0 else "reprovada")
            ids = {"ret": D.estimativa(f"Teste {n}: retorno na reserva", _acum(rp), "%", "produto de (1 + retorno diário) − 1 na reserva", [], S),
                   "dif": D.estimativa(f"Teste {n}: diferença contra a atual na reserva", dif, "p.p.", "proposta − atual", [id_atual], S),
                   "dif_ib": D.estimativa(f"Teste {n}: diferença contra o Ibovespa na reserva", _acum(rp) - ib, "p.p.", "proposta − Ibovespa", [id_ib], S),
                   "vol": D.estimativa(f"Teste {n}: volatilidade na reserva", vol, "% a.a.", "desvio-padrão diário × raiz(252)", [], S),
                   "queda": D.estimativa(f"Teste {n}: maior queda na reserva", _queda(rp), "%", "pior queda do topo ao fundo", [], S)}
            for x in jan:
                x["id"] = D.estimativa(f"Teste {n}: diferença na janela {x['janela'] + JANELAS_TREINO} (reserva)", x["diferenca"], "p.p.", "proposta − atual", [], S)
            out.append({"numero": n, "motivo": t["motivo"], "pesos": t["pesos"], "trocas": t["trocas"], "status": status,
                        "ret": _acum(rp), "dif": dif, "dif_ibov": _acum(rp) - ib, "vol": vol, "vol_atual": vol_a, "queda": _queda(rp),
                        "janelas": jan, "ids": ids, "treino_vitorias": t["vitorias"], "treino_dif_media": t["dif_media"]})
        self.confirmacao = out
        it = {x["id"]: x for x in D.itens}
        f = lambda i: f"{redator.fmt(it[i]['valor'], it[i]['unidade'])} [{i}]" if i in it else "n/d"  # noqa: E731
        return {"carteira_atual_na_reserva": f(id_atual), "ibovespa_na_reserva": f(id_ib),
                "criterio": "regra do projeto, fixada antes dos testes: aprovada = rendeu mais que a atual na reserva inteira e nas 2 janelas, sem volatilidade mais de 20% maior; "
                            "inconclusiva = rendeu mais no total mas perdeu numa janela ou ficou bem mais arriscada; reprovada = rendeu menos",
                "resultados": [{"teste": x["numero"], "status": x["status"], "retorno": f(x["ids"]["ret"]), "contra_a_atual": f(x["ids"]["dif"]),
                                "contra_o_ibovespa": f(x["ids"]["dif_ib"]), "volatilidade": f(x["ids"]["vol"]), "maior_queda": f(x["ids"]["queda"]),
                                "janelas": [f(j["id"]) for j in x["janelas"]]} for x in out]}

    def melhores(self, n: int = MAX_CONFIRMAR) -> list[int]:
        """Para a confirmação automática: os testes com mais vitórias no treino e maior diferença média."""
        bons = [t for t in self.testes if t["dif_media"] > 0] or self.testes
        return [t["numero"] for t in sorted(bons, key=lambda t: (-t["vitorias"], -t["dif_media"]))[:n]]

    def resumo(self) -> dict:
        limpar = lambda t: {k: v for k, v in t.items() if not k.startswith("_")}  # noqa: E731
        return {"periodos": self.periodos(), "testes": [limpar(t) for t in self.testes], "confirmacao": self.confirmacao,
                "regras": {"peso_max": self.peso_max, "max_novos": MAX_NOVOS, "max_testes": MAX_TESTES, "max_confirmar": MAX_CONFIRMAR,
                           "renda_fixa": self.rf_w, "folga_vol": FOLGA_VOL}}
