// Aba "DRE e Balanço": os dois relatórios explicados passo a passo, no mesmo modelo do DCF.
// Os números e os nomes das contas vêm do arquivo da CVM; cada passo tem "ver campos usados".

let DEM = null;
let DEM_VISAO = "dre";       // "dre" | "balanco"
let DEM_PERIODO = "ttm";     // "ttm" ou um ano ("2025")

$("#form-dem").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const tk = $("#ticker-dem").value.split(",")[0].trim().toUpperCase();
  const status = $("#status-dem");
  status.className = "status";
  status.textContent = `Carregando ${tk}… na primeira vez o site baixa os demonstrativos da CVM.`;
  try {
    DEM = await api(`/api/demonstracoes/${encodeURIComponent(tk)}`);
    DEM_PERIODO = "ttm";
    status.textContent = "";
    renderDem();
  } catch (err) {
    status.className = "status erro";
    status.textContent = err.message;
  }
});

document.querySelectorAll("[data-dem]").forEach((b) => b.addEventListener("click", () => {
  DEM_VISAO = b.dataset.dem;
  document.querySelectorAll("[data-dem]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  if (DEM) renderDem();
}));

function renderDem() {
  $("#resultado-dem").innerHTML = `<div class="viz dcf">
    <div class="empresa"><h2>${esc(DEM.empresa)}</h2><span class="tk">${esc(DEM.ticker)}</span></div>
    <div id="dem-corpo"></div></div>`;
  DEM_VISAO === "dre" ? renderDRE() : renderBalanco();
}

// ---------- utilidades ----------
const pctDe = (a, b) => (a !== null && b ? (a / b) * 100 : null);
function camposDe(rastros) {
  const comps = rastros.filter(Boolean).flatMap((r) => r.componentes);
  if (!comps.length) return "";
  return `<details class="campos"><summary>Ver campos usados (CVM)</summary>
    ${rastros.filter(Boolean).map((r) => r.nota ? `<p class="e-nota">${esc(r.nota)}</p>` : "").join("")}
    ${comps.map((c) => htmlComponente(c, "R$")).join("")}</details>`;
}
function passo(n, titulo, corpo) {
  return `<div class="bloco passo"><div class="n">${n}</div><div><h2>${titulo}</h2>${corpo}</div></div>`;
}

// =====================================================================
// DRE
// =====================================================================
function linhaDRE(conta) { return DEM.dre.linhas.find((l) => l.conta === conta); }
function rastroDRE(conta) {
  const l = linhaDRE(conta);
  if (!l) return null;
  return DEM_PERIODO === "ttm" ? l.ttm : l.anos[DEM_PERIODO] || null;
}
const vDRE = (conta) => rastroDRE(conta)?.valor ?? null;
const nomeDRE = (conta) => linhaDRE(conta)?.descricao || conta;

function filhosDRE(conta) {
  const receita = vDRE("3.01");
  const filhos = DEM.dre.linhas.filter((l) => l.conta.startsWith(conta + ".") && l.nivel === conta.split(".").length + 1);
  if (!filhos.length) return "";
  return `<div class="tabela-scroll"><table class="contas"><thead><tr><th>Conta</th><th>Descrição (como está na CVM)</th><th>Valor</th><th>% da receita</th></tr></thead>
    <tbody>${filhos.map((f) => { const v = vDRE(f.conta); return `<tr class="clicavel" data-dre="${esc(f.conta)}"><td><code>${esc(f.conta)}</code></td><td>${esc(f.descricao)} ›</td>
      <td class="${v < 0 ? "neg" : ""}">${sinalBrl(v)}</td><td>${pct(pctDe(v, receita), 1)}</td></tr>`; }).join("")}</tbody></table></div>`;
}

function eqDRE(resultado, partes) {
  const vals = partes.map(vDRE);
  const soma = vals.reduce((s, v) => s + (v || 0), 0);
  const real = vDRE(resultado);
  const dif = real !== null && Math.abs(real - soma) > Math.abs(real) * 0.005 + 1;
  return `<div class="eq">${lk("dre", resultado, `${esc(nomeDRE(resultado))} (${resultado})`)} = ${partes.map((p) => lk("dre", p, `${esc(nomeDRE(p))} (${p})`)).join(" + ")}</div>
    <div class="eq">${vals.map(sinalBrl).join(" + ")} = <strong>${sinalBrl(real)}</strong></div>
    ${dif ? `<p class="dica">A soma dá ${sinalBrl(soma)}; a diferença para o valor informado vem de linhas que esta empresa usa fora do modelo padrão.</p>` : ""}`;
}

function renderDRE() {
  const d = DEM.dre;
  const padrao = ["3.01", "3.03", "3.05", "3.07", "3.11"].every((c) => linhaDRE(c));
  const periodos = [["ttm", "Últimos 12 meses"], ...d.anos.slice().reverse().map((a) => [a, `Ano ${a}`])];
  const receita = vDRE("3.01");
  const m = (c) => pct(pctDe(vDRE(c), receita), 1);
  const lair = vDRE("3.07"), ir = vDRE("3.08");

  let corpo = `
    <div class="meta"><span class="pill">Último documento: ${dataBR(d.ref)}</span></div>
    <div class="chips">${periodos.map(([k, n]) => `<label class="chip"><input type="radio" name="dem-per" value="${k}" ${k === DEM_PERIODO ? "checked" : ""}> ${n}</label>`).join("")}</div>`;

  if (!padrao) {
    corpo += `<div class="aviso-box">⚠ Esta empresa não usa o modelo padrão de DRE (por exemplo, bancos e seguradoras têm outro plano de contas).
      Abaixo estão todas as linhas como aparecem na CVM.</div>${tabelaDRECompleta()}`;
    $("#dem-corpo").innerHTML = corpo;
    ligarPeriodo();
    ligarContas();
    return;
  }

  corpo += `
    <div class="bloco"><h2>A DRE em uma imagem</h2>
      <p class="dica">Da receita até o lucro: barras azuis somam, laranjas subtraem, cinzas são os resultados de cada etapa.</p>
      <div class="legenda"><span><i style="background:var(--c1)"></i>Aumenta</span><span><i style="background:var(--c2)"></i>Diminui</span><span><i style="background:var(--text);opacity:.7"></i>Resultado</span></div>
      <div class="grafico" id="cascata"></div></div>

    ${passo(1, "Quanto a empresa vendeu?", `
      <p>A <strong>receita líquida</strong> é o total vendido no período, já sem impostos sobre vendas, devoluções e descontos. É o ponto de partida: todas as margens são calculadas sobre ela.</p>
      <div class="eq">${lk("dre", "3.01", `${esc(nomeDRE("3.01"))} (3.01)`)} = <strong>${brl(receita)}</strong></div>
      ${camposDe([rastroDRE("3.01")])}`)}

    ${passo(2, "Quanto custou o que foi vendido? → Lucro bruto", `
      <p>O <strong>custo</strong> é o gasto direto para produzir ou comprar o que foi vendido (matéria-prima, mão de obra da fábrica, mercadoria). Na CVM ele aparece negativo, porque reduz o resultado.</p>
      ${eqDRE("3.03", ["3.01", "3.02"])}
      <p><strong>Margem bruta: ${m("3.03")}</strong>: de cada R$ 100 vendidos, sobram ${m("3.03")} depois do custo direto.</p>
      ${camposDe([rastroDRE("3.02"), rastroDRE("3.03")])}`)}

    ${passo(3, "Despesas para operar → EBIT (resultado operacional)", `
      <p>Agora entram as <strong>despesas operacionais</strong>: vender (comissões, marketing), administrar (escritório, diretoria) e outros itens. A equivalência patrimonial (lucro de empresas em que ela tem participação) também entra aqui.</p>
      ${eqDRE("3.05", ["3.03", "3.04"])}
      ${filhosDRE("3.04")}
      <p><strong>Margem EBIT: ${m("3.05")}</strong>: mostra quanto a operação em si gera, antes de juros e impostos. É a melhor medida para comparar a eficiência de empresas do mesmo setor.</p>
      ${ebitda() !== null ? `<div class="eq">${lk("dre", "EBITDA", "EBITDA")} = ${lk("dre", "3.05", "EBIT (3.05)")} + ${lk("dre", "DA", "Depreciação e amortização (DVA 7.04.01)")} = <strong>${brl(ebitda())}</strong> · margem ${pct(pctDe(ebitda(), receita), 1)}</div>` : ""}
      ${camposDe([rastroDRE("3.04"), rastroDRE("3.05")])}`)}

    ${passo(4, "Juros e aplicações → Lucro antes dos impostos", `
      <p>O <strong>resultado financeiro</strong> junta o que a empresa ganha com o caixa aplicado e o que paga de juros sobre dívidas (e variação cambial). Empresas endividadas costumam ter resultado financeiro bem negativo.</p>
      ${eqDRE("3.07", ["3.05", "3.06"])}
      ${filhosDRE("3.06")}
      ${camposDe([rastroDRE("3.06"), rastroDRE("3.07")])}`)}

    ${passo(5, "Impostos sobre o lucro", `
      <p>Sobre o lucro incidem <strong>IR e CSLL</strong> (alíquota nominal de 34% para a maioria das empresas). A alíquota efetiva costuma ser diferente por causa de incentivos fiscais, JCP e prejuízos acumulados.</p>
      ${eqDRE("3.09", ["3.07", "3.08"])}
      ${filhosDRE("3.08")}
      <p><strong>Alíquota efetiva: ${pct(lair ? (-ir / lair) * 100 : null, 1)}</strong> (IR e CSLL ÷ lucro antes dos impostos).</p>
      ${camposDe([rastroDRE("3.08"), rastroDRE("3.09")])}`)}

    ${passo(6, "Lucro líquido: a última linha", `
      <p>Somando o resultado de operações descontinuadas (negócios vendidos ou encerrados), chega-se ao <strong>lucro líquido</strong>. Parte dele pode pertencer a sócios minoritários de controladas; o que interessa ao acionista é a parte dos <strong>controladores</strong>, usada no LPA e no P/L.</p>
      ${linhaDRE("3.10") ? eqDRE("3.11", ["3.09", "3.10"]) : `<div class="eq">${lk("dre", "3.11", `${esc(nomeDRE("3.11"))} (3.11)`)} = <strong>${sinalBrl(vDRE("3.11"))}</strong></div>`}
      ${filhosDRE("3.11")}
      <p><strong>Margem líquida: ${m("3.11")}</strong>.</p>
      ${camposDe([rastroDRE("3.10"), rastroDRE("3.11"), rastroDRE("3.11.01")])}`)}

    <div class="bloco" id="av-dre">${analiseDRE()}</div>
    <details class="bloco"><summary><strong>Todas as linhas da DRE</strong></summary>${tabelaDRECompleta()}</details>`;

  $("#dem-corpo").innerHTML = corpo;
  ligarPeriodo();
  desenharCascata();
  ligarContas();
  ligarAnalise("dre");
}

function ligarPeriodo() {
  document.querySelectorAll("[name=dem-per]").forEach((r) => r.addEventListener("change", () => { DEM_PERIODO = r.value; renderDRE(); }));
}

function tabelaDRECompleta() {
  return `<div class="tabela-scroll"><table class="arvore"><thead><tr><th>Conta</th><th>Descrição</th><th>Valor</th></tr></thead><tbody>
    ${DEM.dre.linhas.map((l) => { const v = vDRE(l.conta); return `<tr class="n${l.nivel} clicavel" data-dre="${esc(l.conta)}"><td><code>${esc(l.conta)}</code></td>
      <td>${esc(l.descricao)}</td><td class="${v < 0 ? "neg" : ""}">${sinalBrl(v)}</td></tr>`; }).join("")}</tbody></table></div>`;
}

function desenharCascata() {
  const el = $("#cascata");
  const itens = [["Receita", "3.01", "total"], ["Custo", "3.02", "delta"], ["Lucro bruto", "3.03", "total"],
    ["Despesas op.", "3.04", "delta"], ["EBIT", "3.05", "total"], ["Financeiro", "3.06", "delta"],
    ["Antes do IR", "3.07", "total"], ["IR e CSLL", "3.08", "delta"],
    ...(linhaDRE("3.10") && vDRE("3.10") ? [["Descontinuadas", "3.10", "delta"]] : []), ["Lucro líquido", "3.11", "total"]]
    .map(([n, c, t]) => ({ n, c, t, v: vDRE(c) ?? 0 }));

  let corrente = 0;
  itens.forEach((it) => {
    if (it.t === "total") { it.de = 0; it.ate = it.v; corrente = it.v; }
    else { it.de = corrente; it.ate = corrente + it.v; corrente = it.ate; }
  });
  const W = el.clientWidth, H = W < 560 ? 300 : 360, m = { t: 22, r: 8, b: 44, l: 8 };
  const vals = itens.flatMap((i) => [i.de, i.ate]);
  const y0 = Math.min(0, ...vals), y1 = Math.max(0, ...vals);
  const Y = (v) => m.t + ((y1 - v) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const passoX = (W - m.l - m.r) / itens.length, larg = Math.max(8, passoX * 0.62);
  const svg = [`<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--muted)"/>`];
  itens.forEach((it, i) => {
    const x = m.l + i * passoX + (passoX - larg) / 2;
    const topo = Y(Math.max(it.de, it.ate)), base = Y(Math.min(it.de, it.ate));
    const cor = it.t === "total" ? "var(--text)" : it.v >= 0 ? "var(--c1)" : "var(--c2)";
    svg.push(`<rect data-dre="${it.c}" class="barra-clicavel" x="${x}" y="${topo}" width="${larg}" height="${Math.max(1, base - topo)}" rx="3" fill="${cor}" ${it.t === "total" ? 'opacity=".7"' : ""}>
      <title>${esc(it.n)} (${it.c}): ${sinalBrl(it.v)}</title></rect>`);
    svg.push(`<text class="rotulo-v" x="${x + larg / 2}" y="${topo - 6}" text-anchor="middle">${sinalBrl(it.v)}</text>`);
    svg.push(`<text class="rotulo-x" x="${x + larg / 2}" y="${H - m.b + 16}" text-anchor="middle">${esc(it.n)}</text>`);
    if (i < itens.length - 1) {
      const xn = m.l + (i + 1) * passoX + (passoX - larg) / 2;
      svg.push(`<line x1="${x + larg}" x2="${xn}" y1="${Y(it.ate)}" y2="${Y(it.ate)}" stroke="var(--muted)" stroke-dasharray="2 2"/>`);
    }
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Cascata da DRE da receita ao lucro líquido">${svg.join("")}</svg>`;
}

// =====================================================================
// BALANÇO
// =====================================================================
function linhaBP(conta) { return DEM.balanco.linhas.find((l) => l.conta === conta); }
const vBP = (c) => linhaBP(c)?.atual?.valor ?? null;
const vBPant = (c) => linhaBP(c)?.anterior?.valor ?? null;
const nomeBP = (c) => linhaBP(c)?.descricao || c;
const buscaBP = (pai, termo) => DEM.balanco.linhas.find((l) => l.conta.startsWith(pai + ".") && l.nivel === 3 && l.descricao.toLowerCase().includes(termo));

function filhosBP(conta) {
  const total = vBP(conta);
  const filhos = DEM.balanco.linhas.filter((l) => l.conta.startsWith(conta + ".") && l.nivel === conta.split(".").length + 1);
  if (!filhos.length) return "";
  return `<div class="tabela-scroll"><table class="contas"><thead><tr><th>Conta</th><th>Descrição (como está na CVM)</th><th>Atual</th><th>Anterior</th><th title="Análise horizontal">Variação</th><th>% do grupo</th><th title="Análise vertical">% do ativo total</th></tr></thead>
    <tbody>${filhos.map((f) => { const a = f.atual?.valor ?? null, p = f.anterior?.valor ?? null;
      return `<tr class="clicavel" data-bp="${esc(f.conta)}"><td><code>${esc(f.conta)}</code></td><td>${esc(f.descricao)} ›</td><td>${sinalBrl(a)}</td><td>${sinalBrl(p)}</td>
        <td class="${a < p ? "neg" : ""}">${p ? pct((a / p - 1) * 100, 1) : "—"}</td><td>${pct(pctDe(a, total), 1)}</td><td>${pct(pctDe(a, vBP("1")), 1)}</td></tr>`; }).join("")}
    </tbody></table></div>`;
}

function camposBP(contas) {
  return camposDe(contas.flatMap((c) => [linhaBP(c)?.atual, linhaBP(c)?.anterior]));
}

function renderBalanco() {
  const b = DEM.balanco;
  const padrao = ["1", "1.01", "1.02", "2", "2.01", "2.02", "2.03"].every((c) => linhaBP(c));
  let corpo = `<div class="meta"><span class="pill">Posição em ${dataBR(b.ref)}</span>
    ${b.ref_anterior ? `<span class="pill">Comparado com ${dataBR(b.ref_anterior)}</span>` : ""}</div>`;
  if (!padrao) {
    corpo += `<div class="aviso-box">⚠ Esta empresa não usa o modelo padrão de balanço (bancos e seguradoras têm outro plano de contas).
      Abaixo estão todas as linhas como aparecem na CVM.</div>${tabelaBPCompleta()}`;
    $("#dem-corpo").innerHTML = corpo;
    ligarContas();
    return;
  }
  const ativo = vBP("1"), ac = vBP("1.01"), anc = vBP("1.02"), pc = vBP("2.01"), pnc = vBP("2.02"), pl = vBP("2.03");
  const estoques = buscaBP("1.01", "estoque"), caixa = vBP("1.01.01") || 0, aplic = vBP("1.01.02") || 0;
  const ind = [
    ["Liquidez corrente", "Ativo circulante ÷ Passivo circulante", ac / pc, "x",
     "Quanto a empresa tem de bens e direitos de curto prazo para cada R$ 1 de dívida de curto prazo. Acima de 1 é confortável."],
    ["Liquidez seca", "(Ativo circulante − Estoques) ÷ Passivo circulante", (ac - (estoques?.atual?.valor || 0)) / pc, "x",
     "Igual à corrente, mas sem os estoques, que podem demorar para virar dinheiro."],
    ["Liquidez imediata", "(Caixa + Aplicações) ÷ Passivo circulante", (caixa + aplic) / pc, "x",
     "Só o dinheiro disponível já, contra as dívidas de curto prazo."],
    ["Capital de giro líquido", "Ativo circulante − Passivo circulante", ac - pc, "R$",
     "A folga (ou o aperto) de recursos de curto prazo para tocar a operação."],
    ["Endividamento geral", "(Passivo circulante + não circulante) ÷ Ativo total × 100", ((pc + pnc) / ativo) * 100, "%",
     "Quanto dos bens da empresa é financiado por terceiros (credores, fornecedores, governo)."],
    ["Passivo ÷ Patrimônio", "(Passivo circulante + não circulante) ÷ Patrimônio líquido", (pc + pnc) / pl, "x",
     "Quantos reais de terceiros para cada R$ 1 dos sócios."],
  ];

  corpo += `
    <div class="bloco"><h2>O balanço em uma imagem</h2>
      <p class="dica">À esquerda, o que a empresa <strong>tem</strong> (ativo). À direita, <strong>de onde veio o dinheiro</strong> para ter isso: dívidas com terceiros (passivo) e dinheiro dos sócios (patrimônio líquido). As duas colunas têm sempre o mesmo tamanho.</p>
      <div class="balanco-visual">
        <div class="coluna"><div class="titulo">Ativo · ${brl(ativo)}</div>
          ${bloco("Ativo circulante", ac, ativo, "--c1", "1.01")}${bloco("Ativo não circulante", anc, ativo, "--c3", "1.02")}</div>
        <div class="coluna"><div class="titulo">Passivo + PL · ${brl(vBP("2"))}</div>
          ${bloco("Passivo circulante", pc, ativo, "--c2", "2.01")}${bloco("Passivo não circulante", pnc, ativo, "--c4", "2.02")}${bloco("Patrimônio líquido", pl, ativo, "--c7", "2.03")}</div>
      </div></div>

    ${passo(1, "A regra de ouro: Ativo = Passivo + Patrimônio líquido", `
      <p>Tudo o que a empresa tem foi pago com dinheiro de alguém: de terceiros (passivo) ou dos sócios (patrimônio líquido). Por isso as duas somas sempre fecham.</p>
      <div class="eq">${lk("bp", "1", `${esc(nomeBP("1"))} (1)`)} = ${lk("bp", "2", `${esc(nomeBP("2"))} (2)`)}</div>
      <div class="eq">${brl(ativo)} = ${brl(pc)} + ${brl(pnc)} + ${brl(pl)} = <strong>${brl(pc + pnc + pl)}</strong></div>
      ${camposBP(["1", "2"])}`)}

    ${passo(2, "Ativo circulante: o que vira dinheiro em até 12 meses", `
      <p>Caixa, aplicações, valores a receber de clientes, estoques. É a parte mais "líquida" do ativo.</p>
      <div class="eq">${lk("bp", "1.01", `${esc(nomeBP("1.01"))} (1.01)`)} = <strong>${brl(ac)}</strong> · ${pct(pctDe(ac, ativo), 1)} do ativo</div>
      ${filhosBP("1.01")}${camposBP(["1.01"])}`)}

    ${passo(3, "Ativo não circulante: o que fica com a empresa por mais tempo", `
      <p>Fábricas, máquinas e terrenos (<strong>imobilizado</strong>), marcas e softwares (<strong>intangível</strong>), participações em outras empresas (<strong>investimentos</strong>) e valores a receber no longo prazo.</p>
      <div class="eq">${lk("bp", "1.02", `${esc(nomeBP("1.02"))} (1.02)`)} = <strong>${brl(anc)}</strong> · ${pct(pctDe(anc, ativo), 1)} do ativo</div>
      ${filhosBP("1.02")}${camposBP(["1.02"])}`)}

    ${passo(4, "Passivo circulante: o que precisa pagar em até 12 meses", `
      <p>Fornecedores, salários, impostos a pagar e a parcela de empréstimos que vence no próximo ano.</p>
      <div class="eq">${lk("bp", "2.01", `${esc(nomeBP("2.01"))} (2.01)`)} = <strong>${brl(pc)}</strong> · ${pct(pctDe(pc, ativo), 1)} do total</div>
      ${filhosBP("2.01")}${camposBP(["2.01"])}`)}

    ${passo(5, "Passivo não circulante: dívidas de longo prazo", `
      <p>Empréstimos, debêntures e outras obrigações que vencem depois de 12 meses. É aqui que costuma estar a maior parte da dívida financeira.</p>
      <div class="eq">${lk("bp", "2.02", `${esc(nomeBP("2.02"))} (2.02)`)} = <strong>${brl(pnc)}</strong> · ${pct(pctDe(pnc, ativo), 1)} do total</div>
      ${filhosBP("2.02")}${camposBP(["2.02"])}`)}

    ${passo(6, "Patrimônio líquido: a parte dos sócios", `
      <p>O dinheiro que os sócios colocaram (<strong>capital social</strong>) mais os lucros que a empresa guardou ao longo dos anos (<strong>reservas</strong>). É a base do VPA e do P/VP.</p>
      <div class="eq">${lk("bp", "2.03", `${esc(nomeBP("2.03"))} (2.03)`)} = <strong>${brl(pl)}</strong> · ${pct(pctDe(pl, ativo), 1)} do total</div>
      ${filhosBP("2.03")}${camposBP(["2.03"])}`)}

    ${passo(7, "O que o balanço diz sobre a saúde da empresa", `
      <div class="indicadores-bp">${ind.map(([n, f, v, u, t]) => `<div class="kpi-bp"><span>${n}</span>
        <b>${u === "R$" ? sinalBrl(v) : u === "%" ? pct(v, 1) : num(v) + "x"}</b><code>${f}</code><p>${t}</p></div>`).join("")}</div>
      ${estoques ? "" : `<p class="dica">Não há conta de estoques no balanço desta empresa; a liquidez seca fica igual à corrente.</p>`}
      ${camposBP(["1.01.01", "1.01.02", estoques?.conta].filter(Boolean))}`)}

    <div class="bloco" id="av-bp">${analiseBP()}</div>
    <details class="bloco"><summary><strong>Todas as linhas do balanço</strong></summary>${tabelaBPCompleta()}</details>`;

  $("#dem-corpo").innerHTML = corpo;
  ligarContas();
  ligarAnalise("bp");
}

function bloco(nome, v, total, cor, conta) {
  const p = pctDe(v, total) || 0;
  return `<div class="parte clicavel" data-bp="${conta}" style="height:${Math.max(p, 0)}%;background:var(${cor})" title="${esc(nome)}: ${brl(v)} · clique para ver as contas">
    ${p >= 7 ? `<span>${esc(nome)}<br>${nf(0).format(p)}% · ${brl(v)}</span>` : ""}</div>`;
}

function tabelaBPCompleta() {
  return `<div class="tabela-scroll"><table class="arvore"><thead><tr><th>Conta</th><th>Descrição</th><th>Atual</th><th>Anterior</th></tr></thead><tbody>
    ${DEM.balanco.linhas.map((l) => `<tr class="n${l.nivel} clicavel" data-bp="${esc(l.conta)}"><td><code>${esc(l.conta)}</code></td><td>${esc(l.descricao)}</td>
      <td>${sinalBrl(l.atual?.valor ?? null)}</td><td>${sinalBrl(l.anterior?.valor ?? null)}</td></tr>`).join("")}</tbody></table></div>`;
}

window.addEventListener("resize", () => DEM && DEM_VISAO === "dre" && !$("#aba-balancos").hidden && !$("#bal-dem").hidden && $("#cascata") && desenharCascata());
document.querySelector('[data-aba="balancos"]').addEventListener("click", () => DEM && DEM_VISAO === "dre" && $("#cascata") && !$("#bal-dem").hidden && desenharCascata());


// =====================================================================
// POPUP: composição de uma conta (clique em qualquer conta, linha ou barra)
// =====================================================================
const lk = (tipo, conta, texto) => `<button type="button" class="conta-link" data-${tipo}="${esc(conta)}">${texto}</button>`;
const DEM_PILHA = [];

function rastroDA() {
  const d = DEM.dre.depreciacao;
  if (!d) return null;
  return DEM_PERIODO === "ttm" ? d.ttm : d.anos[DEM_PERIODO] || null;
}
function ebitda() {
  const e = vDRE("3.05"), da = rastroDA()?.valor;
  return e !== null && da !== null && da !== undefined ? e + da : null;
}

const EXPLICA = {
  "3.01": "Tudo o que a empresa faturou com vendas e serviços, já descontados impostos sobre vendas, devoluções e abatimentos.",
  "3.02": "Gasto direto para produzir ou adquirir o que foi vendido: matéria-prima, mão de obra da produção, mercadorias para revenda.",
  "3.03": "Receita menos custo. Mostra quanto sobra da venda antes das despesas de estrutura.",
  "3.04": "Despesas para manter a empresa funcionando (vender, administrar) e outros ganhos e perdas operacionais, incluindo equivalência patrimonial.",
  "3.05": "EBIT: resultado da operação antes de juros e impostos.",
  "3.06": "Receitas de aplicações menos despesas com juros de dívidas, variação cambial e outros itens financeiros.",
  "3.07": "Lucro antes do imposto de renda e da contribuição social (LAIR).",
  "3.08": "Imposto de renda e CSLL: a parte corrente (paga no período) e a diferida (efeito contábil que será pago ou recuperado no futuro).",
  "3.09": "Lucro das atividades que a empresa continua operando.",
  "3.10": "Resultado de negócios vendidos ou encerrados, separado para não distorcer a comparação.",
  "3.11": "Lucro (ou prejuízo) final do período, de todos os sócios.",
  "EBITDA": "Lucro operacional antes de juros, impostos, depreciação e amortização. Não existe na DRE oficial: é calculado somando ao EBIT a depreciação, que vem da DVA. Aproxima a geração de caixa da operação.",
  "DA": "Depreciação (desgaste de máquinas e prédios), amortização (de intangíveis) e exaustão (de recursos naturais). É uma despesa contábil que não sai do caixa no período; a CVM a mostra na DVA, linha 7.04.01.",
  "1": "Tudo o que a empresa tem ou tem a receber.",
  "1.01": "Bens e direitos que viram dinheiro em até 12 meses.",
  "1.02": "Bens e direitos de longo prazo: o que fica com a empresa por mais de 12 meses.",
  "2": "De onde veio o dinheiro: obrigações com terceiros mais o patrimônio dos sócios.",
  "2.01": "Obrigações que vencem em até 12 meses.",
  "2.02": "Obrigações que vencem depois de 12 meses.",
  "2.03": "O que pertence aos sócios: capital investido mais lucros retidos.",
};

function ligarContas() {
  document.querySelectorAll("#dem-corpo [data-dre]").forEach((el) => el.addEventListener("click", (ev) => {
    ev.stopPropagation(); abrirConta("dre", el.dataset.dre, true);
  }));
  document.querySelectorAll("#dem-corpo [data-bp]").forEach((el) => el.addEventListener("click", (ev) => {
    ev.stopPropagation(); abrirConta("bp", el.dataset.bp, true);
  }));
}

function abrirConta(tipo, conta, novo = false) {
  if (novo) DEM_PILHA.length = 0;
  DEM_PILHA.push([tipo, conta]);
  const html = tipo === "dre" ? popupDRE(conta) : popupBP(conta);
  $("#painel-corpo").innerHTML = html;
  $("#painel-corpo").querySelectorAll("[data-dre]").forEach((el) => el.addEventListener("click", () => abrirConta("dre", el.dataset.dre)));
  $("#painel-corpo").querySelectorAll("[data-bp]").forEach((el) => el.addEventListener("click", () => abrirConta("bp", el.dataset.bp)));
  $("#painel-voltar").hidden = DEM_PILHA.length < 2;
  $("#painel-voltar").onclick = () => { DEM_PILHA.pop(); const [t, c] = DEM_PILHA.pop(); abrirConta(t, c); };
  $("#painel").scrollTop = 0;
  if (!$("#painel").open) $("#painel").showModal();
}

function composicao(filhos, total, valorDe, tipo) {
  if (!filhos.length) return `<p class="vazio-msg">Esta é a conta mais detalhada que a empresa informa à CVM.</p>`;
  const soma = filhos.reduce((s, f) => s + (valorDe(f.conta) || 0), 0);
  const maxAbs = Math.max(...filhos.map((f) => Math.abs(valorDe(f.conta) || 0)), 1);
  const bate = total === null || Math.abs(soma - total) <= Math.abs(total) * 0.005 + 1;
  return `<div class="comp-lista">${filhos.map((f) => {
      const v = valorDe(f.conta);
      const temFilhos = (tipo === "dre" ? DEM.dre.linhas : DEM.balanco.linhas).some((l) => l.conta.startsWith(f.conta + "."));
      return `<button type="button" class="comp-item" data-${tipo}="${esc(f.conta)}">
        <span class="ci-nome"><code>${esc(f.conta)}</code> ${esc(f.descricao)}${temFilhos ? " ›" : ""}</span>
        <span class="ci-valor ${v < 0 ? "neg" : ""}">${sinalBrl(v)}</span>
        <span class="ci-barra"><i style="width:${(Math.abs(v || 0) / maxAbs) * 100}%;background:var(${v < 0 ? "--c2" : "--c1"})"></i></span>
        <span class="ci-pct">${pct(pctDe(v, total), 1)} do total</span></button>`;
    }).join("")}</div>
    <div class="total"><span>Soma das subcontas</span><span>${sinalBrl(soma)}</span></div>
    ${bate ? "" : `<p class="dica">A soma difere do total informado (${sinalBrl(total)}): a empresa não detalha todas as subcontas, ou há subcontas além do nível mostrado.</p>`}`;
}

function popupDRE(conta) {
  const periodo = DEM_PERIODO === "ttm" ? "últimos 12 meses" : `ano ${DEM_PERIODO}`;
  const receita = vDRE("3.01");
  if (conta === "EBITDA" || conta === "DA") {
    const ehE = conta === "EBITDA";
    const v = ehE ? ebitda() : rastroDA()?.valor ?? null;
    return `<div class="p-cab"><div class="sigla">DRE · ${esc(DEM.ticker)} · ${periodo} · indicador calculado</div>
        <h2 id="painel-titulo">${ehE ? "EBITDA" : "Depreciação e amortização"}</h2>
        <div class="valor">${sinalBrl(v)}</div></div>
      <p>${esc(EXPLICA[conta])}</p>
      ${ehE ? `<div class="p-formula">EBITDA = ${lk("dre", "3.05", "EBIT (3.05)")} + ${lk("dre", "DA", "D&A (DVA 7.04.01)")}</div>
        <div class="p-formula">${sinalBrl(vDRE("3.05"))} + ${sinalBrl(rastroDA()?.valor)} = <strong>${sinalBrl(v)}</strong> · margem ${pct(pctDe(v, receita), 1)}</div>` : ""}
      <div class="p-sec">Campos usados</div>
      ${(ehE ? [rastroDRE("3.05"), rastroDA()] : [rastroDA()]).filter(Boolean).map((r) =>
        `<div class="entrada">${r.nota ? `<p class="e-nota">${esc(r.nota)}</p>` : ""}${r.componentes.map((c) => htmlComponente(c, "R$")).join("")}</div>`).join("")}`;
  }
  const l = linhaDRE(conta);
  if (!l) return `<p>Conta ${esc(conta)} não encontrada.</p>`;
  const v = vDRE(conta), r = rastroDRE(conta);
  const filhos = DEM.dre.linhas.filter((x) => x.conta.startsWith(conta + ".") && x.nivel === l.nivel + 1);
  const mae = conta.includes(".") ? conta.split(".").slice(0, -1).join(".") : null;
  const hist = DEM.dre.anos.map((a) => `<td>${sinalBrl(l.anos[a]?.valor ?? null)}</td>`).join("");
  return `<div class="p-cab"><div class="sigla">DRE · ${esc(DEM.ticker)} · ${periodo}</div>
      <h2 id="painel-titulo"><code>${esc(conta)}</code> ${esc(l.descricao)}</h2>
      <div class="valor ${v < 0 ? "neg" : ""}">${sinalBrl(v)}</div></div>
    ${receita ? `<p class="dica">${pct(pctDe(v, receita), 1)} da receita líquida${mae && linhaDRE(mae) ? ` · faz parte de ${lk("dre", mae, `${esc(mae)} ${esc(nomeDRE(mae))}`)}` : ""}</p>` : ""}
    ${EXPLICA[conta] ? `<p>${esc(EXPLICA[conta])}</p>` : ""}
    <div class="p-sec">Contas que compõem</div>
    ${composicao(filhos, v, vDRE, "dre")}
    ${DEM.dre.anos.length ? `<div class="p-sec">Por ano (DFP)</div><div class="tabela-scroll"><table><thead><tr>${DEM.dre.anos.map((a) => `<th>${a}</th>`).join("")}</tr></thead><tbody><tr>${hist}</tr></tbody></table></div>` : ""}
    <div class="p-sec">Campos usados (CVM)</div>
    <div class="entrada">${r?.nota ? `<p class="e-nota">${esc(r.nota)}</p>` : ""}${(r?.componentes || []).map((c) => htmlComponente(c, "R$")).join("") || `<p class="vazio-msg">Sem valor neste período.</p>`}</div>`;
}

function popupBP(conta) {
  const l = linhaBP(conta);
  if (!l) return `<p>Conta ${esc(conta)} não encontrada.</p>`;
  const v = vBP(conta), ant = vBPant(conta), total = vBP("1");
  const filhos = DEM.balanco.linhas.filter((x) => x.conta.startsWith(conta + ".") && x.nivel === l.nivel + 1);
  const mae = conta.includes(".") ? conta.split(".").slice(0, -1).join(".") : null;
  return `<div class="p-cab"><div class="sigla">Balanço · ${esc(DEM.ticker)} · posição em ${dataBR(DEM.balanco.ref)}</div>
      <h2 id="painel-titulo"><code>${esc(conta)}</code> ${esc(l.descricao)}</h2>
      <div class="valor ${v < 0 ? "neg" : ""}">${sinalBrl(v)}</div></div>
    <p class="dica">${pct(pctDe(v, total), 1)} do total · antes: ${sinalBrl(ant)}${ant ? ` (${pct((v / ant - 1) * 100, 1)})` : ""}
      ${mae && linhaBP(mae) ? ` · faz parte de ${lk("bp", mae, `${esc(mae)} ${esc(nomeBP(mae))}`)}` : ""}</p>
    ${EXPLICA[conta] ? `<p>${esc(EXPLICA[conta])}</p>` : ""}
    <div class="p-sec">Contas que compõem</div>
    ${composicao(filhos, v, vBP, "bp")}
    <div class="p-sec">Campos usados (CVM)</div>
    <div class="entrada">${[l.atual, l.anterior].filter(Boolean).flatMap((x) => x.componentes).map((c) => htmlComponente(c, "R$")).join("")}</div>`;
}


// =====================================================================
// ANÁLISE VERTICAL E HORIZONTAL
// =====================================================================
let DEM_AN = { dre: "vertical", bp: "vertical" };
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const rotuloPeriodo = (p) => `${MESES_ABREV[+p.inicio.slice(5, 7) - 1]}–${MESES_ABREV[+p.fim.slice(5, 7) - 1]}/${p.fim.slice(2, 4)}`;

// variação entre dois valores; com troca de sinal (lucro → prejuízo) a % não tem significado
function variacao(a, b) {
  if (a === null || a === undefined || b === null || b === undefined || b === 0) return null;
  if (Math.sign(a) !== Math.sign(b) && a !== 0) return "n/s";
  return (a / b - 1) * 100;
}
const fmtVar = (x, base100 = false) => x === null ? "—" : x === "n/s" ? `<span class="sub-tk" title="Mudou de sinal: a variação % não tem significado">n/s</span>`
  : base100 ? nf(0).format(100 + x) : `<span class="ah">${x > 0 ? "▲" : x < 0 ? "▼" : ""}</span>${x > 0 ? "+" : ""}${nf(1).format(x)}%`;

/* colunas: [{rotulo, sub, v(conta), compara: índice da coluna anterior p/ horizontal, base: índice da coluna base 100}] */
function tabelaAnalise(tipo, colunas, linhas, contaBase, nomeBase) {
  const modo = DEM_AN[tipo];
  const cel = (col, conta) => {
    const v = col.v(conta);
    if (modo === "valores") return `<span class="${v < 0 ? "neg" : ""}">${sinalBrl(v)}</span>`;
    if (modo === "vertical") { const b = col.v(contaBase); return v === null || !b ? "—" : pct(v / Math.abs(b) * 100, 1); }
    const ref = modo === "horizontal" ? col.compara : col.base;
    if (ref === null || ref === undefined) return modo === "base100" && v !== null ? "100" : "—";
    return fmtVar(variacao(v, colunas[ref].v(conta)), modo === "base100");
  };
  const MODOS = [["valores", "Valores (R$)"], ["vertical", "Vertical (% " + nomeBase + ")"], ["horizontal", "Horizontal (variação %)"], ["base100", "Base 100"]];
  const EXPL = {
    valores: "Os valores de cada período, como estão nos documentos da CVM.",
    vertical: `Cada linha dividida por ${nomeBase === "da receita" ? "a receita líquida (3.01) do mesmo período" : "o ativo total (1) da mesma data"}. Mostra a <strong>estrutura</strong>: quanto cada item pesa, e permite comparar empresas de tamanhos diferentes.`,
    horizontal: "Variação de cada linha em relação ao período anterior da mesma série. Mostra a <strong>evolução</strong>: o que cresceu mais rápido. As setas mostram se a linha cresceu ou diminuiu em tamanho, sem dizer se isso é bom ou ruim: um custo que passa de R$ 100 para R$ 120 aparece como ▲ +20%. \"n/s\" = mudou de sinal (ex.: lucro virou prejuízo), a % não tem significado.",
    base100: "Cada linha começa em 100 no primeiro período da série. 130 = 30% acima do início. Bom para ver qual linha cresceu mais no acumulado.",
  };
  return `<div class="av-modos" role="tablist">${MODOS.map(([k, n]) => `<button type="button" class="${modo === k ? "ativo" : ""}" data-av="${tipo}" data-modo="${k}">${n}</button>`).join("")}</div>
    <p class="dica">${EXPL[modo]}</p>
    <div class="tabela-scroll"><table class="arvore av"><thead><tr><th>Conta</th>${colunas.map((c) => `<th>${c.rotulo}${c.sub ? `<span class="sub-tk">${c.sub}</span>` : ""}</th>`).join("")}</tr></thead><tbody>
      ${linhas.map((l) => `<tr class="n${l.nivel}"><td><code>${esc(l.conta)}</code> ${esc(l.descricao)}</td>${colunas.map((c) => `<td>${cel(c, l.conta)}</td>`).join("")}</tr>`).join("")}
    </tbody></table></div>`;
}

function analiseDRE() {
  const d = DEM.dre, cols = [];
  d.anos.forEach((a, i) => cols.push({ rotulo: a, sub: "ano", v: (c) => linhaDRE(c)?.anos[a]?.valor ?? null, compara: i ? i - 1 : null, base: i ? 0 : null }));
  const ac = d.acumulado;
  if (ac?.fonte === "ITR" && ac.atual && ac.anterior) {
    const i0 = cols.length;
    cols.push({ rotulo: rotuloPeriodo(ac.anterior), sub: "acumulado", v: (c) => linhaDRE(c)?.acumulado?.anterior?.valor ?? null, compara: null, base: null });
    cols.push({ rotulo: rotuloPeriodo(ac.atual), sub: "acumulado", v: (c) => linhaDRE(c)?.acumulado?.atual?.valor ?? null, compara: i0, base: i0 });
  }
  const linhas = d.linhas.filter((l) => l.nivel <= 2 && !l.conta.startsWith("3.99") && cols.some((c) => c.v(l.conta)));
  return `<h2>Análise vertical e horizontal da DRE</h2>
    ${cols.length < 2 ? `<p class="dica">Só há um período disponível; a análise horizontal precisa de pelo menos dois.</p>` : ""}
    ${tabelaAnalise("dre", cols, linhas, "3.01", "da receita")}
    ${ac?.fonte === "ITR" ? `<p class="dica">Os acumulados comparam o mesmo intervalo de meses nos dois anos (o ITR traz as duas colunas), o que evita a distorção de sazonalidade.</p>` : ""}`;
}

function analiseBP() {
  const b = DEM.balanco, cols = [];
  (b.anos || []).forEach((a, i) => cols.push({ rotulo: `31/12/${a.slice(2)}`, sub: "fim do ano", v: (c) => linhaBP(c)?.anos?.[a] ?? null, compara: i ? i - 1 : null, base: i ? 0 : null }));
  const ultAno = (b.anos || []).at(-1);
  if (!ultAno || !b.ref.startsWith(ultAno + "-12-31")) {
    const i = cols.length;
    cols.push({ rotulo: dataBR(b.ref), sub: "atual", v: (c) => linhaBP(c)?.atual?.valor ?? null, compara: i ? i - 1 : null, base: i ? 0 : null });
  }
  const linhas = b.linhas.filter((l) => l.nivel <= 3 && cols.some((c) => c.v(l.conta)));
  return `<h2>Análise vertical e horizontal do balanço</h2>
    ${tabelaAnalise("bp", cols, linhas, "1", "do ativo total")}`;
}

function ligarAnalise(tipo) {
  document.querySelectorAll(`[data-av="${tipo}"]`).forEach((b) => b.addEventListener("click", () => {
    DEM_AN[tipo] = b.dataset.modo;
    $(tipo === "dre" ? "#av-dre" : "#av-bp").innerHTML = tipo === "dre" ? analiseDRE() : analiseBP();
    ligarAnalise(tipo);
  }));
}
