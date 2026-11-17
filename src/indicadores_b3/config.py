"""Configuração central: onde ficam os dados locais (cache, banco, relatórios, chaves).

Tudo que é gerado na sua máquina fica em ``data/`` na raiz do projeto (fora do Git).
Para mudar o local, defina a variável de ambiente ``INDICADORES_B3_DATA``.
"""
from __future__ import annotations

import os
from pathlib import Path

PACOTE = Path(__file__).resolve().parent
RAIZ = PACOTE.parent.parent  # .../src/indicadores_b3 -> raiz do repositório

DATA_DIR = Path(os.environ.get("INDICADORES_B3_DATA", RAIZ / "data")).expanduser().resolve()
CACHE_DIR = DATA_DIR / "cache_cvm"          # arquivos baixados da CVM, B3 e Tesouro
DB_CARTEIRAS = DATA_DIR / "carteiras.db"    # carteiras salvas (SQLite)
RELATORIOS_DIR = DATA_DIR / "research_out"  # relatórios dos agentes
CONFIG_IA = DATA_DIR / "config_ia.json"     # chaves das IAs gratuitas (nunca vai para o Git)
STATIC_DIR = PACOTE / "web" / "static"

HOST = os.environ.get("INDICADORES_B3_HOST", "127.0.0.1")
PORTA = int(os.environ.get("INDICADORES_B3_PORT", "8080"))


def garantir_pastas() -> None:
    for p in (DATA_DIR, CACHE_DIR, RELATORIOS_DIR):
        p.mkdir(parents=True, exist_ok=True)
