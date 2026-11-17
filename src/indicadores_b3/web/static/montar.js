// "Montar minha carteira": objetivo, limites, renda fixa, valor → pesos, riscos e lista de compras.
// Usa os campos do formulário de cima (ativos, histórico, taxa livre de risco, retorno esperado).
const RF_ID = "RENDA FIXA (CDI)";
let MONT = { objetivo: "max_sharpe", vol: 12, ret: 15, com_rf: true, rf_min: 0, rf_max: 100, cov: "ledoit", valor: 10000, limites: {} };
let MONT_RES = null;
MONT.globais = {}; MONT.sobrescritas = {}; MONT.visoes = [];
let CMA = null, CMA_CHAVE = "";
const modeloAtual = () => $("#modelo-retorno").value;

const OBJ_INFO = [
  ["min_risco", "Menor risco", "A combinação de ativos que menos oscila. A renda fixa fica no mínimo que você definir."],
  ["max_sharpe", "Melhor risco × retorno", "Maior retorno acima do CDI por unidade de risco (máximo Sharpe). A renda fixa fica no mínimo."],
  ["vol_alvo", "Risco-alvo", "Você diz quanto aceita oscilar por ano; o site busca o maior retorno esperado dentro disso, misturando renda fixa."],
  ["ret_alvo", "Retorno-alvo", "Você diz quanto quer ganhar por ano; o site busca o menor risco que chega lá."],
];

const tickersMont = () => [...new Set($("#tickers-carteira").value.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean))];

