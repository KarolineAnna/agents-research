// Aba Indicadores, detalhe de um ativo: "Cara ou barata?" (três lentes) e gráfico de preço ao longo dos anos.
// Os dois blocos carregam depois do detalhe, sem travar o resto da tela.
let GRAF = null;               // última resposta de /api/preco
let GRAF_VISAO = "preco";      // "preco" (R$) ou "base100" (retorno total contra o Ibovespa)
let GRAF_PERIODO = "5y";
const NOME_LEITURA = { barata: "Barata", justa: "No preço", cara: "Cara", mista: "Sinais mistos" };

function extrasAtivo(e) {
  const alvo = $("#acao-extra");
  if (!alvo || e.erro || !["acao", "fii", "mercado"].includes(e.tipo)) return;
  const b3 = /^[A-Z]{4}\d{1,2}$/.test(e.ticker);
  alvo.innerHTML = `
    ${e.tipo === "acao" ? `<div class="bloco cb-bloco" id="cb-bloco"><h2>Cara ou barata?</h2><p class="status">Calculando as três lentes… na primeira vez o site baixa balanços antigos da CVM e os pares do setor.</p></div>` : ""}
    ${b3 ? `<div class="bloco" id="gp-bloco"><h2>Preço ao longo dos anos</h2><p class="status">Carregando o histórico…</p></div>` : ""}`;
  if (e.tipo === "acao") carregarCaraBarata(e.ticker);
  if (b3) carregarGraficoPreco(e.ticker);
}

// ---------- Cara ou barata ----------
async function carregarCaraBarata(tk) {
  const el = $("#cb-bloco");
  try {
    const r = await api(`/api/valuation/${encodeURIComponent(tk)}`);
    if ($("#cb-bloco") !== el) return; // o usuário já abriu outro ativo
    el.innerHTML = htmlCaraBarata(r);
  } catch (err) {
    el.innerHTML = `<h2>Cara ou barata?</h2><p class="status erro">${esc(err.message)}</p>`;
  }
}

function fmtMult(v) { return v == null ? "n/d" : nf(2).format(v) + "x"; }

function htmlCaraBarata(r) {
  const v = r.veredito || "sem";
  const lentes = r.lentes.map((l) => {
    const ehPreco = l.id === "justo";
    const atual = ehPreco ? fmt(l.atual, "R$/ação") : fmtMult(l.atual);
    const ref = ehPreco ? fmt(l.referencia, "R$/ação") : fmtMult(l.referencia);
    return `<div class="cb-lente cb-${l.leitura || "sem"}">
      <div class="cb-lente-topo"><span>${esc(l.nome)}</span><b>${l.leitura ? NOME_LEITURA[l.leitura] : "Sem dados"}</b></div>
      <div class="cb-conta">${ehPreco ? "Preço" : "Hoje"} <b>${atual}</b> · ${esc(l.rotulo_ref)} <b>${ref}</b> · ${ehPreco ? "potencial" : "diferença"} <b>${fmtDif(l.diferenca)}</b></div>
      ${l.detalhe ? `<p class="dica">${esc(l.detalhe)}</p>` : ""}
    </div>`;
  }).join("");

  const hist = r.historico.length ? `<details class="cb-det"><summary>Múltiplos nos fins de ano (${r.historico.length})</summary>
    <div class="tabela-scroll"><table><thead><tr><th>Ano</th><th class="num">Preço</th><th class="num">Lucro</th><th class="num">PL</th><th class="num">P/L</th><th class="num">P/VP</th><th>Documento</th></tr></thead>
    <tbody>${r.historico.map((h) => `<tr><td>${h.ano}</td><td class="num">${fmt(h.preco, "R$/ação")}</td><td class="num">${fmt(h.lucro, "R$")}</td>
      <td class="num">${fmt(h.pl, "R$")}</td><td class="num">${fmtMult(h.p_l)}</td><td class="num">${fmtMult(h.p_vp)}</td><td>${esc(h.documento)}</td></tr>`).join("")}
    <tr class="cb-hoje"><td>Hoje</td><td class="num">${fmt(r.preco, "R$/ação")}</td><td></td><td></td><td class="num">${fmtMult(r.multiplos.p_l)}</td><td class="num">${fmtMult(r.multiplos.p_vp)}</td><td>Aba Indicadores</td></tr></tbody></table></div>
    <p class="dica">Múltiplo de cada ano = múltiplo de hoje × (preço no fim do ano ÷ preço de hoje) × (lucro ou PL de hoje ÷ lucro ou PL do ano). Supõe a mesma quantidade de ações; recompras e emissões grandes distorcem a conta.</p></details>` : "";

  const pares = (r.pares.pares || []).length ? `<details class="cb-det"><summary>Pares usados (${esc(r.pares.criterio || "")})</summary>
    <div class="tabela-scroll"><table><thead><tr><th>Ativo</th><th class="num">P/L</th><th class="num">P/VP</th></tr></thead>
    <tbody>${r.pares.pares.map((p) => `<tr><td><strong>${esc(p.ticker)}</strong>${p.empresa ? `<span class="sub-tk">${esc(p.empresa)}</span>` : ""}</td>
      ${p.erro ? `<td colspan="2" class="erro">${esc(p.erro)}</td>` : `<td class="num">${fmtMult(p.p_l)}</td><td class="num">${fmtMult(p.p_vp)}</td>`}</tr>`).join("")}
    <tr class="cb-hoje"><td>Mediana</td><td class="num">${fmtMult(r.pares.mediana_p_l)}</td><td class="num">${fmtMult(r.pares.mediana_p_vp)}</td></tr></tbody></table></div></details>` : "";

  const cen = (r.preco_justo.cenarios || []).filter((c) => (c.por_acao ?? c.valor) != null);
  const justo = cen.length ? `<details class="cb-det"><summary>Cenários do preço justo</summary>
    <div class="tabela-scroll"><table><thead><tr><th>Cenário</th>${cen[0].r != null ? `<th class="num">Peso</th><th class="num">Crescimento</th><th class="num">Taxa (r)</th><th class="num">g</th>` : ""}<th class="num">Preço justo</th></tr></thead>
    <tbody>${cen.map((c) => `<tr><td>${esc(c.nome[0].toUpperCase() + c.nome.slice(1))}</td>${c.r != null ? `<td class="num">${pct(c.peso, 0)}</td><td class="num">${pct(c.cresc, 1)}</td><td class="num">${pct(c.r, 1)}</td><td class="num">${pct(c.g, 2)}</td>` : ""}
      <td class="num">${fmt(c.por_acao ?? c.valor, "R$/ação")}</td></tr>`).join("")}</tbody></table></div></details>` : "";

  return `<h2>Cara ou barata?</h2>
    <div class="cb-veredito cb-${v}">
      <span class="cb-selo">${r.veredito ? NOME_LEITURA[r.veredito] : "Sem leitura"}</span>
      <p>${esc(r.texto)}</p>
    </div>
    <div class="cb-lentes">${lentes}</div>
    ${(r.avisos || []).map((a) => `<div class="aviso-box">⚠ ${esc(a)}</div>`).join("")}
    ${hist}${pares}${justo}
    <p class="dica">${esc(r.regra)}</p>`;
}

