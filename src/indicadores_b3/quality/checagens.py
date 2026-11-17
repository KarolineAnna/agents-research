"""Verificações de qualidade dos dados, usadas pelo painel "Saúde dos dados" e pelos testes (pytest).

Três grupos:
  - fontes:       os arquivos em cache existem, estão atualizados e as fontes online respondem?
  - layout:       as colunas que o site usa continuam existindo nos arquivos oficiais?
  - consistencia: os números fecham? (Ativo = Passivo, Lucro bruto = Receita + Custo,
                  preço do Tesouro calculado = publicado, VNA igual entre títulos IPCA+ …)

Cada verificação devolve um dict:
  {"id", "grupo", "nome", "status": ok|aviso|erro|pulado, "detalhe", "fonte", "url", "atualizado"}
Nenhuma verificação baixa arquivos grandes: elas leem o que já está em data/cache_cvm/.
"""
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from indicadores_b3 import config

CACHE = config.CACHE_DIR
ANO = date.today().year
CVM_DADOS = "https://dados.cvm.gov.br/dataset"


def _r(id_, grupo, nome, status, detalhe, fonte="", url="", atualizado=None, itens=None):
    return {"id": id_, "grupo": grupo, "nome": nome, "status": status, "detalhe": detalhe,
            "fonte": fonte, "url": url, "atualizado": atualizado, "itens": itens or []}


def _br(x: float, casas: int = 1) -> str:
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _idade_dias(p: Path) -> float:
    return (time.time() - p.stat().st_mtime) / 86400


def _zip_csv(arq: Path, nome: str, **kw) -> pd.DataFrame:
    with zipfile.ZipFile(arq) as z:
        if nome not in z.namelist():
            raise KeyError(f"{nome} não está dentro de {arq.name}")
        return pd.read_csv(z.open(nome), sep=";", encoding="latin-1", dtype=str, **kw)


def _ultimo(prefixo: str) -> Path | None:
    """Arquivo mais recente em cache com esse prefixo (ex.: 'itr_' → itr_2026.zip)."""
    arqs = sorted(CACHE.glob(f"{prefixo}*"))
    return arqs[-1] if arqs else None


# ======================= FONTES (cache) =======================
CACHES = [
    # prefixo, nome, fonte, url, idade máxima em dias para "ok"
    ("itr_", "ITR (balanços trimestrais)", "CVM", f"{CVM_DADOS}/cia_aberta-doc-itr", 7),
    ("dfp_", "DFP (balanços anuais)", "CVM", f"{CVM_DADOS}/cia_aberta-doc-dfp", 7),
    ("fca_", "FCA (cadastro e tickers)", "CVM", f"{CVM_DADOS}/cia_aberta-doc-fca", 30),
    ("fii_inf_mensal_", "Informe mensal de FII", "CVM", f"{CVM_DADOS}/fii-doc-inf_mensal", 7),
    ("ipe_", "IPE (fatos relevantes)", "CVM", f"{CVM_DADOS}/cia_aberta-doc-ipe", 2),
    ("tesouro_precotaxa", "Preços e taxas do Tesouro Direto", "Tesouro Nacional",
     "https://www.tesourotransparente.gov.br/ckan/dataset/taxas-dos-titulos-ofertados-pelo-tesouro-direto", 2),
    ("cotahist_", "COTAHIST (cotações e opções)", "B3",
     "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/series-historicas/", 4),
]


def fontes_cache() -> list[dict]:
    out = []
    for pref, nome, fonte, url, max_dias in CACHES:
        arq = _ultimo(pref)
        if not arq:
            out.append(_r(f"cache:{pref}", "fontes", nome, "pulado",
                          "Ainda não baixado. Ele é baixado na primeira vez que uma aba precisar dele.", fonte, url))
            continue
        idade = _idade_dias(arq)
        st = "ok" if idade <= max_dias else "aviso"
        det = f"{arq.name} · baixado há {_br(idade)} dia(s)" if idade >= 1 else f"{arq.name} · baixado há {_br(idade * 24, 0)} hora(s)"
        if st == "aviso":
            det += f" (mais de {max_dias}). Ele é renovado quando a aba que o usa for aberta."
        out.append(_r(f"cache:{pref}", "fontes", nome, st, det, fonte, url, _mtime(arq)))
    return out