function renderMontarPainel() {
  const tks = tickersMont(), pmax = +($("#form-carteira [name=peso_max]").value || 100);
  for (const t of tks) MONT.limites[t] ??= { min: 0, max: pmax };
  const alvo = MONT.objetivo === "vol_alvo" ? ["vol", "Risco máximo aceitável (% ao ano)", "Referências aproximadas de volatilidade: renda fixa pós-fixada ≈ 0%, carteira conservadora 3–6%, moderada 6–12%, Ibovespa 20–25%."]
    : MONT.objetivo === "ret_alvo" ? ["ret", "Retorno esperado desejado (% ao ano)", "Com o CDI a " + ($("#cdi-fonte strong")?.textContent.match(/[\d,]+%/)?.[0] || "—") + ", pedir mais que isso exige assumir risco."] : null;
  const m = modeloAtual();
  $("#fluxo-painel").innerHTML = `<ol class="fluxo-gestora" aria-label="Como uma gestora monta uma carteira">
      <li class="${["blocos", "bl"].includes(m) ? "feito" : ""}"><b>Premissas de mercado</b><span>retorno esperado de cada classe (CMA)</span></li>
      <li class="${m === "bl" ? "feito" : ""}"><b>Visões</b><span>suas convicções, com confiança (Black-Litterman)</span></li>
      <li class="feito"><b>Política de investimento</b><span>objetivo de risco e limites</span></li>
      <li class="feito"><b>Otimização</b><span>pesos dentro das regras</span></li>
      <li class="feito"><b>Implementação</b><span>lista de compras</span></li>
      <li><b>Monitoramento</b><span>acompanhar e rebalancear em Minhas carteiras</span></li>
    </ol>`;
  $("#montar-painel").innerHTML = `<div class="montar-cfg">
    <div class="bloco">
      <h3><span class="n-mini">1</span> Qual é o seu objetivo?</h3>
      <div class="objetivos">${OBJ_INFO.map(([k, t, d]) => `<label class="obj ${MONT.objetivo === k ? "ativo" : ""}">
        <input type="radio" name="m-obj" value="${k}" ${MONT.objetivo === k ? "checked" : ""}><b>${t}</b><span>${d}</span></label>`).join("")}</div>
      ${alvo ? `<label class="campo m-alvo"><span>${alvo[1]}</span><input type="number" id="m-alvo" step="0.5" min="0.5" value="${MONT[alvo[0]]}"></label><p class="dica">${alvo[2]}</p>` : ""}
    </div>
    <div class="bloco">
      <h3><span class="n-mini">2</span> Limites por ativo</h3>
      <div class="tabela-scroll"><table class="m-lim"><thead><tr><th>Ativo</th><th>Mín. %</th><th>Máx. %</th></tr></thead><tbody>
        ${tks.map((t) => `<tr><td><code>${esc(t)}</code></td>
          <td><input type="number" min="0" max="100" step="1" data-lim="${esc(t)}" data-k="min" value="${MONT.limites[t].min}"></td>
          <td><input type="number" min="0" max="100" step="1" data-lim="${esc(t)}" data-k="max" value="${MONT.limites[t].max}"></td></tr>`).join("")
          || `<tr><td colspan="3">Informe os ativos no campo acima.</td></tr>`}
        <tr class="m-rf ${MONT.com_rf ? "" : "off"}"><td><label class="m-rf-rot"><input type="checkbox" id="m-rf" ${MONT.com_rf ? "checked" : ""}> Renda fixa (CDI)</label></td>
          <td><input type="number" min="0" max="100" step="1" id="m-rf-min" value="${MONT.rf_min}" ${MONT.com_rf ? "" : "disabled"}></td>
          <td><input type="number" min="0" max="100" step="1" id="m-rf-max" value="${MONT.rf_max}" ${MONT.com_rf ? "" : "disabled"}></td></tr>
      </tbody></table></div>
      <p class="dica">Ex.: cripto no máximo 5%, renda fixa no mínimo 20% (reserva). A renda fixa rende o CDI, sem oscilar.</p>
    </div>
    <div class="bloco m-fim">
      <h3><span class="n-mini">3</span> Quanto vai investir?</h3>
      <label class="campo"><span>Valor (R$)</span><input type="number" id="m-valor" min="1" step="100" value="${MONT.valor}"></label>
      <label class="check m-cov"><input type="checkbox" id="m-cov" ${MONT.cov === "ledoit" ? "checked" : ""}>
        <span>Estimativa robusta do risco (Ledoit-Wolf). Recomendado: reduz pesos extremos causados por ruído nos dados.</span></label>
      <button type="button" id="m-montar">Montar carteira</button>
    </div>
  </div>`;
  document.querySelectorAll("[name=m-obj]").forEach((r) => r.addEventListener("change", () => { MONT.objetivo = r.value; renderMontarPainel(); }));
  $("#m-alvo")?.addEventListener("input", (e) => { MONT[MONT.objetivo === "vol_alvo" ? "vol" : "ret"] = +e.target.value; });
  document.querySelectorAll("[data-lim]").forEach((i) => i.addEventListener("input", () => { MONT.limites[i.dataset.lim][i.dataset.k] = +i.value; }));
  $("#m-rf").addEventListener("change", (e) => { MONT.com_rf = e.target.checked; renderMontarPainel(); });
  $("#m-rf-min").addEventListener("input", (e) => { MONT.rf_min = +e.target.value; });
  $("#m-rf-max").addEventListener("input", (e) => { MONT.rf_max = +e.target.value; });
  $("#m-valor").addEventListener("input", (e) => { MONT.valor = +e.target.value; });
  $("#m-cov").addEventListener("change", (e) => { MONT.cov = e.target.checked ? "ledoit" : "amostral"; });
  $("#m-montar").addEventListener("click", () => $("#form-carteira").requestSubmit());
}

async function montarCarteira() {
  const f = new FormData($("#form-carteira")), tks = tickersMont();
  const corpo = {
    tickers: tks, periodo: f.get("periodo"), modelo: f.get("modelo") || "blocos", cov: MONT.cov,
    globais: MONT.globais, sobrescritas: MONT.sobrescritas, visoes: f.get("modelo") === "bl" ? MONT.visoes : [],
    objetivo: MONT.objetivo, alvo: MONT.objetivo === "vol_alvo" ? MONT.vol : MONT.objetivo === "ret_alvo" ? MONT.ret : null,
    limites: Object.fromEntries(tks.map((t) => [t, MONT.limites[t] || { min: 0, max: 100 }])),
    com_rf: MONT.com_rf, rf_min: MONT.rf_min, rf_max: MONT.rf_max, valor: MONT.valor,
  };
  if (f.get("rf")) corpo.rf = +f.get("rf");
  if (corpo.modelo === "capm" && f.get("mercado")) corpo.mercado = +f.get("mercado");
  const st = $("#status-carteira"), botoes = [$("#botao-carteira"), $("#m-montar")];
  botoes.forEach((b) => b && (b.disabled = true));
  st.className = "status"; st.textContent = "Montando a carteira e testando a estabilidade dos pesos…";
  try {
    MONT_RES = await fetch("/api/carteira/montar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) })
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });
    MONT_RES.periodo_codigo = corpo.periodo;
    st.textContent = "";
    renderMontagem();
  } catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { botoes.forEach((b) => b && (b.disabled = false)); }
}

