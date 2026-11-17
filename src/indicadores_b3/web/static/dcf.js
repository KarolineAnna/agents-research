// Aba "DCF": fluxo de caixa descontado, passo a passo.
// O servidor entrega só os números reais (CVM) com rastreio; toda a conta do DCF é feita aqui,
// para as premissas poderem ser ajustadas e o resultado mudar na hora.

let DCF = null;
const PREM = { cresc: 5, g: 3.5, r: null, anos: 5, anos2: 5, base: "ttm", modoR: "wacc", meio: true, metodo: "fcff",
  cen: { pessimista: { dc: -3, dr: 1.5, dg: -0.5, w: 25 }, base: { dc: 0, dr: 0, dg: 0, w: 50 }, otimista: { dc: 3, dr: -1, dg: 0.5, w: 25 } } };
let WACC_IN = null; // insumos do WACC (editáveis)
let DCF_WACC_ABERTO = false, DCF_CONTA_ABERTA = false, DCF_MC_ABERTO = false;


$("#form-dcf").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const tk = $("#ticker-dcf").value.split(",")[0].trim().toUpperCase();
  const status = $("#status-dcf");
  status.className = "status";
  status.textContent = `Carregando ${tk}… na primeira vez o site baixa os demonstrativos da CVM.`;
  try {
    DCF = await api(`/api/dcf/${encodeURIComponent(tk)}`);
    if (PREM.r === null) PREM.r = DCF.cdi ? Math.round(DCF.cdi.valor + 5) : 15;
    iniciarWACC();
    status.textContent = "";
    renderDCF();
  } catch (err) {
    status.className = "status erro";
    status.textContent = err.message;
  }
});

// ---------- Cálculo ----------
function crescimentoNoAno(p, t) {
  // 1º estágio: crescimento escolhido; 2º estágio: converge em linha reta até g (o ano seguinte já cresce g)
  if (t <= p.anos) return p.cresc;
  return p.cresc + (p.g - p.cresc) * (t - p.anos) / (p.anos2 + 1);
}

function calcularDCF(p, d) {
  const R = d.rastreio;
  const media = d.historico.length ? d.historico.reduce((s, h) => s + h.fcl, 0) / d.historico.length : null;
  const fcff0 = p.base === "media" && media !== null ? media
    : p.base === "resultado" && R.fcff_resultado?.valor != null ? R.fcff_resultado.valor : R.fcl.valor;
  const dividaLiqBal = R.divida_bruta.valor - R.caixa.valor;
  // fluxo do acionista: tira os juros (após IR) e supõe que a dívida líquida cresce junto com a empresa (alavancagem estável)
  const juros = Math.abs(d.wacc?.despesa_fin?.valor || 0), ir = (WACC_IN?.ir ?? 34) / 100;
  const fcfe = p.metodo === "fcfe";
  const ajusteAcionista = fcfe ? -juros * (1 - ir) + (p.g / 100) * Math.max(dividaLiqBal, 0) : 0;
  const fcl0 = fcff0 + ajusteAcionista;
  const r = p.r / 100, g = p.g / 100;

  const anos = [];
  let fcl = fcl0;
  for (let t = 1; t <= p.anos + p.anos2; t++) {
    const c = crescimentoNoAno(p, t);
    fcl = fcl * (1 + c / 100);
    const fator = 1 / (1 + r) ** (t - (p.meio ? 0.5 : 0));  // meio do ano: o caixa entra ao longo do ano
    anos.push({ t, c, fase: t <= p.anos ? 1 : 2, fcl, fator, vp: fcl * fator });
  }
  const n = anos.length;
  const somaVP = anos.reduce((s, a) => s + a.vp, 0);
  const ultimo = anos[n - 1].fcl;
  const terminal = r > g ? (ultimo * (1 + g)) / (r - g) : null;
  const vpTerminal = terminal !== null ? terminal / (1 + r) ** (n - (p.meio ? 0.5 : 0)) : null;
  const ev = vpTerminal !== null ? somaVP + vpTerminal : null;
  const dividaLiq = fcfe ? 0 : dividaLiqBal;  // no FCFE o valor presente já é das ações
  const equity = ev !== null ? ev - dividaLiq : null;
  const porAcao = equity !== null && R.acoes.valor ? equity / R.acoes.valor : null;
  const preco = R.preco.valor;
  return { fcff0, fcl0, juros, ajusteAcionista, dividaLiqBal, media, anos, somaVP, ultimo, terminal, vpTerminal, ev, dividaLiq, equity, porAcao, preco,
           margem: porAcao !== null && preco ? (porAcao / preco - 1) * 100 : null };
}

function calcularCenarios(d) {
  const out = Object.entries(PREM.cen).map(([nome, c]) => {
    const p = { ...PREM, cresc: PREM.cresc + c.dc, r: PREM.r + c.dr, g: PREM.g + c.dg };
    const x = p.r > p.g ? calcularDCF(p, d) : null;
    return { nome, ...c, cresc: p.cresc, r: p.r, g: p.g, porAcao: x?.porAcao ?? null };
  });
  const validos = out.filter((c) => c.porAcao != null);
  const somaW = validos.reduce((s, c) => s + c.w, 0);
  const ponderado = somaW > 0 ? validos.reduce((s, c) => s + c.w * c.porAcao, 0) / somaW : null;
  return { cenarios: out, ponderado, somaW };
}

// ---------- Render ----------
function slider(id, rotulo, valor, min, max, passo, ajuda) {
  return `<label class="premissa">
    <span class="p-rotulo">${rotulo}</span>
    <span class="p-valor" id="v-${id}">${nf(1).format(valor)}%</span>
    <input type="range" id="${id}" min="${min}" max="${max}" step="${passo}" value="${valor}">
    <span class="p-ajuda">${ajuda}</span>
  </label>`;
}

function htmlCampos(rastro) {
  return `<details class="campos"><summary>Ver campos usados (CVM)</summary>
    ${rastro.nota ? `<p class="e-nota">${esc(rastro.nota)}</p>` : ""}
    ${rastro.componentes.map((c) => htmlComponente(c, "R$")).join("")}</details>`;
}

