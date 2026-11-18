"""Coleta dos dados de base.

- Fundamentos: dados abertos da CVM (ITR/DFP consolidados)
- Preço e proventos: yfinance

Este módulo só busca e organiza números "crus". As fórmulas dos indicadores
ficam em indicadores.py.
"""
import time
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from indicadores_b3 import config
from indicadores_b3.data.fontes import url_yahoo

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
CACHE = config.CACHE_DIR
CACHE.mkdir(parents=True, exist_ok=True)
ANO = pd.Timestamp.now().year
ANOS = [ANO - 2, ANO - 1, ANO]
UM_DIA = 86400
DEMOS = {"DRE_con": "DRE", "DVA_con": "DVA", "BPA_con": "BPA", "BPP_con": "BPP",
         "DFC_MI_con": "DFC (método indireto)", "DFC_MD_con": "DFC (método direto)",
         "composicao_capital": "Composição do capital"}


def so_digitos(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True)


# ---------- Download / leitura ----------
def baixar_zip(tipo: str, ano: int) -> Path | None:
    """Baixa o zip da CVM e guarda em disco por 1 dia."""
    arq = CACHE / f"{tipo.lower()}_{ano}.zip"
    # anos já fechados há mais de um ano quase não mudam: o arquivo em cache vale para sempre
    if arq.exists() and (ano <= ANO - 2 or time.time() - arq.stat().st_mtime < UM_DIA):
        return arq
    try:
        r = requests.get(f"{CVM}/{tipo}/DADOS/{tipo.lower()}_cia_aberta_{ano}.zip", timeout=300)
    except requests.RequestException:  # sem internet ou CVM fora do ar: usa o que já estiver em cache
        return arq if arq.exists() else None
    if not r.ok:
        return arq if arq.exists() else None
    arq.write_bytes(r.content)
    return arq


@lru_cache(maxsize=256)
def ler_csv(tipo: str, ano: int, sufixo: str, cnpj: str | None = None) -> pd.DataFrame:
    arq = baixar_zip(tipo, ano)
    if arq is None:
        return pd.DataFrame()
    nome = f"{tipo.lower()}_cia_aberta_{sufixo}_{ano}.csv"
    with zipfile.ZipFile(arq) as zf:
        if nome not in zf.namelist():
            return pd.DataFrame()
        df = pd.read_csv(zf.open(nome), sep=";", encoding="latin-1", dtype=str)
    col_cnpj = next(c for c in df.columns if c.upper().startswith("CNPJ"))
    df["CNPJ"] = so_digitos(df[col_cnpj])
    if cnpj:
        df = df[df["CNPJ"] == cnpj]
    return df


@lru_cache(maxsize=1)
def mapa_tickers() -> dict[str, str]:
    """Ticker -> CNPJ, a partir do FCA (valores mobiliários)."""
    for ano in reversed(ANOS):
        df = ler_csv("FCA", ano, "valor_mobiliario")
        if not df.empty:
            df = df.dropna(subset=["Codigo_Negociacao"])
            return dict(zip(df["Codigo_Negociacao"].str.strip().str.upper(), df["CNPJ"]))
    return {}


def demonstrativo(sufixo: str, cnpj: str) -> pd.DataFrame:
    partes = []
    for tipo in ("ITR", "DFP"):
        for ano in ANOS:
            d = ler_csv(tipo, ano, sufixo, cnpj)
            if not d.empty:
                partes.append(d.assign(FONTE=tipo))
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    df["DEMO"] = DEMOS.get(sufixo, sufixo)
    # só a versão mais recente de cada entrega
    df["VERSAO"] = df["VERSAO"].astype(int)
    df = df[df["VERSAO"] == df.groupby(["FONTE", "DT_REFER"])["VERSAO"].transform("max")]
    if "VL_CONTA" in df:
        mult = df["ESCALA_MOEDA"].str.upper().eq("MIL").map({True: 1000, False: 1})
        df["VL"] = df["VL_CONTA"].astype(float) * mult
    return df


# ---------- Rastreio ----------
# Cada número de base vem acompanhado dos campos exatos usados para chegar nele:
#   {"valor": float, "componentes": [ {sinal, papel, fonte, documento, ...} ], "nota": str}

