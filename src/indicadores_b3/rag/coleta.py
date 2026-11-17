"""Coleta: baixa os PDFs dos comunicados (IPE da CVM), extrai o texto por página e grava no armazém.

Os metadados vêm do arquivo aberto do IPE (data/comunicados.py); cada linha traz o link do documento no
sistema da CVM (rad.cvm.gov.br). O PDF fica em cache em data/cache_docs/<protocolo>.pdf.
PDFs escaneados (imagem, sem texto) são registrados com status "sem_texto" — o OCR fica fora do escopo.
"""
from __future__ import annotations

import hashlib
import io
import logging
import time
import zipfile

import requests

from indicadores_b3 import config
from indicadores_b3.data import comunicados
from indicadores_b3.rag import armazem

log = logging.getLogger(__name__)
PASTA = config.DATA_DIR / "cache_docs"
CABECALHO = {"User-Agent": "Mozilla/5.0 (indicadores-b3; estudo pessoal)"}


def extrair_paginas(conteudo: bytes) -> list[str]:
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(conteudo))
    out = []
    for pg in leitor.pages:
        try:
            out.append(armazem.limpar_pagina(pg.extract_text() or ""))
        except Exception:  # noqa: BLE001 — página corrompida não derruba o documento
            out.append("")
    return out


def extrair(conteudo: bytes) -> tuple[list[str], list[list[str]]]:
    """Texto de cada página (pypdf) e, para cada página, os trechos das tabelas (linha a linha, com cabeçalho e seção)."""
    from indicadores_b3.rag import tabelas
    paginas = extrair_paginas(conteudo)
    try:
        brutos = tabelas.textos_por_pagina(conteudo) or paginas
    except Exception:  # noqa: BLE001 — o pdfplumber falhar não impede o texto corrido
        brutos = paginas
    return paginas, [tabelas.trechos_de_tabela(t) for t in brutos]


