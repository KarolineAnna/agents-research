// Carteira eficiente → "Por que ficou abaixo do Ibovespa?": agente de carteira (com IA ou por regras fixas).
let DIAG = null;

function iniciarDiagnostico(r) {
  const el = $("#m-diag");
  if (!el) return;
  const pesos = Object.fromEntries(r.alocacao.filter((a) => a.peso >= 0.05).map((a) => [a.ticker, +a.peso.toFixed(2)]));
  el.innerHTML = `<h2>Diagnóstico contra o Ibovespa</h2>
    <p class="dica">O agente compara a carteira com o Ibovespa, mostra quem somou e quem tirou e depois investiga: formula hipóteses,
      testa cada uma nos primeiros 60% do período (treino) e confirma as melhores nos 40% finais, que ele não viu (reserva).
      A renda fixa fica sempre no peso que você escolheu.</p>
    <div class="mc-acoes">
      <button type="button" id="diag-ia">Diagnosticar com o agente de IA</button>
      <button type="button" class="secundario" id="diag-regras">Só os números (sem IA)</button>
    </div>
    <p class="status" id="diag-status"></p>
    <div id="diag-res"></div>`;
  const rodar = async (ia) => {
    const st = $("#diag-status");
    el.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    st.className = "status";
    st.textContent = ia ? "O agente está investigando: testando hipóteses no treino e confirmando na reserva (1 a 4 minutos)…" : "Calculando…";
    try {
      DIAG = await fetch("/api/carteira/diagnostico", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pesos, periodo: r.periodo_codigo || "3y", ia }) })
        .then(async (x) => { const j = await x.json(); if (!x.ok) throw new Error(j.detail || x.statusText); return j; });
      st.textContent = "";
      $("#diag-res").innerHTML = htmlDiagnostico(DIAG);
    } catch (err) { st.className = "status erro"; st.textContent = err.message; }
    finally { el.querySelectorAll("button").forEach((b) => { b.disabled = false; }); }
  };
  $("#diag-ia").addEventListener("click", () => rodar(true));
  $("#diag-regras").addEventListener("click", () => rodar(false));
}

function dgItens(r) {
  const out = {};
  for (const d of [r.diagnostico, r.diagnostico_treino, r.laboratorio_dossie, ...Object.values(r.cara_ou_barata || {})]) for (const x of d?.itens || []) out[x.id] = x;
  return out;
}

// [C12] vira uma marca discreta com o nome e a fórmula do número
function dgCitar(html, itens) {
  return html.replace(/\[((?:[A-Z0-9]+\.)?[CVTE]\d+)\]/g, (m, id) => {
    const x = itens[id];
    return `<span class="dg-id" title="${esc(x ? `${x.nome}${x.formula ? ` = ${x.formula}` : ""}` : id)}">${id}</span>`;
  });
}

function dgSecao(r, chave, titulo, itens) {
  const t = r.secoes[chave];
  return t ? `<div class="dg-sec"><h3>${titulo}</h3>${dgCitar(rsMd(t), itens)}</div>` : "";
}

const dgNome = (t) => (t === RF_ID ? "Renda fixa (CDI)" : t === "_IBOV" ? "BOVA11" : t);
const dgPp = (v) => (v == null ? "n/d" : `${v > 0 ? "+" : ""}${nf(2).format(v)} p.p.`);

