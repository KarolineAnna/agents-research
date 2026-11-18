"""Classificação setorial das ações listadas.

Fonte oficial: campo ``Setor_Atividade`` do Formulário Cadastral (FCA) da CVM, arquivo
``fca_cia_aberta_geral_<ano>.csv``. É o setor que a própria companhia declara à CVM.

Em cima dele, dois ajustes do projeto (declarados, não oficiais):
  - ``Emp. Adm. Part. - <setor>`` (holding que atua em <setor>) vira <setor>, com ``holding = True``;
  - cada setor é agrupado num **macrossetor** inspirado na classificação da B3 (Financeiro, Utilidade pública…).
    A B3 tem a sua própria classificação (setor › subsetor › segmento), que pode diferir em alguns casos
    (ex.: supermercados são "consumo não cíclico" na B3, mas a CVM os põe em "Comércio").

Pares de uma empresa = outras companhias do mesmo setor, uma ação por companhia (a mais negociada no
último pregão do COTAHIST da B3), ordenadas pelo volume financeiro.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from indicadores_b3.data import fundamentos

MACRO = {
    "Financeiro": ["Bancos", "Intermediação Financeira", "Seguradoras e Corretoras", "Crédito Imobiliário",
                   "Bolsas de Valores/Mercadorias e Futuros", "Arrendamento Mercantil", "Securitização de Recebíveis", "Factoring"],
    "Utilidade pública": ["Energia Elétrica", "Saneamento, Serv. Água e Gás"],
    "Petróleo, gás e biocombustíveis": ["Petróleo e Gás"],
    "Materiais básicos": ["Metalurgia e Siderurgia", "Extração Mineral", "Papel e Celulose", "Petroquímicos e Borracha",
                          "Química", "Embalagens", "Reflorestamento"],
    "Bens industriais": ["Máquinas, Equipamentos, Veículos e Peças", "Serviços Transporte e Logística"],
    "Consumo cíclico": ["Construção Civil, Mat. Constr. e Decoração", "Comércio (Atacado e Varejo)", "Têxtil e Vestuário",
                        "Educação", "Hospedagem e Turismo", "Brinquedos e Lazer"],
    "Consumo não cíclico": ["Alimentos", "Bebidas e Fumo", "Agricultura (Açúcar, Álcool e Cana)"],
    "Saúde": ["Serviços médicos", "Farmacêutico e Higiene"],
    "Tecnologia e comunicações": ["Telecomunicações", "Comunicação e Informática"],
}
# algumas abreviações das holdings ("Emp. Adm. Part. - Máqs., Equip., ...") diferem do nome do setor
SINONIMOS = {
    "Máqs., Equip., Veíc. e Peças": "Máquinas, Equipamentos, Veículos e Peças",
    "Const. Civil, Mat. Const. e Decoração": "Construção Civil, Mat. Constr. e Decoração",
    "Sem Setor Principal": "Holdings diversificadas",
}
MACRO_DE = {s: m for m, ss in MACRO.items() for s in ss}


def normalizar(setor_cvm: str | None) -> tuple[str, bool]:
    """'Emp. Adm. Part. - Energia Elétrica' → ('Energia Elétrica', True)."""
    s = (setor_cvm or "").strip()
    m = re.match(r"Emp\. Adm\. Part\.\s*-\s*(.*)", s)
    holding = bool(m)
    s = m.group(1).strip() if m else s
    return SINONIMOS.get(s, s) or "Não informado", holding


@lru_cache(maxsize=1)
def _cadastro() -> pd.DataFrame:
    """CNPJ → setor (FCA mais recente de cada companhia, nos dois últimos anos)."""
    partes = []
    for ano in fundamentos.ANOS[-2:]:
        df = fundamentos.ler_csv("FCA", ano, "geral")
        if not df.empty and "Setor_Atividade" in df:
            partes.append(df)
    if not partes:
        return pd.DataFrame(columns=["cnpj", "empresa", "setor_cvm", "data_ref", "ano"])
    g = pd.concat(partes)
    g["cnpj"] = g["CNPJ_Companhia"].astype(str).str.replace(r"\D", "", regex=True)
    g = g.sort_values(["Data_Referencia", "Versao"]).drop_duplicates("cnpj", keep="last")
    return g.rename(columns={"Nome_Empresarial": "empresa", "Setor_Atividade": "setor_cvm",
                             "Data_Referencia": "data_ref"})[["cnpj", "empresa", "setor_cvm", "data_ref", "Descricao_Atividade"]]


@lru_cache(maxsize=1)
def _volumes() -> dict[str, float]:
    """Volume financeiro do último pregão por ticker (B3 · COTAHIST). Vazio se o arquivo não estiver disponível."""
    try:
        from indicadores_b3.data import opcoes
        _, arq = opcoes.ultimo_pregao()
        df = opcoes.ler(arq)
        df = df[df.TPMERC == "010"]
        return dict(zip(df.CODNEG, df.VOLTOT.astype(float), strict=False))
    except Exception:  # noqa: BLE001 — sem COTAHIST, a ordem vira alfabética
        return {}


@lru_cache(maxsize=1)
def tabela() -> pd.DataFrame:
    """Uma linha por ticker de ação: ticker, cnpj, empresa, setor, macrossetor, holding, volume."""
    mapa = fundamentos.mapa_tickers()
    cad = _cadastro().set_index("cnpj")
    vol = _volumes()
    linhas = []
    for tk, cnpj in mapa.items():
        if cnpj not in cad.index:
            continue
        c = cad.loc[cnpj]
        setor, holding = normalizar(c.setor_cvm)
        linhas.append({"ticker": tk, "cnpj": cnpj, "empresa": c.empresa, "setor_cvm": c.setor_cvm, "setor": setor,
                       "macro": MACRO_DE.get(setor, "Outros"), "holding": holding, "atividade": c.get("Descricao_Atividade"),
                       "data_ref": c.data_ref, "volume": vol.get(tk, 0.0)})
    return pd.DataFrame(linhas)


def _fonte(data_ref: str | None = None) -> dict:
    return {"fonte": "CVM", "documento": "FCA · dados gerais (campo Setor_Atividade)",
            "url": f"{fundamentos.CVM}/FCA/DADOS/", "data_ref": data_ref,
            "nota": "Setor declarado pela companhia à CVM. O macrossetor é um agrupamento do projeto, inspirado na B3."}


def setor_de(ticker: str) -> dict:
    t = tabela()
    r = t[t.ticker == ticker.strip().upper()]
    if r.empty:
        return {"ticker": ticker.upper(), "setor": None, "macro": None,
                "nota": "Sem classificação: não é ação de companhia aberta no cadastro da CVM (ETF, FII, BDR…)."}
    r = r.iloc[0]
    return {"ticker": r.ticker, "empresa": r.empresa, "setor": r.setor, "macro": r.macro, "holding": bool(r.holding),
            "setor_cvm": r.setor_cvm, "atividade": r.atividade, "fonte": _fonte(r.data_ref)}


def _uma_por_empresa(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém o ticker mais negociado de cada companhia (ex.: PETR4 em vez de PETR3)."""
    return df.sort_values(["volume", "ticker"], ascending=[False, True]).drop_duplicates("cnpj")


