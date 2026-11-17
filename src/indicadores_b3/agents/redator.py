"""Redator: transforma os dossiês em texto corrido, sem criar números.

Dois modos:
  - "modelo" (padrão): texto montado por regras fixas a partir dos dossiês. Determinístico, sempre funciona.
  - "ia" (opcional): um modelo local pelo Ollama (gratuito, roda no seu computador, sem internet e sem chave).
    Ative instalando o Ollama (https://ollama.com), baixando um modelo (ex.: `ollama pull qwen2.5:7b`)
    e, se quiser outro, definindo a variável de ambiente OLLAMA_MODEL.

Em qualquer modo o texto passa pelo VALIDADOR: cada número escrito precisa existir nos dossiês
(com a mesma arredondagem). Se a IA escrever um número que não está lá, o texto dela é descartado
e o sistema usa o texto do modo "modelo", registrando os números rejeitados.
"""
from __future__ import annotations

import json
import os
import re

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


# ---------------- formatação ----------------
def br(v, casas=1):
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt(v, unidade=""):
    """Formata como o relatório mostra: R$ grandes em bilhões, % com 1 casa, múltiplos com 2."""
    if v is None:
        return "—"
    u = unidade or ""
    if u == "R$":
        if abs(v) >= 1e9:
            return f"R$ {br(v / 1e9, 1)} bi"
        if abs(v) >= 1e6:
            return f"R$ {br(v / 1e6, 1)} mi"
        return f"R$ {br(v, 2)}"
    if u.startswith("%"):
        return f"{br(v, 1)}%" + (" a.a." if "a.a." in u else "")
    if u == "x":
        return f"{br(v, 2)}x"
    if u == "p.p.":
        return f"{br(v, 2)} p.p."
    if abs(v) >= 1e5 and float(v).is_integer():
        return br(v, 0)
    return br(v, 2)


# ---------------- validador ----------------
NUM = re.compile(r"(?<![\w\[])[-−+]?\d{1,3}(?:\.\d{3})*(?:,\d+)?(?![\w\]])|(?<![\w\[])[-−+]?\d+(?:[.,]\d+)?(?![\w\]])")


