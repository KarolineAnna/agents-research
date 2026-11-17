"""Tabelas dos relatórios de RI viram trechos próprios, com o rótulo de cada linha ligado aos números certos.

Problema: o texto corrido extraído de um PDF perde a estrutura das tabelas, e um trecho de 900 caracteres pode
separar o número do rótulo ou do trimestre. Aqui cada linha de tabela vira:
    "Qualidade do crédito | Índice de inadimplência acima de 90 dias | 3T26: 1,9% | 2T26: 2,0% | 3T25: 2,2%"
A seção (título mais próximo acima) e o cabeçalho (3T26, 2T26...) vão junto, então a busca por "inadimplência"
traz o número já com o período, e o validador confere o número contra a página.

Como reconhece uma tabela (vale para PDFs com ou sem linhas de grade):
- linha de dados: um rótulo seguido de 2 ou mais valores numéricos no fim da linha (1,9% · 9.120 · (35) · R$ 11,2 · n.d.);
- cabeçalho: a linha anterior às linhas de dados com 2 ou mais períodos (3T26, 2T26, 9M26, 2025, 1S26...) ou nomes de colunas.
O texto vem do pdfplumber (ordem de leitura por linha); sem ele, do texto já extraído da página.
"""
from __future__ import annotations

import io
import re

VALOR = re.compile(r"^(?:[-−–]|\(?[-−]?(?:R\$)?\s?\d[\d.]*(?:,\d+)?\s?(?:%|p\.?p\.?|x|bi|mi|mil)?\)?|n\.?\s?[dmaD]\.?|n/[da]|-+)$", re.I)
PERIODO = re.compile(r"^(?:[1-4][TQ]\d{2}|[1-4][TQ]\d{4}|\d{1,2}M\d{2}|[12]S\d{2}|(?:19|20)\d{2}|[1-4]º?T(?:\d{2}|\d{4})|var\.?|Δ%?|%)$", re.I)
ROW_GRUPO = 6  # linhas de tabela por trecho


def _tokens(linha: str) -> list[str]:
    # junta "R$ 11,2" e "11,2 %" num token só
    linha = re.sub(r"R\$\s+(?=\d)", "R$", linha)
    linha = re.sub(r"(?<=\d)\s+(%|bi\b|mi\b|mil\b|p\.p\.)", r"\1", linha)
    return linha.split()


def _dados(linha: str) -> tuple[str, list[str]] | None:
    """(rótulo, valores) se a linha termina em 2+ valores numéricos e tem rótulo; senão None."""
    tk = _tokens(linha)
    vals = []
    while tk and VALOR.match(tk[-1]) and not (tk[-1].endswith(")") and not tk[-1].startswith("(")):
        vals.insert(0, tk.pop())  # "90)" fecha um parêntese do rótulo, como em "(NPL 90)": não é valor
    rotulo = " ".join(tk).strip(" :.-–")
    if len(vals) < 2 or not rotulo or not re.search(r"[A-Za-zÀ-ú]{3}", rotulo):
        return None
    if not any(re.search(r"\d", v) for v in vals):
        return None
    return rotulo, vals


def _cabecalho(linha: str) -> list[str] | None:
    tk = _tokens(linha)
    per = [t for t in tk if PERIODO.match(t)]
    return per if len(per) >= 2 else None


def _titulo(linha: str) -> bool:
    s = linha.strip()
    return 3 <= len(s) <= 90 and not s.endswith((".", ";", ",")) and not _dados(s) and bool(re.search(r"[A-Za-zÀ-ú]{3}", s))


def linhas_de_tabela(texto: str) -> list[str]:
    """Cada linha de dados vira 'seção | rótulo | período: valor | ...' (sem período conhecido: 'col 1: valor')."""
    out, secao, cab = [], "", None
    linhas = [x.strip() for x in texto.splitlines() if x.strip()]
    for ln in linhas:
        c = _cabecalho(ln)
        d = None if c and all(PERIODO.match(v) for v in (_dados(ln) or ("", ["x"]))[1]) else _dados(ln)
        if d is None:
            if c:
                cab = c
            elif _titulo(ln):
                secao, cab = ln, None  # título novo: começa outra tabela
            continue
        rotulo, vals = d
        if cab and len(vals) > len(cab):  # números a mais que colunas: os primeiros fazem parte do rótulo
            rotulo, vals = " ".join([rotulo, *vals[:len(vals) - len(cab)]]), vals[len(vals) - len(cab):]
        nomes = cab[-len(vals):] if cab and len(cab) >= len(vals) else [f"col {k + 1}" for k in range(len(vals))]
        partes = [secao] if secao else []
        bonito = [re.sub(r"(?<=\d)(bi|mi|mil)$", r" \1", re.sub(r"R\$(?=\d)", "R$ ", v)) for v in vals]
        out.append(" | ".join(partes + [rotulo] + [f"{n}: {v}" for n, v in zip(nomes, bonito, strict=True)]))
    return out


def trechos_de_tabela(texto: str, grupo: int = ROW_GRUPO) -> list[str]:
    ls = linhas_de_tabela(texto)
    return ["\n".join(ls[i:i + grupo]) for i in range(0, len(ls), grupo)]


def textos_por_pagina(conteudo: bytes) -> list[str] | None:
    """Texto de cada página pelo pdfplumber (melhor ordem de leitura para tabelas). None se não estiver instalado."""
    try:
        import pdfplumber
    except ImportError:
        return None
    out = []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pg in pdf.pages:
            try:
                out.append(pg.extract_text() or "")
            except Exception:  # noqa: BLE001 — página com problema não derruba o documento
                out.append("")
    return out