# ======================= FONTES (online) =======================
def _online_bcb():
    from indicadores_b3.data.fontes import cdi_atual
    c = cdi_atual()
    d = c["componentes"][0]["data_ref"]
    atraso = (pd.Timestamp.now().normalize() - pd.Timestamp(d)).days
    st = "ok" if atraso <= 5 else "aviso"
    return _r("online:bcb", "fontes", "Banco Central (SGS): CDI", st,
              f"Último CDI publicado: {_br(c['valor'], 2)}% a.a. em {pd.Timestamp(d):%d/%m/%Y} ({atraso} dia(s) atrás)",
              "Banco Central", c["componentes"][0]["url"], d)


def _online_tesouro_venda():
    from indicadores_b3.data import tesouro
    v = tesouro.a_venda()
    if v["ok"]:
        return _r("online:td", "fontes", "Tesouro Transparente: títulos à venda (vendas recentes)", "ok",
                  f"{len(v['codigos'])} títulos com venda nos {tesouro.JANELA_VENDAS} dias até {pd.Timestamp(v['ate']):%d/%m/%Y}",
                  "Tesouro Nacional", v["url"], v["ate"])
    return _r("online:td", "fontes", "Tesouro Transparente: títulos à venda (vendas recentes)", "aviso",
              f"Sem resposta ({v.get('erro')}). A renda fixa mostra todos os títulos do arquivo oficial.",
              "Tesouro Nacional", v["url"])


def _online_yf():
    from indicadores_b3.data.fontes import historico_yf, url_yahoo
    s = historico_yf("^BVSP", "1mo")
    if s.empty:
        return _r("online:yf", "fontes", "yfinance: Ibovespa", "erro", "O yfinance não retornou dados.",
                  "yfinance", url_yahoo("^BVSP"))
    d = s.index[-1]
    atraso = (pd.Timestamp.now().normalize() - d).days
    return _r("online:yf", "fontes", "yfinance: Ibovespa", "ok" if atraso <= 5 else "aviso",
              f"Último fechamento: {_br(s.iloc[-1], 0)} pontos em {d:%d/%m/%Y}",
              "yfinance", url_yahoo("^BVSP"), d.strftime("%Y-%m-%d"))


def _online_futuros():
    from indicadores_b3.data import futuros
    f = futuros.curva_di() if hasattr(futuros, "curva_di") else None
    if not f or not f.get("pontos"):
        return _r("online:b3fut", "fontes", "B3: curva DI futuro", "aviso",
                  "A página de ajustes da B3 não retornou a curva (é uma página HTML, pode mudar).", "B3")
    return _r("online:b3fut", "fontes", "B3: curva DI futuro", "ok",
              f"{len(f['pontos'])} vencimentos · pregão {f.get('pregao')}", "B3", f.get("url", ""))


def fontes_online() -> list[dict]:
    testes = [("online:bcb", "Banco Central (SGS): CDI", _online_bcb),
              ("online:td", "Site do Tesouro Direto: títulos à venda", _online_tesouro_venda),
              ("online:yf", "yfinance: Ibovespa", _online_yf),
              ("online:b3fut", "B3: curva DI futuro", _online_futuros)]

    def rodar(t):
        id_, nome, fn = t
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            return _r(id_, "fontes", nome, "erro", f"Falhou: {type(e).__name__}: {str(e)[:200]}")

    with ThreadPoolExecutor(4) as ex:
        return list(ex.map(rodar, testes))