def _paraf(s: str) -> float | None:
    s = s.replace("−", "-").replace("+", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _cat(unidade: str | None) -> str:
    u = unidade or ""
    return "R$" if u.startswith("R$") else "%" if u.startswith("%") or u == "p.p." else "x" if u == "x" else "n"


def numeros_permitidos(dossies: list[dict]) -> dict[str, list[float]]:
    """Números dos dossiês por categoria de unidade (R$, %, x, n), nas escalas em que aparecem (bi, mi, unidade)."""
    vals = {"R$": [], "%": [], "x": [], "n": []}

    def add(v, u):
        if isinstance(v, int | float):
            c = _cat(u)
            vals[c].extend([v, abs(v)] + ([v / 1e9, abs(v) / 1e9, v / 1e6, abs(v) / 1e6] if c in ("R$", "n") else []))

    for d in dossies:
        for x in d.get("itens", []):
            add(x.get("valor"), x.get("unidade"))
            for c in x.get("componentes") or []:
                add(c.get("valor"), "R$")
        ex = d.get("extras", {})
        for linha in ex.get("comparacao", []):
            for v in linha["valores"].values():
                add(v, linha.get("unidade"))
            add(linha.get("mediana_pares"), linha.get("unidade"))
        s = ex.get("sensibilidade")
        if s:
            for v in s["ke"] + s["roe"] + [s["g"]]:
                add(v, "%")
            for v in (p for l in s["precos"] for p in l):
                add(v, "R$")
    return vals


def _bate(n: float, casas: int, permitidos: list[float]) -> bool:
    tol = 0.5 * 10 ** (-casas) + 1e-9
    return any(abs(n - p) <= tol for p in permitidos)


def _categoria_no_texto(texto: str, ini: int, fim: int) -> str | None:
    """Unidade escrita junto do número: 'R$ 22,65' → R$; '22,2%' ou '1,2 p.p.' → %; '1,96x' → x."""
    antes, depois = texto[max(0, ini - 4):ini], texto[fim:fim + 6]
    if re.search(r"R\$\s*$", antes):
        return "R$"
    if re.match(r"\s*(?:%|p\.p\.|pontos? percentua)", depois):
        return "%"
    if re.match(r"x\b|\s*vezes", depois):
        return "x"
    return None


def validar(texto: str, dossies: list[dict]) -> list[str]:
    """Devolve os números do texto que NÃO existem nos dossiês, conferindo também a unidade (R$ com R$, % com %…).
    Ignora anos, ids de citação, datas, tickers e contagens pequenas (3 cenários)."""
    perm = numeros_permitidos(dossies)
    todos = [v for l in perm.values() for v in l]
    texto = re.sub(r"\[(?:[A-Z0-9]+\.)?[FMICVTE]\d+(?:\s*[,;]\s*(?:[A-Z0-9]+\.)?[FMICVTE]\d+)*\]", " ", texto)  # citações, ex.: [F1], [BBDC4.F19]
    texto = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b", " ", texto)  # datas
    texto = re.sub(r"\b[A-Z]{4}\d{1,2}\b", " ", texto)  # tickers
    # números de normas e documentos (Resolução CMN 4.966, Lei 6.404, art. 202) não são dados
    texto = re.sub(r"(?i)\b(?:resolu[çc][ãa]o|circular|lei|instru[çc][ãa]o|of[íi]cio|art(?:igo)?\.?|CMN|BCB|CVM|IFRS|CPC)"
                   r"(?:\s+(?:CMN|BCB|CVM|n[ºo°]\.?))*\s*n?[ºo°]?\s*\d[\d./-]*", " ", texto)
    ruins = []
    for m in NUM.finditer(texto):
        s = m.group(0)
        n = _paraf(s)
        if n is None:
            continue
        cat = _categoria_no_texto(texto, m.start(), m.end())
        inteiro = float(n).is_integer() and "," not in s
        if cat is None and inteiro and (abs(n) <= 12 or 1990 <= n <= 2100):  # contagens e anos
            continue
        casas = len(s.split(",")[1]) if "," in s else 0
        if not _bate(n, casas, perm[cat] if cat else todos):
            ruins.append(s + ("%" if cat == "%" else "x" if cat == "x" else "") if cat != "R$" else "R$ " + s)
    return ruins


# ---------------- texto por regras ----------------
def _it(d, nome):
    return next((x for x in d.get("itens", []) if x["nome"] == nome or x["nome"].startswith(nome)), None)


def _c(x):
    return f"{fmt(x['valor'], x.get('unidade'))} [{x['id']}]" if x else None


def texto_modelo(fin: dict | None, mkt: dict | None, inv: dict | None) -> dict:
    """Relatório por regras fixas, nas mesmas seções do agente: destaques, tese, riscos, oportunidades, leitura, limitações.
    Só usa números dos dossiês, com a citação [id] ao lado."""
    from indicadores_b3.agents.estilo import texto as sem_travessao
    sec: dict[str, str] = {}
    destaques = []
    por_nome = {x["nome"]: x for x in (inv or {}).get("itens", [])}
    if fin:
        for metrica in ("ROE", "P/VP", "P/L", "Custo do crédito", "Margem líq.", "Dív.Líq/EBITDA"):
            x = _it(fin, metrica)
            if not x or x["valor"] is None:
                continue
            med = por_nome.get(f"{metrica} — mediana dos pares")
            if med and med["valor"] is not None:
                rel = "acima" if x["valor"] > med["valor"] else "abaixo"
                destaques.append(f"{metrica} de {_c(x)}, {rel} da mediana dos pares ({_c(med)}).")
            elif len(destaques) < 3:
                destaques.append(f"{metrica} de {_c(x)}.")
        lucro = _it(fin, "Lucro líquido dos controladores (12m)") or _it(fin, "Lucro líq.")
        if lucro and lucro["valor"] is not None:
            destaques.insert(0, f"Lucro dos controladores em 12 meses de {_c(lucro)} (dados da CVM até {fin['extras'].get('ref')}).")
    pp, pot = por_nome.get("Preço justo ponderado pelos cenários"), por_nome.get("Potencial ponderado")
    if pp and pot:
        destaques.append(f"Preço justo ponderado pelos cenários de {_c(pp)}, potencial de {_c(pot)} sobre o preço atual.")
    sec["destaques"] = "\n".join(f"- {d}" for d in destaques[:5])

    tese = (inv or {}).get("extras", {}).get("tese", {})
    ds = [d for d in (fin, mkt, inv) if d]
    # só leituras cujos números estão nos dossiês (diferenças calculadas, como ROE − Ke, ficam de fora)
    partes = [l["texto"] for d in (fin, inv) if d for l in d.get("leituras", [])
              if l.get("tipo") != "fato" and not validar(l["texto"], ds)][:3]
    ke, ke_i = por_nome.get("Ke (CAPM)"), por_nome.get("Ke implícito no preço")
    if ke and ke_i:
        partes.append(f"O preço de hoje equivale a um custo de capital de {_c(ke_i)}, contra {_c(ke)} pelo CAPM com as premissas declaradas.")
    sec["tese"] = " ".join(partes) or "Dados insuficientes para uma tese."
    sec["riscos"] = "\n".join(f"- {r}" for r in tese.get("riscos", [])[:4])
    sec["oportunidades"] = "\n".join(f"- {o}" for o in tese.get("oportunidades", [])[:3]) or "- Nenhuma identificada pelas regras."
    if tese.get("opiniao"):
        sec["leitura"] = "Opinião: " + tese["opiniao"][0].lower() + tese["opiniao"][1:]
    aus = [a["nome"] for d in (fin, mkt, inv) if d for a in d.get("ausentes", [])]
    sec["limitacoes"] = "\n".join(f"- {a}: não disponível nas fontes usadas." for a in list(dict.fromkeys(aus))[:3])
    return {k: sem_travessao(v) for k, v in sec.items() if v}


# ---------------- IA local (opcional) ----------------
def ollama_disponivel() -> str | None:
    """Devolve o nome do modelo se o Ollama estiver rodando e tiver o modelo; senão None."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        nomes = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None
    if OLLAMA_MODEL in nomes:
        return OLLAMA_MODEL
    base = OLLAMA_MODEL.split(":")[0]
    return next((n for n in nomes if n.split(":")[0] == base), None)


def _compacto(d: dict) -> list[dict]:
    return [{"id": x["id"], "tipo": x["tipo"], "nome": x["nome"], "valor": fmt(x["valor"], x.get("unidade"))}
            for x in d.get("itens", []) if x.get("valor") is not None]


PROMPT = """Você é redator de um relatório de análise de ações em português do Brasil.
Escreva um resumo executivo de 2 a 3 parágrafos sobre {assunto}.
REGRAS OBRIGATÓRIAS:
1. Use SOMENTE números que aparecem na lista abaixo, escritos exatamente como estão (mesma formatação).
2. Depois de cada número, coloque o id entre colchetes, ex.: 22,2% [F12].
3. Não invente números, datas, fatos, notícias nem projeções. Se algo não está na lista, não mencione.
4. Diferencie: "fato" (dado de fonte), "estimativa" (resultado de modelo), "premissa" (escolha declarada).
5. Não recomende compra ou venda.

ITENS:
{itens}

LEITURAS JÁ FEITAS (pode reescrever, sem acrescentar números):
{leituras}
"""


def redigir(fin: dict | None, mkt: dict | None, inv: dict | None, usar_ia: bool = True) -> dict:
    dossies = [d for d in (fin, mkt, inv) if d]
    secoes = texto_modelo(fin, mkt, inv)
    out = {"modo": "modelo", "modelo": None, "secoes": secoes, "resumo": None, "rejeitados": [], "aviso": None}
    out["rejeitados_modelo"] = validar(" ".join(secoes.values()), dossies)  # autoteste do próprio template
    if not usar_ia:
        return out
    modelo = ollama_disponivel()
    if not modelo:
        out["aviso"] = "Ollama não encontrado em " + OLLAMA_URL + ": texto gerado pelo modo 'modelo' (regras fixas)."
        return out
    itens = [i for d in dossies for i in _compacto(d)]
    leituras = [l["texto"] for d in dossies for l in d.get("leituras", [])]
    prompt = PROMPT.format(assunto=(fin or inv or {}).get("assunto", "a empresa"),
                           itens=json.dumps(itens, ensure_ascii=False), leituras="\n".join("- " + l for l in leituras))
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json={"model": modelo, "prompt": prompt, "stream": False,
                                                              "options": {"temperature": 0.1}}, timeout=240)
        texto = r.json().get("response", "").strip()
    except Exception as e:
        out["aviso"] = f"Falha ao chamar o Ollama ({type(e).__name__}): usado o modo 'modelo'."
        return out
    ruins = validar(texto, dossies)
    if ruins or not texto:
        out["rejeitados"] = ruins
        out["aviso"] = (f"O texto da IA ({modelo}) foi descartado: trouxe {len(ruins)} número(s) que não estão nos dossiês "
                        f"({', '.join(ruins[:6])}). Usado o modo 'modelo'.")
        return out
    out.update({"modo": "ia", "modelo": modelo, "resumo": texto})
    return out