// ---------- Gráfico de preço ----------
async function carregarGraficoPreco(tk, periodo = GRAF_PERIODO) {
  const el = $("#gp-bloco");
  if (!el) return;
  GRAF_PERIODO = periodo;
  el.querySelector(".gp-corpo")?.classList.add("carregando");
  try {
    const r = await api(`/api/preco/${encodeURIComponent(tk)}?periodo=${periodo}`);
    if ($("#gp-bloco") !== el) return;
    GRAF = r;
    renderGraficoPreco();
  } catch (err) {
    el.innerHTML = `<h2>Preço ao longo dos anos</h2><p class="status erro">${esc(err.message)}</p>`;
  }
}

function renderGraficoPreco() {
  const r = GRAF, s = r.estatisticas, el = $("#gp-bloco");
  const temIbov = !!r.ibov_base100;
  if (!temIbov && GRAF_VISAO === "base100") GRAF_VISAO = "preco";
  const per = Object.entries({ "1y": "1 ano", "5y": "5 anos", "10y": "10 anos", max: "Máx." })
    .map(([k, n]) => `<button type="button" data-gp-per="${k}" aria-pressed="${k === r.periodo}">${n}</button>`).join("");
  const anos = Object.entries(r.proventos_por_ano || {});
  el.innerHTML = `
    <h2>Preço ao longo dos anos</h2>
    <div class="gp-controles">
      <div class="gp-seg" role="group" aria-label="Período">${per}</div>
      <div class="gp-seg" role="group" aria-label="Visão">
        <button type="button" data-gp-visao="preco" aria-pressed="${GRAF_VISAO === "preco"}">Preço (R$)</button>
        <button type="button" data-gp-visao="base100" aria-pressed="${GRAF_VISAO === "base100"}" ${temIbov ? "" : "disabled"}>Contra o Ibovespa</button>
      </div>
    </div>
    <div class="kpis gp-kpis">
      <div><span>Preço no período</span><b class="${s.variacao_preco < 0 ? "neg" : ""}">${fmtDif(s.variacao_preco)}</b></div>
      <div><span>Retorno com proventos</span><b class="${s.retorno_total < 0 ? "neg" : ""}">${fmtDif(s.retorno_total)}</b></div>
      <div><span>Ibovespa no período</span><b class="${(s.ibov_retorno ?? 0) < 0 ? "neg" : ""}">${fmtDif(s.ibov_retorno)}</b></div>
      <div><span>Retorno ao ano</span><b>${s.retorno_anual == null ? "n/d" : fmtDif(s.retorno_anual)}</b></div>
      <div><span>Volatilidade ao ano</span><b>${s.vol_anual == null ? "n/d" : pct(s.vol_anual, 1)}</b></div>
      <div><span>Maior queda</span><b class="neg">${pct(s.drawdown_max, 1)}</b></div>
    </div>
    <div class="grafico gp-corpo" id="gp-grafico"><div class="tooltip" id="gp-tip" hidden></div></div>
    <p class="dica">${GRAF_VISAO === "preco"
      ? "Fechamento de cada dia em R$, ajustado só por desdobramentos e grupamentos. Os pontos na base marcam os proventos (data-ex)."
      : "Base 100 no primeiro dia. A linha da ação soma os proventos reinvestidos (retorno total), como o Ibovespa, que também é um índice de retorno total."}
      ${r.semanal ? " Período longo: um ponto por semana." : ""}
      Maior queda: de ${dataBR(s.drawdown_pico)} a ${dataBR(s.drawdown_data)}. Máxima ${fmt(s.maxima, "R$/ação")} em ${dataBR(s.maxima_data)}, mínima ${fmt(s.minima, "R$/ação")} em ${dataBR(s.minima_data)}.
      Fonte: <a href="${esc(r.fontes[0].url)}" target="_blank" rel="noopener">yfinance (Yahoo Finance) ↗</a>, fonte não oficial.</p>
    ${anos.length ? `<details class="cb-det"><summary>Proventos por ano (R$ por ação)</summary><div class="tabela-scroll"><table>
      <thead><tr>${anos.map(([a]) => `<th class="num">${a}</th>`).join("")}</tr></thead>
      <tbody><tr>${anos.map(([, v]) => `<td class="num">${nf(2).format(v)}</td>`).join("")}</tr></tbody></table></div></details>` : ""}`;
  el.querySelectorAll("[data-gp-per]").forEach((b) => b.addEventListener("click", () => carregarGraficoPreco(r.ticker, b.dataset.gpPer)));
  el.querySelectorAll("[data-gp-visao]").forEach((b) => b.addEventListener("click", () => { GRAF_VISAO = b.dataset.gpVisao; renderGraficoPreco(); }));
  desenharGraficoPreco();
}