# ======================= LAYOUT =======================
def _layout_cvm(tipo: str, sufixo: str, obrig: list[str]) -> dict:
    arq = _ultimo(f"{tipo}_")
    nome = f"Colunas do {tipo.upper()} · {sufixo}"
    if not arq:
        return _r(f"layout:{tipo}:{sufixo}", "layout", nome, "pulado", "Arquivo ainda não baixado.", "CVM")
    ano = arq.stem.split("_")[-1]
    interno = f"{tipo}_cia_aberta_{sufixo}_{ano}.csv" if sufixo else f"{tipo}_cia_aberta_{ano}.csv"
    df = _zip_csv(arq, interno, nrows=5)
    faltam = [c for c in obrig if c not in df.columns]
    if faltam:
        return _r(f"layout:{tipo}:{sufixo}", "layout", nome, "erro",
                  f"Faltam colunas: {faltam}. Disponíveis: {list(df.columns)}", "CVM", "", _mtime(arq))
    return _r(f"layout:{tipo}:{sufixo}", "layout", nome, "ok", f"{len(obrig)} colunas usadas pelo site presentes ({interno})",
              "CVM", "", _mtime(arq))


def _layout_tolerante(id_, nome, arq, interno, modulo) -> dict:
    """FII e IPE procuram colunas por uma lista de nomes alternativos (COLUNAS do módulo)."""
    if not arq:
        return _r(id_, "layout", nome, "pulado", "Arquivo ainda não baixado.", "CVM")
    df = _zip_csv(arq, interno, nrows=5)
    faltam = [campo for campo, alternativas in modulo.COLUNAS.items() if not any(a in df.columns for a in alternativas)]
    if faltam:
        return _r(id_, "layout", nome, "aviso",
                  f"Campos sem coluna correspondente: {faltam}. Ajuste COLUNAS em {modulo.__name__}.py",
                  "CVM", "", _mtime(arq))
    return _r(id_, "layout", nome, "ok", f"Todos os {len(modulo.COLUNAS)} campos encontrados", "CVM", "", _mtime(arq))


def layout() -> list[dict]:
    out = []
    cols_dem = ["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "ESCALA_MOEDA", "ORDEM_EXERC", "DT_FIM_EXERC",
                "CD_CONTA", "DS_CONTA", "VL_CONTA"]
    for tipo in ("itr", "dfp"):
        for suf in ("DRE_con", "BPA_con", "BPP_con", "DFC_MI_con"):
            out.append(_layout_cvm(tipo, suf, cols_dem))
    out.append(_layout_cvm("fca", "valor_mobiliario", ["CNPJ_Companhia", "Nome_Empresarial", "Valor_Mobiliario",
                                                       "Codigo_Negociacao", "Mercado", "Data_Fim_Negociacao"]))
    from indicadores_b3.data import comunicados, fii
    arq = _ultimo("fii_inf_mensal_")
    if arq:
        ano = arq.stem.split("_")[-1]
        with zipfile.ZipFile(arq) as z:
            nomes = z.namelist()
        # COLUNAS do fii.py mistura campos do "geral" e do "complemento": checa contra a união
        dfs = [_zip_csv(arq, n, nrows=3) for n in nomes if "geral" in n or "complemento" in n]
        todas = set().union(*[set(d.columns) for d in dfs])
        faltam = [c for c, alt in fii.COLUNAS.items() if not any(a in todas for a in alt)]
        out.append(_r("layout:fii", "layout", "Colunas do informe mensal de FII", "aviso" if faltam else "ok",
                      f"Campos sem coluna: {faltam}. Ajuste COLUNAS em fii.py" if faltam
                      else f"Todos os {len(fii.COLUNAS)} campos encontrados ({ano})", "CVM", "", _mtime(arq)))
    else:
        out.append(_r("layout:fii", "layout", "Colunas do informe mensal de FII", "pulado", "Arquivo ainda não baixado.", "CVM"))
    arq = _ultimo("ipe_")
    out.append(_layout_tolerante("layout:ipe", "Colunas do IPE (comunicados)", arq,
                                 f"ipe_cia_aberta_{arq.stem.split('_')[-1]}.csv" if arq else "", comunicados))
    t = CACHE / "tesouro_precotaxa.csv"
    if t.exists():
        df = pd.read_csv(t, sep=";", encoding="latin-1", dtype=str, nrows=3)
        obrig = ["Tipo Titulo", "Data Vencimento", "Data Base", "Taxa Compra Manha", "PU Compra Manha"]
        faltam = [c for c in obrig if c not in df.columns]
        out.append(_r("layout:tesouro", "layout", "Colunas do arquivo do Tesouro", "erro" if faltam else "ok",
                      f"Faltam: {faltam}" if faltam else "Colunas de taxa e preço presentes", "Tesouro Nacional", "", _mtime(t)))
    a = _ultimo("cotahist_")
    if a:
        with zipfile.ZipFile(a) as z:
            linhas = z.read(z.namelist()[0]).decode("latin-1").splitlines()
        tamanhos = {len(l) for l in linhas if l}
        ok = tamanhos == {245} and linhas[0].startswith("00") and linhas[-1].startswith("99")
        out.append(_r("layout:cotahist", "layout", "Layout do COTAHIST (B3)", "ok" if ok else "erro",
                      f"{len(linhas)} linhas de 245 posições, com cabeçalho e rodapé" if ok
                      else f"Tamanhos de linha encontrados: {sorted(tamanhos)[:5]}", "B3", "", _mtime(a)))
    return out


