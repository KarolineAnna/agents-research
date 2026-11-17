"""Testes com os dados reais em cache_cvm/ (os mesmos do painel "Saúde dos dados").

Rode depois de usar o site, para os arquivos estarem baixados:  pytest -v
Verificações cujo arquivo ainda não foi baixado são puladas.
"""
import pytest

from indicadores_b3.quality import checagens


def _ids(lista):
    return [v["id"] for v in lista]


def _avaliar(v, exigir_ok=False):
    if v["status"] == "pulado":
        pytest.skip(v["detalhe"])
    msg = f"{v['nome']}: {v['detalhe']}\n" + "\n".join(f"  - {i}" for i in v["itens"][:10])
    assert v["status"] != "erro", msg
    if exigir_ok:
        assert v["status"] == "ok", msg


LAYOUT = checagens.layout()
CONSIST = checagens.consistencia()


@pytest.mark.parametrize("v", LAYOUT, ids=_ids(LAYOUT))
def test_layout_das_fontes(v):
    """Se a CVM, a B3 ou o Tesouro mudarem o formato do arquivo, este teste falha."""
    _avaliar(v, exigir_ok=True)


@pytest.mark.parametrize("v", CONSIST, ids=_ids(CONSIST))
def test_numeros_fecham(v):
    """Ativo = Passivo, DRE fecha, preço do Tesouro calculado = publicado etc."""
    _avaliar(v, exigir_ok=v["id"].startswith("cons:td"))
