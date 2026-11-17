"""Configuração dos testes.

Testes marcados com ``dados`` usam os arquivos oficiais em data/cache_cvm e são pulados quando eles não existem
(por exemplo, no GitHub Actions). Rode o site uma vez para baixá-los.
"""
import pytest

from indicadores_b3 import config


@pytest.fixture(scope="session")
def tem_cache() -> bool:
    return config.CACHE_DIR.exists() and any(config.CACHE_DIR.iterdir())