function renderDCF() {
  aplicarWACC();  // a taxa mostrada no resumo do WACC já sai atualizada
  const d = DCF, R = d.rastreio;
  const cdiTxt = d.cdi ? `CDI hoje: ${pct(d.cdi.valor)} (Banco Central)` : "CDI indisponível";
  $("#resultado-dcf").innerHTML = `
    <div class="viz dcf">
      <div class="empresa"><h2>${esc(d.empresa)}</h2><span class="tk">${esc(d.ticker)}</span></div>
      <div class="meta"><span class="pill">Balanço de ${dataBR(d.balanco_ref)}</span>
        <span class="pill">Preço: ${brl2(R.preco.valor)}</span><span class="pill">${cdiTxt}</span></div>
      <div id="dcf-topo"></div>

      <div class="bloco premissas">
        <h2>Premissas</h2>
        <div class="premissas-grid">
          ${slider("p-cresc", "Crescimento do FCL nos próximos anos", PREM.cresc, -10, 30, 0.5,
                   "Quanto o caixa livre cresce por ano no período projetado.")}
          <div class="premissa">
            <span class="p-rotulo">Taxa de desconto (r)</span><span class="p-valor" id="v-p-r">${nf(1).format(PREM.r)}%</span>
            <select id="p-modo-r"><option value="wacc" ${PREM.modoR === "wacc" ? "selected" : ""}>${PREM.metodo === "fcfe" ? "Ke pelo CAPM (como o mercado)" : "WACC (como o mercado)"}</option>
              <option value="manual" ${PREM.modoR === "manual" ? "selected" : ""}>Digitar a taxa</option></select>
            <input type="range" id="p-r" min="5" max="30" step="0.5" value="${PREM.r}" ${PREM.modoR === "wacc" ? "hidden" : ""}>
            <span class="p-ajuda">${PREM.modoR === "wacc" ? "Custo médio do capital: ações e dívida, ponderados. Ajuste os insumos abaixo." : `Seu retorno mínimo exigido. Ponto de partida comum: CDI + 4 a 6 pontos. ${cdiTxt}.`}</span>
          </div>
          ${slider("p-g", "Crescimento na perpetuidade (g)", PREM.g, 0, 8, 0.25,
                   "Crescimento “para sempre” depois da projeção. Costuma ficar perto da inflação de longo prazo e precisa ser menor que r.")}
          <label class="premissa">
            <span class="p-rotulo">Anos de projeção</span><span class="p-valor" id="v-p-anos">${PREM.anos} anos</span>
            <input type="range" id="p-anos" min="3" max="10" step="1" value="${PREM.anos}">
            <span class="p-ajuda">Quantos anos você projeta ano a ano antes da perpetuidade.</span>
          </label>
          <label class="premissa">
            <span class="p-rotulo">Anos de transição (2º estágio)</span><span class="p-valor" id="v-p-anos2">${PREM.anos2} anos</span>
            <input type="range" id="p-anos2" min="0" max="10" step="1" value="${PREM.anos2}">
            <span class="p-ajuda">Depois do período projetado, o crescimento cai em linha reta até g, em vez de despencar de uma vez. É como os analistas modelam empresas que ainda crescem acima da economia. Zero = um estágio só.</span>
          </label>
          <label class="premissa">
            <span class="p-rotulo">Método</span>
            <select id="p-metodo">
              <option value="fcff" ${PREM.metodo === "fcff" ? "selected" : ""}>Fluxo da empresa (FCFF ÷ WACC)</option>
              <option value="fcfe" ${PREM.metodo === "fcfe" ? "selected" : ""}>Fluxo do acionista (FCFE ÷ Ke)</option>
            </select>
            <span class="p-ajuda">FCFF: caixa para credores e acionistas, descontado pelo WACC; depois se tira a dívida. FCFE: caixa que sobra só para o acionista (depois dos juros), descontado pelo custo do capital próprio. Os dois devem dar valores parecidos quando a alavancagem é estável.</span>
          </label>
          <label class="premissa">
            <span class="p-rotulo">Ponto de partida do FCL</span>
            <select id="p-base">
              <option value="ttm" ${PREM.base === "ttm" ? "selected" : ""}>FCL ajustado, últimos 12 meses</option>
              <option value="media" ${PREM.base === "media" ? "selected" : ""} ${d.historico.length ? "" : "disabled"}>FCL ajustado, média dos anos fechados</option>
              <option value="resultado" ${PREM.base === "resultado" ? "selected" : ""} ${d.rastreio.fcff_resultado?.valor != null ? "" : "disabled"}>Pelo resultado (EBIT × (1 − IR) + D&amp;A − investimentos)</option>
            </select>
            <label class="m-rf-rot" style="margin-top:8px"><input type="checkbox" id="p-meio" ${PREM.meio ? "checked" : ""}> Convenção do meio do ano</label>
            <span class="p-ajuda">O FCL oscila muito de um ano para o outro; a média suaviza anos atípicos.</span>
          </label>
        </div>
      </div>
      ${PREM.modoR === "wacc" ? `<details class="dcf-det" id="wacc-det" ${DCF_WACC_ABERTO ? "open" : ""}><summary>Taxa de desconto: <b id="wacc-resumo">${PREM.metodo === "fcfe" ? "Ke" : "WACC"} ${nf(1).format(PREM.r)}%</b> · ver e editar os insumos</summary>${htmlWACCEditor()}</details>` : ""}
      <div id="dcf-passos"></div>
    </div>`;

  const ligar = (id, chave, sufixo = "%") => $(`#${id}`).addEventListener("input", (ev) => {
    PREM[chave] = +ev.target.value;
    $(`#v-${id}`).textContent = sufixo === "anos" ? `${PREM[chave]} anos` : `${nf(1).format(PREM[chave])}%`;
    renderPassos();
  });
  ligar("p-cresc", "cresc"); ligar("p-r", "r"); ligar("p-g", "g"); ligar("p-anos", "anos", "anos"); ligar("p-anos2", "anos2", "anos");
  $("#p-metodo").addEventListener("change", (ev) => { PREM.metodo = ev.target.value; aplicarWACC(); renderDCF(); });
  $("#p-base").addEventListener("change", (ev) => { PREM.base = ev.target.value; renderPassos(); });
  $("#p-meio").addEventListener("change", (ev) => { PREM.meio = ev.target.checked; renderPassos(); });
  $("#p-modo-r").addEventListener("change", (ev) => { PREM.modoR = ev.target.value; aplicarWACC(); renderDCF(); });
  document.querySelectorAll("[data-w]").forEach((i) => i.addEventListener("input", () => {
    WACC_IN[i.dataset.w] = i.type === "checkbox" ? i.checked : i.tagName === "SELECT" ? i.value : +i.value;
    if (i.tagName === "SELECT") { aplicarWACC(); renderDCF(); return; }
    aplicarWACC(); $("#v-p-r").textContent = `${nf(1).format(PREM.r)}%`; $("#wacc-res").innerHTML = htmlWACCRes();
    if ($("#wacc-resumo")) $("#wacc-resumo").textContent = `${PREM.metodo === "fcfe" ? "Ke" : "WACC"} ${nf(1).format(PREM.r)}%`; renderPassos();
  }));
  $("#wacc-det")?.addEventListener("toggle", (ev) => { DCF_WACC_ABERTO = ev.target.open; });
  aplicarWACC();
  $("#v-p-r").textContent = `${nf(1).format(PREM.r)}%`;
  renderPassos();
}