def linha_cvm(row) -> dict:
    """Uma linha do arquivo da CVM, no formato exibido no site."""
    periodo = (f"{row.DT_INI_EXERC} a {row.DT_FIM_EXERC}"
               if "DT_INI_EXERC" in row and pd.notna(row.DT_INI_EXERC) else f"posição em {row.DT_REFER}")
    return {
        "fonte": "CVM",
        "documento": f"{row.FONTE} · {row.DEMO}",
        "arquivo": f"{row.FONTE.lower()}_cia_aberta_{'_'.join(k for k, v in DEMOS.items() if v == row.DEMO)}"
                   f"_{row.DT_REFER[:4]}.csv",
        "url": f"{CVM}/{row.FONTE}/DADOS/{row.FONTE.lower()}_cia_aberta_{row.DT_REFER[:4]}.zip",
        "versao": int(row.VERSAO),
        "data_ref": row.DT_REFER,
        "periodo": periodo,
        "conta": row.CD_CONTA,
        "descricao": row.DS_CONTA,
        "escala": row.ESCALA_MOEDA,
        "valor_original": float(row.VL_CONTA),
        "valor": float(row.VL),
    }


def comp(sinal: str, papel: str, linha: dict) -> dict:
    return {"sinal": sinal, "papel": papel, **linha}


def rastro(valor, componentes, nota="") -> dict:
    return {"valor": None if valor is None else float(valor), "componentes": componentes, "nota": nota}


def nao_encontrado(conta: str) -> dict:
    return rastro(None, [], f"Conta {conta} não encontrada nos arquivos da CVM.")


# ---------- Contas ----------
def linha_acumulada(df, fonte, ref, ordem, conta):
    d = df[(df.FONTE == fonte) & (df.DT_REFER == ref) & df.ORDEM_EXERC.str.startswith(ordem)
           & (df.CD_CONTA == conta)]
    if d.empty:
        return None
    return d[d.DT_INI_EXERC == d.DT_INI_EXERC.min()].iloc[0]  # acumulado do exercício, não o trimestre


def ttm(df: pd.DataFrame, conta: str) -> dict:
    """Últimos 12 meses de uma conta de resultado (DRE/DVA)."""
    if df.empty:
        return nao_encontrado(conta)
    ref = df.DT_REFER.max()

    if (df[df.DT_REFER == ref].FONTE == "DFP").any():
        r = linha_acumulada(df, "DFP", ref, "ÚLT", conta)
        if r is None:
            return nao_encontrado(conta)
        return rastro(r.VL, [comp("+", "Exercício completo", linha_cvm(r))],
                      "O documento mais recente é o DFP (ano fechado), então os 12 meses são o próprio ano.")

    refs_dfp = df[(df.FONTE == "DFP") & (df.DT_REFER < ref)].DT_REFER
    if refs_dfp.empty:
        return rastro(None, [], "Não há DFP anterior para montar os 12 meses.")
    anual = linha_acumulada(df, "DFP", refs_dfp.max(), "ÚLT", conta)
    atual = linha_acumulada(df, "ITR", ref, "ÚLT", conta)
    anterior = linha_acumulada(df, "ITR", ref, "PEN", conta)
    if anual is None or atual is None or anterior is None:
        return nao_encontrado(conta)

    return rastro(
        anual.VL + atual.VL - anterior.VL,
        [comp("+", "Último ano fechado (DFP)", linha_cvm(anual)),
         comp("+", "Acumulado deste ano (ITR, coluna do exercício atual)", linha_cvm(atual)),
         comp("−", "Mesmo período do ano passado (ITR, coluna do exercício anterior)", linha_cvm(anterior))],
        "12 meses = último ano fechado + acumulado deste ano − mesmo período do ano passado. "
        "Assim o trecho que se repete não é contado duas vezes.",
    )


def linha_saldo(bp: pd.DataFrame, ref: str, conta: str):
    d = bp[(bp.DT_REFER == ref) & bp.ORDEM_EXERC.str.startswith("ÚLT") & (bp.CD_CONTA == conta)]
    return None if d.empty else d.iloc[0]


def soma_saldos(bp: pd.DataFrame, ref: str, partes: list[tuple[str, str, str]], nota: str) -> dict:
    """partes = [(sinal, conta, papel)] — soma/subtrai contas de balanço numa data."""
    total, comps = 0.0, []
    for sinal, conta, papel in partes:
        r = linha_saldo(bp, ref, conta)
        if r is None:
            continue
        total += r.VL if sinal == "+" else -r.VL
        comps.append(comp(sinal, papel, linha_cvm(r)))
    if not comps:
        return rastro(None, [], "Nenhuma das contas foi encontrada.")
    return rastro(total, comps, nota)


