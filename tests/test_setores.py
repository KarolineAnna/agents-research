"""Classificação setorial (CVM · FCA) e sugestão de pares."""
import pytest

from indicadores_b3 import config
from indicadores_b3.data import setores


def test_normalizar_holdings_e_sinonimos():
    assert setores.normalizar("Emp. Adm. Part. - Energia Elétrica") == ("Energia Elétrica", True)
    assert setores.normalizar("Emp. Adm. Part. - Máqs., Equip., Veíc. e Peças") == ("Máquinas, Equipamentos, Veículos e Peças", True)
    assert setores.normalizar("Bancos") == ("Bancos", False)
    assert setores.normalizar(None)[0] == "Não informado"


def test_todo_setor_do_mapa_tem_um_unico_macrossetor():
    vistos = [s for ss in setores.MACRO.values() for s in ss]
    assert len(vistos) == len(set(vistos))


@pytest.mark.skipif(not (config.CACHE_DIR / "fca_2026.zip").exists() and not any(config.CACHE_DIR.glob("fca_*.zip")),
                    reason="FCA da CVM não baixado")
def test_pares_de_banco_sao_bancos_de_outras_empresas():
    p = setores.pares("ITUB4", 4)
    assert p["setor"] == "Bancos" and p["macro"] == "Financeiro"
    tks = [x["ticker"] for x in p["pares"]]
    assert tks and not any(t.startswith("ITUB") for t in tks)
    assert len({t[:4] for t in tks}) == len(tks)  # uma ação por empresa
    assert all(x["setor"] == "Bancos" for x in p["pares"])