document.addEventListener("change", (e) => {
  const i = e.target.closest?.(".cen-in");
  if (!i || !DCF) return;
  PREM.cen[i.dataset.cen][i.dataset.k] = +i.value || 0;
  renderPassos();
});

function renderPassos() {
  const d = DCF, R = d.rastreio, x = calcularDCF(PREM, d);
  const invalido = PREM.r <= PREM.g;
  const fclNeg = x.fcl0 <= 0;

  const hist = d.historico.map((h) => `<tr><td>${h.ano}</td><td>${brl(h.fco)}</td><td>${brl(h.fci)}</td><td>${brl(h.ajustes || 0)}</td>
    <td class="${h.fcl < 0 ? "neg" : ""}"><strong>${brl(h.fcl)}</strong></td></tr>`).join("");
  const ajustes = (d.ajustes || []).filter((a) => a.valor);
  const res = R.fcff_resultado?.valor;
  const distante = x.porAcao && x.preco ? x.porAcao / x.preco : null;
  const conf = res && R.fcl.valor ? Math.abs(res / R.fcl.valor - 1) : null;

  const linhasProj = x.anos.map((a) => `<tr class="${a.fase === 2 ? "fase2" : ""}"><td>Ano ${a.t}${a.fase === 2 ? " <small>2º estágio</small>" : ""}</td><td>${nf(1).format(a.c)}%</td><td>${brl(a.fcl)}</td>
    <td>1 ÷ (1 + ${nf(1).format(PREM.r)}%)<sup>${PREM.meio ? nf(1).format(a.t - 0.5) : a.t}</sup> = ${nf(3).format(a.fator)}</td><td><strong>${brl(a.vp)}</strong></td></tr>`).join("");

  const pctTerm = x.ev ? (x.vpTerminal / x.ev) * 100 : null;

  $("#dcf-topo").innerHTML = `
    ${invalido ? "" : `<div class="veredito dcf-resumo ${x.margem >= 0 ? "acima" : "abaixo"}">
      <div><span>Valor justo (DCF)</span><b>${brl2(x.porAcao)}</b></div>
      <div><span>Preço na bolsa</span><b>${brl2(x.preco)}</b></div>
      <div><span>${x.margem >= 0 ? "Potencial de alta" : "Preço acima do valor justo"}</span><b>${pct(x.margem, 1)}</b></div>
      <div><span>Ponderado pelos cenários</span><b>${brl2(calcularCenarios(d).ponderado)}</b></div></div>`}
    ${(d.alertas || []).map((a) => `<div class="aviso-box">⚠ ${esc(a)}</div>`).join("")}
    ${distante && (distante > 2.5 || distante < 0.4) ? `<div class="aviso-box">⚠ O valor justo ficou ${distante > 1 ? nf(1).format(distante) + " vezes o" : "muito abaixo do"} preço atual.
      Diferenças assim quase sempre vêm das premissas (ponto de partida do FCL, crescimento, taxa), não de uma "pechincha": confira o passo 1 e compare com a conferência pelo resultado.</div>` : ""}
    ${fclNeg ? `<div class="aviso-box">⚠ O fluxo de caixa livre de partida é negativo (${brl(x.fcl0)}). Projetar um número negativo
      gera um valor negativo: o DCF simples não funciona bem para empresas que estão queimando caixa. Tente a média dos anos.</div>` : ""}
    ${invalido ? `<div class="aviso-box">⚠ A taxa de desconto (r) precisa ser maior que o crescimento na perpetuidade (g).
      Com r ≤ g a fórmula da perpetuidade dá infinito.</div>` : ""}`;

  $("#dcf-passos").innerHTML = `
    ${invalido ? "" : htmlCenarios(d)}
    ${invalido || fclNeg ? "" : htmlMC(d)}
    ${invalido ? "" : `<div class="bloco"><h2>Sensibilidade: taxa × g</h2>${tabelaSensibilidade(d)}</div>`}
    <details class="dcf-det dcf-conta" id="dcf-conta" ${DCF_CONTA_ABERTA ? "open" : ""}><summary>Ver a conta passo a passo</summary>
    <div class="bloco passo"><div class="n">1</div><div>
      <h2>Quanto caixa a empresa gera hoje?</h2>
      <p>O <strong>fluxo de caixa livre (FCL)</strong> é o dinheiro que sobra depois de a empresa operar e investir no próprio negócio.
        É ele que, no fim, pode ir para os donos e para pagar dívidas.</p>
      <div class="eq">FCL contábil = Caixa das operações (6.01) + Caixa dos investimentos (6.02)</div>
      <div class="eq">${brl(R.fco.valor)} + (${brl(R.fci.valor)}) = ${brl(R.fcl_contabil?.valor ?? R.fcl.valor)} nos últimos 12 meses</div>
      ${ajustes.length ? `<h3 class="sub">Ajustes que o mercado faz</h3>
        <p>Algumas saídas de caixa da operação aparecem na DFC como <em>financiamento</em>. Somar o FCL sem tirá-las superestima o caixa
          (em varejistas, o caixa operacional pode parecer 10 vezes maior que o real).</p>
        <div class="tabela-scroll"><table><tbody>${ajustes.map((a) => `<tr><td>${esc(a.rotulo)}</td><td><code>${esc(a.contas.join(", "))}</code></td>
          <td class="neg"><strong>${brl(a.valor)}</strong></td></tr>`).join("")}</tbody></table></div>
        <div class="eq">FCL ajustado = ${brl(R.fcl_contabil?.valor)} ${ajustes.map((a) => `− ${brl(Math.abs(a.valor))}`).join(" ")} = <strong>${brl(R.fcl.valor)}</strong></div>` : ""}
      ${htmlCampos(R.fcl)}
      ${res != null ? `<h3 class="sub">Conferência pelo resultado</h3>
        <div class="eq">EBIT × (1 − 34%) + depreciação − investimentos = <strong>${brl(res)}</strong></div>
        <p class="dica">${conf !== null && conf > 0.5 ? "⚠ Diferente do FCL ajustado em mais de 50%: um dos dois está distorcido por um ano atípico (capital de giro, venda de ativos). Considere usar a média ou este valor como ponto de partida."
          : "Próximo do FCL ajustado: o ponto de partida parece plausível."}</p>` : ""}
      ${hist ? `<h3 class="sub">Histórico anual (DFP)</h3>
        <div class="tabela-scroll"><table><thead><tr><th>Ano</th><th>Operações</th><th>Investimentos</th><th>Ajustes</th><th>FCL ajustado</th></tr></thead>
        <tbody>${hist}</tbody></table></div>
        ${x.media !== null ? `<p class="dica">Média dos anos: ${brl(x.media)}.</p>` : ""}` : ""}
      ${PREM.metodo === "fcfe" ? `<h3 class="sub">Do caixa da empresa ao caixa do acionista (FCFE)</h3>
        <div class="eq">FCFE = FCFF − juros × (1 − IR) + g × dívida líquida</div>
        <div class="eq">${brl(x.fcff0)} − ${brl(x.juros)} × (1 − ${nf(0).format(WACC_IN.ir)}%) + ${nf(1).format(PREM.g)}% × ${brl(Math.max(x.dividaLiqBal, 0))} = <strong>${brl(x.fcl0)}</strong></div>
        <p class="dica">Juros: despesas financeiras dos últimos 12 meses (DRE 3.06.02). A última parcela supõe alavancagem estável: a dívida líquida cresce junto com a empresa e esse dinheiro novo também é do acionista.</p>` : ""}
      <p class="dica">Ponto de partida usado: <strong>${brl(x.fcl0)}</strong> (${PREM.base === "media" ? "FCL ajustado, média dos anos" : PREM.base === "resultado" ? "pelo resultado" : "FCL ajustado, últimos 12 meses"}).</p>
    </div></div>

    <div class="bloco passo"><div class="n">2</div><div>
      <h2>Projetar o caixa dos próximos ${PREM.anos + PREM.anos2} anos</h2>
      <p>Supomos que o fluxo cresce ${nf(1).format(PREM.cresc)}% ao ano por ${PREM.anos} anos${PREM.anos2 ? ` e depois desacelera em linha reta até ${nf(1).format(PREM.g)}% ao longo de ${PREM.anos2} anos (2º estágio)` : ""}. Mas R$ 1 daqui a 5 anos vale menos que R$ 1 hoje,
        porque hoje você poderia investir esse real a ${nf(1).format(PREM.r)}% ao ano. Por isso cada ano é <strong>descontado</strong>.</p>
      <div class="eq">Valor presente = FCL do ano ÷ (1 + r)<sup>${PREM.meio ? "ano − 0,5" : "ano"}</sup></div>
      ${PREM.meio ? `<p class="dica">Convenção do meio do ano: o caixa entra ao longo do ano, não todo no último dia; por isso o expoente é ano − 0,5. É o padrão em relatórios de análise.</p>` : ""}
      <div class="tabela-scroll"><table><thead><tr><th>Ano</th><th>Crescimento</th><th>${x.ajusteAcionista ? "FCFE" : "FCL"} projetado</th><th>Fator de desconto</th><th>Valor presente</th></tr></thead>
        <tbody>${linhasProj}<tr class="soma"><td colspan="4">Soma dos valores presentes</td><td><strong>${brl(x.somaVP)}</strong></td></tr></tbody></table></div>
    </div></div>

    <div class="bloco passo"><div class="n">3</div><div>
      <h2>E depois disso? O valor terminal</h2>
      <p>A empresa não acaba no ano ${x.anos.length}. Para o resto do tempo, supomos um crescimento menor e constante (g = ${nf(1).format(PREM.g)}%)
        e usamos a fórmula da perpetuidade (modelo de Gordon).</p>
      <div class="eq">Valor terminal = fluxo do ano ${x.anos.length} × (1 + g) ÷ (r − g)</div>
      ${invalido ? "" : `<div class="eq">${brl(x.ultimo)} × ${nf(3).format(1 + PREM.g / 100)} ÷ (${nf(1).format(PREM.r)}% − ${nf(1).format(PREM.g)}%) = <strong>${brl(x.terminal)}</strong></div>
      <div class="eq">Trazido a valor presente: ${brl(x.terminal)} ÷ (1 + r)<sup>${PREM.meio ? nf(1).format(x.anos.length - 0.5) : x.anos.length}</sup> = <strong>${brl(x.vpTerminal)}</strong></div>`}
    </div></div>

    <div class="bloco passo"><div class="n">4</div><div>
      <h2>Valor da empresa</h2>
      <div class="eq">Valor da empresa = soma dos anos projetados + valor terminal (ambos a valor presente)</div>
      ${invalido ? "" : `<div class="eq">${brl(x.somaVP)} + ${brl(x.vpTerminal)} = <strong>${brl(x.ev)}</strong></div>
      ${barraComposicao(x.somaVP, x.vpTerminal)}
      <p class="dica">${pctTerm !== null ? `O valor terminal responde por ${nf(0).format(pctTerm)}% do total.` : ""}
        É normal ele ser a maior parte, e é por isso que pequenas mudanças em r e g mexem tanto no resultado.</p>`}
    </div></div>

    <div class="bloco passo"><div class="n">5</div><div>
      <h2>${PREM.metodo === "fcfe" ? "Do valor das ações ao valor por ação" : "Do valor da empresa ao valor por ação"}</h2>
      ${PREM.metodo === "fcfe" ? `<p>No fluxo do acionista os juros já foram pagos: o valor presente calculado já é o valor das ações, sem tirar a dívida.</p>`
        : `<p>O valor da empresa pertence a credores e acionistas. Tirando a dívida líquida, sobra o que é dos acionistas.</p>
      <div class="eq">Valor das ações = Valor da empresa − Dívida líquida</div>`}
      ${invalido ? "" : `
      <div class="eq">${brl(x.ev)} − ${brl(x.dividaLiq)} = <strong>${brl(x.equity)}</strong></div>
      <div class="eq">Valor justo por ação = ${brl(x.equity)} ÷ ${fmt(R.acoes.valor, "qtd")} ações = <strong>${brl2(x.porAcao)}</strong></div>
`}
      <details class="campos"><summary>Ver campos usados (dívida, caixa, ações, preço)</summary>
        ${["divida_bruta", "caixa", "acoes", "preco"].map((k) => `<p class="e-nota"><strong>${{
          divida_bruta: "Dívida bruta", caixa: "Caixa e aplicações", acoes: "Ações em circulação", preco: "Preço" }[k]}</strong></p>
          ${R[k].componentes.map((c) => htmlComponente(c, k === "acoes" ? "qtd" : k === "preco" ? "R$/ação" : "R$")).join("")}`).join("")}
      </details>
    </div></div>

    </details>
    ${invalido ? "" : htmlMercadoDCF(x, pctTerm)}`;
  $("#dcf-conta")?.addEventListener("toggle", (ev) => { DCF_CONTA_ABERTA = ev.target.open; });
  ligarMC();
}