# ---------- Dados de base ----------
# Nome e resumo da fonte de cada número cru (o detalhe completo vem do rastreio).
BASE = {
    "preco":         ("Preço da ação", "yfinance — fechamento mais recente"),
    "proventos_12m": ("Proventos por ação (12m)", "yfinance — dividendos/JCP com data-ex nos últimos 12 meses"),
    "receita":       ("Receita líquida (12m)", "CVM · DRE 3.01"),
    "ebit":          ("EBIT (12m)", "CVM · DRE 3.05"),
    "depreciacao":   ("Depreciação e amortização (12m)", "CVM · DVA 7.04.01"),
    "lucro_total":   ("Lucro líquido total (12m)", "CVM · DRE 3.11"),
    "lucro_contr":   ("Lucro líquido dos controladores (12m)", "CVM · DRE 3.11.01"),
    "pl_contr":      ("Patrimônio líquido dos controladores", "CVM · BPP 2.03 − não controladores"),
    "divida_bruta":  ("Dívida bruta", "CVM · BPP 2.01.04 + 2.02.01"),
    "caixa":         ("Caixa e aplicações", "CVM · BPA 1.01.01 + 1.01.02"),
    "acoes":         ("Ações em circulação", "CVM · composição do capital (total − tesouraria)"),
}


def rastro_acoes(cap: pd.DataFrame) -> dict:
    if cap.empty:
        return rastro(None, [], "Arquivo de composição do capital não encontrado.")
    c = cap[cap.DT_REFER == cap.DT_REFER.max()].iloc[0]
    base = {"fonte": "CVM", "documento": f"{c.FONTE} · Composição do capital",
            "arquivo": f"{c.FONTE.lower()}_cia_aberta_composicao_capital_{c.DT_REFER[:4]}.csv",
            "url": f"{CVM}/{c.FONTE}/DADOS/{c.FONTE.lower()}_cia_aberta_{c.DT_REFER[:4]}.zip",
            "versao": int(c.VERSAO), "data_ref": c.DT_REFER, "periodo": f"posição em {c.DT_REFER}",
            "escala": "UNIDADE"}
    total = float(c.QT_ACAO_TOTAL_CAP_INTEGR)
    tesouro = float(c.QT_ACAO_TOTAL_TESOURO or 0)
    return rastro(total - tesouro, [
        comp("+", "Total de ações do capital", {**base, "conta": "QT_ACAO_TOTAL_CAP_INTEGR",
             "descricao": "Quantidade total de ações do capital integralizado", "valor": total}),
        comp("−", "Ações em tesouraria", {**base, "conta": "QT_ACAO_TOTAL_TESOURO",
             "descricao": "Ações recompradas pela própria empresa (não recebem lucro)", "valor": tesouro}),
    ], "Ações em tesouraria são da própria empresa, então ficam fora da conta.")


def acoes_na_escala(acoes: dict, preco: dict, pl: dict) -> tuple[dict, str | None]:
    """O arquivo de composição do capital da CVM não traz a escala e algumas empresas (Vale, Ambev, Itaúsa, Itaú…)
    informam a quantidade em milhares. Se preço × ações der menos de 5% do patrimônio, só pode estar em milhares."""
    a, p, v = acoes.get("valor"), preco.get("valor"), pl.get("valor")
    if a and p and v and v > 0 and p * a < 0.05 * v:
        return ({**acoes, "valor": a * 1000,
                 "nota": "Quantidade informada em milhares no arquivo da CVM (sem coluna de escala): multiplicada por 1.000. " + acoes["nota"]},
                "A CVM informa as ações desta empresa em milhares (o arquivo não traz a escala); a quantidade foi multiplicada por 1.000.")
    return acoes, None


def rastro_yfinance(t, simbolo: str) -> tuple[dict, dict]:
    hist = t.history(period="5d")
    if hist.empty:
        preco = rastro(None, [], "yfinance não retornou cotação.")
    else:
        dia = hist.index[-1].strftime("%Y-%m-%d")
        v = float(hist["Close"].iloc[-1])
        preco = rastro(v, [comp("+", "Fechamento mais recente", {
            "fonte": "yfinance", "documento": "Ticker.history()", "url": url_yahoo(simbolo), "data_ref": dia,
            "periodo": f"pregão de {dia}", "conta": "Close", "descricao": "Preço de fechamento", "valor": v})],
            "Cotação com cerca de 15 minutos de atraso durante o pregão.")

    dvd = t.dividends
    comps = []
    if not dvd.empty:
        dvd.index = dvd.index.tz_localize(None)
        for dt, v in dvd[dvd.index >= pd.Timestamp.now() - pd.DateOffset(years=1)].items():
            d = dt.strftime("%Y-%m-%d")
            comps.append(comp("+", "Provento", {
                "fonte": "yfinance", "documento": "Ticker.dividends", "url": url_yahoo(simbolo), "data_ref": d,
                "periodo": f"data-ex {d}", "conta": "Dividends",
                "descricao": "Dividendo ou JCP por ação", "valor": float(v)}))
    proventos = rastro(sum(c["valor"] for c in comps), comps,
                       "Soma dos proventos com data-ex nos últimos 12 meses. "
                       "O yfinance não diferencia dividendo de JCP." if comps else
                       "Nenhum provento com data-ex nos últimos 12 meses no yfinance.")
    return preco, proventos