function desenharGraficoPreco() {
  const r = GRAF, el = $("#gp-grafico");
  if (!el) return;
  const W = el.clientWidth, H = W < 560 ? 280 : 360;
  const m = { t: 12, r: 72, b: 30, l: 56 };
  const n = r.datas.length;
  const base = GRAF_VISAO === "base100";
  const series = base
    ? [{ id: r.ticker, cor: "var(--c1)", v: r.total_base100 }, { id: "Ibovespa", cor: "var(--muted)", v: r.ibov_base100, tracejada: true }]
    : [{ id: r.ticker, cor: "var(--c1)", v: r.fechamento }];
  const todos = series.flatMap((s) => s.v).filter((x) => x != null);
  let y0 = Math.min(...todos), y1 = Math.max(...todos);
  if (base) { y0 = Math.min(y0, 100); y1 = Math.max(y1, 100); }
  const pad = (y1 - y0) * 0.06 || 1;
  y0 -= pad; y1 += pad;
  if (!base) y0 = Math.max(0, y0);
  const X = (i) => m.l + (n > 1 ? i / (n - 1) : 0.5) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  const gy = ticks(y0, y1, 5);
  const curto = r.periodo === "1y";
  const marcas = [];
  r.datas.forEach((d, i) => {
    const chave = curto ? d.slice(0, 7) : d.slice(0, 4);
    if (i > 0 && chave === (curto ? r.datas[i - 1].slice(0, 7) : r.datas[i - 1].slice(0, 4))) return;
    if (marcas.length && X(i) - X(marcas[marcas.length - 1]) < (curto ? 40 : 38)) return;
    marcas.push(i);
  });
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const rot = (d) => curto ? MESES[+d.slice(5, 7) - 1] + (d.slice(5, 7) === "01" ? "/" + d.slice(2, 4) : "") : d.slice(0, 4);
  const fmtY = (v) => base ? nf(0).format(v) : (v >= 100 ? nf(0).format(v) : nf(2).format(v));

  const svg = [];
  svg.push(`<g class="grade">${gy.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/>`).join("")}</g>`);
  if (base) svg.push(`<line x1="${m.l}" x2="${W - m.r}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--muted)" stroke-width="1"/>`);
  svg.push(`<g class="eixo">${gy.map((v) => `<text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${base ? "" : "R$ "}${fmtY(v)}</text>`).join("")}
    ${marcas.map((i) => `<text x="${X(i)}" y="${H - m.b + 18}" text-anchor="${i === 0 ? "start" : "middle"}">${rot(r.datas[i])}</text>`).join("")}</g>`);
  // área suave sob a linha principal
  const p0 = series[0];
  const linha = (s) => s.v.map((v, i) => (v == null ? "" : `${i === 0 || s.v[i - 1] == null ? "M" : "L"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`)).join("");
  svg.push(`<path d="${linha(p0)}L${X(n - 1).toFixed(1)},${H - m.b}L${X(0).toFixed(1)},${H - m.b}Z" fill="var(--c1)" opacity=".08"/>`);
  const fins = [];
  series.slice().reverse().forEach((s) => {
    svg.push(`<path d="${linha(s)}" fill="none" stroke="${s.cor}" stroke-width="${s.tracejada ? 1.5 : 2}" stroke-linejoin="round" ${s.tracejada ? 'stroke-dasharray="5 4"' : ""}/>`);
    const u = s.v.length - 1 - [...s.v].reverse().findIndex((x) => x != null);
    if (u >= 0 && u < s.v.length) fins.push({ id: s.id, x: X(u), y: Y(s.v[u]) });
  });
  fins.sort((a, b) => a.y - b.y);
  for (let i = 1; i < fins.length; i++) if (fins[i].y - fins[i - 1].y < 14) fins[i].y = fins[i - 1].y + 14;
  svg.push(fins.map((f) => `<text class="rotulo" x="${f.x + 6}" y="${f.y + 4}">${esc(f.id)}</text>`).join(""));
  // proventos: pontos na base do gráfico (só na visão de preço)
  if (!base && r.proventos.length) {
    const ini = r.datas[0], fim = r.datas[n - 1];
    const idx = (d) => { let lo = 0, hi = n - 1; while (lo < hi) { const md = (lo + hi) >> 1; if (r.datas[md] < d) lo = md + 1; else hi = md; } return lo; };
    svg.push(`<g>${r.proventos.filter((p) => p.data >= ini && p.data <= fim).map((p) =>
      `<circle cx="${X(idx(p.data)).toFixed(1)}" cy="${H - m.b - 4}" r="2.5" fill="var(--c2)" opacity=".8"><title>Provento de R$ ${nf(4).format(p.valor)} (data-ex ${dataBR(p.data)})</title></circle>`).join("")}</g>`);
  }
  svg.push(`<line id="gp-cursor" y1="${m.t}" y2="${H - m.b}" stroke="var(--muted)" stroke-width="1" visibility="hidden"/>`);
  svg.push(`<circle id="gp-ponto" r="4" fill="var(--c1)" stroke="var(--surface)" stroke-width="2" visibility="hidden"/>`);
  svg.push(`<rect class="alvo" x="${m.l}" y="0" width="${W - m.l - m.r}" height="${H}"/>`);
  el.querySelector("svg")?.remove();
  el.insertAdjacentHTML("afterbegin", `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Gráfico do preço de ${esc(r.ticker)} ${esc(r.periodo_nome)}">${svg.join("")}</svg>`);

  const tip = $("#gp-tip"), cursor = el.querySelector("#gp-cursor"), ponto = el.querySelector("#gp-ponto"), camada = el.querySelector(".alvo");
  const mover = (clientX) => {
    const rc = camada.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((clientX - rc.left) / rc.width) * (n - 1))));
    const x = X(i);
    cursor.setAttribute("x1", x); cursor.setAttribute("x2", x); cursor.setAttribute("visibility", "visible");
    ponto.setAttribute("cx", x); ponto.setAttribute("cy", Y(p0.v[i])); ponto.setAttribute("visibility", "visible");
    const linhas = base
      ? series.filter((s) => s.v[i] != null).map((s) => `<div><span>${esc(s.id)}</span><b>${nf(1).format(s.v[i])}</b></div>`).join("")
      : `<div><span>Fechamento</span><b>${fmt(r.fechamento[i], "R$/ação")}</b></div>`;
    tip.innerHTML = `<strong>${dataBR(r.datas[i])}</strong>${linhas}`;
    tip.hidden = false;
    tip.style.left = `${x + 12 + tip.offsetWidth > W ? x - tip.offsetWidth - 12 : x + 12}px`;
    tip.style.top = `${m.t}px`;
  };
  camada.addEventListener("mousemove", (ev) => mover(ev.clientX));
  camada.addEventListener("touchmove", (ev) => { mover(ev.touches[0].clientX); }, { passive: true });
  camada.addEventListener("mouseleave", () => { tip.hidden = true; cursor.setAttribute("visibility", "hidden"); ponto.setAttribute("visibility", "hidden"); });
}

window.addEventListener("resize", () => GRAF && $("#gp-grafico") && desenharGraficoPreco());
