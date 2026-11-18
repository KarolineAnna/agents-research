"""Tesouro Direto: preços e taxas oficiais do Tesouro Nacional (dados abertos).

Fonte: https://www.tesourotransparente.gov.br/ckan/dataset/taxas-dos-titulos-ofertados-pelo-tesouro-direto
Arquivo: precotaxatesourodireto.csv (separador ';', latin-1, vírgula decimal, datas DD/MM/AAAA)
Colunas usadas: Tipo Titulo, Data Vencimento, Data Base, Taxa Compra Manha, Taxa Venda Manha,
                PU Compra Manha, PU Venda Manha, PU Base Manha

Código usado no site: TD-<TIPO>-<AAAAMMDD do vencimento>, ex.: TD-IPCA-20350515.
"""
import time
from functools import lru_cache

import pandas as pd
import requests

from indicadores_b3 import config
from indicadores_b3.data.fontes import erro_amigavel

URL = ("https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
       "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv")
PAGINA = "https://www.tesourotransparente.gov.br/ckan/dataset/taxas-dos-titulos-ofertados-pelo-tesouro-direto"
CACHE = config.CACHE_DIR / "tesouro_precotaxa.csv"
CACHE.parent.mkdir(parents=True, exist_ok=True)

SIGLAS = {  # Tipo Titulo -> sigla do código
    "Tesouro Selic": "SELIC",
    "Tesouro Prefixado": "PRE",
    "Tesouro Prefixado com Juros Semestrais": "PREJS",
    "Tesouro IPCA+": "IPCA",
    "Tesouro IPCA+ com Juros Semestrais": "IPCAJS",
    "Tesouro IGPM+ com Juros Semestrais": "IGPMJS",
    "Tesouro Renda+ Aposentadoria Extra": "RENDA",
    "Tesouro Educa+": "EDUCA",
}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                         errors="coerce")


