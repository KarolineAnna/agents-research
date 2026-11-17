// Aba "Modelos": carteira robusta e GARCH. (O Monte Carlo fica dentro do DCF, em dcf.js; as anomalias, na Saúde dos dados.)
// Todo modelo aparece ao lado de uma referência simples e com o teste fora da amostra.

let MOD_VISAO = "carteira";
const MOD = { carteira: null, garch: null };
const COR_MET = { iguais: "--text", classico: "--c2", lw: "--c1", minvar_lw: "--c3", hrp: "--c7" };

document.querySelectorAll("[data-mod]").forEach((b) => b.addEventListener("click", () => {
  MOD_VISAO = b.dataset.mod;
  document.querySelectorAll("[data-mod]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  renderMod();
}));

function formMod(id, valor, rotulo, extra = "", classe = "") {
  return `<form id="${id}" class="form-linha mod-form">
    <input id="${id}-in" type="text" value="${esc(valor)}" autocomplete="off" spellcheck="false">
    <button type="button" class="secundario" data-seletor="#${id}-in" ${classe ? `data-classe="${classe}"` : ""}>＋ Escolher da lista</button>
    ${extra}<button type="submit">${rotulo}</button></form>
    <p id="${id}-st" class="status" role="status"></p><div id="${id}-res"></div>`;
}

function renderMod() {
  const v = MOD_VISAO;
  if (v === "estudos") { $("#resultado-mod").innerHTML = htmlEstudosModelos(); ligarEstudosModelos(); return; }
  const html = {
    carteira: `<p class="dica formatos">Compara 5 jeitos de montar a carteira e testa cada um <strong>fora da amostra</strong>: a cada mês, estima com o ano anterior e mede o resultado no mês seguinte.</p>
      ${formMod("mc-cart", "PETR4, VALE3, ITUB4, WEGE3, BBAS3, BOVA11", "Rodar", `<select id="mc-cart-per" class="mini"><option value="3y">3 anos</option><option value="5y" selected>5 anos</option></select>
      <input id="mc-cart-max" class="mini" type="number" min="5" max="100" value="40" title="Peso máximo por ativo (%)">`)}`,
    garch: `<p class="dica formatos">Prevê a volatilidade com GARCH(1,1) e compara, fora da amostra, com a volatilidade histórica de 21 dias.</p>${formMod("mc-garch", "PETR4", "Rodar")}`,
  }[v];
  $("#resultado-mod").innerHTML = `<div class="viz dcf">${html}</div>`;
  document.querySelectorAll("#resultado-mod [data-seletor]").forEach((b) =>
    b.addEventListener("click", () => abrirSeletor(b.dataset.seletor, b.dataset.classe)));
  const ligar = { carteira: ["mc-cart", rodarCarteira], garch: ["mc-garch", rodarGarch] }[v];
  $(`#${ligar[0]}`).addEventListener("submit", (e) => { e.preventDefault(); ligar[1](); });
  if (MOD[v]) ({ carteira: mostrarCarteira, garch: mostrarGarch })[v]();
}

async function chamar(id, url, msg) {
  const st = $(`#${id}-st`);
  st.className = "status"; st.textContent = msg;
  try { const r = await api(url); st.textContent = ""; return r; }
  catch (err) { st.className = "status erro"; st.textContent = err.message; return null; }
}

function graficoLinhas(el, datas, series, { formatoY = (v) => nf(0).format(v), base = null, marcaX = null } = {}) {
  const W = el.clientWidth, H = W < 560 ? 280 : 340, m = { t: 12, r: 16, b: 30, l: 52 };
  const n = datas.length;
  const todos = series.flatMap((s) => s.v).filter((x) => x !== null);
  let y0 = Math.min(...todos, base ?? Infinity), y1 = Math.max(...todos, base ?? -Infinity);
  const pad = (y1 - y0) * 0.06 || 1; y0 -= pad; y1 += pad;
  const X = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r), Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  const gy = ticks(y0, y1, 5);
  const anos = []; datas.forEach((d, i) => { if (i === 0 || d.slice(0, 4) !== datas[i - 1].slice(0, 4)) { if (anos.length && X(i) - X(anos.at(-1)) < 44) anos.pop(); anos.push(i); } });
  const svg = [`<g class="grade">${gy.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/>`).join("")}</g>`,
    `<g class="eixo">${gy.map((v) => `<text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${formatoY(v)}</text>`).join("")}
     ${anos.map((i) => `<text x="${X(i)}" y="${H - m.b + 18}" text-anchor="middle">${datas[i].slice(0, 4)}</text>`).join("")}</g>`];
  if (base !== null) svg.push(`<line x1="${m.l}" x2="${W - m.r}" y1="${Y(base)}" y2="${Y(base)}" stroke="var(--muted)"/>`);
  if (marcaX !== null) { const i = datas.findIndex((d) => d >= marcaX); if (i >= 0) svg.push(`<rect x="${X(i)}" y="${m.t}" width="${W - m.r - X(i)}" height="${H - m.t - m.b}" fill="var(--surface-2)" opacity=".6"/><text class="titulo-eixo" x="${X(i) + 6}" y="${m.t + 14}">fora da amostra</text>`); }
  series.forEach((s) => {
    let d = "", ab = false;
    s.v.forEach((v, i) => { if (v === null) { ab = false; return; } d += `${ab ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; ab = true; });
    svg.push(`<path d="${d}" fill="none" stroke="var(${s.cor})" stroke-width="${s.largura || 2}" ${s.tracejada ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin="round"/>`);
  });
  svg.push(`<line class="cursor" y1="${m.t}" y2="${H - m.b}" stroke="var(--muted)" visibility="hidden"/><rect class="alvo" x="${m.l}" y="0" width="${W - m.l - m.r}" height="${H}"/>`);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img">${svg.join("")}</svg><div class="tooltip" hidden></div>`;
  const camada = el.querySelector(".alvo"), tip = el.querySelector(".tooltip"), cur = el.querySelector(".cursor");
  camada.addEventListener("mousemove", (ev) => {
    const r = camada.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((ev.clientX - r.left) / r.width) * (n - 1))));
    cur.setAttribute("x1", X(i)); cur.setAttribute("x2", X(i)); cur.setAttribute("visibility", "visible");
    tip.innerHTML = `<strong>${dataBR(datas[i])}</strong>` + series.filter((s) => s.v[i] !== null).sort((a, b) => b.v[i] - a.v[i])
      .map((s) => `<div><span><i class="ponto" style="background:var(${s.cor})"></i>${esc(s.nome)}</span><b>${formatoY(s.v[i])}</b></div>`).join("");
    tip.hidden = false;
    tip.style.left = `${X(i) + 12 + tip.offsetWidth > W ? X(i) - tip.offsetWidth - 12 : X(i) + 12}px`; tip.style.top = `${m.t}px`;
  });
  camada.addEventListener("mouseleave", () => { tip.hidden = true; cur.setAttribute("visibility", "hidden"); });
}