function barraComposicao(a, b) {
  const tot = a + b;
  if (!(tot > 0) || a < 0 || b < 0) return "";
  const pa = (a / tot) * 100;
  return `<div class="composicao" role="img" aria-label="Composição do valor da empresa">
    <div style="width:${pa}%;background:var(--c1)"><span>Anos projetados ${nf(0).format(pa)}%</span></div>
    <div style="width:${100 - pa}%;background:var(--c2)"><span>Valor terminal ${nf(0).format(100 - pa)}%</span></div>
  </div>`;
}

const NOME_CEN = { pessimista: "Pessimista", base: "Base", otimista: "Otimista" };
function htmlCenarios(d) {
  const r = calcularCenarios(d), preco = d.rastreio.preco.valor;
  const campo = (nome, k, passo) => `<input type="number" step="${passo}" class="cen-in" data-cen="${nome}" data-k="${k}" value="${PREM.cen[nome][k]}">`;
  return `<div class="bloco passo"><div class="n">★</div><div>
    <h2>Cenários: pessimista, base e otimista</h2>
    <p>Um número só esconde a incerteza. Analistas montam três cenários mudando as premissas principais e ponderam pela chance de cada um.
      Nos cenários pessimista e otimista, os campos somam (ou subtraem) pontos percentuais às premissas do cenário base.</p>
    <div class="tabela-scroll"><table class="cen"><thead><tr><th>Cenário</th><th>Crescimento</th><th>Taxa (r)</th><th>g</th><th>Peso</th>
      <th>Valor por ação</th><th>vs. preço</th></tr></thead><tbody>
      ${r.cenarios.map((c) => {
        const cel = (k, passo, v, casas = 1) => c.nome === "base" ? `<span class="cen-v">${nf(casas).format(v)}%</span>`
          : `${campo(c.nome, k, passo)}<span class="cen-v">= ${nf(casas).format(v)}%</span>`;
        return `<tr><td><b>${NOME_CEN[c.nome]}</b></td><td>${cel("dc", 0.5, c.cresc)}</td><td>${cel("dr", 0.5, c.r)}</td><td>${cel("dg", 0.25, c.g, 2)}</td>
        <td>${campo(c.nome, "w", 5)}<span class="cen-v">%</span></td>
        <td><strong>${c.porAcao != null ? brl2(c.porAcao) : "r ≤ g"}</strong></td>
        <td class="${c.porAcao >= preco ? "pos" : "neg"}">${c.porAcao != null && preco ? pct((c.porAcao / preco - 1) * 100, 0) : "—"}</td></tr>`; }).join("")}
      <tr class="soma"><td colspan="5">Valor ponderado${r.somaW !== 100 ? ` <small>(pesos somam ${nf(0).format(r.somaW)}%: normalizados)</small>` : ""}</td>
        <td><strong>${brl2(r.ponderado)}</strong></td><td class="${r.ponderado >= preco ? "pos" : "neg"}">${r.ponderado && preco ? pct((r.ponderado / preco - 1) * 100, 0) : "—"}</td></tr>
    </tbody></table></div>
  </div></div>`;
}

