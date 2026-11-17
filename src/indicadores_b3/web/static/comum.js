// Formatações usadas por abas públicas e privadas (as privadas ficam em extras/, fora do GitHub).
const brl = (v) => fmt(v, "R$");
const brl2 = (v) => fmt(v, "R$/ação");
const sinalBrl = (v) => (v === null || v === undefined ? "—" : v < 0 ? `(${brl(Math.abs(v))})` : brl(v));
function fmtDif(v) { return v == null ? "n/d" : (v > 0 ? "+" : "") + nf(1).format(v) + "%"; }