# ======================= CONSISTÊNCIA =======================
def _demo_ultimo(tipo: str, sufixo: str) -> tuple[pd.DataFrame, Path] | tuple[None, None]:
    arq = _ultimo(f"{tipo}_")
    if not arq:
        return None, None
    ano = arq.stem.split("_")[-1]
    df = _zip_csv(arq, f"{tipo}_cia_aberta_{sufixo}_{ano}.csv",
                  usecols=["CNPJ_CIA", "DENOM_CIA", "DT_REFER", "VERSAO", "ORDEM_EXERC", "CD_CONTA", "VL_CONTA"])
    df = df[df["ORDEM_EXERC"] == "ÚLTIMO"].copy()
    df["VL_CONTA"] = pd.to_numeric(df["VL_CONTA"], errors="coerce")
    df["VERSAO"] = pd.to_numeric(df["VERSAO"], errors="coerce")
    # só a versão mais recente de cada entrega
    df = df[df["VERSAO"] == df.groupby(["CNPJ_CIA", "DT_REFER"])["VERSAO"].transform("max")]
    return df, arq


def _pivo(df: pd.DataFrame, contas: list[str]) -> pd.DataFrame:
    p = df[df["CD_CONTA"].isin(contas)].pivot_table(index=["CNPJ_CIA", "DENOM_CIA", "DT_REFER"], columns="CD_CONTA",
                                                    values="VL_CONTA", aggfunc="first")
    return p.dropna(subset=[c for c in contas if c in p.columns])


def balanco_fecha(tipo="itr", tolerancia=0.005) -> dict:
    nome = f"Balanço fecha: Ativo total = Passivo total ({tipo.upper()})"
    bpa, arq = _demo_ultimo(tipo, "BPA_con")
    if bpa is None:
        return _r(f"cons:balanco:{tipo}", "consistencia", nome, "pulado", "Arquivo ainda não baixado.", "CVM")
    bpp, _ = _demo_ultimo(tipo, "BPP_con")
    a = bpa[bpa["CD_CONTA"] == "1"].set_index(["CNPJ_CIA", "DENOM_CIA", "DT_REFER"])["VL_CONTA"]
    p = bpp[bpp["CD_CONTA"] == "2"].set_index(["CNPJ_CIA", "DENOM_CIA", "DT_REFER"])["VL_CONTA"]
    j = pd.concat([a.rename("ativo"), p.rename("passivo")], axis=1).dropna()
    j = j[j["ativo"] != 0]
    j["dif"] = (j["ativo"] - j["passivo"]).abs() / j["ativo"].abs()
    ruins = j[j["dif"] > tolerancia].sort_values("dif", ascending=False)
    itens = [{"empresa": i[1], "data": i[2], "detalhe": f"ativo {r.ativo:,.0f} × passivo {r.passivo:,.0f} ({r.dif:.1%})"}
             for i, r in ruins.head(15).iterrows()]
    st = "ok" if ruins.empty else ("aviso" if len(ruins) / len(j) < 0.02 else "erro")
    return _r(f"cons:balanco:{tipo}", "consistencia", nome, st,
              f"{len(j) - len(ruins)} de {len(j)} balanços fecham (tolerância {_br(tolerancia * 100)}%)."
              + (f" {len(ruins)} não fecham: erro de entrega da empresa; o site mostra o número como veio." if len(ruins) else ""),
              "CVM", "", _mtime(arq), itens)