def pares(ticker: str, n: int = 4) -> dict:
    """Empresas do mesmo setor, mais negociadas primeiro. Se houver menos de 2, completa com o macrossetor."""
    t = tabela()
    alvo = t[t.ticker == ticker.strip().upper()]
    if alvo.empty:
        return {"ticker": ticker.upper(), "pares": [], "criterio": "sem classificação setorial", **setor_de(ticker)}
    a = alvo.iloc[0]
    outros = t[(t.cnpj != a.cnpj) & (t.volume > 0 if t.volume.sum() > 0 else True)]
    mesmo = _uma_por_empresa(outros[outros.setor == a.setor])
    criterio = f"mesmo setor: {a.setor}"
    if len(mesmo) < 2:
        extra = _uma_por_empresa(outros[(outros.macro == a.macro) & (outros.setor != a.setor)])
        mesmo = pd.concat([mesmo, extra])
        criterio = f"mesmo setor: {a.setor}, completado com o macrossetor {a.macro}"
    lista = mesmo.head(n)
    return {"ticker": a.ticker, "setor": a.setor, "macro": a.macro, "criterio": criterio,
            "ordem": "volume financeiro no último pregão (B3 · COTAHIST)" if t.volume.sum() > 0 else "alfabética",
            "pares": [{"ticker": r.ticker, "empresa": r.empresa, "setor": r.setor, "volume": r.volume} for r in lista.itertuples()],
            "fonte": _fonte(a.data_ref)}


def resumo() -> dict:
    """Macrossetor › setor › empresas (um ticker por companhia), para a tela e o seletor."""
    t = tabela()
    if t.empty:
        return {"macros": [], "fonte": _fonte()}
    out = []
    for macro, gm in t.groupby("macro"):
        setores = []
        for setor, gs in gm.groupby("setor"):
            emp = _uma_por_empresa(gs)
            setores.append({"setor": setor, "n_empresas": int(len(emp)),
                            "empresas": [{"ticker": r.ticker, "empresa": r.empresa, "holding": bool(r.holding)} for r in emp.itertuples()]})
        out.append({"macro": macro, "n_empresas": int(gm.cnpj.nunique()),
                    "setores": sorted(setores, key=lambda s: -s["n_empresas"])})
    return {"macros": sorted(out, key=lambda m: -m["n_empresas"]), "fonte": _fonte()}
