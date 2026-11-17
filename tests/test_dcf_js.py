"""O DCF da tela (dcf.js) e o do "cara ou barata" (Python) têm que dar o mesmo número; e os dois batem com a conta à mão.
Roda o JavaScript com o Node; sem Node instalado, o teste é pulado."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from indicadores_b3.analytics.valuation_rapido import dcf_por_acao

DCF_JS = Path(__file__).parents[1] / "src" / "indicadores_b3" / "web" / "static" / "dcf.js"
CASOS = [(1000, 12, 3.5, 5, 2000, 100), (500, 15, 4, 10, -300, 50), (2500, 10.5, 3, 0, 8000, 1000)]


def _mao(fcl, r, g, cresc, dl, acoes):
    r, g, vp = r / 100, g / 100, 0.0
    for t in range(1, 11):
        c = cresc if t <= 5 else cresc + (g * 100 - cresc) * (t - 5) / 6
        fcl *= 1 + c / 100
        vp += fcl / (1 + r) ** (t - 0.5)
    vp += fcl * (1 + g) / (r - g) / (1 + r) ** 9.5
    return (vp - dl) / acoes


@pytest.mark.skipif(shutil.which("node") is None, reason="Node não instalado")
def test_dcf_da_tela_igual_ao_python_e_a_mao(tmp_path):
    script = tmp_path / "rodar.js"
    script.write_text(f"""
const fs = require('fs'); const src = fs.readFileSync({json.dumps(str(DCF_JS))}, 'utf8');
var WACC_IN = {{ ir: 34 }};
eval(src.slice(src.indexOf('const PREM'), src.indexOf('let WACC_IN')).replace('const PREM', 'var PREM')
     + src.slice(src.indexOf('// ---------- Cálculo ----------'), src.indexOf('// ---------- Render ----------')));
const out = {json.dumps(CASOS)}.map(([fcl, r, g, cresc, dl, acoes]) => {{
  const d = {{ historico: [], rastreio: {{ fcl: {{ valor: fcl }}, divida_bruta: {{ valor: Math.max(dl, 0) }}, caixa: {{ valor: Math.max(-dl, 0) }},
    acoes: {{ valor: acoes }}, preco: {{ valor: 10 }} }} }};
  return calcularDCF({{ ...PREM, r, g, cresc, metodo: "fcff", base: "ttm" }}, d).porAcao;
}});
console.log(JSON.stringify(out));""", encoding="utf-8")
    js = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    for caso, v_js in zip(CASOS, js, strict=True):
        assert v_js == pytest.approx(dcf_por_acao(*caso), rel=1e-9)
        assert v_js == pytest.approx(_mao(*caso), rel=1e-9)
