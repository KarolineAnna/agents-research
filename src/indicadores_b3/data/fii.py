"""Fundos imobiliários: informe mensal estruturado da CVM.

Fonte: https://dados.cvm.gov.br/dataset/fii-doc-inf_mensal
Arquivos: inf_mensal_fii_{ano}.zip, com CSVs "geral" (cadastro, ISIN) e "complemento" (PL, cotas, DY...).

Os nomes de coluna mudaram ao longo do tempo (ex.: CNPJ_Fundo -> CNPJ_Fundo_Classe após a
Resolução CVM 175). Por isso cada campo aceita uma lista de nomes; se nenhum existir, o erro
mostra as colunas disponíveis para você ajustar a lista.
"""
import time
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from indicadores_b3 import config
from indicadores_b3.data.fontes import comp, rastro

BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS"
DICIONARIO = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/META/meta_inf_mensal_fii.zip"
CACHE = config.CACHE_DIR
CACHE.mkdir(parents=True, exist_ok=True)
ANO = pd.Timestamp.now().year
ANOS = [ANO - 1, ANO]

COLUNAS = {
    "cnpj":     ["CNPJ_Fundo_Classe", "CNPJ_Fundo", "CNPJ"],
    "data":     ["Data_Referencia"],
    "versao":   ["Versao"],
    "nome":     ["Nome_Fundo_Classe", "Nome_Fundo"],
    "isin":     ["Codigo_ISIN", "ISIN"],
    "segmento": ["Segmento_Atuacao"],
    "pl":       ["Patrimonio_Liquido"],
    "cotas":    ["Cotas_Emitidas"],
    "vp_cota":  ["Valor_Patrimonial_Cotas"],
    "dy_mes":   ["Percentual_Dividend_Yield_Mes"],
    "cotistas": ["Total_Numero_Cotistas", "Numero_Cotistas"],
}


def col(df: pd.DataFrame, campo: str, obrigatorio=True) -> str | None:
    baixo = {c.lower(): c for c in df.columns}
    for nome in COLUNAS[campo]:
        if nome.lower() in baixo:
            return baixo[nome.lower()]
    if obrigatorio:
        raise KeyError(f"Campo '{campo}' não encontrado no informe mensal de FII. Tentei {COLUNAS[campo]}. "
                       f"Colunas disponíveis: {list(df.columns)}. Ajuste COLUNAS em fii.py "
                       f"(dicionário: {DICIONARIO}).")
    return None


def num(s: pd.Series) -> pd.Series:
    """CVM às vezes usa vírgula decimal."""
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def baixar(ano: int) -> Path | None:
    arq = CACHE / f"fii_inf_mensal_{ano}.zip"
    if arq.exists() and time.time() - arq.stat().st_mtime < 86400:
        return arq
    try:
        r = requests.get(f"{BASE_URL}/inf_mensal_fii_{ano}.zip", timeout=300)
    except requests.RequestException:  # sem internet: usa o arquivo em cache, mesmo antigo
        return arq if arq.exists() else None
    if not r.ok:
        return arq if arq.exists() else None
    arq.write_bytes(r.content)
    return arq


@lru_cache(maxsize=8)
def tabela(parte: str, ano: int) -> tuple[pd.DataFrame, str]:
    """parte = 'geral' ou 'complemento'. Retorna (df, nome do arquivo)."""
    arq = baixar(ano)
    if arq is None:
        return pd.DataFrame(), ""
    with zipfile.ZipFile(arq) as zf:
        nome = next((n for n in zf.namelist() if parte in n.lower()), None)
        if nome is None:
            return pd.DataFrame(), ""
        df = pd.read_csv(zf.open(nome), sep=";", encoding="latin-1", dtype=str)
    df["_ANO"] = ano
    df["_ARQUIVO"] = nome
    return df, nome


def juntar(parte: str) -> pd.DataFrame:
    dfs = [tabela(parte, a)[0] for a in ANOS]
    dfs = [d for d in dfs if not d.empty]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


@lru_cache(maxsize=1)
def mapa_tickers() -> dict[str, dict]:
    """Ticker (4 letras) -> {cnpj, nome, isin}. O ISIN de cota de FII é BR + 4 letras do ticker + CTF..."""
    g = juntar("geral")
    if g.empty:
        return {}
    c_isin, c_cnpj, c_data = col(g, "isin"), col(g, "cnpj"), col(g, "data")
    c_nome, c_seg = col(g, "nome", False), col(g, "segmento", False)
    g = g.dropna(subset=[c_isin]).sort_values(c_data)
    mapa = {}
    for _, r in g.iterrows():  # o mais recente sobrescreve
        isin = str(r[c_isin]).strip().upper()
        if len(isin) >= 6 and isin.startswith("BR"):
            mapa[isin[2:6]] = {"cnpj": r[c_cnpj], "isin": isin,
                               "nome": r[c_nome] if c_nome else "", "segmento": r[c_seg] if c_seg else ""}
    return mapa