function tabelaSensibilidade(d) {
  const rs = [-2, -1, 0, 1, 2].map((k) => PREM.r + k);
  const gs = [-1, -0.5, 0, 0.5, 1].map((k) => +(PREM.g + k).toFixed(2)).filter((g) => g >= 0);
  const preco = d.rastreio.preco.valor;
  const cab = `<tr><th>r \\ g</th>${gs.map((g) => `<th>${nf(1).format(g)}%</th>`).join("")}</tr>`;
  const linhas = rs.map((r) => `<tr><th>${nf(1).format(r)}%</th>${gs.map((g) => {
    if (r <= g) return `<td class="na">—</td>`;
    const v = calcularDCF({ ...PREM, r, g }, d).porAcao;
    const atual = r === PREM.r && g === PREM.g;
    return `<td class="${v >= preco ? "acima" : "abaixo"} ${atual ? "atual" : ""}">${brl2(v)}</td>`;
  }).join("")}</tr>`).join("");
  return `<div class="tabela-scroll"><table class="sens"><thead>${cab}</thead><tbody>${linhas}</tbody></table></div>`;
}


// ---------- WACC e "como o mercado faz" ----------
function iniciarWACC() {
  const w = DCF.wacc || {}, R = DCF.rastreio;
  const D = R.divida_bruta.valor || 0, df = Math.abs(w.despesa_fin?.valor ?? 0);
  const rf = w.rf?.valor ?? (DCF.cdi ? DCF.cdi.valor : 13);
  let kd = D > 0 && df > 0 ? (df / D) * 100 : rf + 2;
  const kdAviso = kd > 30 || kd < 5;
  if (kdAviso) kd = rf + 2;
  const mu = w.mercado_usd || {};
  const v = (x, padrao) => +(x?.valor ?? padrao).toFixed(2);
  WACC_IN = { beta: w.beta?.valor ?? 1, ajustar: true, rf, erp: w.erp ?? 5, kd: +kd.toFixed(1), ir: w.ir ?? 34, kdAviso,
              metodoKe: mu.rf_us ? "mercado" : "local", rf_us: v(mu.rf_us, 4.3), crp: v(mu.crp, 2.5), pi_br: v(mu.pi_br, 3.5), pi_us: v(mu.pi_us, 2.3) };
}

