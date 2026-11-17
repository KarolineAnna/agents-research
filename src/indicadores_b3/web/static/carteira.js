// Aba "Carteira eficiente" (Markowitz).
// Usa $, esc e nf definidos em app.js.

const pct = (v, d = 2) => (v === null || v === undefined ? "—" : nf(d).format(v) + "%");
const num = (v, d = 2) => (v === null || v === undefined ? "—" : nf(d).format(v));
let CARTEIRA = null;
let selecionada = null;

let VISAO = "montar";  // "montar" | "bruto" | "impostos"

// Dados da visão atual (sem ou com impostos), no mesmo formato para o gráfico e os cards.
function vista() {
  return VISAO === "impostos" ? CARTEIRA.impostos.resultado : CARTEIRA;
}

// ---------- CDI automático ----------
async function carregarCDI() {
  try {
    const cdi = await api("/api/cdi");
    const c = cdi.componentes[0];
    $("#cdi-fonte").innerHTML = `Taxa livre de risco automática: <strong>CDI de ${pct(cdi.valor)} a.a.</strong>
      em ${dataBR(c.data_ref)} (Banco Central, ${esc(c.documento)} · <a href="${esc(c.url)}" target="_blank" rel="noopener">abrir fonte ↗</a>).
      Digite outro valor no campo para substituir.`;
  } catch (err) {
    $("#cdi-fonte").textContent = "Não consegui consultar o CDI no Banco Central; informe a taxa livre de risco manualmente.";
  }
}
carregarCDI();

// ---------- Busca ----------
$("#form-carteira").addEventListener("submit", (ev) => {
  ev.preventDefault();
  if (VISAO === "montar") montarCarteira(); else carregarFronteira();
});

async function carregarFronteira() {
  const form = $("#form-carteira");
  const f = new FormData(form);
  const q = new URLSearchParams({
    tickers: f.get("tickers"),
    periodo: f.get("periodo"),
    peso_max: f.get("peso_max") || "100",
    horizonte: f.get("horizonte") || "2",
    isencao: f.get("isencao") ? "true" : "false",
  });
  if (f.get("rf")) q.set("rf", f.get("rf"));
  q.set("modelo", f.get("modelo") || "historico");
  if (f.get("modelo") === "capm" && f.get("mercado")) q.set("mercado", f.get("mercado"));

  const botoes = document.querySelectorAll('[form="form-carteira"][type=submit], #form-carteira button');
  const status = $("#status-carteira");
  botoes.forEach((b) => (b.disabled = true));
  status.className = "status";
  status.textContent = "Baixando preços, câmbio e CDI e otimizando… na primeira vez pode demorar (arquivos da CVM).";
  try {
    CARTEIRA = await api(`/api/carteira?${q}`);
    selecionada = null;
    status.textContent = "";
    renderCarteira();
  } catch (err) {
    status.className = "status erro";
    status.textContent = err.message;
  } finally {
    botoes.forEach((b) => (b.disabled = false));
  }
}

$("#botao-carteira").hidden = VISAO === "montar";

$("#modelo-retorno").addEventListener("change", (ev) => {
  $("#campo-mercado").hidden = ev.target.value !== "capm";
});