@lru_cache(maxsize=1)
def _tabela(dia: str) -> pd.DataFrame:
    if not (CACHE.exists() and time.time() - CACHE.stat().st_mtime < 86400):
        try:
            r = requests.get(URL, timeout=300)
            r.raise_for_status()
            CACHE.write_bytes(r.content)
        except requests.RequestException:
            if not CACHE.exists():  # sem internet e sem cache: não há o que fazer
                raise
            # sem internet: segue com o arquivo em cache (a data base aparece no site e no painel de saúde)
    df = pd.read_csv(CACHE, sep=";", encoding="latin-1", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df["base"] = pd.to_datetime(df["Data Base"], dayfirst=True, errors="coerce")
    df["vencimento"] = pd.to_datetime(df["Data Vencimento"], dayfirst=True, errors="coerce")
    for c in ["Taxa Compra Manha", "Taxa Venda Manha", "PU Compra Manha", "PU Venda Manha", "PU Base Manha"]:
        if c in df.columns:
            df[c] = _num(df[c])
    df["sigla"] = df["Tipo Titulo"].map(SIGLAS).fillna("OUTRO")
    df["codigo"] = "TD-" + df["sigla"] + "-" + df["vencimento"].dt.strftime("%Y%m%d")
    return df.dropna(subset=["base", "vencimento"])


def tabela() -> pd.DataFrame:
    return _tabela(pd.Timestamp.now().strftime("%Y-%m-%d"))


def eh_tesouro(codigo: str) -> bool:
    return codigo.upper().startswith("TD-")


def titulo(codigo: str) -> pd.DataFrame:
    df = tabela()
    t = df[df["codigo"] == codigo.upper()].sort_values("base")
    if t.empty:
        raise LookupError(f"{codigo}: título não encontrado no arquivo do Tesouro Direto.")
    return t


def nome(codigo: str) -> str:
    t = titulo(codigo).iloc[-1]
    return f"{t['Tipo Titulo']} {t['vencimento']:%Y} (venc. {t['vencimento']:%d/%m/%Y})"


def serie_pu(codigo: str, inicio) -> tuple[pd.Series, dict]:
    """Preço unitário de mercado (PU base, manhã) por dia — é o valor de marcação a mercado."""
    t = titulo(codigo)
    t = t[t["base"] >= pd.Timestamp(inicio)]
    s = pd.Series(t["PU Base Manha"].values, index=t["base"]).dropna()
    s = s[~s.index.duplicated(keep="last")]
    fonte = {"fonte": "Tesouro Nacional", "documento": "precotaxatesourodireto.csv · coluna PU Base Manha",
             "descricao": "Preço unitário de mercado do título (marcação a mercado)", "url": URL}
    return s, fonte


def ofertados() -> list[dict]:
    """Títulos à venda (vendas recentes nos dados abertos do Tesouro); se falhar, todos os do arquivo mais recente."""
    df = tabela()
    ult = df[df["base"] == df["base"].max()].sort_values(["Tipo Titulo", "vencimento"])
    venda = a_venda()
    if venda["ok"]:
        ult = ult[ult["codigo"].isin(venda["codigos"])]
    return [{"ticker": r["codigo"], "nome": f"{r['Tipo Titulo']} {r['vencimento']:%Y}",
             "detalhe": f"Taxa {r['Taxa Compra Manha']:.2f}% · vence {r['vencimento']:%d/%m/%Y}".replace(".", ","),
             "classe": "Renda fixa"} for _, r in ult.iterrows()]


def dados(codigo: str) -> dict:
    """Base para o catálogo de indicadores de Tesouro, com rastreio."""
    t = titulo(codigo)
    atual = t.iloc[-1]
    hoje = atual["base"]

    def linha(r, coluna, descricao, valor):
        return {"sinal": "+", "papel": "Arquivo do Tesouro Direto", "fonte": "Tesouro Nacional",
                "documento": "precotaxatesourodireto.csv", "url": URL, "data_ref": r["base"].strftime("%Y-%m-%d"),
                "periodo": f"data base {r['base']:%Y-%m-%d}", "conta": coluna, "descricao": descricao,
                "valor": float(valor)}

    def campo(coluna, descricao, nota=""):
        v = atual.get(coluna)
        return {"valor": None if pd.isna(v) else float(v),
                "componentes": [] if pd.isna(v) else [linha(atual, coluna, descricao, v)], "nota": nota}

    ano = t[t["base"] <= hoje - pd.DateOffset(years=1)]
    r_ant = ano.iloc[-1] if not ano.empty else t.iloc[0]
    pu = t.set_index("base")["PU Base Manha"].dropna()
    pu = pu[pu.index > hoje - pd.DateOffset(years=1)]
    ret = pu.pct_change().dropna()

    anos_venc = (atual["vencimento"] - hoje).days / 365.25
    return {
        "ticker": codigo.upper(), "empresa": nome(codigo), "balanco_ref": hoje.strftime("%Y-%m-%d"),
        "rastreio": {
            "taxa_compra": campo("Taxa Compra Manha", "Taxa de compra (% a.a.)",
                                 "Taxa que o Tesouro paga a quem compra hoje e leva até o vencimento. "
                                 "Selic: taxa acima da Selic. IPCA+: taxa acima da inflação. Prefixado: taxa total."),
            "pu_compra": campo("PU Compra Manha", "Preço de compra do título (R$)"),
            "preco": campo("PU Base Manha", "Preço de mercado do título (R$)",
                           "Marcação a mercado: quanto o título vale hoje se vendido antes do vencimento."),
            "preco_12m": {"valor": float(r_ant["PU Base Manha"]),
                          "componentes": [linha(r_ant, "PU Base Manha", "Preço de mercado ~12 meses atrás (R$)",
                                                r_ant["PU Base Manha"])], "nota": ""},
            "anos_vencimento": {"valor": anos_venc, "componentes": [linha(atual, "Data Vencimento",
                                f"Vencimento em {atual['vencimento']:%d/%m/%Y}", anos_venc)],
                                "nota": "Anos entre a data base do arquivo e o vencimento."},
            "desvio_diario": {"valor": float(ret.std()) if len(ret) > 5 else None, "componentes": [],
                              "nota": f"Desvio-padrão de {len(ret)} variações diárias do preço de mercado."},
            "obs_ano": {"valor": len(ret), "componentes": [], "nota": "Dias com preço publicado no último ano."},
        },
    }


# ---------- Quais títulos estão à venda hoje ----------
# O arquivo de preços lista também títulos que só aceitam resgate e não tem uma coluna "à venda".
# A resposta vem de outro dado aberto oficial, "Vendas do Tesouro Direto" (Tesouro Transparente):
# vendas diárias por título, publicadas com 2 dias de atraso. Título com venda registrada nos últimos
# 14 dias da série = está sendo oferecido. (A lista JSON do site do Tesouro Direto, usada antes, saiu do ar em 08/2025.)
VENDAS_PACOTE = "f0468ecc-ae97-4287-89c2-6d8139fb4343"
VENDAS_API = f"https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id={VENDAS_PACOTE}"
VENDAS_PAGINA = f"https://www.tesourotransparente.gov.br/ckan/dataset/{VENDAS_PACOTE}"
VENDAS_CACHE = config.CACHE_DIR / "tesouro_vendas.csv"
JANELA_VENDAS = 14  # dias corridos


def _baixar_vendas() -> None:
    if VENDAS_CACHE.exists() and time.time() - VENDAS_CACHE.stat().st_mtime < 86400:
        return
    try:
        pacote = requests.get(VENDAS_API, timeout=60).json()["result"]
        url = next(r["url"] for r in pacote["resources"] if str(r.get("url", "")).lower().endswith(".csv")
                   or str(r.get("format", "")).lower() == "csv")
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        VENDAS_CACHE.write_bytes(r.content)
    except (requests.RequestException, KeyError, StopIteration, ValueError):
        if not VENDAS_CACHE.exists():
            raise


def codigos_vendidos(df: pd.DataFrame, janela: int = JANELA_VENDAS) -> tuple[set[str], pd.Timestamp]:
    """Códigos com venda nos últimos `janela` dias da série. Acha as colunas pelo nome (tipo, vencimento, data da venda)."""
    cols = {c.lower(): c for c in df.columns}
    tipo = next(v for k, v in cols.items() if "tipo" in k)
    venc = next(v for k, v in cols.items() if "venc" in k)
    data = next(v for k, v in cols.items() if "data" in k and "venc" not in k)
    d = pd.DataFrame({"tipo": df[tipo].str.strip(), "venc": pd.to_datetime(df[venc], dayfirst=True, errors="coerce"),
                      "data": pd.to_datetime(df[data], dayfirst=True, errors="coerce")}).dropna()
    ult = d["data"].max()
    rec = d[d["data"] > ult - pd.Timedelta(days=janela)]
    return {f"TD-{SIGLAS.get(t, 'OUTRO')}-{v:%Y%m%d}" for t, v in zip(rec["tipo"], rec["venc"], strict=True)}, ult


@lru_cache(maxsize=2)
def _a_venda(dia: str) -> tuple[frozenset, str]:
    _baixar_vendas()
    df = pd.read_csv(VENDAS_CACHE, sep=";", encoding="latin-1", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    cods, ult = codigos_vendidos(df)
    if not cods:
        raise ValueError("nenhuma venda recente no arquivo")
    return frozenset(cods), ult.strftime("%Y-%m-%d")


def a_venda() -> dict:
    """{'ok': True, 'codigos': {...}, 'ate': data} ou {'ok': False, 'erro': ...}."""
    try:
        cods, ate = _a_venda(pd.Timestamp.now().strftime("%Y-%m-%d"))
        return {"ok": True, "codigos": set(cods), "url": VENDAS_PAGINA, "ate": ate,
                "nota": f"Títulos com venda registrada nos {JANELA_VENDAS} dias até {pd.Timestamp(ate):%d/%m/%Y} "
                        "(Vendas do Tesouro Direto, dados abertos, 2 dias de atraso)."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": erro_amigavel(e), "url": VENDAS_PAGINA}