function calcWACC() {
  const W = WACC_IN, R = DCF.rastreio;
  const E = (R.preco.valor || 0) * (R.acoes.valor || 0), D = R.divida_bruta.valor || 0;
  const beta = W.ajustar ? 0.67 * W.beta + 0.33 : W.beta;
  // Ke "padrão de mercado": em dólar (Treasury + risco-país + β × prêmio) e convertido para reais pelo diferencial de inflação
  const keUSD = W.rf_us + W.crp + beta * W.erp;
  const ke = W.metodoKe === "mercado" ? ((1 + keUSD / 100) * (1 + W.pi_br / 100) / (1 + W.pi_us / 100) - 1) * 100 : W.rf + beta * W.erp;
  const kdLiq = W.kd * (1 - W.ir / 100);
  const pe = E + D > 0 ? E / (E + D) : 1, pd = 1 - pe;
  return { E, D, beta, ke, keUSD, kdLiq, pe, pd, valor: pe * ke + pd * kdLiq };
}

function aplicarWACC() {
  if (PREM.modoR === "wacc" && WACC_IN) { const c = calcWACC(); PREM.r = +(PREM.metodo === "fcfe" ? c.ke : c.valor).toFixed(1); }
}

function htmlWACCRes() {
  const c = calcWACC(), W = WACC_IN;
  const keTxt = W.metodoKe === "mercado"
    ? `<div class="eq">Ke em dólar = ${nf(1).format(W.rf_us)}% + ${nf(1).format(W.crp)}% + ${nf(2).format(c.beta)} × ${nf(1).format(W.erp)}% = <strong>${nf(1).format(c.keUSD)}%</strong></div>
       <div class="eq">Ke em reais = (1 + ${nf(1).format(c.keUSD)}%) × (1 + ${nf(1).format(W.pi_br)}%) ÷ (1 + ${nf(1).format(W.pi_us)}%) − 1 = <strong>${nf(1).format(c.ke)}%</strong></div>`
    : `<div class="eq">Custo do capital próprio (CAPM): Ke = ${nf(1).format(W.rf)}% + ${nf(2).format(c.beta)} × ${nf(1).format(W.erp)}% = <strong>${nf(1).format(c.ke)}%</strong></div>`;
  if (PREM.metodo === "fcfe") return keTxt + `<p class="dica">No fluxo do acionista a taxa de desconto é o próprio Ke: os credores já receberam os juros.</p>`;
  return keTxt + `<div class="eq">Custo da dívida após IR: Kd = ${nf(1).format(W.kd)}% × (1 − ${nf(0).format(W.ir)}%) = <strong>${nf(1).format(c.kdLiq)}%</strong></div>
    <div class="eq">WACC = ${pct(c.pe * 100, 0)} × ${nf(1).format(c.ke)}% + ${pct(c.pd * 100, 0)} × ${nf(1).format(c.kdLiq)}% = <strong>${nf(1).format(c.valor)}%</strong></div>
    <p class="dica">Pesos a valor de mercado: ações = preço × ações (${brl(c.E)}); dívida = dívida bruta do balanço (${brl(c.D)}).</p>`;
}

