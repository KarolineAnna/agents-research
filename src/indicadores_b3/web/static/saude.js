// Aba "Saúde dos dados": roda as verificações de checagens.py e mostra o resultado.
let SAUDE = null;
const GRUPOS_SAUDE = {
  fontes: ["Fontes e atualização", "Os arquivos em cache existem e estão recentes? As fontes online respondem?"],
  layout: ["Formato dos arquivos", "As colunas que o site usa continuam nos arquivos oficiais? Se a fonte mudar o formato, aparece aqui antes de virar número errado."],
  consistencia: ["Os números fecham?", "Conferências contábeis e de precificação em todos os dados baixados, não só nas empresas que você consultou."],
};
const SELO = { ok: ["ok", "OK"], aviso: ["aviso", "Atenção"], erro: ["erro", "Erro"], pulado: ["pulado", "Não baixado"] };

async function rodarSaude() {
  const st = $("#status-saude"), btn = $("#saude-rodar"), online = $("#saude-online").checked;
  btn.disabled = true; st.className = "status";
  st.textContent = online ? "Verificando arquivos e consultando as fontes online…" : "Verificando os arquivos em cache…";
  try { SAUDE = await api(`/api/saude?online=${online}`); st.textContent = ""; renderSaude(); }
  catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { btn.disabled = false; }
}

function renderSaude() {
  const s = SAUDE, r = s.resumo;
  const geral = r.erro ? "erro" : r.aviso ? "aviso" : "ok";
  const frase = { ok: "Tudo certo: as fontes estão em dia e os números fecham.",
    aviso: "Funcionando, com pontos de atenção abaixo.", erro: "Há verificações com erro: confira antes de confiar nos números afetados." }[geral];
  const linha = (v) => `<details class="saude-item s-${v.status}" ${v.status === "erro" ? "open" : ""}>
      <summary><span class="selo s-${v.status}">${SELO[v.status][1]}</span><span class="si-nome">${esc(v.nome)}</span>
        <span class="si-det">${esc(v.detalhe)}</span></summary>
      <div class="si-corpo">
        ${v.fonte ? `<p><strong>Fonte:</strong> ${v.url ? `<a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.fonte)} ↗</a>` : esc(v.fonte)}
          ${v.atualizado ? ` · arquivo de ${esc(v.atualizado)}` : ""}</p>` : ""}
        ${v.itens.length ? `<div class="tabela-scroll"><table><thead><tr><th>Item</th><th>Data</th><th>Detalhe</th></tr></thead><tbody>
          ${v.itens.map((i) => `<tr><td>${esc(i.empresa)}</td><td>${esc(i.data)}</td><td>${esc(i.detalhe)}</td></tr>`).join("")}</tbody></table></div>` : ""}
        <p class="sub-tk">Verificação: <code>${esc(v.id)}</code></p>
      </div></details>`;
  $("#resultado-saude").innerHTML = `
    <div class="saude-topo s-${geral}">
      <div><b>${frase}</b><span>Verificado em ${esc(s.quando.replace(/(\d{4})-(\d{2})-(\d{2})/, "$3/$2/$1"))} · ${nf(1).format(s.segundos)} s${s.online ? " · com fontes online" : ""}</span></div>
      <div class="saude-cont">${["ok", "aviso", "erro", "pulado"].map((k) => `<span class="selo s-${k}">${r[k]} ${SELO[k][1].toLowerCase()}</span>`).join("")}</div>
    </div>
    ${Object.entries(GRUPOS_SAUDE).map(([g, [titulo, desc]]) => {
      const vs = s.verificacoes.filter((v) => v.grupo === g);
      return vs.length ? `<div class="bloco"><h2>${titulo}</h2><p class="dica">${desc}</p>${vs.map(linha).join("")}</div>` : "";
    }).join("")}
    <p class="dica">As mesmas verificações rodam nos testes automáticos: na pasta do projeto, <code>python -m pytest -v</code>.</p>`;
}

$("#saude-rodar").addEventListener("click", rodarSaude);
document.querySelector('[data-aba="saude"]').addEventListener("click", () => { if (!SAUDE) rodarSaude(); });
if (location.hash === "#saude") rodarSaude();

// ---------- Conferir uma empresa: checagens, anomalias (Isolation Forest), contas que fecham e agente de qualidade ----------
const REGRAS_SAUDE = { nulo: "Valor ausente", defasagem: "Balanço antigo", fora_da_faixa: "Fora da faixa plausível",
  divergencia_externa: "Diferente do yfinance", sem_fonte_externa: "Sem fonte para comparar" };
const CAUSAS_SAUDE = { dado_real: ["ok", "Dado real"], erro_fonte: ["aviso", "Erro da fonte"], erro_calculo: ["erro", "Erro de cálculo"] };
let SAUDE_EMP = null;

async function conferirEmpresa(ev) {
  ev?.preventDefault();
  const tk = $("#saude-emp-in").value.trim().toUpperCase(), st = $("#saude-emp-st");
  st.className = "status"; st.textContent = "Conferindo… na primeira vez baixa o ITR de todas as companhias.";
  $("#saude-emp-res").innerHTML = "";
  try {
    const [chk, an] = await Promise.all([api(`/api/saude/empresa/${encodeURIComponent(tk)}`),
      api(`/api/saude/anomalias/${encodeURIComponent(tk)}`).catch((e) => ({ erro: e.message }))]);
    SAUDE_EMP = { chk, an };
    st.textContent = "";
    $("#saude-emp-res").innerHTML = htmlEmpresaSaude();
    $("#saude-agente")?.addEventListener("click", () => investigarEmpresa(tk));
  } catch (err) { st.className = "status erro"; st.textContent = err.message; }
}

