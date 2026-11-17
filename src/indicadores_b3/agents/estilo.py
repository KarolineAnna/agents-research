"""Padrão de escrita dos relatórios: seções fixas, frases curtas e sem travessão.

- rotulo("Preço justo — base") → "Preço justo (base)"
- texto("O preço — que já subiu — caiu") → "O preço, que já subiu, caiu"
- celula(None) / "—" → "n/d"
- secoes(markdown) → {"destaques": ..., "tese": ...} a partir dos títulos "## ..." do texto do agente
"""
from __future__ import annotations

import re
import unicodedata

TRAVESSAO = "[—–]"
SECOES = {  # título no texto do agente → chave
    "destaques": "destaques", "tese": "tese", "riscos": "riscos", "oportunidades": "oportunidades",
    "leitura final": "leitura", "leitura": "leitura", "opiniao": "leitura", "limitacoes": "limitacoes",
    "o que nao foi possivel verificar": "limitacoes",
}


def rotulo(nome: str) -> str:
    """Nomes de itens: o trecho depois do travessão vira complemento entre parênteses."""
    if not nome:
        return nome
    m = re.match(rf"^(.*?)\s*{TRAVESSAO}\s*(.+)$", nome)
    return f"{m.group(1).strip()} ({m.group(2).strip()})" if m else nome


def texto(s: str | None) -> str:
    """Prosa: travessões viram vírgula (ou dois-pontos no início de explicação); separadores '---' somem."""
    if not s:
        return s or ""
    s = re.sub(r"(?m)^\s*([-*_])\1{2,}\s*$\n?", "", s)            # linhas ---
    s = re.sub(r"(?m)^(\s*)[—–]\s+", r"\1- ", s)                  # travessão usado como marcador de lista
    s = re.sub(rf"\s+{TRAVESSAO}\s+", ", ", s)                     # aposto: "x — y — z" → "x, y, z"
    s = re.sub(rf"(?<=\w){TRAVESSAO}(?=\w)", "-", s)              # intervalos "2025–2026"
    s = re.sub(rf"\s*{TRAVESSAO}\s*", ", ", s)
    s = re.sub(r",\s*,", ",", s)
    return re.sub(r",\s*([.;:)])", r"\1", s)


def celula(v) -> str:
    return "n/d" if v is None or (isinstance(v, str) and re.fullmatch(rf"\s*{TRAVESSAO}?\s*", v)) else str(v)


def _chave(titulo: str, mapa: dict | None = None) -> str | None:
    mapa = mapa or SECOES
    t = "".join(c for c in unicodedata.normalize("NFD", titulo.lower()) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z ]", " ", t).strip()
    t = re.sub(r"\s+", " ", t)
    return mapa.get(t) or next((v for k, v in mapa.items() if t.startswith(k)), None)


def secoes(md: str | None, mapa: dict | None = None) -> dict[str, str]:
    """Divide o texto do agente pelos títulos ## em seções conhecidas (as desconhecidas vão para 'outros').
    mapa: títulos → chaves (padrão: as seções do Research)."""
    out: dict[str, str] = {}
    atual, buf = "intro", []
    for linha in (md or "").splitlines():
        m = re.match(r"^#{1,3}\s+(.*)", linha)
        if m:
            if buf and "".join(buf).strip():
                out[atual] = (out.get(atual, "") + "\n" + "\n".join(buf)).strip()
            atual, buf = _chave(m.group(1), mapa) or "outros", []
        else:
            buf.append(linha)
    if buf and "".join(buf).strip():
        out[atual] = (out.get(atual, "") + "\n" + "\n".join(buf)).strip()
    return {k: texto(v) for k, v in out.items()}