function leiturasMont(r) {
  const out = [], m = r.metricas;
  // compara dentro da parte de risco (a renda fixa não oscila, então não entra na conta)
  const pesoRisco = r.alocacao.filter((a) => a.ticker !== RF_ID).reduce((s, a) => s + a.peso, 0) || 100;
  for (const a of r.alocacao) {
    if (a.ticker === RF_ID || a.peso < 0.5) continue;
    const rel = a.peso / pesoRisco * 100;
    if (a.contribuicao_risco > rel + 15 && a.contribuicao_risco > 25)
      out.push(["aviso", `<strong>${esc(a.ticker)}</strong> é ${pct(rel, 0)} da parte investida em ativos de risco, mas responde por ${pct(a.contribuicao_risco, 0)} da oscilação da carteira.`]);
  }
  const instaveis = r.alocacao.filter((a) => a.faixa && a.faixa.p90 - a.faixa.p10 > 30).map((a) => (a.ticker === RF_ID ? "renda fixa" : a.ticker));
  if (instaveis.length) out.push(["aviso", `Pesos instáveis em ${instaveis.map(esc).join(", ")}: com pequenas mudanças nos dados o peso varia mais de 30 pontos. Considere limites mais apertados ou pesos parecidos entre eles.`]);
  if (m.n_efetivo < 3 && r.alocacao.filter((a) => a.ticker !== RF_ID).length >= 4)
    out.push(["aviso", `Concentrada: a parte de risco equivale a só ${nf(1).format(m.n_efetivo)} ativos de mesmo peso. Limites máximos menores aumentam a diversificação.`]);
  (r.premissas?.ativos || []).filter((a) => a.aviso).forEach((a) => out.push(["aviso", `<strong>${esc(a.ticker)}</strong>: ${esc(a.aviso)}`]));
  if (r.parametros.modelo === "historico" && r.parametros.objetivo !== "min_risco")
    out.push(["info", "O retorno esperado vem da média histórica, que favorece quem mais subiu no passado. Compare escolhendo <strong>CAPM</strong> em \"Retorno esperado\"."]);
  if (!out.some((o) => o[0] === "aviso")) out.unshift(["ok", "Sem concentração de risco relevante e com pesos estáveis nas reamostragens."]);
  return out;
}