// =====================================================================
// 1. CARTEIRA ROBUSTA
// =====================================================================
async function rodarCarteira() {
  const q = new URLSearchParams({ tickers: $("#mc-cart-in").value, periodo: $("#mc-cart-per").value, peso_max: $("#mc-cart-max").value });
  const r = await chamar("mc-cart", `/api/modelos/carteira?${q}`, "Baixando preços, otimizando cada janela e reamostrando… pode levar até um minuto.");
  if (r) { MOD.carteira = r; mostrarCarteira(); }
}

function mostrarCarteira() {
  const c = MOD.carteira, p = c.parametros, M = Object.keys(c.metodos), B = c.backtest;
  const melhor = M.reduce((a, m) => ((B[m].sharpe ?? -9) > (B[a].sharpe ?? -9) ? m : a), M[0]);
  const linhasBT = M.map((m) => `<tr><td><i class="ponto" style="background:var(${COR_MET[m]})"></i> ${esc(c.metodos[m])}</td>
    <td>${pct(B[m].retorno, 1)}</td><td>${pct(B[m].volatilidade, 1)}</td><td><strong>${num(B[m].sharpe)}</strong></td>
    <td class="neg">${pct(B[m].max_drawdown, 1)}</td><td>${pct(B[m].giro_medio, 1)}</td>
    <td>${m === "iguais" ? "referência" : B[m].ganha_da_referencia ? `<span class="tag">ganha</span>` : `<span class="tag perde">perde</span>`}</td></tr>`).join("");
  const est = c.estabilidade;
  const faixa = (m, t) => { const f = est[m].faixas[t]; return `<div class="faixa" title="5%: ${nf(1).format(f.p5)}% · mediana ${nf(1).format(f.p50)}% · 95%: ${nf(1).format(f.p95)}%">
    <i style="left:${f.p5}%;width:${Math.max(f.p95 - f.p5, 0.8)}%;background:var(${COR_MET[m]})"></i><b style="left:${f.p50}%"></b></div>`; };

  $("#mc-cart-res").innerHTML = `
    <div class="dados-usados"><span class="pill">${dataBR(p.inicio)} a ${dataBR(p.fim)} · ${p.dias} dias</span>
      <span class="pill">Janela de estimação: ${p.janela} dias · rebalanceia a cada ${p.rebal} dias</span>
      <span class="pill">Taxa livre de risco: ${pct(p.rf)} ${p.rf_fonte ? "(CDI, Banco Central)" : ""}</span>
      <span class="pill">Peso máximo: ${pct(p.peso_max, 0)} (o HRP não usa limite)</span></div>

    ${passo(1, "O teste que importa: fora da amostra", `
      <p>Cada método só usou dados <strong>anteriores</strong> a cada mês para decidir os pesos, e foi avaliado no mês seguinte. É o que você teria vivido de verdade.
        A referência é dividir igualmente: um método só vale a pena se ganhar dela.</p>
      <div class="legenda">${M.map((m) => `<span><i class="linha" style="background:var(${COR_MET[m]})"></i>${esc(c.metodos[m])}</span>`).join("")}</div>
      <div class="grafico" id="mc-bt"></div>
      <div class="tabela-scroll"><table><thead><tr><th>Método</th><th>Retorno a.a.</th><th>Volatilidade</th><th>Sharpe</th><th>Pior queda</th><th>Giro por rebalanceamento</th><th>× pesos iguais</th></tr></thead>
        <tbody>${linhasBT}</tbody></table></div>
      <p class="dica">Melhor Sharpe fora da amostra neste período: <strong>${esc(c.metodos[melhor])}</strong>. "Giro" é quanto da carteira muda a cada rebalanceamento; giro alto = mais custo de corretagem e impostos, que não estão descontados aqui.</p>`)}

    ${passo(2, "Estabilidade: os pesos mudam se os dados mudarem um pouco?", `
      <p>Reamostramos ${p.n_boot} vezes os dias do último ano (bootstrap) e otimizamos de novo. A barra mostra a faixa onde ficaram 90% dos pesos de cada ativo;
        o traço é a mediana. <strong>Faixa larga = o método é sensível ao ruído</strong> e o peso que ele dá hoje não é confiável.</p>
      <div class="tabela-scroll"><table class="estab"><thead><tr><th>Ativo</th>${Object.keys(est).map((m) => `<th>${esc(c.metodos[m])}</th>`).join("")}</tr></thead>
        <tbody>${c.tickers.map((t) => `<tr><td><strong>${esc(t)}</strong></td>${Object.keys(est).map((m) => `<td>${faixa(m, t)}</td>`).join("")}</tr>`).join("")}
        <tr class="soma"><td>Instabilidade média (desvio dos pesos)</td>${Object.keys(est).map((m) => `<td><strong>${nf(1).format(est[m].instabilidade)} p.p.</strong></td>`).join("")}</tr></tbody></table></div>`)}

    ${passo(3, "Pesos sugeridos hoje por cada método", `
      <div class="tabela-scroll"><table><thead><tr><th>Ativo</th>${M.map((m) => `<th>${esc(c.metodos[m])}</th>`).join("")}</tr></thead>
        <tbody>${c.tickers.map((t) => `<tr><td><strong>${esc(t)}</strong></td>${M.map((m) => `<td>${pct(c.atual[m][t], 1)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="dica">Fontes dos preços: ${c.tickers.map((t) => `${esc(t)} ${(c.fontes[t] || []).map((f) => `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.fonte)} ↗</a>`).join(" + ")}`).join(" · ")}</p>`)}

    <h2 style="margin:28px 0 12px">Entenda os métodos</h2>
    <div class="conceitos">
      <div class="bloco"><h3>Ledoit-Wolf</h3><div class="eq">Σ* = δ·F + (1 − δ)·S</div><p>Mistura a covariância medida (S) com uma estrutura simples (F). O δ é escolhido pelos dados: quanto menos dados, mais "encolhe". Reduz os pesos extremos que o ruído cria.</p></div>
      <div class="bloco"><h3>Mínima variância</h3><div class="eq">mín wᵀΣw</div><p>Ignora o retorno esperado, que é o número mais difícil de estimar. Costuma ser mais estável que o máximo Sharpe.</p></div>
      <div class="bloco"><h3>HRP</h3><div class="eq">clusters → bissecção recursiva</div><p>Agrupa ativos que andam juntos (clustering hierárquico pela correlação) e divide o risco entre os grupos, sem inverter a matriz de covariância.</p></div>
      <div class="bloco"><h3>Walk-forward</h3><div class="eq">estima em [t−${p.janela}, t) · aplica em [t, t+${p.rebal})</div><p>Simula o uso real: nunca usa informação do futuro. É a forma honesta de comparar modelos.</p></div>
    </div>`;
  graficoLinhas($("#mc-bt"), c.datas, M.map((m) => ({ nome: c.metodos[m], cor: COR_MET[m], v: B[m].curva, largura: m === "iguais" ? 2.5 : 2, tracejada: m === "iguais" })), { base: 100 });
}

// =====================================================================
// 2. GARCH
// =====================================================================
async function rodarGarch() {
  const r = await chamar("mc-garch", `/api/modelos/garch/${encodeURIComponent($("#mc-garch-in").value.split(",")[0].trim())}`, "Estimando o GARCH…");
  if (r) { MOD.garch = r; mostrarGarch(); }
}

function mostrarGarch() {
  const g = MOD.garch, p = g.parametros, t = g.teste;
  const venceu = t.vencedor_qlike === "garch";
  $("#mc-garch-res").innerHTML = `
    <div class="empresa"><h2>${esc(g.ticker)}</h2><span class="tk">${esc(g.nome)}</span></div>
    <p class="dica">Preços: ${(g.fontes || []).map((f) => `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.fonte)} ↗</a>`).join(" + ")}</p>

    ${passo(1, "A ideia: a volatilidade vem em ondas", `
      <p>Dias agitados costumam vir seguidos de dias agitados. O GARCH(1,1) prevê a variância de amanhã a partir de três partes:</p>
      <div class="eq">σ²ₜ₊₁ = ω + α·r²ₜ + β·σ²ₜ</div>
      <div class="eq">σ²ₜ₊₁ = ${nf(4).format(p.omega)} + ${nf(3).format(p.alpha)}·(choque de hoje)² + ${nf(3).format(p.beta)}·(variância de hoje)</div>
      <div class="indicadores-bp">
        <div class="kpi-bp"><span>α · reação a choques</span><b>${nf(3).format(p.alpha)}</b><p>Quanto um dia forte de hoje aumenta a previsão de amanhã.</p></div>
        <div class="kpi-bp"><span>β · memória</span><b>${nf(3).format(p.beta)}</b><p>Quanto da volatilidade de hoje continua amanhã.</p></div>
        <div class="kpi-bp"><span>Persistência (α + β)</span><b>${nf(3).format(p.persistencia)}</b><p>${p.meia_vida ? `Um choque perde metade do efeito em ~${nf(0).format(p.meia_vida)} dias.` : "Persistência ≥ 1: o modelo não volta à média."}</p></div>
        <div class="kpi-bp"><span>Volatilidade de longo prazo</span><b>${pct(p.vol_longo_prazo, 1)}</b><code>√(ω ÷ (1 − α − β)) anualizado</code><p>O nível para onde o modelo puxa a volatilidade.</p></div>
      </div>`)}

    ${passo(2, "Ganhou da volatilidade histórica fora da amostra?", `
      <p>Os parâmetros foram estimados só com os dados até ${dataBR(t.inicio)}. Depois, para cada um dos ${t.dias} dias seguintes, os dois métodos previram a variância do dia,
        e comparamos com o que aconteceu (retorno ao quadrado).</p>
      <div class="tabela-scroll"><table><thead><tr><th>Método</th><th>Erro QLIKE (menor = melhor)</th><th>Erro quadrático médio</th></tr></thead><tbody>
        <tr><td>GARCH(1,1)</td><td><strong>${nf(4).format(t.garch.qlike)}</strong></td><td>${nf(3).format(t.garch.mse)}</td></tr>
        <tr><td>Histórica de 21 dias (referência)</td><td><strong>${nf(4).format(t.historica.qlike)}</strong></td><td>${nf(3).format(t.historica.mse)}</td></tr>
      </tbody></table></div>
      <div class="aviso-box ${venceu ? "ok-box" : ""}">${venceu ? "✓ O GARCH previu melhor que a média histórica neste período (pelo critério QLIKE, o mais usado para volatilidade)."
        : "✗ Neste ativo e período, o GARCH <strong>não</strong> ganhou da volatilidade histórica simples. Use a histórica."}</div>`)}

    ${passo(3, "Previsão para os próximos dias", `
      <div class="veredito"><div><span>Volatilidade prevista para amanhã (anualizada)</span><b>${pct(g.previsao.amanha, 1)}</b></div>
        <div><span>Média prevista nos próximos 21 dias úteis</span><b>${pct(g.previsao.media_21d, 1)}</b></div>
        <div><span>Histórica dos últimos 21 dias</span><b>${pct(g.previsao.hist_21d, 1)}</b></div></div>
      <p class="dica">Você pode usar a média de 21 dias como σ no Black-Scholes (aba Derivativos → "Outra…").</p>
      <div class="legenda"><span><i class="linha" style="background:var(--c1)"></i>GARCH (volatilidade condicional)</span><span><i class="linha tracejada"></i>Histórica 21 dias</span></div>
      <div class="grafico" id="mc-garch-g"></div>`)}`;
  graficoLinhas($("#mc-garch-g"), g.grafico.datas, [
    { nome: "GARCH", cor: "--c1", v: g.grafico.garch },
    { nome: "Histórica 21d", cor: "--muted", v: g.grafico.hist21, tracejada: true }], { formatoY: (v) => nf(0).format(v) + "%", marcaX: g.grafico.inicio_teste });
}

// =====================================================================
// 4. PARES E ANOMALIAS
// =====================================================================
renderMod();