def dre_fecha(tipo="itr", tolerancia=0.01) -> dict:
    nome = f"DRE fecha: Lucro bruto = Receita + Custo ({tipo.upper()})"
    dre, arq = _demo_ultimo(tipo, "DRE_con")
    if dre is None:
        return _r(f"cons:dre:{tipo}", "consistencia", nome, "pulado", "Arquivo ainda não baixado.", "CVM")
    p = _pivo(dre, ["3.01", "3.02", "3.03"])
    p = p[p["3.01"].abs() > 0]
    p["dif"] = (p["3.03"] - (p["3.01"] + p["3.02"])).abs() / p["3.01"].abs()
    ruins = p[p["dif"] > tolerancia].sort_values("dif", ascending=False)
    itens = [{"empresa": i[1], "data": i[2], "detalhe": f"3.01 + 3.02 = {r['3.01'] + r['3.02']:,.0f} × 3.03 = {r['3.03']:,.0f}"}
             for i, r in ruins.head(15).iterrows()]
    st = "ok" if ruins.empty else ("aviso" if len(ruins) / max(len(p), 1) < 0.05 else "erro")
    return _r(f"cons:dre:{tipo}", "consistencia", nome, st,
              f"{len(p) - len(ruins)} de {len(p)} DREs fecham. Bancos e seguradoras usam outro plano de contas e ficam de fora.",
              "CVM", "", _mtime(arq), itens)


def tesouro_precos(tolerancia_pct=0.01) -> list[dict]:
    t = CACHE / "tesouro_precotaxa.csv"
    if not t.exists():
        return [_r("cons:td:pu", "consistencia", "Tesouro: preço calculado = publicado", "pulado", "Arquivo ainda não baixado.",
                   "Tesouro Nacional")]
    from indicadores_b3.analytics import rendafixa
    from indicadores_b3.data import tesouro
    df = tesouro.tabela()
    ult = df[df["base"] == df["base"].max()]
    base = ult["base"].iloc[0].date()
    liq = rendafixa.proximo_util(base + pd.Timedelta(days=1).to_pytimedelta())  # liquidação: dia útil seguinte
    out = []
    # 1) prefixados: PU calculado pela convenção (252 d.u., feriados) deve bater com o publicado
    linhas, ruins = [], []
    for _, r in ult[ult["sigla"].isin(["PRE", "PREJS"])].iterrows():
        fl, _ = rendafixa.fluxos(r["sigla"], r["vencimento"].date(), liq)
        pu = rendafixa.analisar(fl, float(r["Taxa Compra Manha"]), liq)["pu"]
        pub = float(r["PU Compra Manha"])
        if pub <= 0:
            continue
        d = (pu / pub - 1) * 100
        linhas.append(d)
        if abs(d) > tolerancia_pct:
            ruins.append({"empresa": r["codigo"], "data": str(base), "detalhe": f"calculado {pu:.2f} × publicado {pub:.2f} ({d:+.3f}%)"})
    st = "ok" if not ruins else "aviso"
    out.append(_r("cons:td:pu", "consistencia", "Tesouro prefixado: preço calculado = publicado", st,
                  f"{len(linhas) - len(ruins)} de {len(linhas)} títulos com diferença até {_br(tolerancia_pct, 2)}% "
                  f"(maior: {_br(max(map(abs, linhas)), 3)}%)" if linhas else "Nenhum prefixado com preço na data base.",
                  "Tesouro Nacional", tesouro.PAGINA, str(base), ruins))
    # 2) IPCA+: todos os títulos usam o mesmo VNA → o VNA implícito deve ser praticamente igual
    vnas = []
    for _, r in ult[ult["sigla"].isin(["IPCA", "IPCAJS"])].iterrows():
        fl, _ = rendafixa.fluxos(r["sigla"], r["vencimento"].date(), liq)
        pu = rendafixa.analisar(fl, float(r["Taxa Compra Manha"]), liq)["pu"]
        pub = float(r["PU Compra Manha"])
        if pub > 0:
            vnas.append((r["codigo"], pub / (pu / 100)))
    if vnas:
        v = np.array([x for _, x in vnas])
        disp = (v.max() - v.min()) / np.median(v) * 100
        st = "ok" if disp < 0.1 else "aviso"
        out.append(_r("cons:td:vna", "consistencia", "Tesouro IPCA+: VNA implícito igual entre títulos", st,
                      f"{len(v)} títulos · VNA mediano R$ {np.median(v):,.2f} · dispersão {disp:.3f}%".replace(",", "X").replace(".", ",").replace("X", "."),
                      "Tesouro Nacional", tesouro.PAGINA, str(base),
                      [{"empresa": c, "data": str(base), "detalhe": f"VNA R$ {x:,.2f}"} for c, x in vnas] if st != "ok" else []))
    # 3) data base recente
    atraso = np.busday_count(base, date.today())
    out.append(_r("cons:td:data", "consistencia", "Tesouro: arquivo com data base recente", "ok" if atraso <= 3 else "aviso",
                  f"Data base {base:%d/%m/%Y} ({atraso} dia(s) útil(eis) atrás)", "Tesouro Nacional", tesouro.PAGINA, str(base)))
    return out