function renderMontagem() {
  const r = MONT_RES, p = r.parametros, m = r.metricas;
  const total = r.compras.reduce((s, c) => s + c.valor, 0);
  const barra = (a) => {
    const fx = a.faixa;
    return `<div class="m-barra" title="${fx ? `Faixa nas reamostragens: ${pct(fx.p10, 0)} a ${pct(fx.p90, 0)}` : ""}">
      ${fx ? `<span class="m-faixa" style="left:${fx.p10}%;width:${Math.max(fx.p90 - fx.p10, 0.5)}%"></span>` : ""}
      <span class="m-peso" style="width:${a.peso}%"></span></div>`;
  };
  $("#montar-resultado").innerHTML = `<div class="viz">
    <div class="dados-usados">
      <span class="pill">${esc(p.objetivo_nome)}${p.alvo ? `: ${pct(p.alvo, 1)} a.a.` : ""}</span>
      <span class="pill">Histórico: ${esc(p.periodo)} · ${dataBR(p.inicio)} a ${dataBR(p.fim)}</span>
      <span class="pill">${["blocos", "bl"].includes(p.modelo) ? "Renda fixa (CDI esperado no horizonte)" : "CDI"}: ${pct(p.rf)}</span>
      <span class="pill">Retorno esperado: ${esc(p.modelo_nome || p.modelo)}</span>
      <span class="pill">Risco: ${p.cov === "ledoit" ? "Ledoit-Wolf" : "covariância amostral"}</span>
    </div>
    <div class="m-kpis">
      <div><span>Retorno esperado</span><b>${pct(m.retorno, 1)}</b><small>ao ano</small></div>
      <div><span>Volatilidade</span><b>${pct(m.volatilidade, 1)}</b><small>ao ano</small></div>
      <div><span>Sharpe</span><b>${num(m.sharpe)}</b><small>retorno extra por risco</small></div>
      <div><span>Num mês ruim (1 em 20)</span><b class="neg">${pct(m.var95_mes, 1)}</b><small>R$ ${nf(0).format(Math.abs(m.var95_mes) / 100 * p.valor)} de ${brlInt(p.valor)}</small></div>
      <div><span>Pior queda no período</span><b class="neg">${pct(m.max_drawdown, 1)}</b><small>${dataBR(m.drawdown_de)} a ${dataBR(m.drawdown_ate)}</small></div>
    </div>
    <div class="m-leituras">${leiturasMont(r).map(([t, h]) => `<p class="m-l ${t}">${h}</p>`).join("")}</div>

    <div class="bloco">
      <h2>Lista de compras · ${brlInt(p.valor)}</h2>
      <p class="dica">Preços do último fechamento disponível. Ações, FIIs e ETFs em quantidades inteiras; a sobra vai para a renda fixa.</p>
      <div class="tabela-scroll"><table class="m-compras"><thead><tr><th>Ativo</th><th>Preço</th><th>Quantidade</th><th>Valor</th><th>Peso real</th><th>Como comprar</th></tr></thead><tbody>
        ${r.compras.filter((c) => c.valor > 0.5).map((c) => `<tr><td><strong>${esc(c.ticker === RF_ID ? "Renda fixa (CDI)" : c.ticker)}</strong></td>
          <td>${c.preco ? `R$ ${num(c.preco)}<span class="sub-tk">${dataBR(c.data_preco)}</span>` : "—"}</td>
          <td>${c.quantidade === null ? "—" : c.classe === "b3" ? nf(0).format(c.quantidade) : nf(c.classe === "tesouro" ? 2 : 6).format(c.quantidade)}</td>
          <td>R$ ${num(c.valor)}</td><td>${pct(c.peso_real, 1)}</td><td class="m-como">${esc(c.como)}</td></tr>`).join("")}
        <tr class="soma"><td>Total</td><td></td><td></td><td>R$ ${num(total)}</td><td>100%</td><td></td></tr>
      </tbody></table></div>
      <div class="mc-acoes">
        <button type="button" id="m-salvar">Salvar em Minhas carteiras</button>
        <button type="button" class="secundario" id="m-copiar">Copiar lista</button>
        ${r.rf_equivalente ? `<span class="dica">Ao salvar, a renda fixa vira <code>${esc(r.rf_equivalente)}</code> (Tesouro Selic mais curto à venda), para o acompanhamento ter preço.</span>` : ""}
      </div>
    </div>

    ${r.black_litterman ? htmlResultadoBL(r.black_litterman) : ""}
    <div class="bloco">
      <h2>Alocação</h2>
      <p class="dica">A barra escura é o peso; a faixa clara mostra entre quanto e quanto o peso ficou em ${r.estabilidade_n || "várias"} reamostragens do histórico (10% a 90%). Faixa estreita = peso confiável.</p>
      <div class="tabela-scroll"><table class="m-aloc"><thead><tr><th>Ativo</th><th>Peso</th><th></th><th>Parte do risco</th><th>Retorno esperado</th><th>Volatilidade</th></tr></thead><tbody>
        ${r.alocacao.map((a) => `<tr class="${a.peso < 0.05 ? "zero" : ""}"><td><strong>${esc(a.ticker === RF_ID ? "Renda fixa (CDI)" : a.ticker)}</strong><span class="sub-tk">${esc(a.ticker === RF_ID ? "rende o CDI, sem oscilar" : a.nome)}</span></td>
          <td><b>${pct(a.peso, 1)}</b>${a.faixa ? `<span class="sub-tk">${pct(a.faixa.p10, 0)}–${pct(a.faixa.p90, 0)}</span>` : ""}</td>
          <td class="m-col-barra">${barra(a)}</td>
          <td><div class="m-barra rc"><span class="m-peso" style="width:${Math.max(0, Math.min(100, a.contribuicao_risco))}%"></span></div><span class="sub-tk">${pct(a.contribuicao_risco, 0)}</span></td>
          <td>${pct(a.retorno_esperado, 1)}</td><td>${pct(a.volatilidade, 1)}</td></tr>`).join("")}
      </tbody></table></div>
    </div>

    <div class="bloco">
      <h2>Como essa carteira teria se saído</h2>
      <p class="dica">Valor de R$ 100 aplicados no início, com os pesos de hoje e rebalanceamento diário. <strong>Atenção:</strong> os pesos foram escolhidos olhando esse mesmo período, então o resultado é otimista; para um teste justo (fora da amostra), use a aba Modelos.</p>
      <div class="legenda"><span><i class="linha" style="background:var(--c1)"></i>Carteira</span><span><i class="linha" style="background:var(--c2)"></i>Ibovespa</span><span><i class="linha tracejada"></i>Renda fixa à taxa usada (${pct(p.rf, 1)} a.a.)</span></div>
      <div class="grafico" id="m-hist"></div>
      <p class="dica">Retorno anualizado no período: <strong>${pct(m.retorno_hist_aa, 1)}</strong>. Perda média nos 5% piores meses (CVaR): ${pct(m.cvar95_mes, 1)}.</p>
    </div>
    <div class="bloco" id="m-diag"></div>

    <div class="conceitos">
      <div class="bloco"><h3>Parte do risco</h3><div class="eq">RCᵢ = wᵢ × (Σw)ᵢ ÷ σ²</div><p>Quanto cada ativo contribui para a oscilação total. Um ativo pequeno e muito volátil pode dominar o risco.</p></div>
      <div class="bloco"><h3>Mês ruim (VaR 95%)</h3><div class="eq">5º percentil dos retornos de 21 dias</div><p>Em 1 de cada 20 meses do histórico, a carteira perdeu pelo menos isso. O CVaR é a média desses meses ruins.</p></div>
      <div class="bloco"><h3>Pior queda (drawdown)</h3><div class="eq">mín (valor ÷ máximo anterior − 1)</div><p>A maior perda do topo ao fundo no período. Pergunte-se se você aguentaria ver isso sem vender.</p></div>
      <div class="bloco"><h3>Faixa dos pesos</h3><div class="eq">bootstrap: reamostrar dias e reotimizar</div><p>Se o peso muda muito com pequenas mudanças nos dados, a otimização está reagindo a ruído. Prefira limites que deixem as faixas estreitas.</p></div>
      <div class="bloco"><h3>Ledoit-Wolf</h3><div class="eq">Σ = δ·alvo + (1 − δ)·Σamostral</div><p>"Encolhe" a matriz de risco para uma estrutura simples, na medida ótima. Menos ruído, pesos menos extremos.</p></div>
      <div class="bloco"><h3>Nº efetivo de ativos</h3><div class="eq">1 ÷ Σ wᵢ²</div><p>${nf(1).format(m.n_efetivo)} aqui. 10 ativos com 10% cada dão 10; um ativo com 90% dá perto de 1.</p></div>
    </div>
  </div>`;
  if (typeof iniciarDiagnostico === "function") iniciarDiagnostico(r);
  const h = r.historico;
  graficoLinhas($("#m-hist"), h.datas, [
    { nome: "Carteira", cor: "--c1", v: h.carteira, largura: 2.5 },
    ...(h.refs.Ibovespa ? [{ nome: "Ibovespa", cor: "--c2", v: h.refs.Ibovespa }] : []),
    { nome: "Renda fixa", cor: "--muted", v: h.refs["CDI (taxa atual)"], tracejada: true },
  ], { formatoY: (v) => nf(0).format(v), base: 100 });
  $("#m-salvar").addEventListener("click", () => {
    const pesos = {};
    for (const c of r.compras) if (c.peso_real > 0.005) {
      const t = c.ticker === RF_ID ? (r.rf_equivalente || null) : c.ticker;
      if (t) pesos[t] = +(pesos[t] || 0) + c.peso_real;
    }
    const soma = Object.values(pesos).reduce((s, v) => s + v, 0);
    for (const t in pesos) pesos[t] = +(pesos[t] * 100 / soma).toFixed(2);
    salvarCarteiraSugerida(pesos, `${p.objetivo_nome.split(" (")[0]} · ${new Date().toLocaleDateString("pt-BR")}`, Math.round(p.valor),
      `Montada no site: ${p.objetivo_nome}${p.alvo ? ` ${p.alvo}% a.a.` : ""}, histórico ${p.periodo}`);
  });
  $("#m-copiar").addEventListener("click", async () => {
    const txt = r.compras.filter((c) => c.valor > 0.5).map((c) => `${c.ticker === RF_ID ? "Renda fixa (CDI)" : c.ticker}\t${c.quantidade ?? ""}\tR$ ${num(c.valor)}`).join("\n");
    try { await navigator.clipboard.writeText(txt); $("#m-copiar").textContent = "Copiado ✓"; } catch { $("#m-copiar").textContent = "Não consegui copiar"; }
  });
}

