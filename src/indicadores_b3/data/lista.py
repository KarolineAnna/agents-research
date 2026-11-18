"""Listagem de ativos disponíveis, separada por classe, para o seletor do site.

  acoes      -> CVM, FCA (valores mobiliários negociados das companhias abertas)
  fiis       -> CVM, informe mensal de FII (código derivado do ISIN: 4 letras + "11")
  etfs       -> lista mantida à mão em etfs.csv (a CVM não liga ticker de ETF ao fundo)
  outros     -> cripto, ouro e dólar suportados pelo site
  renda_fixa -> Tesouro Nacional, títulos no arquivo mais recente do Tesouro Direto
"""
import csv
from functools import lru_cache
from pathlib import Path

from indicadores_b3.data import fii, fundamentos, tesouro

CLASSES = {
    "acoes": "Ações",
    "fiis": "FIIs",
    "etfs": "ETFs",
    "outros": "Cripto, ouro e dólar",
    "renda_fixa": "Renda fixa (Tesouro)",
}
FONTES = {
    "acoes": "CVM · FCA (valores mobiliários)",
    "fiis": "CVM · informe mensal de FII (código derivado do ISIN)",
    "etfs": "Lista manual em etfs.csv — edite para incluir outros",
    "outros": "Ativos suportados pelo site",
    "renda_fixa": "Tesouro Nacional · precotaxatesourodireto.csv",
}


def _col(df, *nomes):
    baixo = {c.lower(): c for c in df.columns}
    return next((baixo[n.lower()] for n in nomes if n.lower() in baixo), None)


TICKER_ACAO = r"[A-Z0-9]{4}(3|4|5|6|7|8|11)"


def _acoes_fca() -> dict[str, dict]:
    """Ações e units no FCA da CVM. Junta os dois últimos anos (empresas que ainda não
    entregaram o FCA deste ano aparecem pelo do ano anterior)."""
    out = {}
    for ano in fundamentos.ANOS[-2:]:  # o mais recente sobrescreve
        df = fundamentos.ler_csv("FCA", ano, "valor_mobiliario")
        if df.empty:
            continue
        c_tk, c_nome = _col(df, "Codigo_Negociacao"), _col(df, "Nome_Empresarial", "Nome_Companhia")
        c_vm, c_fim, c_merc = _col(df, "Valor_Mobiliario"), _col(df, "Data_Fim_Negociacao"), _col(df, "Mercado")
        df = df.dropna(subset=[c_tk]).copy()
        df["_tk"] = df[c_tk].str.strip().str.upper()
        df = df[df["_tk"].str.fullmatch(TICKER_ACAO)]
        if c_vm:  # só ações e units (tira debêntures, notas etc.)
            df = df[df[c_vm].str.contains("Aç|Unit", case=False, na=False)]
        for _, r in df.iterrows():
            encerrada = c_fim and str(r[c_fim]).strip() not in ("", "nan")
            fora_bolsa = c_merc and isinstance(r[c_merc], str) and "Bolsa" not in r[c_merc]
            out[r["_tk"]] = {"nome": r[c_nome] if c_nome else "", "tipo": r[c_vm] if c_vm else "",
                             "encerrada": bool(encerrada), "fora_bolsa": bool(fora_bolsa)}
    return out


def _acoes_b3() -> tuple[dict[str, dict], str | None]:
    """Ações e units com negócio no último pregão (arquivo COTAHIST oficial da B3)."""
    try:
        from indicadores_b3.data import opcoes
        dia, arq = opcoes.ultimo_pregao()
        df = opcoes.ler(arq)
    except Exception:  # noqa: BLE001 — sem B3, fica só a CVM
        return {}, None
    df = df[(df.TPMERC == "010") & df.CODNEG.str.fullmatch(TICKER_ACAO) & df.ESPECI.str.match(r"(ON|PN|UNT)")]
    return ({r.CODNEG: {"nome": r.NOMRES, "especie": r.ESPECI} for r in df.itertuples()}, dia.strftime("%d/%m/%Y"))


@lru_cache(maxsize=1)
def acoes() -> list[dict]:
    fca = _acoes_fca()
    b3, pregao = _acoes_b3()
    FONTES["acoes"] = (f"B3 · COTAHIST do pregão de {pregao} + CVM · FCA" if pregao
                       else "CVM · FCA (valores mobiliários) — arquivo da B3 indisponível agora")
    try:
        from indicadores_b3.data import setores
        st = setores.tabela().set_index("ticker")[["setor", "macro", "volume"]].to_dict("index")
    except Exception:  # noqa: BLE001 — sem FCA geral, segue sem setor
        st = {}
    itens = []
    for tk in sorted(set(fca) | set(b3)):
        f, b = fca.get(tk), b3.get(tk)
        if b:  # negociou no último pregão: está listada
            det = f"{b['especie']} · negociada em {pregao}"
            itens.append({"ticker": tk, "nome": (f or {}).get("nome") or b["nome"], "detalhe": det, "classe": "Ação", **st.get(tk, {})})
        elif f and not f["encerrada"] and not f["fora_bolsa"]:
            det = f["tipo"] + (" · sem negócio no último pregão" if pregao else "")
            itens.append({"ticker": tk, "nome": f["nome"], "detalhe": det, "classe": "Ação", **st.get(tk, {})})
    return itens


@lru_cache(maxsize=1)
def fiis() -> list[dict]:
    return sorted(({"ticker": f"{k}11", "nome": v["nome"], "detalhe": v.get("segmento") or "", "classe": "FII"}
                   for k, v in fii.mapa_tickers().items()), key=lambda x: x["ticker"])


def etfs() -> list[dict]:
    arq = Path(__file__).parent / "etfs.csv"
    with arq.open(encoding="utf-8") as f:
        return [{"ticker": r["ticker"], "nome": r["nome"], "detalhe": r["indice"], "classe": "ETF"}
                for r in csv.DictReader(f)]


def outros() -> list[dict]:
    return [
        {"ticker": "BTC", "nome": "Bitcoin", "detalhe": "Yahoo (US$) × PTAX", "classe": "Cripto"},
        {"ticker": "ETH", "nome": "Ethereum", "detalhe": "Yahoo (US$) × PTAX", "classe": "Cripto"},
        {"ticker": "SOL", "nome": "Solana", "detalhe": "Yahoo (US$) × PTAX", "classe": "Cripto"},
        {"ticker": "OURO", "nome": "Ouro (contrato futuro COMEX)", "detalhe": "Yahoo GC=F × PTAX", "classe": "Commodity"},
        {"ticker": "USD", "nome": "Dólar americano", "detalhe": "PTAX venda — Banco Central", "classe": "Moeda"},
    ]


def listar(classe: str) -> dict:
    funcs = {"acoes": acoes, "fiis": fiis, "etfs": etfs, "outros": outros, "renda_fixa": tesouro.ofertados}
    if classe not in funcs:
        raise ValueError(f"Classe inválida. Use: {', '.join(CLASSES)}")
    itens = funcs[classe]()  # antes da fonte: acoes() atualiza o texto da fonte
    return {"classe": classe, "nome": CLASSES[classe], "fonte": FONTES[classe], "itens": itens}