function htmlWACCEditor() {
  const w = DCF.wacc || {}, W = WACC_IN;
  const fonte = (r) => { const c = r?.componentes?.[0]; return c?.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.fonte)} ↗</a>` : ""; };
  const mu = w.mercado_usd || {};
  const fonteOuNota = (r) => (r?.premissa || !r?.componentes?.length ? `Premissa · ${esc((r?.nota || "").split(".")[0])}` : `${fonte(r)} · ${esc(r.componentes[0].data_ref || "")}`);
  return `<div class="bloco wacc">
    <h3>Taxa de desconto: ${PREM.metodo === "fcfe" ? "o custo do capital próprio (Ke)" : "o WACC"}</h3>
    <p class="dica">Analistas descontam o fluxo de caixa livre da empresa pelo <strong>custo médio ponderado de capital</strong>: o retorno exigido pelos acionistas (pelo CAPM)
      e o custo da dívida (com o benefício fiscal dos juros), cada um no seu peso. Todos os insumos são editáveis.</p>
    <label class="campo ke-metodo"><span>Como calcular o custo do capital próprio (Ke)</span>
      <select data-w="metodoKe">
        <option value="mercado" ${W.metodoKe === "mercado" ? "selected" : ""}>Padrão de mercado: em dólar + risco-país, convertido para reais</option>
        <option value="local" ${W.metodoKe === "local" ? "selected" : ""}>Juro local: prefixado longo do Tesouro + β × prêmio</option>
      </select></label>
    <div class="wacc-grid">
      ${W.metodoKe === "mercado" ? `
      <label class="campo"><span>Juro dos EUA, 10 anos (% a.a.)</span><input type="number" step="0.1" data-w="rf_us" value="${W.rf_us}">
        <small class="sub-tk">${fonteOuNota(mu.rf_us)}</small></label>
      <label class="campo"><span>Risco-país (% a.a.)</span><input type="number" step="0.1" data-w="crp" value="${W.crp}">
        <small class="sub-tk">${fonteOuNota(mu.crp)}</small></label>
      <label class="campo"><span>Inflação de longo prazo no Brasil (% a.a.)</span><input type="number" step="0.1" data-w="pi_br" value="${W.pi_br}">
        <small class="sub-tk">${fonteOuNota(mu.pi_br)}</small></label>
      <label class="campo"><span>Inflação de longo prazo nos EUA (% a.a.)</span><input type="number" step="0.1" data-w="pi_us" value="${W.pi_us}">
        <small class="sub-tk">${fonteOuNota(mu.pi_us)}</small></label>` : `
      <label class="campo"><span>Taxa livre de risco (% a.a.)</span><input type="number" step="0.1" data-w="rf" value="${W.rf}">
        <small class="sub-tk">Juro prefixado longo do Tesouro · ${fonte(w.rf)}</small></label>`}
      <label class="campo"><span>Beta (β)</span><input type="number" step="0.05" data-w="beta" value="${+W.beta.toFixed(2)}">
        <small class="sub-tk">${w.beta?.valor != null ? `Semanal, 2 anos, contra o Ibovespa · ${fonte(w.beta)}` : esc(w.beta?.nota || "Informe")}</small>
        <span class="m-rf-rot"><input type="checkbox" data-w="ajustar" ${W.ajustar ? "checked" : ""}> Ajustar (0,67·β + 0,33)</span></label>
      <label class="campo"><span>Prêmio de risco de ações (% a.a.)</span><input type="number" step="0.5" data-w="erp" value="${W.erp}">
        <small class="sub-tk">Premissa. Casas de análise no Brasil costumam usar de 4% a 6%.</small></label>
      <label class="campo"><span>Custo da dívida antes do IR (% a.a.)</span><input type="number" step="0.1" data-w="kd" value="${W.kd}">
        <small class="sub-tk">${W.kdAviso ? "A conta despesa financeira ÷ dívida deu um número fora do comum; usado juro livre de risco + 2." : "Despesas financeiras (12m, DRE 3.06.02) ÷ dívida bruta."}</small></label>
      <label class="campo"><span>IR + CSLL (%)</span><input type="number" step="1" data-w="ir" value="${W.ir}">
        <small class="sub-tk">Alíquota nominal de 34% (lucro real).</small></label>
    </div>
    <div id="wacc-res">${htmlWACCRes()}</div>
  </div>`;
}

function htmlMercadoDCF(x, pctTerm) {
  const c = calcWACC(), r = PREM.r / 100, g = PREM.g / 100;
  const outro = calcularDCF({ ...PREM, meio: !PREM.meio }, DCF);
  const efeitoMeio = outro.porAcao && x.porAcao ? (x.porAcao / outro.porAcao - 1) * 100 * (PREM.meio ? 1 : -1) : null;
  const multPerp = r > g ? 1 / (r - g) : null;
  const tvAlto = pctTerm !== null && pctTerm > 75;
  return `<details class="bloco mercado-faz"><summary><span class="mf-tag">Como o mercado faz</span> O que um analista conferiria neste DCF</summary>
    <ul>
      <li><strong>Taxa de desconto.</strong> ${PREM.modoR === "wacc"
        ? `Você está usando o WACC de ${nf(1).format(c.valor)}%, como nos relatórios. O β e o prêmio de risco são as premissas mais discutidas: mude o prêmio em 1 ponto e veja a tabela de sensibilidade.`
        : `Você digitou ${nf(1).format(PREM.r)}%. Pelo WACC com os insumos padrão, a taxa seria ${nf(1).format(c.valor)}%. Relatórios de análise justificam a taxa assim, item por item.`}</li>
      <li><strong>Peso da perpetuidade.</strong> O valor terminal é ${nf(0).format(pctTerm)}% do valor da empresa. ${tvAlto
        ? "Acima de ~75%, o resultado depende quase só do que acontece depois do período projetado: analistas alongam a projeção (10 anos) ou usam um segundo estágio de crescimento."
        : "Está numa faixa comum em relatórios (50% a 75%)."}</li>
      <li><strong>Conferência por múltiplos.</strong> A perpetuidade equivale a pagar ${multPerp ? nf(1).format(multPerp) + " vezes" : "—"} o caixa do ano ${PREM.anos + 1},
        e o valor da empresa é ${x.fcl0 > 0 ? nf(1).format(x.ev / x.fcl0) + " vezes" : "—"} o FCL atual. O mercado sempre compara o DCF com múltiplos de empresas parecidas
        (EV/EBITDA, P/L): se o DCF implica um múltiplo muito acima dos pares, alguma premissa está otimista.</li>
      <li><strong>Convenção do meio do ano.</strong> ${PREM.meio ? "Ligada" : "Desligada"}: ${efeitoMeio !== null ? `ela muda o valor por ação em cerca de ${nf(1).format(Math.abs(efeitoMeio))}%` : "—"}. É o padrão em bancos e casas de análise.</li>
      <li><strong>Projeção por partes.</strong> Aqui projetamos o FCL inteiro. Analistas projetam receita, margem, impostos, investimentos (capex) e capital de giro, ano a ano,
        em 2 ou 3 estágios, e apresentam cenários (base, otimista, pessimista) com probabilidades.</li>
    </ul>
    <p class="dica">Leia mais em Estudos: <button type="button" class="link" data-artigo="dcf">DCF</button> ·
      <button type="button" class="link" data-artigo="taxa-desconto">taxa de desconto</button> · <button type="button" class="link" data-artigo="capm">CAPM</button></p>
  </details>`;
}

document.addEventListener("click", (ev) => {
  const b = ev.target.closest("#resultado-dcf [data-artigo]");
  if (b) { mostrarAba("estudos"); abrirEstudo(b.dataset.artigo); }
});

// ---------- Monte Carlo: faixa de valores com as MESMAS premissas e o MESMO cálculo do DCF acima ----------
// Média de cada premissa = o valor escolhido nos controles. Só a incerteza (desvio) é sorteada:
//   crescimento: desvio do crescimento anual da receita (CVM) nos últimos anos; sem histórico, 3 pontos (premissa)
//   taxa: faixa usual do prêmio de risco (4% a 6%, ±1 ponto) × β ajustado × peso das ações no WACC
//   g: 0,5 ponto (premissa); taxa e g sorteados juntos (correlação 0,5), porque os dois carregam a inflação
const MC = { n: 4000, sc: null, sr: null, sg: 0.5, rho: 0.5 };

function normalMC(rng) { let u = 0, v = 0; while (u === 0) u = rng(); while (v === 0) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
function sementeMC(s) { return () => ((s = Math.imul(48271, s) % 2147483647) & 2147483647) / 2147483647; }

function desviosMC(d) {
  const cr = d.crescimento_receita || {};
  const hist = cr.desvio != null ? Math.min(Math.max(cr.desvio, 1), 15) : null;
  let srAuto = 1, srFonte = "premissa: ±1 ponto";
  if (PREM.modoR === "wacc" && WACC_IN) {
    const c = calcWACC();
    srAuto = c.beta * 1 * (PREM.metodo === "fcfe" ? 1 : c.pe);
    srFonte = `prêmio de risco 4% a 6% (±1 ponto) × β ${nf(2).format(c.beta)}${PREM.metodo === "fcfe" ? "" : ` × ${pct(c.pe * 100, 0)} em ações`}`;
  }
  return {
    sc: MC.sc ?? hist ?? 3, scFonte: MC.sc != null ? "digitado" : hist != null ? `desvio do crescimento da receita em ${cr.n} anos (CVM)` : "premissa: histórico curto",
    sr: MC.sr ?? +srAuto.toFixed(2), srFonte: MC.sr != null ? "digitado" : srFonte,
    sg: MC.sg, rho: MC.rho,
  };
}

function simularMC(d) {
  const D = desviosMC(d), rng = sementeMC(42), out = [], ent = { c: [], r: [], g: [] };
  for (let i = 0; i < MC.n; i++) {
    let c, r, g, k = 0;
    do {  // r precisa ficar pelo menos 1 ponto acima de g; sorteia de novo se não ficar
      const z1 = normalMC(rng), z2 = normalMC(rng), z3 = normalMC(rng);
      g = PREM.g + D.sg * z1;
      r = PREM.r + D.sr * (D.rho * z1 + Math.sqrt(1 - D.rho ** 2) * z2);
      c = PREM.cresc + D.sc * z3;
    } while (r - g < 1 && ++k < 20);
    if (r - g < 1) continue;
    const v = calcularDCF({ ...PREM, cresc: c, r, g }, d).porAcao;
    if (v == null || !isFinite(v)) continue;
    out.push(v); ent.c.push(c); ent.r.push(r); ent.g.push(g);
  }
  return { out, ent, D };
}

function correlMC(a, b) {
  const n = a.length, ma = a.reduce((s, x) => s + x, 0) / n, mb = b.reduce((s, x) => s + x, 0) / n;
  let c = 0, va = 0, vb = 0;
  for (let i = 0; i < n; i++) { c += (a[i] - ma) * (b[i] - mb); va += (a[i] - ma) ** 2; vb += (b[i] - mb) ** 2; }
  return va && vb ? c / Math.sqrt(va * vb) : 0;
}

function histogramaMC(vals, preco) {
  const ord = [...vals].sort((a, b) => a - b), q = (p) => ord[Math.floor(p * (ord.length - 1))];
  const lo = q(0.01), hi = q(0.99), nb = 32, w = (hi - lo) / nb || 1, bins = Array(nb).fill(0);
  vals.forEach((v) => { if (v >= lo && v <= hi) bins[Math.min(nb - 1, Math.floor((v - lo) / w))]++; });
  const W = 640, H = 150, m = { l: 8, r: 8, t: 8, b: 22 }, mx = Math.max(...bins);
  const X = (v) => m.l + ((v - lo) / (hi - lo || 1)) * (W - m.l - m.r), bw = (W - m.l - m.r) / nb;
  const barras = bins.map((b, i) => { const x0 = lo + i * w, h = (b / mx) * (H - m.t - m.b);
    return `<rect x="${m.l + i * bw + 1}" y="${H - m.b - h}" width="${bw - 2}" height="${h}" fill="${x0 + w / 2 >= preco ? "var(--c3)" : "var(--c8)"}" opacity=".75"/>`; }).join("");
  const fora = preco > hi ? `<text x="${W - m.r}" y="${m.t + 10}" text-anchor="end" class="mc-rot">preço ${brl2(preco)} →</text>`
    : preco < lo ? `<text x="${m.l}" y="${m.t + 10}" class="mc-rot">← preço ${brl2(preco)}</text>` : "";
  const p = fora || preco >= lo && preco <= hi ? fora || `<line x1="${X(preco)}" x2="${X(preco)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--text)" stroke-width="1.5" stroke-dasharray="4 3"/>
    <text x="${X(preco)}" y="${H - 6}" text-anchor="middle" class="mc-rot">preço ${brl2(preco)}</text>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" class="mc-hist" role="img" aria-label="Distribuição do valor justo">${barras}${p}
    <text x="${m.l}" y="${H - 6}" class="mc-rot">${brl2(lo)}</text><text x="${W - m.r}" y="${H - 6}" text-anchor="end" class="mc-rot">${brl2(hi)}</text></svg>`;
}

function htmlMC(d) {
  const { out, ent, D } = simularMC(d), preco = d.rastreio.preco.valor;
  if (out.length < 100) return "";
  const ord = [...out].sort((a, b) => a - b), q = (p) => ord[Math.floor(p * (ord.length - 1))];
  const acima = out.filter((v) => v > preco).length / out.length * 100;
  const peso = [["Crescimento", correlMC(ent.c, out)], ["Taxa de desconto", correlMC(ent.r, out)], ["g", correlMC(ent.g, out)]]
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const campo = (k, v, passo, rot, fonte) => `<label class="mc-campo"><span>${rot}</span><input type="number" step="${passo}" class="mc-in" data-mc="${k}" value="${v}"><small>${esc(fonte)}</small></label>`;
  return `<div class="bloco mc">
    <h2>Faixa de valores (Monte Carlo)</h2>
    <div class="mc-kpis">
      <div><span>80% dos cenários entre</span><b>${brl2(q(0.1))} e ${brl2(q(0.9))}</b></div>
      <div><span>Mediana</span><b>${brl2(q(0.5))}</b></div>
      <div><span>Cenários acima do preço</span><b>${pct(acima, 0)}</b></div>
    </div>
    ${histogramaMC(out, preco)}
    <p class="mc-peso">O que mais move o resultado: ${peso.map(([n, c]) => `<b>${n}</b> (${nf(2).format(Math.abs(c))})`).join(" · ")}</p>
    <details class="dcf-det" id="mc-det" ${DCF_MC_ABERTO ? "open" : ""}><summary>Incerteza usada (${nf(0).format(out.length)} sorteios)</summary>
      <div class="mc-campos">
        ${campo("sc", +D.sc.toFixed(2), 0.5, "Crescimento: desvio (pontos)", D.scFonte)}
        ${campo("sr", +D.sr.toFixed(2), 0.25, "Taxa: desvio (pontos)", D.srFonte)}
        ${campo("sg", D.sg, 0.25, "g: desvio (pontos)", "premissa")}
        ${campo("rho", D.rho, 0.1, "Correlação taxa × g", "premissa: as duas carregam a inflação")}
      </div>
      <p class="dica">Cada premissa é sorteada em torno do valor escolhido nos controles acima, com o mesmo cálculo do DCF. A fração acima do preço não é a chance de a ação subir: é a fração das suas premissas sorteadas em que o DCF supera o preço.</p>
    </details>
  </div>`;
}

function ligarMC() {
  $("#mc-det")?.addEventListener("toggle", (ev) => { DCF_MC_ABERTO = ev.target.open; });
  document.querySelectorAll(".mc-in").forEach((i) => i.addEventListener("change", () => {
    const v = i.value === "" ? null : +i.value;
    MC[i.dataset.mc] = i.dataset.mc === "rho" ? Math.max(-0.95, Math.min(0.95, v ?? 0.5)) : v == null ? null : Math.max(0, v);
    renderPassos();
  }));
}