const brlInt = (v) => "R$ " + nf(0).format(v);
$("#tickers-carteira").addEventListener("input", renderMontarPainel);
$("#tickers-carteira").addEventListener("change", renderMontarPainel);
$("#form-carteira [name=peso_max]").addEventListener("change", () => { MONT.limites = {}; renderMontarPainel(); });
renderMontarPainel();


// ---------- Premissas de mercado (CMA) e visões (Black-Litterman) ----------
const fmtCMA = (v) => (v === null || v === undefined ? "—" : `${v < 0 ? "−" : ""}${nf(1).format(Math.abs(v))}%`);
const GLOBAIS_INFO = [
  ["horizonte", "Horizonte (anos)", "Prazo das premissas: pega os juros e a inflação da curva nesse prazo.", 1],
  ["crescimento_real", "Crescimento real do lucro (% a.a.)", "Ações: crescimento acima da inflação. Referência comum: PIB potencial, 1,5–2,5%.", 0.1],
  ["repreco", "Reprecificação (% a.a.)", "Ações: se você espera que os múltiplos (P/L) subam (+) ou caiam (−) até o horizonte.", 0.1],
  ["diluicao", "Diluição (% a.a.)", "Ações: emissão líquida de novas ações, que dilui o acionista.", 0.1],
  ["premio_acoes", "Prêmio de ações para ETFs (% a.a.)", "Retorno extra exigido da bolsa sobre o juro prefixado.", 0.5],
  ["inflacao_eua", "Inflação dos EUA (% a.a.)", "Usada no ouro. Meta do Fed: 2%.", 0.1],
  ["premio_cripto", "Prêmio de cripto (% a.a.)", "Não há fundamento observável; é uma opinião sua.", 0.5],
];