def dados_base(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    cnpj = mapa_tickers().get(ticker)
    if not cnpj:
        raise LookupError(f"{ticker} não encontrado no cadastro da CVM (FCA)")

    dre, dva = demonstrativo("DRE_con", cnpj), demonstrativo("DVA_con", cnpj)
    bpa, bpp = demonstrativo("BPA_con", cnpj), demonstrativo("BPP_con", cnpj)
    cap = demonstrativo("composicao_capital", cnpj)
    if dre.empty or bpp.empty:
        raise LookupError(f"{ticker}: sem demonstrativos consolidados na CVM")
    ref = dre.DT_REFER.max()

    from indicadores_b3.agents import financial as fin_banco  # import aqui: research.financial também importa este módulo
    if fin_banco.eh_banco(dre):
        try:
            preco, proventos = rastro_yfinance(yf.Ticker(f"{ticker}.SA"), f"{ticker}.SA")
        except Exception:  # noqa: BLE001 — sem internet
            preco = proventos = rastro(None, [], "yfinance indisponível.")
        if preco["valor"] is None:
            preco = fin_banco.preco(ticker)
        return fin_banco.dados_banco(ticker, cnpj, dre, preco, proventos)

    lucro_total = ttm(dre, "3.11")
    lucro_contr = ttm(dre, "3.11.01")
    if lucro_contr["valor"] is None:
        lucro_contr = {**lucro_total, "nota": "A empresa não separa o lucro dos controladores (3.11.01); "
                                              "usado o lucro total (3.11). " + lucro_total["nota"]}

    da = ttm(dva, "7.04.01")
    if da["valor"] is not None:
        da = {**da, "valor": abs(da["valor"]),
              "nota": da["nota"] + " Na DVA a depreciação vem com sinal negativo; usamos o valor absoluto."}

    nao_contr = bpp[(bpp.DT_REFER == ref) & bpp.ORDEM_EXERC.str.startswith("ÚLT")
                    & bpp.CD_CONTA.str.startswith("2.03.")
                    & bpp.DS_CONTA.str.contains("Não Controladores", case=False, na=False)]
    partes_pl = [("+", "2.03", "Patrimônio líquido consolidado")]
    if not nao_contr.empty:
        partes_pl.append(("−", nao_contr.CD_CONTA.iloc[0], "Parte dos sócios minoritários das controladas"))

    try:
        preco, proventos = rastro_yfinance(yf.Ticker(f"{ticker}.SA"), f"{ticker}.SA")
    except Exception:  # noqa: BLE001 — sem internet: usa o COTAHIST da B3 em cache
        preco = proventos = rastro(None, [], "yfinance indisponível.")
    if preco["valor"] is None:
        preco = fin_banco.preco(ticker)

    rastreio = {
        "preco": preco,
        "proventos_12m": proventos,
        "receita": ttm(dre, "3.01"),
        "ebit": ttm(dre, "3.05"),
        "depreciacao": da,
        "lucro_total": lucro_total,
        "lucro_contr": lucro_contr,
        "pl_contr": soma_saldos(bpp, ref, partes_pl,
                                "O PL consolidado inclui a parte de sócios minoritários das controladas; "
                                "ela é retirada para ficar só o que pertence aos acionistas da empresa."),
        "divida_bruta": soma_saldos(bpp, ref, [
            ("+", "2.01.04", "Empréstimos e financiamentos de curto prazo"),
            ("+", "2.02.01", "Empréstimos e financiamentos de longo prazo")],
            "Inclui debêntures. Não inclui arrendamentos (IFRS 16)."),
        "caixa": soma_saldos(bpa, ref, [
            ("+", "1.01.01", "Caixa e equivalentes de caixa"),
            ("+", "1.01.02", "Aplicações financeiras de curto prazo")], ""),
        "acoes": rastro_acoes(cap),
    }
    rastreio["acoes"], aviso = acoes_na_escala(rastreio["acoes"], preco, rastreio["pl_contr"])
    return {
        "avisos": [aviso] if aviso else [],
        "ticker": ticker,
        "empresa": dre.DENOM_CIA.iloc[0],
        "balanco_ref": ref,
        "valores": {k: r["valor"] for k, r in rastreio.items()},
        "rastreio": rastreio,
    }