function htmlDiagnostico(r) {
  const d = r.diagnostico, ex = d.extras, itens = dgItens(r);
  const v = (nome) => d.itens.find((x) => x.nome === nome)?.valor;
  const ret = v("Retorno da carteira no período"), ib = v("Retorno do Ibovespa no período"), cdi = v("CDI no período");
  const dif = v("Diferença da carteira contra o Ibovespa");
  const autor = r.modo === "agente" ? `agente de IA (${esc((r.provedores || []).join(", "))})` : "regras fixas";
  const maxAbs = Math.max(...ex.atribuicao.map((a) => Math.abs(a.efeito)), 0.01);
  const barra = (e) => `<div class="dg-barra"><span class="${e < 0 ? "neg" : "pos"}" style="width:${Math.abs(e) / maxAbs * 50}%;${e < 0 ? "right:50%" : "left:50%"}"></span></div>`;
  const L = r.laboratorio, P = L.periodos;
  const conf = Object.fromEntries((L.confirmacao || []).map((c) => [c.numero, c]));
  const STATUS = { aprovada: "Aprovada", inconclusiva: "Inconclusiva", reprovada: "Reprovada" };
  const trocas = (t) => [t.trocas.entra.length ? `entra ${t.trocas.entra.join(", ")}` : "", t.trocas.sai.length ? `sai ${t.trocas.sai.join(", ")}` : ""].filter(Boolean).join(" · ") || "só muda os pesos";
  const pesosTxt = (p) => Object.entries(p).map(([k, w]) => `${esc(dgNome(k))} ${pct(w, 1)}`).join(" · ");
  return `
    <div class="dg-meta">${dataBR(ex.inicio)} a ${dataBR(ex.fim)} · texto: ${autor} · ${esc(r.gerado_em)}</div>
    ${r.aviso ? `<div class="aviso-box">⚠ ${esc(r.aviso)}</div>` : ""}
    <div class="kpis dg-kpis">
      <div><span>Carteira</span><b class="${ret < 0 ? "neg" : ""}">${fmtDif(ret)}</b></div>
      <div><span>Ibovespa</span><b class="${ib < 0 ? "neg" : ""}">${fmtDif(ib)}</b></div>
      <div><span>CDI</span><b>${fmtDif(cdi)}</b></div>
      <div><span>Diferença</span><b class="${dif < 0 ? "neg" : ""}">${dgPp(dif)}</b></div>
    </div>
    ${dgSecao(r, "diagnostico", r.modo === "agente" ? "Diagnóstico do agente (período de treino)" : "Diagnóstico", itens)}
    <div class="dg-grade">
      <div>
        <h3>Quem somou e quem tirou</h3>
        <div class="tabela-scroll"><table class="dg-atrib"><thead><tr><th>Ativo</th><th class="num">Peso</th><th class="num">Retorno</th><th class="num">Efeito</th><th></th></tr></thead>
        <tbody>${[...ex.atribuicao].sort((a, b) => a.efeito - b.efeito).map((a) => `<tr><td><strong>${esc(dgNome(a.ticker))}</strong><span class="sub-tk">${esc(a.setor)}</span></td>
          <td class="num">${pct(a.peso, 1)}</td><td class="num ${a.retorno < 0 ? "neg" : ""}">${fmtDif(a.retorno)}</td>
          <td class="num ${a.efeito < 0 ? "neg" : ""}">${dgPp(a.efeito)}</td><td class="dg-col-barra">${barra(a.efeito)}</td></tr>`).join("")}</tbody></table></div>
        <p class="dica">Efeito = peso × (soma dos retornos diários do ativo − soma dos do Ibovespa). A soma dos efeitos dá a diferença da carteira nessa medida, que fica perto da diferença dos retornos acumulados.</p>
      </div>
      <div>
        <h3>Por setor</h3>
        <div class="tabela-scroll"><table><thead><tr><th>Setor</th><th class="num">Peso</th><th class="num">Efeito</th></tr></thead>
        <tbody>${ex.setores.map((s) => `<tr><td>${esc(s.setor)}<span class="sub-tk">${esc(s.ativos.map(dgNome).join(", "))}</span></td><td class="num">${pct(s.peso, 1)}</td>
          <td class="num ${s.efeito < 0 ? "neg" : ""}">${dgPp(s.efeito)}</td></tr>`).join("")}</tbody></table></div>
      </div>
    </div>
    ${dgSecao(r, "quem", "Quem mais pesou no resultado", itens)}
    ${dgSecao(r, "riscos", "Riscos", itens)}
    <h3>Hipóteses testadas no treino</h3>
    <p class="dica">Treino: ${esc(P.treino.replace(/(\d{4})-(\d{2})-(\d{2})/g, "$3/$2/$1"))}, em 3 janelas. Cada linha é uma ideia ${r.modo === "agente" ? "que o agente formulou" : "das regras fixas"}, comparada com a carteira atual em cada janela.</p>
    <div class="tabela-scroll"><table class="dg-testes"><thead><tr><th>#</th><th>Hipótese</th><th class="num">Venceu a atual</th><th class="num">Diferença média</th><th class="num">Volatilidade</th><th>Confirmação</th></tr></thead>
      <tbody>${L.testes.map((t) => `<tr><td>${t.numero}</td><td>${esc(t.motivo || "sem motivo")}<span class="sub-tk">${esc(trocas(t))}</span>
          <details class="dg-pesos"><summary>pesos</summary>${pesosTxt(t.pesos)}</details></td>
        <td class="num">${t.vitorias} de 3</td><td class="num ${t.dif_media < 0 ? "neg" : ""}">${dgPp(t.dif_media)}</td>
        <td class="num">${pct(t.vol, 1)}<span class="sub-tk">atual ${pct(t.vol_atual, 1)}</span></td>
        <td>${conf[t.numero] ? `<span class="dg-st dg-${conf[t.numero].status}">${STATUS[conf[t.numero].status]}</span>` : '<span class="sub-tk">não enviada</span>'}</td></tr>`).join("")}</tbody></table></div>
    ${dgSecao(r, "hipoteses", "O que foi testado", itens)}
    <h3>Confirmação na reserva</h3>
    <p class="dica">Reserva: ${esc(P.reserva.replace(/(\d{4})-(\d{2})-(\d{2})/g, "$3/$2/$1"))}, em 2 janelas, dias que ${r.modo === "agente" ? "o agente" : "as regras"} não viu.
      Regra do projeto, fixada antes dos testes: aprovada = rendeu mais que a carteira atual na reserva inteira e nas 2 janelas, sem volatilidade mais de 20% maior.</p>
    ${(L.confirmacao || []).length ? `<div class="dg-conf">${L.confirmacao.map((c) => `<div class="dg-conf-item dg-${c.status}">
      <div class="dg-conf-topo"><b>Teste ${c.numero}</b><span class="dg-st dg-${c.status}">${STATUS[c.status]}</span></div>
      <p>${esc(c.motivo || "")}</p>
      <div class="dg-conf-num"><span>Contra a atual <b class="${c.dif < 0 ? "neg" : ""}">${dgPp(c.dif)}</b></span><span>Contra o Ibovespa <b class="${c.dif_ibov < 0 ? "neg" : ""}">${dgPp(c.dif_ibov)}</b></span>
        <span>Janelas <b>${c.janelas.map((j) => dgPp(j.diferenca)).join(" · ")}</b></span><span>Maior queda <b class="neg">${pct(c.queda, 1)}</b></span></div>
      <details class="dg-pesos"><summary>pesos</summary>${pesosTxt(c.pesos)}</details></div>`).join("")}</div>` : '<p class="dica">Nenhuma proposta foi confirmada.</p>'}
    ${dgSecao(r, "confirmacao", "O que passou na confirmação", itens)}
    ${r.secoes.leitura ? `<div class="rs-leitura"><p>${dgCitar(esc(r.secoes.leitura), itens)}</p></div>` : ""}
    ${dgSecao(r, "limitacoes", "Limitações", itens)}
    ${(r.passos || []).length ? `<details class="cb-det"><summary>Como o agente investigou (${r.passos.filter((p) => p.tipo === "ferramenta").length} chamadas de ferramenta)</summary>${rsPassos(r.passos)}</details>` : ""}
    <p class="dica">Passe o mouse sobre um id (C12, E4) para ver o número e a fórmula. Mesmo uma proposta aprovada passou num único período de reserva: é uma pista forte, não uma garantia.</p>`;
}
