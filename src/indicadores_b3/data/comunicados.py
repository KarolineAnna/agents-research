"""Fatos relevantes e comunicados das companhias: dados abertos da CVM (IPE).

Fonte: https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe
Arquivo: ipe_cia_aberta_{ano}.zip (atualizado pela CVM; aqui o cache é de 6 horas)
Cada linha é um documento entregue, com link para o PDF no sistema da CVM.

FIIs não estão neste conjunto; para eles o site mostra o link do Fundos.NET (B3).
"""
import time
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from indicadores_b3 import config
from indicadores_b3.data import fii, fundamentos

BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS"
PAGINA = "https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe"
CACHE = config.CACHE_DIR
CACHE.mkdir(parents=True, exist_ok=True)
SEIS_HORAS = 6 * 3600
PADRAO = ["Fato Relevante", "Comunicado ao Mercado", "Aviso aos Acionistas"]

COLUNAS = {
    "cnpj": ["CNPJ_Companhia", "CNPJ_CIA"],
    "nome": ["Nome_Companhia", "DENOM_CIA"],
    "entrega": ["Data_Entrega"],
    "referencia": ["Data_Referencia"],
    "categoria": ["Categoria"],
    "tipo": ["Tipo"],
    "especie": ["Especie"],
    "assunto": ["Assunto"],
    "link": ["Link_Download"],
    "protocolo": ["Protocolo_Entrega"],
    "versao": ["Versao"],
}


def col(df, campo, obrigatorio=True):
    baixo = {c.lower(): c for c in df.columns}
    for n in COLUNAS[campo]:
        if n.lower() in baixo:
            return baixo[n.lower()]
    if obrigatorio:
        raise KeyError(f"Coluna '{campo}' não encontrada no IPE da CVM (tentei {COLUNAS[campo]}). "
                       f"Colunas disponíveis: {list(df.columns)}. Ajuste COLUNAS em comunicados.py.")
    return None


def baixar(ano: int) -> Path | None:
    arq = CACHE / f"ipe_{ano}.zip"
    if arq.exists() and time.time() - arq.stat().st_mtime < SEIS_HORAS:
        return arq
    try:
        r = requests.get(f"{BASE_URL}/ipe_cia_aberta_{ano}.zip", timeout=300)
    except requests.RequestException:  # sem internet: usa o arquivo em cache, mesmo antigo
        return arq if arq.exists() else None
    if not r.ok:
        return arq if arq.exists() else None
    arq.write_bytes(r.content)
    return arq


@lru_cache(maxsize=4)
def _tabela(ano: int, bloco: int) -> pd.DataFrame:  # bloco = janela de 6h, para renovar o cache
    arq = baixar(ano)
    if arq is None:
        return pd.DataFrame()
    with zipfile.ZipFile(arq) as zf:
        nome = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(zf.open(nome), sep=";", encoding="latin-1", dtype=str)
    df["_ARQUIVO"], df["_ANO"] = nome, ano
    df["_CNPJ"] = df[col(df, "cnpj")].str.replace(r"\D", "", regex=True)
    return df


def tabela() -> pd.DataFrame:
    bloco = int(time.time() // SEIS_HORAS)
    ano = pd.Timestamp.now().year
    dfs = [d for d in (_tabela(ano - 1, bloco), _tabela(ano, bloco)) if not d.empty]
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def listar(tickers: list[str], categorias: list[str] | None = None, limite: int = 60) -> dict:
    categorias = categorias or PADRAO
    df = tabela()
    if df.empty:
        raise LookupError("Não consegui baixar os documentos (IPE) da CVM.")
    c_cat = col(df, "categoria")
    todas_categorias = sorted(df[c_cat].dropna().unique().tolist())

    itens, avisos = [], []
    for t in dict.fromkeys(x.strip().upper() for x in tickers if x.strip()):
        cnpj = fundamentos.mapa_tickers().get(t)
        if not cnpj:
            f = fii.buscar(t)
            if f:
                digitos = "".join(ch for ch in f["cnpj"] if ch.isdigit())
                avisos.append({"ticker": t, "texto": "FIIs não estão no conjunto de dados da CVM usado aqui. "
                               "Os comunicados do fundo ficam no Fundos.NET da B3.",
                               "url": f"https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo={digitos}"})
            else:
                avisos.append({"ticker": t, "texto": "Não é uma companhia aberta no cadastro da CVM "
                               "(ETF, cripto, Tesouro etc. não publicam fatos relevantes aqui).", "url": None})
            continue
        d = df[(df["_CNPJ"] == cnpj) & df[c_cat].isin(categorias)]
        for _, r in d.iterrows():
            g = lambda campo, r=r: (r[c] if (c := col(df, campo, False)) and pd.notna(r[c]) else "")
            itens.append({
                "ticker": t, "empresa": g("nome"), "data_entrega": g("entrega"), "data_referencia": g("referencia"),
                "categoria": g("categoria"), "tipo": g("tipo"), "especie": g("especie"), "assunto": g("assunto"),
                "link": g("link"), "protocolo": g("protocolo"), "versao": g("versao"),
                "arquivo": r["_ARQUIVO"], "fonte_url": f"{BASE_URL}/ipe_cia_aberta_{r['_ANO']}.zip",
            })

    itens.sort(key=lambda x: x["data_entrega"], reverse=True)
    return {"itens": itens[:limite], "total": len(itens), "avisos": avisos,
            "categorias": todas_categorias, "selecionadas": categorias, "pagina_fonte": PAGINA}