// ---------- Sub-abas: sem / com impostos ----------
document.querySelectorAll("[data-sub]").forEach((b) => b.addEventListener("click", () => {
  VISAO = b.dataset.sub;
  document.querySelectorAll("[data-sub]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  $("#params-impostos").hidden = VISAO !== "impostos";
  $("#montar-painel").hidden = VISAO !== "montar";
  $("#fluxo-painel").hidden = VISAO !== "montar";
  $("#premissas-painel").hidden = VISAO !== "montar" || !["blocos", "bl"].includes($("#modelo-retorno").value);
  $("#resultado-carteira").hidden = VISAO === "montar";
  $("#montar-resultado").hidden = VISAO !== "montar";
  $("#botao-carteira").textContent = "Traçar fronteira";
  $("#botao-carteira").hidden = VISAO === "montar";  // em "Montar", o botão fica no fim do passo 3
  selecionada = null;
  if (VISAO !== "montar") { if (CARTEIRA) renderCarteira(); else carregarFronteira(); }
}));

// ---------- Render ----------
function htmlFontes(fontes) {
  return (fontes || []).map((f) =>
    `<a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.descricao)}">${esc(f.fonte)} ↗</a>`).join(" + ");
}

function renderCarteira() {
  const c = CARTEIRA, d = c.dados, v = vista(), imp = c.impostos;
  const comImposto = VISAO === "impostos";
  const rfTxt = comImposto
    ? `Renda fixa líquida: ${pct(imp.renda_fixa.liquido)} (CDI ${pct(imp.renda_fixa.bruto)} − ${pct(imp.renda_fixa.aliquota, 1)} de IR)`
    : `Taxa livre de risco: ${pct(d.rf)}${d.rf_fonte ? " (CDI, Banco Central)" : " (informada)"}`;

  $("#resultado-carteira").innerHTML = `
    <div class="viz">
      <div class="dados-usados">
        <span class="pill">Histórico: ${esc(d.periodo)} · ${dataBR(d.inicio)} a ${dataBR(d.fim)}</span>
        <span class="pill">${d.dias} dias de retorno em comum</span>
        <span class="pill">${rfTxt}</span>
        <span class="pill">Peso máximo: ${pct(d.peso_max, 0)}</span>
        <span class="pill">Retorno esperado: ${esc(d.modelo_nome)}</span>
      </div>

      ${comImposto ? htmlImpostos(imp) : ""}

      <div class="bloco">
        <h2>Risco × retorno ${comImposto ? "depois dos impostos" : ""}</h2>
        <p class="dica">Cada ponto é uma carteira. Clique num ponto da fronteira para ver os pesos dele.</p>
        <div class="legenda">
          <span><i class="linha" style="background:var(--s1)"></i>Fronteira eficiente</span>
          <span><i style="background:var(--s2)"></i>Máximo Sharpe</span>
          <span><i style="background:var(--s3)"></i>Mínima variância</span>
          <span><i style="background:var(--text)"></i>Ativos individuais</span>
          <span><i style="background:var(--muted);opacity:.35"></i>Carteiras aleatórias</span>
          ${v.rf > 0 ? `<span><i class="linha" style="background:repeating-linear-gradient(90deg,var(--muted) 0 4px,transparent 4px 7px)"></i>Linha de mercado de capitais</span>` : ""}
        </div>
        <div class="grafico" id="grafico"><div class="tooltip" id="tip" hidden></div></div>
      </div>

      <div class="carteiras">
        ${htmlCarteira(v.max_sharpe, "var(--s2)", comImposto ? c.max_sharpe : null)}
        ${htmlCarteira(v.min_var, "var(--s3)", comImposto ? c.min_var : null)}
        <div class="bloco" id="cart-selecionada">${htmlSelecionada()}</div>
      </div>

      ${comImposto ? "" : `
      <div class="bloco">
        <h2>Ativos individuais</h2>
        <p class="dica">${d.modelo === "capm"
          ? "Retorno = retorno esperado pelo CAPM (veja o bloco abaixo); a coluna \"Retorno histórico\" mostra a média dos retornos diários × 252."
          : "Retorno = média dos retornos diários × 252."} Volatilidade = desvio-padrão diário × √252. Preços em reais.</p>
        <div class="tabela-scroll"><table>
          <thead><tr><th>Ativo</th><th>Retorno anual${d.modelo === "capm" ? " (CAPM)" : ""}</th>${d.modelo === "capm" ? "<th>Retorno histórico</th>" : ""}<th>Volatilidade anual</th><th>Sharpe</th><th>Preço inicial → final</th><th>Fonte</th></tr></thead>
          <tbody>${c.ativos.map((a) => `
            <tr><td><strong>${esc(a.ticker)}</strong><span class="sub-tk">${esc(a.nome)}</span></td>
              <td class="${a.retorno < 0 ? "neg" : ""}">${pct(a.retorno)}</td>
              ${d.modelo === "capm" ? `<td class="${a.retorno_hist < 0 ? "neg" : ""}">${pct(a.retorno_hist)}</td>` : ""}
              <td>${pct(a.volatilidade)}</td><td>${num(a.sharpe)}</td>
              <td>R$ ${num(a.preco_inicial)} → R$ ${num(a.preco_final)}</td>
              <td class="fontes">${htmlFontes(a.fontes)}</td></tr>`).join("")}
          </tbody>
        </table></div>
      </div>

      ${htmlCAPM(c.capm, d.modelo)}

      <div class="bloco">
        <h2>Correlação entre os retornos diários</h2>
        <p class="dica">De −1 a 1. Quanto menor a correlação entre dois ativos, mais a combinação deles reduz o risco.</p>
        ${htmlCorrelacao(c.correlacao)}
      </div>`}

      <h2 style="margin:28px 0 12px">Entenda o modelo</h2>
      ${htmlConceitos()}
    </div>`;

  desenharGrafico();
  if (!comImposto) desenharSML();
  document.querySelectorAll(".salvar-cart").forEach((b) => b.addEventListener("click", () =>
    salvarCarteiraSugerida(JSON.parse(b.dataset.pesos), `${b.dataset.nome} · ${new Date().toLocaleDateString("pt-BR")}`)));
}

function htmlImpostos(imp) {
  const rf = imp.renda_fixa;
  return `
    <div class="bloco">
      <h2>Como os impostos entram na conta</h2>
      <p class="dica">Retorno líquido = proventos × (1 − alíquota dos proventos) + ganho de preço × (1 − alíquota do ganho).
        O risco também é multiplicado por (1 − alíquota do ganho), supondo que prejuízos são compensados com ganhos futuros.</p>
      <div class="tabela-scroll"><table class="impostos">
        <thead><tr><th>Ativo</th><th>Classe</th><th>Retorno bruto</th><th>Proventos</th><th>Ganho de preço</th>
          <th>IR sobre o ganho</th><th>Retorno líquido</th><th>Volatilidade líquida</th></tr></thead>
        <tbody>${imp.ativos.map((a) => `
          <tr><td><strong>${esc(a.ticker)}</strong></td><td>${esc(a.classe)}</td>
            <td>${pct(a.retorno_bruto)}</td><td>${pct(a.parte_proventos)}</td><td>${pct(a.parte_ganho)}</td>
            <td>${a.isento ? `<span class="tag">isento</span>` : pct(a.aliquota_ganho, 1)}</td>
            <td class="${a.retorno_liquido < 0 ? "neg" : ""}"><strong>${pct(a.retorno_liquido)}</strong></td>
            <td>${pct(a.vol_liquida)}</td></tr>`).join("")}
          <tr><td><strong>CDI</strong></td><td>Renda fixa</td><td>${pct(rf.bruto)}</td><td>—</td><td>—</td>
            <td>${pct(rf.aliquota, 1)}</td><td><strong>${pct(rf.liquido)}</strong></td><td>—</td></tr>
        </tbody>
      </table></div>
      <details class="base-legal">
        <summary>Base legal e observações de cada classe</summary>
        ${[...new Map(imp.ativos.map((a) => [a.classe, a])).values()].map((a) => `
          <p><strong>${esc(a.classe)}:</strong> ${esc(a.base_legal)}.
            ${a.isencao ? `Isenção: ${esc(a.isencao)}${a.isento ? " (aplicada)" : " (não aplicada)"}.` : ""}
            ${esc(a.nota)}</p>`).join("")}
        <p><strong>Renda fixa (CDI):</strong> ${esc(rf.base_legal)}. Horizonte de ${rf.dias} dias → ${pct(rf.aliquota, 1)}.</p>
        <p class="dica">Simplificação para estudo, com regras conferidas em out/2026. Não considera IOF, come-cotas,
          day trade, compensação de prejuízos de meses anteriores nem o imposto mínimo de altas rendas (Lei 15.270/2025).
          Confirme sua situação com um contador.</p>
      </details>
    </div>`;
}

function htmlPesos(pesos) {
  const linhas = Object.entries(pesos).sort((a, b) => b[1] - a[1]);
  return `<div class="pesos">${linhas.map(([tk, p]) => `
    <span class="tk ${p < 0.01 ? "zero" : ""}">${esc(tk)}</span>
    <span class="peso-trilho"><i style="width:${Math.max(0, p)}%"></i></span>
    <span class="pct ${p < 0.01 ? "zero" : ""}">${pct(p, 1)}</span>`).join("")}</div>`;
}

function htmlKpis(c) {
  return `<div class="kpis">
    <div><span>Retorno esperado</span><b>${pct(c.retorno, 1)}</b></div>
    <div><span>Volatilidade</span><b>${pct(c.volatilidade, 1)}</b></div>
    <div><span>Sharpe</span><b>${num(c.sharpe)}</b></div></div>`;
}

function htmlCarteira(c, cor, antes = null) {
  if (!c) return `<div class="bloco"><p class="vazio-cart">A otimização não convergiu.</p></div>`;
  const comparacao = antes ? `<p class="cart-exp">Sem impostos, esta carteira teria retorno de ${pct(antes.retorno, 1)}
    e volatilidade de ${pct(antes.volatilidade, 1)}.</p>` : "";
  return `<div class="bloco">
    <div class="cart-cab"><i style="background:${cor}"></i>${esc(c.nome)}${antes ? " (líquida)" : ""}</div>
    <p class="cart-exp">${esc(c.explicacao)}</p>
    ${htmlKpis(c)}${htmlPesos(c.pesos)}${comparacao}
    <button type="button" class="secundario salvar-cart" data-pesos="${esc(JSON.stringify(c.pesos))}" data-nome="${esc(c.nome)}">Salvar como carteira para acompanhar</button></div>`;
}

function htmlSelecionada() {
  if (!selecionada) return `<div class="cart-cab"><i style="background:var(--s1)"></i>Ponto da fronteira</div>
    <p class="vazio-cart">Clique num ponto da linha azul no gráfico para ver a composição daquela carteira.</p>`;
  return `<div class="cart-cab"><i style="background:var(--s1)"></i>Ponto da fronteira</div>
    <p class="cart-exp">A carteira de menor risco possível para um retorno esperado de ${pct(selecionada.retorno, 1)}.</p>
    ${htmlKpis(selecionada)}${htmlPesos(selecionada.pesos)}`;
}

function htmlCorrelacao({ tickers, matriz }) {
  // Divergente: azul (negativo) – cinza (zero) – laranja (positivo); o texto fica sempre na cor do texto.
  const fundo = (v) => `color-mix(in srgb, ${v >= 0 ? "var(--pos)" : "var(--negc)"} ${Math.round(Math.abs(v) * 55)}%, var(--surface))`;
  return `<div class="tabela-scroll"><table class="corr">
    <thead><tr><th></th>${tickers.map((t) => `<th>${esc(t)}</th>`).join("")}</tr></thead>
    <tbody>${matriz.map((linha, i) => `<tr><th>${esc(tickers[i])}</th>${linha.map((v, j) =>
      `<td style="background:${i === j ? "var(--surface-2)" : fundo(v)}" title="${esc(tickers[i])} × ${esc(tickers[j])}: ${num(v)}">${num(v)}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div>`;
}

function htmlConceitos() {
  const itens = [
    ["Retorno esperado da carteira", "E[Rp] = Σ wᵢ × μᵢ",
     "A média ponderada dos retornos esperados de cada ativo (μᵢ), usando os pesos (wᵢ) da carteira."],
    ["Risco da carteira", "σp = √( Σᵢ Σⱼ wᵢ × wⱼ × σᵢⱼ )",
     "Não é a média dos riscos: depende da covariância (σᵢⱼ) entre cada par. Ativos que não andam juntos se compensam, e o risco da carteira fica menor que o de cada ativo. Essa é a ideia da diversificação."],
    ["Índice de Sharpe", "Sharpe = (E[Rp] − rf) ÷ σp",
     "Quanto de retorno acima da taxa livre de risco (rf) a carteira entrega por unidade de risco. Quanto maior, melhor a relação risco × retorno."],
    ["Fronteira eficiente", "mín σp  sujeito a  E[Rp] = alvo, Σ wᵢ = 1, 0 ≤ wᵢ ≤ peso máx.",
     "Para cada nível de retorno, a carteira de menor risco. Qualquer carteira abaixo da linha é ineficiente: existe outra com o mesmo risco e mais retorno."],
    ["Linha de mercado de capitais", "E[R] = rf + Sharpeₘₐₓ × σ",
     "Combinando a carteira de máximo Sharpe com a renda fixa (rf), você anda nessa reta: mais renda fixa = menos risco; menos renda fixa = mais risco. Só aparece quando a taxa livre de risco é informada."],
    ["CAPM (retorno esperado)", "E[Rᵢ] = rf + βᵢ × (E[Rm] − rf)",
     "O mercado só remunera o risco que não some com a diversificação: o risco de mercado, medido pelo β. Ao escolher CAPM, essa conta substitui a média histórica de cada ativo, que é muito instável."],
    ["Beta (β)", "βᵢ = Cov(Rᵢ, Rm) ÷ Var(Rm)",
     "Quanto o ativo se move quando o Ibovespa se move 1%. β = 1 acompanha o mercado; β > 1 amplifica; β < 1 amortece; β perto de 0 quase não depende da bolsa (ex.: dólar, ouro)."],
    ["Alfa de Jensen", "αᵢ = Rᵢ − [rf + βᵢ × (Rm − rf)]",
     "Retorno que o ativo teve além do que o CAPM explicaria pelo seu β, usando os retornos realizados no período. Positivo = ficou acima da Security Market Line."],
    ["Cuidados", "",
     "O modelo usa o passado como estimativa do futuro, e é muito sensível ao retorno médio: pequenas mudanças geram pesos extremos (por isso o peso máximo ajuda). Ele mede risco só pela volatilidade, não considera custos nem impostos, e o resultado muda bastante com o período escolhido."],
  ];
  return `<div class="conceitos">${itens.map(([t, eq, txt]) => `
    <div class="bloco"><h3>${esc(t)}</h3>${eq ? `<div class="eq">${esc(eq)}</div>` : ""}<p>${esc(txt)}</p></div>`).join("")}</div>`;
}

// ---------- CAPM ----------
function htmlCAPM(cp, modelo) {
  if (!cp) return "";
  if (cp.erro) return `<div class="bloco"><h2>CAPM</h2><p class="aviso-box">${esc(cp.erro)}</p></div>`;
  const m = cp.mercado;
  const origem = m.esperado_origem === "informado" ? "informado por você" : "média histórica do Ibovespa no período";
  const premio = m.esperado - cp.rf;
  return `<div class="bloco">
    <h2>CAPM: β, alfa de Jensen e Security Market Line</h2>
    <p class="dica">Mercado = Ibovespa (<a href="${esc(m.url)}" target="_blank" rel="noopener">yfinance ^BVSP ↗</a>),
      ${cp.dias} dias de retorno em comum de ${dataBR(cp.inicio)} a ${dataBR(cp.fim)}.
      ${modelo === "capm" ? "<strong>A otimização acima usou o retorno do CAPM.</strong>" : "A otimização acima usou a média histórica; escolha CAPM no formulário para usar a coluna \"Retorno CAPM\"."}</p>
    <div class="dados-usados">
      <span class="pill">rf: ${pct(cp.rf)}</span>
      <span class="pill">Ibovespa realizado: ${pct(m.retorno_hist)} a.a.</span>
      <span class="pill">E[Rm]: ${pct(m.esperado)} (${origem})</span>
      <span class="pill">Prêmio de mercado: ${pct(premio)}</span>
    </div>
    ${premio < 0 ? `<p class="aviso-box">O retorno esperado do Ibovespa está abaixo da taxa livre de risco: pelo CAPM, quanto maior o β, menor o retorno esperado. Isso acontece quando a bolsa rendeu menos que o CDI no período; informe um retorno esperado do Ibovespa se quiser outra premissa.</p>` : ""}
    <div class="legenda">
      <span><i class="linha" style="background:var(--s1)"></i>Security Market Line</span>
      <span><i style="background:var(--s3)"></i>Alfa positivo (acima da linha)</span>
      <span><i style="background:var(--s2)"></i>Alfa negativo (abaixo)</span>
      <span><i style="background:var(--text)"></i>Ibovespa (β = 1)</span>
    </div>
    <p class="dica">O gráfico usa os retornos <strong>realizados</strong> no período: a reta vai da taxa livre de risco (β = 0)
      até o Ibovespa (β = 1). A distância vertical de cada ativo até a reta é o alfa de Jensen.</p>
    <div class="grafico" id="grafico-sml"><div class="tooltip" id="tip-sml" hidden></div></div>
    <div class="tabela-scroll"><table>
      <thead><tr><th>Ativo</th><th>β</th><th>R²</th><th>Retorno histórico</th><th>Retorno CAPM</th><th>Alfa de Jensen</th></tr></thead>
      <tbody>${cp.ativos.map((a) => `<tr>
        <td><strong>${esc(a.ticker)}</strong></td>
        <td title="Cov(ativo, Ibov) ${num(a.cov_mercado, 4)} ÷ Var(Ibov) ${num(m.var_anual, 4)} (anualizadas)">${num(a.beta)}</td>
        <td>${num(a.r2)}</td>
        <td class="${a.retorno_hist < 0 ? "neg" : ""}">${pct(a.retorno_hist)}</td>
        <td>${pct(a.retorno_capm)}</td>
        <td class="${a.alfa < 0 ? "neg" : ""}">${a.alfa > 0 ? "+" : ""}${pct(a.alfa)}</td></tr>`).join("")}
      </tbody></table></div>
    <p class="dica">Retorno CAPM = ${pct(cp.rf)} + β × ${pct(premio)}. Alfa = retorno histórico − [${pct(cp.rf)} + β × (${pct(m.retorno_hist)} − ${pct(cp.rf)})].
      R² mostra quanto da variação do ativo o Ibovespa explica: com R² baixo, o β é pouco informativo.
      Ativos negociados fora da B3 (cripto, ouro, dólar) fecham em horários diferentes do Ibovespa, o que tende a puxar o β para perto de zero.</p>
  </div>`;
}

function desenharSML() {
  const el = $("#grafico-sml");
  if (!el || !CARTEIRA.capm || CARTEIRA.capm.erro) return;
  const cp = CARTEIRA.capm, rf = cp.rf, rm = cp.mercado.retorno_hist;
  const W = el.clientWidth, H = W < 560 ? 300 : 360;
  const mg = { t: 12, r: 16, b: 44, l: 62 };
  const bs = cp.ativos.map((a) => a.beta), ys = cp.ativos.map((a) => a.retorno_hist);
  const x0 = Math.min(0, ...bs) - 0.1, x1 = Math.max(1.2, ...bs) + 0.1;
  const sml = (b) => rf + b * (rm - rf);
  const yv = [...ys, sml(x0), sml(x1), rm, rf];
  const pad = (Math.max(...yv) - Math.min(...yv)) * 0.08 || 1;
  const y0 = Math.min(...yv) - pad, y1 = Math.max(...yv) + pad;
  const X = (v) => mg.l + (v - x0) / (x1 - x0) * (W - mg.l - mg.r);
  const Y = (v) => H - mg.b - (v - y0) / (y1 - y0) * (H - mg.t - mg.b);
  const tx = ticks(x0, x1), ty = ticks(y0, y1);
  const svg = `<svg width="${W}" height="${H}" role="img" aria-label="Security Market Line">
    <g class="grade">${ty.map((v) => `<line x1="${mg.l}" x2="${W - mg.r}" y1="${Y(v)}" y2="${Y(v)}"/>`).join("")}</g>
    <g class="eixo">${ty.map((v) => `<text x="${mg.l - 8}" y="${Y(v) + 4}" text-anchor="end">${num(v, 0)}%</text>`).join("")}
    ${tx.map((v) => `<text x="${X(v)}" y="${H - mg.b + 18}" text-anchor="middle">${num(v, 1)}</text>`).join("")}</g>
    <text x="${(mg.l + W - mg.r) / 2}" y="${H - 6}" text-anchor="middle" class="titulo-eixo">β (beta contra o Ibovespa)</text>
    <text transform="translate(14 ${(H - mg.b) / 2}) rotate(-90)" text-anchor="middle" class="titulo-eixo">Retorno anual histórico</text>
    <line x1="${X(x0)}" x2="${X(x1)}" y1="${Y(sml(x0))}" y2="${Y(sml(x1))}" stroke="var(--s1)" stroke-width="2"/>
    ${cp.ativos.map((a) => `<line x1="${X(a.beta)}" x2="${X(a.beta)}" y1="${Y(sml(a.beta))}" y2="${Y(a.retorno_hist)}"
      stroke="${a.alfa >= 0 ? "var(--s3)" : "var(--s2)"}" stroke-dasharray="3 3"/>`).join("")}
    <circle cx="${X(1)}" cy="${Y(rm)}" r="5" fill="var(--text)" data-t="Ibovespa · β 1,00 · ${pct(rm)}"/>
    ${cp.ativos.map((a) => `<circle cx="${X(a.beta)}" cy="${Y(a.retorno_hist)}" r="6" fill="${a.alfa >= 0 ? "var(--s3)" : "var(--s2)"}"
      stroke="var(--surface)" stroke-width="1.5" data-t="${esc(a.ticker)} · β ${num(a.beta)} · retorno ${pct(a.retorno_hist)} · alfa ${pct(a.alfa)}"/>
      <text x="${X(a.beta) + 9}" y="${Y(a.retorno_hist) + 4}" class="rotulo">${esc(a.ticker)}</text>`).join("")}
  </svg>`;
  el.insertAdjacentHTML("afterbegin", svg);
  const tip = $("#tip-sml");
  el.querySelectorAll("circle[data-t]").forEach((c) => {
    c.addEventListener("mouseenter", () => {
      tip.textContent = c.dataset.t; tip.hidden = false;
      tip.style.left = `${+c.getAttribute("cx") + 10}px`; tip.style.top = `${+c.getAttribute("cy") - 30}px`;
    });
    c.addEventListener("mouseleave", () => (tip.hidden = true));
  });
}

// ---------- Gráfico (SVG feito à mão) ----------
function ticks(min, max, n = 6) {
  const passo0 = (max - min) / n;
  const mag = 10 ** Math.floor(Math.log10(passo0));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= passo0);
  const out = [];
  for (let v = Math.ceil(min / passo) * passo; v <= max + 1e-9; v += passo) out.push(+v.toFixed(10));
  return out;
}

function desenharGrafico() {
  const c = vista(), el = $("#grafico");
  const W = el.clientWidth, H = W < 560 ? 320 : 420;
  const m = { t: 12, r: 16, b: 44, l: 62 };

  const pontos = [...c.aleatorias.map(([x, y]) => ({ x, y })), ...c.ativos.map((a) => ({ x: a.volatilidade, y: a.retorno })),
    ...c.fronteira.map((p) => ({ x: p.volatilidade, y: p.retorno }))];
  const xs = pontos.map((p) => p.x), ys = pontos.map((p) => p.y);
  const pad = (a, b) => (b - a) * 0.08 || 1;
  const x0 = 0, x1 = Math.max(...xs) + pad(0, Math.max(...xs));
  const y0 = Math.min(0, Math.min(...ys) - pad(Math.min(...ys), Math.max(...ys)));
  const y1 = Math.max(...ys) + pad(Math.min(...ys), Math.max(...ys));
  const X = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);

  const gx = ticks(x0, x1), gy = ticks(y0, y1);
  const svg = [];
  svg.push(`<g class="grade">${gy.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/>`).join("")}</g>`);
  svg.push(`<g class="eixo">
    ${gy.map((v) => `<text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${nf(0).format(v)}%</text>`).join("")}
    ${gx.map((v) => `<text x="${X(v)}" y="${H - m.b + 18}" text-anchor="middle">${nf(0).format(v)}%</text>`).join("")}
  </g>`);
  svg.push(`<text class="titulo-eixo" x="${(m.l + W - m.r) / 2}" y="${H - 6}" text-anchor="middle">Risco (volatilidade anual)</text>`);
  svg.push(`<text class="titulo-eixo" transform="translate(13 ${(m.t + H - m.b) / 2}) rotate(-90)" text-anchor="middle">Retorno esperado anual</text>`);

  // Carteiras aleatórias
  svg.push(`<g fill="var(--muted)" opacity=".28">${c.aleatorias.map(([x, y]) =>
    `<circle cx="${X(x)}" cy="${Y(y)}" r="2"/>`).join("")}</g>`);

  // Linha de mercado de capitais
  if (c.rf > 0 && c.max_sharpe) {
    const s = c.max_sharpe.sharpe, rf = c.rf;
    // vai de (0, rf) até sair do gráfico pela direita ou pelo topo
    const xf = s > 0 ? Math.min(x1, (y1 - rf) / s) : x1;
    svg.push(`<line x1="${X(0)}" y1="${Y(rf)}" x2="${X(xf)}" y2="${Y(rf + s * xf)}"
      stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>`);
  }

  // Fronteira
  const fr = c.fronteira;
  svg.push(`<polyline fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round"
    points="${fr.map((p) => `${X(p.volatilidade)},${Y(p.retorno)}`).join(" ")}"/>`);
  svg.push(fr.map((p, i) => `<circle cx="${X(p.volatilidade)}" cy="${Y(p.retorno)}" r="${selecionada === p ? 6 : 3}"
    fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>`).join(""));

  // Ativos
  svg.push(c.ativos.map((a) => `<circle cx="${X(a.volatilidade)}" cy="${Y(a.retorno)}" r="5" fill="var(--text)" stroke="var(--surface)" stroke-width="2"/>
    <text class="rotulo" x="${X(a.volatilidade) + 8}" y="${Y(a.retorno) + 4}">${esc(a.ticker)}</text>`).join(""));

  // Carteiras ótimas
  const destaque = (p, cor, rotulo) => p ? `<circle cx="${X(p.volatilidade)}" cy="${Y(p.retorno)}" r="8" fill="${cor}" stroke="var(--surface)" stroke-width="2"/>
    <text class="rotulo" x="${X(p.volatilidade) - 12}" y="${Y(p.retorno) - 12}" text-anchor="end">${rotulo}</text>` : "";
  svg.push(destaque(c.min_var, "var(--s3)", "Mín. variância"));
  svg.push(destaque(c.max_sharpe, "var(--s2)", "Máx. Sharpe"));

  // Alvos de hover/clique (maiores que a marca)
  const alvos = [
    ...fr.map((p, i) => ({ p, tipo: "fronteira", nome: "Ponto da fronteira", i })),
    ...c.ativos.map((a) => ({ p: a, tipo: "ativo", nome: a.ticker })),
    ...(c.min_var ? [{ p: c.min_var, tipo: "otima", nome: "Mínima variância" }] : []),
    ...(c.max_sharpe ? [{ p: c.max_sharpe, tipo: "otima", nome: "Máximo Sharpe" }] : []),
  ];
  // Uma camada transparente por cima: o ponto mais próximo do mouse (até 24px) é o ativo.
  svg.push(`<rect class="alvo" x="0" y="0" width="${W}" height="${H}"/>`);

  el.querySelector("svg")?.remove();
  el.insertAdjacentHTML("afterbegin", `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img"
    aria-label="Gráfico de risco por retorno com a fronteira eficiente">${svg.join("")}</svg>`);

  const tip = $("#tip"), camada = el.querySelector(".alvo");
  const maisProximo = (ev) => {
    const r = camada.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    let melhor = null, dist = 24;
    for (const a of alvos) {
      const d = Math.hypot(X(a.p.volatilidade) - mx, Y(a.p.retorno) - my);
      if (d < dist) [melhor, dist] = [a, d];
    }
    return melhor;
  };
  camada.addEventListener("mousemove", (ev) => {
    const a = maisProximo(ev);
    camada.style.cursor = a?.tipo === "fronteira" ? "pointer" : "default";
    if (!a) return (tip.hidden = true);
    tip.innerHTML = `<strong>${esc(a.nome)}</strong>
      <div>Retorno <b>${pct(a.p.retorno, 1)}</b></div>
      <div>Volatilidade <b>${pct(a.p.volatilidade, 1)}</b></div>
      <div>Sharpe <b>${num(a.p.sharpe)}</b></div>
      ${a.tipo === "fronteira" ? `<div style="margin-top:4px">clique para ver os pesos</div>` : ""}`;
    tip.hidden = false;
    const x = X(a.p.volatilidade), y = Y(a.p.retorno);
    tip.style.left = `${Math.max(0, Math.min(x + 14, W - tip.offsetWidth - 4))}px`;
    tip.style.top = `${Math.max(y - tip.offsetHeight - 10, 0)}px`;
  });
  camada.addEventListener("mouseleave", () => (tip.hidden = true));
  camada.addEventListener("click", (ev) => {
    const a = maisProximo(ev);
    if (a?.tipo !== "fronteira") return;
    selecionada = a.p;
    $("#cart-selecionada").innerHTML = htmlSelecionada();
    desenharGrafico();
  });
}

document.querySelector('[data-aba="carteira"]').addEventListener("click", () => CARTEIRA && desenharGrafico());

let _redim;
window.addEventListener("resize", () => {
  clearTimeout(_redim);
  _redim = setTimeout(() => CARTEIRA && !$("#aba-carteira").hidden && desenharGrafico(), 150);
});