def cotahist_acoes() -> dict:
    a = _ultimo("cotahist_")
    if not a:
        return _r("cons:b3:lista", "consistencia", "B3: ações negociadas no último pregão", "pulado", "Arquivo ainda não baixado.", "B3")
    from indicadores_b3.data import opcoes
    df = opcoes.ler(a)
    from indicadores_b3.data import lista
    v = df[(df.TPMERC == "010") & df.CODNEG.str.fullmatch(lista.TICKER_ACAO) & df.ESPECI.str.match(r"(ON|PN|UNT)")]
    sem_preco = v[~(v.PREULT > 0)]
    st = "ok" if len(v) >= 250 and sem_preco.empty else "aviso"
    return _r("cons:b3:lista", "consistencia", "B3: ações negociadas no último pregão", st,
              f"{len(v)} ações e units com negócio no pregão de {pd.Timestamp(a.stem.split('_')[-1]):%d/%m/%Y}"
              + (f"; {len(sem_preco)} sem preço" if len(sem_preco) else "") + (" (esperado: 250 ou mais)" if len(v) < 250 else ""),
              "B3", "", _mtime(a))


def consistencia() -> list[dict]:
    out = []
    for fn in (lambda: balanco_fecha("itr"), lambda: balanco_fecha("dfp"), lambda: dre_fecha("itr"),
               lambda: dre_fecha("dfp"), cotahist_acoes):
        try:
            out.append(fn())
        except Exception as e:  # noqa: BLE001
            out.append(_r("cons:erro", "consistencia", "Verificação", "erro", f"{type(e).__name__}: {e}"))
    try:
        out.extend(tesouro_precos())
    except Exception as e:  # noqa: BLE001
        out.append(_r("cons:td", "consistencia", "Tesouro", "erro", f"{type(e).__name__}: {e}"))
    return out


# ======================= tudo =======================
def rodar(online: bool = False) -> dict:
    inicio = time.time()
    res = fontes_cache() + (fontes_online() if online else []) + layout() + consistencia()
    resumo = {s: sum(1 for r in res if r["status"] == s) for s in ("ok", "aviso", "erro", "pulado")}
    return {"quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "segundos": round(time.time() - inicio, 1),
            "online": online, "resumo": resumo, "verificacoes": res}


if __name__ == "__main__":
    import json
    import sys
    r = rodar(online="--online" in sys.argv)
    for v in r["verificacoes"]:
        print(f"[{v['status']:>6}] {v['nome']}: {v['detalhe']}")
    print(json.dumps(r["resumo"]))