async function carregarPremissas(forcar = false) {
  const el = $("#premissas-painel"), m = modeloAtual();
  el.hidden = VISAO !== "montar" || !["blocos", "bl"].includes(m);
  if (el.hidden) return;
  const tks = tickersMont(), periodo = $("#form-carteira [name=periodo]").value;
  const chave = JSON.stringify([tks, periodo, MONT.globais]);
  if (!tks.length) { el.innerHTML = ""; return; }
  if (!forcar && CMA && chave === CMA_CHAVE) { renderPremissas(); return; }
  el.innerHTML = `<div class="bloco"><p class="status">Montando as premissas de mercado (curva do Tesouro, proventos, juros dos EUA)…</p></div>`;
  try {
    CMA = await fetch("/api/carteira/premissas", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: tks, periodo, globais: MONT.globais }) })
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });
    CMA_CHAVE = chave;
    renderPremissas();
  } catch (err) { el.innerHTML = `<div class="bloco"><p class="status erro">${esc(err.message)}</p></div>`; }
}

function renderPremissas() {
  const P = CMA, mk = P.mercado, g = P.globais, bl = modeloAtual() === "bl";
  const fonteLink = (r) => { const c = r.componentes?.[0]; return c?.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.fonte)} ↗</a>` : esc(c?.fonte || ""); };
  const nomes = P.ativos.map((a) => a.ticker);
  const opc = (sel) => nomes.map((t) => `<option ${t === sel ? "selected" : ""}>${esc(t)}</option>`).join("");
  $("#premissas-painel").innerHTML = `<div class="bloco premissas">
    <h3><span class="n-mini">★</span> Premissas de mercado</h3>
    <p class="prem-sub">Capital Market Assumptions · horizonte de ${nf(0).format(g.horizonte)} anos</p>
    <p class="dica">É como gestoras e fundos de pensão estimam retorno: cada classe decomposta em <strong>blocos observáveis hoje</strong>
      (taxa dos títulos, dividendos, inflação implícita, juros), e não a média do passado. Você pode sobrescrever qualquer número.
      Entenda: ${[["cma", "premissas de mercado"], ["grinold-kroner", "Grinold-Kroner"], ["black-litterman", "Black-Litterman"], ["processo-gestora", "como uma gestora monta a carteira"]]
        .map(([id, n]) => `<button type="button" class="link" data-artigo="${id}">${n}</button>`).join(" · ")}</p>
    <div class="dados-usados">
      <span class="pill">Juro prefixado em ${nf(0).format(g.horizonte)} anos (CDI esperado): <b>${fmtCMA(mk.juro_pre.valor)}</b> · ${fonteLink(mk.juro_pre)}</span>
      <span class="pill">Inflação implícita: <b>${fmtCMA(mk.inflacao.valor)}</b> · ${fonteLink(mk.inflacao)}</span>
      <span class="pill">Juro EUA 5 anos: <b>${fmtCMA(mk.juro_eua.valor)}</b> · ${fonteLink(mk.juro_eua)}${mk.juro_eua.nota ? " (padrão)" : ""}</span>
    </div>
    <details class="prem-globais"><summary>Ajustar premissas gerais</summary>
      <div class="prem-g-grid">${GLOBAIS_INFO.map(([k, n, d, st]) => `<label class="campo"><span title="${esc(d)}">${n}</span>
        <input type="number" step="${st}" data-glob="${k}" value="${g[k]}"><small class="sub-tk">${esc(d)}</small></label>`).join("")}</div>
      <button type="button" class="secundario" id="prem-recalc">Recalcular premissas</button>
    </details>
    <div class="tabela-scroll"><table class="prem-tab"><thead><tr><th>Ativo</th><th>Como o mercado estima</th><th>Blocos</th><th>Calculado</th><th>Sua premissa</th></tr></thead><tbody>
      ${P.ativos.map((a) => `<tr><td><strong>${esc(a.ticker)}</strong></td><td class="prem-met">${esc(a.metodo)}${a.aviso ? `<span class="prem-av">⚠ ${esc(a.aviso)}</span>` : ""}</td>
        <td class="prem-blocos">${a.blocos.map((b, i) => `<span class="chip-b">${i ? (b.valor < 0 ? "−" : "+") : ""} ${esc(b.nome)} <b>${fmtCMA(i ? Math.abs(b.valor) : b.valor)}</b></span>`).join("")}</td>
        <td><b>${fmtCMA(a.calculado)}</b></td>
        <td><input type="number" step="0.1" class="prem-inp" data-sobre="${esc(a.ticker)}" placeholder="${a.calculado === null ? "informe" : nf(1).format(a.calculado)}" value="${MONT.sobrescritas[a.ticker] ?? ""}"></td></tr>`).join("")}
    </tbody></table></div>
    <p class="dica">Os blocos somam aproximadamente (alguns se combinam por multiplicação, como juro × prêmio). Prefixados levados ao vencimento rendem a própria taxa; IPCA+ rende a taxa real mais a inflação.</p>
    ${bl ? htmlVisoes(opc) : `<p class="dica">Quer incluir as suas convicções? Escolha <strong>Black-Litterman</strong> em "Retorno esperado".</p>`}
  </div>`;
  document.querySelectorAll("[data-sobre]").forEach((i) => i.addEventListener("input", () => {
    if (i.value === "") delete MONT.sobrescritas[i.dataset.sobre]; else MONT.sobrescritas[i.dataset.sobre] = +i.value;
  }));
  document.querySelectorAll("[data-glob]").forEach((i) => i.addEventListener("input", () => { MONT.globais[i.dataset.glob] = +i.value; }));
  $("#prem-recalc").addEventListener("click", () => carregarPremissas(true));
  document.querySelectorAll("[data-artigo]").forEach((b) => b.addEventListener("click", () => { mostrarAba("estudos"); abrirEstudo(b.dataset.artigo); }));
  if (bl) ligarVisoes();
}

function htmlVisoes(opc) {
  return `<div class="visoes">
    <h3><span class="n-mini">✎</span> Suas visões</h3>
    <p class="prem-sub">Black-Litterman</p>
    <p class="dica">Como um comitê de investimentos: você registra convicções e o quanto confia nelas. O modelo mistura as premissas de mercado com as visões,
      na proporção da confiança e do risco de cada ativo. Sem visões, o resultado é igual às premissas.</p>
    ${MONT.visoes.map((v, i) => `<div class="visao" data-i="${i}">
      <select data-v="tipo"><option value="abs" ${v.tipo === "abs" ? "selected" : ""}>Retorno absoluto</option><option value="rel" ${v.tipo === "rel" ? "selected" : ""}>Um ativo melhor que outro</option></select>
      <select data-v="a">${opc(v.a)}</select>
      ${v.tipo === "rel" ? `<span>rende</span><input type="number" step="0.5" data-v="q" value="${v.q}"><span>p.p. a.a. acima de</span><select data-v="b">${opc(v.b)}</select>`
        : `<span>rende</span><input type="number" step="0.5" data-v="q" value="${v.q}"><span>% a.a.</span>`}
      <select data-v="confianca">${["baixa", "media", "alta"].map((c) => `<option value="${c}" ${v.confianca === c ? "selected" : ""}>Confiança ${c === "media" ? "média" : c}</option>`).join("")}</select>
      <button type="button" class="link perigo" data-rm="${i}" aria-label="Remover visão">×</button></div>`).join("")}
    <button type="button" class="secundario" id="visao-add">+ Adicionar visão</button>
  </div>`;
}

function ligarVisoes() {
  document.querySelectorAll(".visao").forEach((el) => {
    const v = MONT.visoes[+el.dataset.i];
    el.querySelectorAll("[data-v]").forEach((c) => c.addEventListener("change", () => {
      v[c.dataset.v] = c.dataset.v === "q" ? +c.value : c.value;
      if (c.dataset.v === "tipo") renderPremissas();
    }));
  });
  document.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { MONT.visoes.splice(+b.dataset.rm, 1); renderPremissas(); }));
  $("#visao-add").addEventListener("click", () => {
    const n = CMA.ativos.map((a) => a.ticker);
    MONT.visoes.push({ tipo: "rel", a: n[0], b: n[1] || n[0], q: 2, confianca: "media" });
    renderPremissas();
  });
}

function htmlResultadoBL(bl) {
  return `<div class="bloco"><h2>Premissas × após suas visões</h2>
    <p class="dica">O Black-Litterman move o retorno esperado na direção das visões, mais quanto maior a confiança. Ativos correlacionados com o da visão também se movem.</p>
    ${bl.visoes.length ? `<div class="tabela-scroll"><table class="m-compras"><thead><tr><th>Visão</th><th>Confiança</th><th>Premissas diziam</th><th>Você disse</th><th>Resultado</th></tr></thead><tbody>
      ${bl.visoes.map((v) => `<tr><td>${v.tipo === "rel" ? `${esc(v.a)} − ${esc(v.b)}` : esc(v.a)}</td><td>${esc(v.confianca === "media" ? "média" : v.confianca)}</td>
        <td>${fmtCMA(v.prior)}</td><td>${fmtCMA(v.q)}</td><td><b>${fmtCMA(v.posterior)}</b></td></tr>`).join("")}</tbody></table></div>` : `<p class="dica">Nenhuma visão registrada: o resultado usa só as premissas de mercado.</p>`}
    <div class="tabela-scroll"><table class="m-compras"><thead><tr><th>Ativo</th><th>Premissa de mercado</th><th>Após as visões</th><th>Diferença</th></tr></thead><tbody>
      ${bl.ativos.map((a) => `<tr><td><strong>${esc(a.ticker)}</strong></td><td>${fmtCMA(a.prior)}</td><td><b>${fmtCMA(a.posterior)}</b></td><td>${a.posterior - a.prior >= 0 ? "+" : "−"}${nf(2).format(Math.abs(a.posterior - a.prior))} p.p.</td></tr>`).join("")}
    </tbody></table></div></div>`;
}

$("#modelo-retorno").addEventListener("change", () => { renderMontarPainel(); carregarPremissas(); });
$("#tickers-carteira").addEventListener("change", () => carregarPremissas());
$("#form-carteira [name=periodo]").addEventListener("change", () => carregarPremissas());
document.querySelector('[data-aba="carteira"]').addEventListener("click", () => carregarPremissas());
if (location.hash === "#carteira") carregarPremissas();