function htmlEmpresaSaude() {
  const { chk, an } = SAUDE_EMP, probs = chk.problemas.filter((p) => p.severidade !== "info");
  const tabProb = probs.length ? `<div class="tabela-scroll"><table><thead><tr><th>Campo</th><th>Problema</th><th>Detalhe</th></tr></thead><tbody>
      ${probs.map((p) => `<tr><td><code>${esc(p.campo)}</code></td><td>${esc(REGRAS_SAUDE[p.regra] || p.regra)}</td><td>${esc(p.detalhe)}</td></tr>`).join("")}</tbody></table></div>
      <div class="mc-acoes"><button type="button" id="saude-agente">Investigar com o agente de IA</button></div><div id="saude-agente-res"></div>`
    : `<p class="saude-ok">✓ Nenhum indicador fora da faixa, ausente ou diferente do yfinance.</p>`;
  let anom = "";
  if (an.erro) anom = `<p class="status erro">${esc(an.erro)}</p>`;
  else {
    const ident = `<div class="tabela-scroll"><table><thead><tr><th>Regra contábil</th><th>Informado</th><th>Soma das partes</th><th>Status</th></tr></thead><tbody>
      ${an.identidades.map((i) => `<tr><td>${esc(i.regra)}</td><td>${sinalBrl(i.informado)}</td><td>${sinalBrl(i.calculado)}</td>
        <td>${i.status === "ok" ? '<span class="tag">✓ fecha</span>' : i.status === "não fecha" ? '<span class="tag perde">✗ não fecha</span>' : "n/d"}</td></tr>`).join("")}</tbody></table></div>`;
    if (an.erro_pares) anom = `<h3>Contas que precisam fechar</h3>${ident}<p class="dica">${esc(an.erro_pares)}</p>`;
    else {
      const R = Object.keys(an.razoes_def), u = (r) => (r === "liquidez" || r === "giro" ? "x" : "%");
      const v = (x, r) => (u(r) === "x" ? num(x) + "x" : pct(x, 1)), a = an.anomalia;
      anom = `<h3>Contas que precisam fechar</h3>${ident}
        <h3>Fora do padrão? (Isolation Forest, ${an.n_empresas} companhias do ITR de ${dataBR(an.ref)})</h3>
        <div class="aviso-box ${a.sinalizada ? "" : "ok-box"}">${a.sinalizada ? `⚠ Entre as 5% mais atípicas: confira os indicadores com distância acima de 3.` : `✓ Dentro do padrão (mais atípica que ${nf(0).format(a.percentil)}% das companhias).`}</div>
        <div class="tabela-scroll"><table><thead><tr><th>Indicador</th><th class="num">${esc(an.ticker)}</th><th class="num">Mediana</th><th class="num">Percentil</th><th class="num">Distância</th></tr></thead><tbody>
          ${R.map((r) => { const z = an.z_robusto[r]; return `<tr><td>${esc(an.razoes_def[r][0])}</td><td class="num"><b>${v(an.alvo[r], r)}</b></td><td class="num">${v(an.mediana_mercado[r], r)}</td>
            <td class="num">${nf(0).format(an.percentis[r])}</td><td class="num ${Math.abs(z) > 3 ? "neg" : ""}">${nf(1).format(z)}</td></tr>`; }).join("")}</tbody></table></div>
        <p class="dica">Anomalia não é defeito: pode ser um negócio diferente de verdade. Distância = (valor − mediana) ÷ desvio absoluto mediano; acima de 3 é bem incomum.</p>`;
    }
  }
  return `<h3>${esc(chk.empresa || chk.ticker)}: checagens dos indicadores</h3>${tabProb}${anom}`;
}

async function investigarEmpresa(tk) {
  const el = $("#saude-agente-res"), btn = $("#saude-agente");
  btn.disabled = true; el.innerHTML = '<p class="status">O agente está conferindo as contas da CVM e o yfinance…</p>';
  try {
    const r = await fetch(`/api/saude/agente/${encodeURIComponent(tk)}`, { method: "POST" })
      .then(async (x) => { const j = await x.json(); if (!x.ok) throw new Error(j.detail || x.statusText); return j; });
    el.innerHTML = (r.diagnostico || []).length ? `<div class="tabela-scroll"><table><thead><tr><th>Campo</th><th>Causa</th><th>Evidência</th><th>O que fazer</th></tr></thead><tbody>
      ${r.diagnostico.map((d) => { const c = CAUSAS_SAUDE[d.causa] || ["pulado", d.causa]; return `<tr><td><code>${esc(d.campo)}</code></td><td><span class="selo s-${c[0]}">${esc(c[1])}</span></td>
        <td>${esc(d.evidencia)}</td><td>${esc(d.acao_sugerida || "")}</td></tr>`; }).join("")}</tbody></table></div>`
      : `<p class="status">${(r.passos || []).some((p) => p.tipo === "erro") ? "A IA não respondeu: tente de novo em alguns minutos." : "O agente não chegou a um diagnóstico válido."}</p>`;
  } catch (err) { el.innerHTML = `<p class="status erro">${esc(err.message)}</p>`; }
  finally { btn.disabled = false; }
}

$("#form-saude-emp").addEventListener("submit", conferirEmpresa);
