"""Cliente único para modelos de linguagem GRATUITOS, todos pela mesma interface (formato OpenAI de chat + ferramentas).

Provedores (na ordem configurada; se um falhar ou estourar o limite, passa para o próximo):
  gemini  Google AI Studio — nível gratuito sem cartão, com limites por minuto/dia. Chave em https://aistudio.google.com/apikey
          Atenção: no nível gratuito o Google pode usar os dados enviados para melhorar os modelos.
  groq    Groq — nível gratuito sem cartão, com limites. Chave em https://console.groq.com/keys
  ollama  Modelo no seu computador (https://ollama.com). Sem limite e sem internet, porém mais fraco.

As chaves ficam no arquivo config_ia.json, na pasta do projeto (só no seu computador), ou nas variáveis de
ambiente GEMINI_API_KEY / GROQ_API_KEY. Nenhum plano pago é usado: se o limite gratuito acabar, o provedor
devolve erro 429 e o sistema tenta o próximo.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

from indicadores_b3 import config

CONFIG = config.CONFIG_IA
PROVEDORES = {
    "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai/", "env": "GEMINI_API_KEY", "nome": "Gemini (Google AI Studio, gratuito)"},
    "groq": {"base": "https://api.groq.com/openai/v1/", "env": "GROQ_API_KEY", "nome": "Groq (gratuito)"},
    "ollama": {"base": os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/v1/", "env": None, "nome": "Ollama (local)"},
}
ORDEM_PADRAO = ["gemini", "groq", "ollama"]


log = logging.getLogger(__name__)

TENTATIVAS = 3            # por provedor, antes de passar ao próximo
TENTATIVAS_503 = 2        # servidor sobrecarregado: insistir muito só faz esperar; melhor passar ao próximo modelo
TIMEOUT_CHAT = {"ollama": 240}  # Ollama roda no PC e é lento por natureza
TIMEOUT_PADRAO = 60       # Gemini e Groq respondem em segundos; parado há 1 minuto = travado, passa ao próximo
ESPERA_MAX_S = 20         # teto do backoff / Retry-After
TRANSITORIOS = {408, 409, 425, 429, 500, 502, 503, 504}


class ErroProvedor(Exception):
    """Falha de um provedor depois das novas tentativas. ``transitorio`` indica limite/instabilidade."""

    def __init__(self, msg: str, transitorio: bool = True):
        super().__init__(msg)
        self.transitorio = transitorio


def ler_config() -> dict:
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    c.setdefault("ordem", ORDEM_PADRAO)
    c.setdefault("chaves", {})
    c.setdefault("modelos", {})
    return c


def salvar_config(ordem=None, chaves: dict | None = None, modelos: dict | None = None) -> dict:
    c = ler_config()
    if ordem:
        c["ordem"] = [p for p in ordem if p in PROVEDORES]
    for k, v in (chaves or {}).items():
        if k in PROVEDORES and v is not None:
            if v.strip():
                c["chaves"][k] = v.strip()
            else:
                c["chaves"].pop(k, None)
    for k, v in (modelos or {}).items():
        if k in PROVEDORES:
            if v:
                c["modelos"][k] = v.strip()
            else:
                c["modelos"].pop(k, None)
    CONFIG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return c


def _chave(p: str, c: dict) -> str | None:
    env = PROVEDORES[p]["env"]
    return (os.environ.get(env) if env else None) or c["chaves"].get(p)


def status() -> dict:
    """Para a tela: quais provedores estão prontos (sem expor a chave)."""
    c = ler_config()
    out = []
    for p in c["ordem"]:
        k = _chave(p, c)
        out.append({"id": p, "nome": PROVEDORES[p]["nome"], "chave": (k[:4] + "…" + k[-4:]) if k and len(k) > 10 else None,
                    "precisa_chave": PROVEDORES[p]["env"] is not None, "modelo": c["modelos"].get(p)})
    return {"ordem": c["ordem"], "provedores": out}


def _reservas_gemini(ids: list[str]) -> list[str]:
    """Modelos Gemini em ordem de preferência: flash mais novo, flash-lite mais novo, flash da versão anterior.
    Quando o principal está sobrecarregado (erro 503), o agente passa para o seguinte."""
    ver = lambda i: [float(x) for x in re.findall(r"\d+(?:\.\d+)?", i)[:1]]  # noqa: E731
    flash = sorted((i for i in ids if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash", i)), key=ver, reverse=True)
    lite = sorted((i for i in ids if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash-lite", i)), key=ver, reverse=True)
    ordem = flash[:1] + lite[:1] + flash[1:2]
    return ordem or ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


def _escolher_modelo(p: str, ids: list[str]) -> str | None:
    ids = [i.removeprefix("models/") for i in ids]
    if p == "gemini":
        return _reservas_gemini(ids)[0]
    if p == "groq":
        for pref in (r"openai/gpt-oss-120b", r"llama-3\.3-70b", r"qwen", r"llama-4", r"gpt-oss"):
            m = next((i for i in ids if re.search(pref, i)), None)
            if m:
                return m
        return None
    return next((i for i in ids if re.search(r"qwen|llama|mistral|gemma", i)), ids[0] if ids else None)


def modelos_de(p: str, c: dict | None = None) -> list[str]:
    """Modelo principal do provedor e, no Gemini, as reservas para sobrecarga."""
    c = c or ler_config()
    if c["modelos"].get(p):
        return [c["modelos"][p]]
    try:
        r = requests.get(PROVEDORES[p]["base"] + "models", headers=_cab(p, c), timeout=8)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError):
        return _reservas_gemini([]) if p == "gemini" else []
    if p == "gemini":
        return _reservas_gemini([i.removeprefix("models/") for i in ids])
    m = _escolher_modelo(p, ids)
    return [m] if m else []


def _cab(p, c):
    k = _chave(p, c)
    return {"Authorization": f"Bearer {k}"} if k else {}


def disponiveis() -> list[tuple[str, str]]:
    """[(provedor, modelo)] na ordem configurada, só os que têm chave (ou Ollama rodando)."""
    c = ler_config()
    out = []
    for p in c["ordem"]:
        if PROVEDORES[p]["env"] and not _chave(p, c):
            continue
        out.extend((p, m) for m in modelos_de(p, c))
    return out


def _espera(tentativa: int, r: requests.Response | None) -> float:
    if r is not None and r.headers.get("Retry-After", "").replace(".", "", 1).isdigit():
        return min(float(r.headers["Retry-After"]), ESPERA_MAX_S)
    if r is not None and r.status_code == 503:  # servidor sobrecarregado: espera mais antes de insistir
        return min(3 * 2 ** tentativa, ESPERA_MAX_S)  # 3 s, 6 s, 12 s
    return min(2 ** tentativa, ESPERA_MAX_S)  # 1 s, 2 s, 4 s...


def conversar(p: str, modelo: str, mensagens: list[dict], ferramentas: list[dict], timeout: float | None = None,
              tentativas: int = TENTATIVAS, dormir=time.sleep) -> dict:
    """Uma chamada de chat, com novas tentativas para erros transitórios (limite 429, 5xx, rede).
    Tempo esgotado e servidor sobrecarregado (503) desistem cedo, para o agente passar logo ao próximo provedor.
    Devolve a mensagem do assistente (pode trazer tool_calls) e, em ``_uso``, os tokens informados pelo provedor."""
    timeout = timeout or TIMEOUT_CHAT.get(p, TIMEOUT_PADRAO)
    n503 = 0
    c = ler_config()
    corpo = {"model": modelo, "messages": mensagens, "temperature": 0.1}
    if ferramentas:
        corpo["tools"] = ferramentas
        corpo["tool_choice"] = "auto"
    ultimo = "sem resposta"
    for t in range(tentativas):
        r = None
        try:
            r = requests.post(PROVEDORES[p]["base"] + "chat/completions", headers=_cab(p, c), json=corpo, timeout=timeout)
        except requests.Timeout as e:
            # esperar de novo o mesmo tempo raramente resolve: o agente troca de provedor
            raise ErroProvedor(f"{p} ({modelo}): não respondeu em {timeout:.0f} s") from e
        except requests.RequestException as e:
            ultimo = f"{p}: sem conexão ({type(e).__name__})"
        else:
            if r.status_code < 400:
                try:
                    j = r.json()
                    msg = j["choices"][0]["message"]
                except (ValueError, KeyError, IndexError) as e:
                    raise ErroProvedor(f"{p}: resposta em formato inesperado", transitorio=False) from e
                msg["_uso"] = j.get("usage") or {}
                return msg
            if r.status_code not in TRANSITORIOS:
                # 400/401/403/404: chave errada, modelo inexistente, pedido inválido — repetir não adianta
                raise ErroProvedor(f"{p}: erro {r.status_code} — {r.text[:300]}", transitorio=False)
            ultimo = (f"{p} ({modelo}): limite gratuito atingido (429)" if r.status_code == 429
                      else f"{p} ({modelo}): servidor sobrecarregado (503) — o problema é do lado do Google/provedor, não do site"
                      if r.status_code == 503 else f"{p} ({modelo}): erro temporário {r.status_code}")
            if r.status_code == 503:
                n503 += 1
                if n503 >= TENTATIVAS_503:
                    raise ErroProvedor(ultimo + f" depois de {t + 1} tentativas.")
        if t < tentativas - 1:
            s = _espera(t, r)
            log.warning("%s; nova tentativa em %.0f s", ultimo, s)
            dormir(s)
    raise ErroProvedor(ultimo + f" depois de {tentativas} tentativas.")


# ---------------- embeddings (para a busca semântica do RAG) ----------------
EMBED_PREF = {"gemini": [r"gemini-embedding", r"text-embedding"], "ollama": [r"nomic-embed", r"mxbai-embed", r"bge", r"embed"]}


def modelo_embedding(p: str, c: dict | None = None) -> str | None:
    """Modelo de embeddings disponível no provedor (Groq não oferece embeddings)."""
    c = c or ler_config()
    if p not in EMBED_PREF:
        return None
    if c["modelos"].get(f"{p}_embed"):
        return c["modelos"][f"{p}_embed"]
    try:
        r = requests.get(PROVEDORES[p]["base"] + "models", headers=_cab(p, c), timeout=8)
        r.raise_for_status()
        ids = [m["id"].removeprefix("models/") for m in r.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError):
        return "gemini-embedding-001" if p == "gemini" and _chave(p, c) else None
    for pref in EMBED_PREF[p]:
        m = sorted(i for i in ids if re.search(pref, i))
        if m:
            return m[-1]
    return None


def provedor_embedding() -> tuple[str, str] | None:
    """(provedor, modelo) para embeddings, na ordem configurada; None = só busca por palavras (BM25)."""
    c = ler_config()
    for p in c["ordem"]:
        if p not in EMBED_PREF or (PROVEDORES[p]["env"] and not _chave(p, c)):
            continue
        m = modelo_embedding(p, c)
        if m:
            return p, m
    return None


def embeddings(p: str, modelo: str, textos: list[str], lote: int = 64, dormir=time.sleep) -> list[list[float]]:
    """Vetores dos textos, em lotes, com novas tentativas para limite gratuito (429)."""
    c = ler_config()
    out: list[list[float]] = []
    for i in range(0, len(textos), lote):
        corpo = {"model": modelo, "input": textos[i:i + lote]}
        for t in range(TENTATIVAS):
            try:
                r = requests.post(PROVEDORES[p]["base"] + "embeddings", headers=_cab(p, c), json=corpo, timeout=120)
            except requests.RequestException as e:
                if t == TENTATIVAS - 1:
                    raise ErroProvedor(f"{p}: sem conexão para embeddings ({type(e).__name__})") from e
                dormir(_espera(t, None))
                continue
            if r.status_code < 400:
                dados = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
                out.extend(d["embedding"] for d in dados)
                break
            if r.status_code not in TRANSITORIOS or t == TENTATIVAS - 1:
                raise ErroProvedor(f"{p}: erro {r.status_code} nos embeddings — {r.text[:200]}", transitorio=r.status_code in TRANSITORIOS)
            dormir(_espera(t, r))
    return out