def buscar(ticker: str) -> dict | None:
    return mapa_tickers().get(ticker[:4].upper())


def dados_cvm(ticker: str) -> dict:
    """Últimos 12 informes mensais do fundo, com rastreio de cada campo."""
    cad = buscar(ticker)
    if not cad:
        raise LookupError(f"{ticker}: não encontrei o FII no informe mensal da CVM.")
    c = juntar("complemento")
    if c.empty:
        raise LookupError("Não consegui baixar o informe mensal de FII da CVM.")
    c_cnpj, c_data, c_ver = col(c, "cnpj"), col(c, "data"), col(c, "versao")
    f = c[c[c_cnpj] == cad["cnpj"]].copy()
    if f.empty:
        raise LookupError(f"{ticker}: CNPJ {cad['cnpj']} sem informes mensais.")
    f[c_ver] = num(f[c_ver])
    f = f[f[c_ver] == f.groupby(c_data)[c_ver].transform("max")].sort_values(c_data)
    ultimos = f.tail(12)
    atual = ultimos.iloc[-1]

    def linha(r, campo, descricao, valor):
        coluna = col(c, campo)
        return {"fonte": "CVM", "documento": "Informe mensal de FII", "versao": int(r[c_ver]),
                "arquivo": r["_ARQUIVO"], "url": f"{BASE_URL}/inf_mensal_fii_{r['_ANO']}.zip",
                "data_ref": r[c_data], "periodo": f"mês de {r[c_data][:7]}",
                "conta": coluna, "descricao": descricao, "valor": valor}

    def ultimo(campo, descricao, nota=""):
        coluna = col(c, campo, obrigatorio=False)
        if not coluna:
            return rastro(None, [], f"Coluna de '{campo}' não existe no arquivo.")
        v = num(pd.Series([atual[coluna]])).iloc[0]
        return rastro(v, [comp("+", "Informe mais recente", linha(atual, campo, descricao, float(v)))], nota)

    def soma_12m_pct(campo, descricao, nota):
        """Soma 12 meses de um percentual. A CVM grava como fração (0,0072 = 0,72%);
        se o valor já vier em %, não multiplica. A conversão aparece no rastreio."""
        coluna = col(c, campo, obrigatorio=False)
        if not coluna:
            return rastro(None, [], f"Coluna de '{campo}' não existe no arquivo.")
        brutos = [(r, num(pd.Series([r[coluna]])).iloc[0]) for _, r in ultimos.iterrows()]
        brutos = [(r, v) for r, v in brutos if pd.notna(v)]
        if not brutos:
            return rastro(None, [], "Sem valores nos últimos informes.")
        fracao = max(abs(v) for _, v in brutos) < 0.05
        comps = [comp("+", f"Mês {r[c_data][:7]}",
                      {**linha(r, campo, descricao, float(v * 100 if fracao else v)), "valor_original": float(v),
                       "escala": "FRAÇÃO (×100)" if fracao else "%"}) for r, v in brutos]
        aviso = "" if len(comps) == 12 else f" Atenção: só {len(comps)} meses disponíveis."
        conv = " O arquivo traz o valor em fração; multiplicamos por 100." if fracao else ""
        return rastro(sum(x["valor"] for x in comps), comps, nota + conv + aviso)

    return {
        "cadastro": cad,
        "data_ref": atual[c_data],
        "rastreio": {
            "vp_cota": ultimo("vp_cota", "Valor patrimonial por cota (R$)",
                              "Patrimônio líquido do fundo dividido pelo número de cotas, informado pelo administrador."),
            "pl": ultimo("pl", "Patrimônio líquido (R$)"),
            "cotas": ultimo("cotas", "Quantidade de cotas emitidas"),
            "cotistas": ultimo("cotistas", "Número de cotistas"),
            "dy_patrimonial_12m": soma_12m_pct("dy_mes", "Dividend yield do mês (% do patrimônio)",
                                               "Soma do DY mensal informado à CVM nos últimos 12 informes. "
                                               "É calculado sobre o patrimônio, não sobre o preço de mercado."),
        },
    }
