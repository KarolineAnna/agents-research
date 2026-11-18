"""Futuros e curva de juros (DI): páginas públicas da B3.

ATENÇÃO: diferente do COTAHIST e da CVM, a B3 publica estes dados em páginas HTML feitas para
leitura humana. O código lê a tabela da página; se a B3 mudar o layout, esta parte pode quebrar
(a mensagem de erro avisa). Por isso ela é a parte menos robusta do site.

- Ajustes do pregão: preço de ajuste de cada vencimento de DI1, DOL, WDO, IND, WIN...
- Taxas referenciais DI × pré: a curva de juros que o mercado negocia, por prazo.
"""
import io
from functools import lru_cache

import pandas as pd
import requests

BASE = "https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis"
URL_AJUSTES = BASE + "/lum-ajustes-do-pregao-ptBR.asp?dData1={data}"
URL_TAXAS = BASE + "/lum-taxas-referenciais-bmf-ptBR.asp?Data={data}&Data1={data1}&slcTaxa=PRE"
MERCADORIAS = {"DI1": "DI de 1 dia (juros)", "DOL": "Dólar cheio", "WDO": "Mini dólar",
               "IND": "Ibovespa cheio", "WIN": "Mini Ibovespa"}


def _num(s):
    if pd.api.types.is_numeric_dtype(s):  # read_html já converteu (decimal="," thousands=".")
        return s.astype(float)
    return pd.to_numeric(s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                         errors="coerce")


def _html(url: str) -> list[pd.DataFrame]:
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    try:
        return pd.read_html(io.StringIO(r.text), decimal=",", thousands=".")
    except ValueError:
        return []


def _dias_recentes():
    dia = pd.Timestamp.now().normalize()
    for _ in range(10):
        if dia.dayofweek < 5:
            yield dia
        dia -= pd.Timedelta(days=1)


@lru_cache(maxsize=2)
def ajustes(_hora: int = 0) -> dict:
    for dia in _dias_recentes():
        url = URL_AJUSTES.format(data=dia.strftime("%d/%m/%Y"))
        for t in _html(url):
            cols = [str(c).strip() for c in t.columns]
            if any("Vencimento" in c for c in cols) and any("ajuste atual" in c.lower() for c in cols):
                t.columns = cols
                c_merc = next(c for c in cols if "Mercadoria" in c)
                c_venc = next(c for c in cols if "Vencimento" in c)
                c_ant = next(c for c in cols if "ajuste anterior" in c.lower())
                c_atu = next(c for c in cols if "ajuste atual" in c.lower())
                c_val = next((c for c in cols if "valor do ajuste" in c.lower()), None)
                t[c_merc] = t[c_merc].ffill().astype(str).str.split().str[0]
                t = t[t[c_merc].isin(MERCADORIAS)]
                if t.empty:
                    continue
                return {
                    "pregao": dia.strftime("%Y-%m-%d"), "url": url,
                    "itens": [{"mercadoria": r[c_merc], "nome": MERCADORIAS[r[c_merc]], "vencimento": str(r[c_venc]),
                               "ajuste_anterior": float(_num(pd.Series([r[c_ant]])).iloc[0]),
                               "ajuste_atual": float(_num(pd.Series([r[c_atu]])).iloc[0]),
                               "valor_ajuste_contrato": float(_num(pd.Series([r[c_val]])).iloc[0]) if c_val else None}
                              for _, r in t.iterrows()],
                }
    raise LookupError("Não consegui ler a página de ajustes do pregão da B3 (o layout pode ter mudado). "
                      f"Confira manualmente: {URL_AJUSTES.format(data=pd.Timestamp.now().strftime('%d/%m/%Y'))}")


@lru_cache(maxsize=2)
def curva_di(_hora: int = 0) -> dict:
    for dia in _dias_recentes():
        url = URL_TAXAS.format(data=dia.strftime("%d/%m/%Y"), data1=dia.strftime("%Y%m%d"))
        for t in _html(url):
            if t.shape[1] < 2:
                continue
            t = t.copy()
            t.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
            dias = _num(t.iloc[:, 0])
            taxa252 = _num(t.iloc[:, 1])
            ok = dias.notna() & taxa252.notna()
            if ok.sum() < 5:
                continue
            pontos = [{"dias_corridos": int(d), "anos": round(d / 365, 3), "taxa": float(x)}
                      for d, x in zip(dias[ok], taxa252[ok])]
            return {"pregao": dia.strftime("%Y-%m-%d"), "url": url, "pontos": pontos,
                    "nota": "Taxa DI × pré em % a.a., base 252 dias úteis, por prazo em dias corridos."}
    raise LookupError("Não consegui ler a página de taxas referenciais da B3 (o layout pode ter mudado).")


def dados(hora: int) -> dict:
    out = {"mercadorias": MERCADORIAS, "erros": []}
    for nome, f in (("ajustes", ajustes), ("curva", curva_di)):
        try:
            out[nome] = f(hora)
        except Exception as e:
            out[nome] = None
            out["erros"].append(str(e))
    return out