def _pdf_de(conteudo: bytes) -> bytes | None:
    """O link da CVM às vezes entrega o PDF direto, às vezes um ZIP com o PDF dentro."""
    if conteudo[:4] == b"%PDF":
        return conteudo
    if conteudo[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            nome = next((n for n in z.namelist() if n.lower().endswith(".pdf")), None)
            return z.read(nome) if nome else None
    return None


def baixar_pdf(protocolo: str, url: str, timeout: int = 60) -> bytes:
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = PASTA / f"{protocolo}.pdf"
    if arq.exists() and arq.stat().st_size > 0:
        return arq.read_bytes()
    r = requests.get(url, headers=CABECALHO, timeout=timeout)
    r.raise_for_status()
    pdf = _pdf_de(r.content)
    if pdf is None:
        raise ValueError("o link não devolveu um PDF (a CVM pode estar fora do ar ou o documento ser de outro formato)")
    arq.write_bytes(pdf)
    return pdf


def indexar(tickers: list[str], categorias: list[str] | None = None, por_empresa: int = 10, pausa: float = 0.5,
            embeddings: bool = True) -> dict:
    """Baixa e indexa os documentos mais recentes de cada empresa. Pula os que já estão no armazém."""
    lista = comunicados.listar(tickers, categorias, limite=por_empresa * max(1, len(tickers)) * 3)
    ja = {d["protocolo"] for d in armazem.documentos()}
    contagem: dict[str, int] = {}
    resultado = {"novos": [], "pulados": 0, "falhas": [], "avisos": [a["texto"] for a in lista.get("avisos", [])]}
    for it in lista["itens"]:
        t = it["ticker"]
        if contagem.get(t, 0) >= por_empresa:
            continue
        contagem[t] = contagem.get(t, 0) + 1
        prot = str(it.get("protocolo") or "").strip()
        if not prot or not it.get("link"):
            continue
        if prot in ja:
            resultado["pulados"] += 1
            continue
        try:
            pdf = baixar_pdf(prot, it["link"])
            paginas, tabs = extrair(pdf)
            com_texto = sum(1 for p in paginas if len(p) > 40)
            meta = {**{k: it.get(k) for k in ("ticker", "empresa", "data_entrega", "data_referencia", "categoria", "tipo",
                                              "especie", "assunto")},
                    "protocolo": prot, "url": it["link"], "sha256": hashlib.sha256(pdf).hexdigest(),
                    "status": "ok" if com_texto else "sem_texto"}
            doc_id = armazem.salvar_documento(meta, paginas, tabs)
            resultado["novos"].append({"id": doc_id, "ticker": t, "assunto": it.get("assunto"), "paginas": len(paginas),
                                       "status": meta["status"], "linhas_de_tabela": sum(len(x) for x in tabs)})
        except Exception as e:  # noqa: BLE001 — um documento com problema não interrompe os outros
            log.warning("falha no documento %s: %s", prot, e)
            resultado["falhas"].append({"protocolo": prot, "ticker": t, "assunto": it.get("assunto"), "erro": str(e)[:200]})
        time.sleep(pausa)  # educação com o servidor da CVM
    if embeddings:
        resultado["embeddings"] = armazem.garantir_embeddings()
    resultado["estatisticas"] = armazem.estatisticas()
    return resultado


# ---------------- relatórios de RI (resultados) ----------------
# A empresa entrega à CVM o mesmo material do site de RI: relatório gerencial (MD&A), press-release e a
# apresentação de resultados. É a cópia oficial, com data e protocolo, e tem o que os demonstrativos padronizados
# não têm: inadimplência de 90 dias, índice de Basileia, lucro recorrente, guidance.
CATEGORIAS_RI = ["Dados Econômico-Financeiros", "Comunicado ao Mercado"]
TIPOS_RI = ("análise gerencial", "analise gerencial", "press-release", "press release", "release de resultado",
            "apresentações a analistas", "apresentacoes a analistas")


def eh_ri(item: dict) -> bool:
    t = f"{item.get('tipo') or ''} {item.get('assunto') or ''}".lower()
    return any(k in t for k in TIPOS_RI)


def indexar_ri(ticker: str, quantidade: int = 2, embeddings: bool = True) -> dict:
    """Baixa e indexa os relatórios de resultados mais recentes da empresa (relatório gerencial e press-release primeiro)."""
    lista = comunicados.listar([ticker], CATEGORIAS_RI, limite=400)
    itens = [i for i in lista["itens"] if eh_ri(i)]
    prioridade = lambda i: (0 if "gerencial" in (i.get("tipo") or "").lower() or "release" in (i.get("tipo") or "").lower() else 1)  # noqa: E731
    # por data (mais recente primeiro); no mesmo dia, o relatório gerencial/press-release antes da apresentação
    itens.sort(key=lambda i: (i["data_entrega"], -prioridade(i)), reverse=True)
    vistos_dia, escolhidos = set(), []
    for i in itens:
        if "inglês" in (i.get("assunto") or "").lower() or "english" in (i.get("assunto") or "").lower():
            continue
        if i["data_entrega"] in vistos_dia:
            continue  # um documento por data de divulgação
        vistos_dia.add(i["data_entrega"])
        escolhidos.append(i)
        if len(escolhidos) >= quantidade:
            break
    ja = {d["protocolo"]: d for d in armazem.documentos(ticker)}
    out = {"documentos": [], "falhas": []}
    for it in escolhidos:
        prot = str(it.get("protocolo") or "").strip()
        if prot in ja:
            out["documentos"].append(ja[prot])
            continue
        try:
            pdf = baixar_pdf(prot, it["link"], timeout=120)
            paginas, tabs = extrair(pdf)
            meta = {**{k: it.get(k) for k in ("ticker", "empresa", "data_entrega", "data_referencia", "categoria", "tipo",
                                              "especie", "assunto")},
                    "protocolo": prot, "url": it["link"], "sha256": hashlib.sha256(pdf).hexdigest(),
                    "status": "ok" if sum(1 for p in paginas if len(p) > 40) else "sem_texto"}
            doc_id = armazem.salvar_documento(meta, paginas, tabs)
            out["documentos"].append({**meta, "id": doc_id, "paginas": len(paginas)})
        except Exception as e:  # noqa: BLE001
            out["falhas"].append({"protocolo": prot, "tipo": it.get("tipo"), "erro": str(e)[:200]})
    if embeddings and out["documentos"]:
        out["embeddings"] = armazem.garantir_embeddings()
    return out

