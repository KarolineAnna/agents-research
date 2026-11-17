// Aba "Research": agente com IA (ou as etapas Financial, Market e Investment por regras fixas) que gera um dossiê rastreável
// e um relatório. Na segunda página da seção, os relatórios salvos agrupados por empresa.
let RS = null;
const RS_TIPO = { fato: "Fato", calculado: "Calculado", premissa: "Premissa", estimativa: "Estimativa" };
const RS_AGENTE = { financial: "Financial Analyst", market: "Market Research Analyst", investment: "Investment Research Analyst" };

function rsBr(v, c = 1) {
  return v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c });
}
function rsFmt(v, u = "") {
  if (v == null) return "n/d";
  if (u === "R$") return Math.abs(v) >= 1e9 ? `R$ ${rsBr(v / 1e9)} bi` : Math.abs(v) >= 1e6 ? `R$ ${rsBr(v / 1e6)} mi` : `R$ ${rsBr(v, 2)}`;
  if (u.startsWith("%")) return `${rsBr(v)}%${u.includes("a.a.") ? " a.a." : ""}`;
  if (u === "x") return `${rsBr(v, 2)}x`;
  if (u === "p.p.") return `${rsBr(v, 2)} p.p.`;
  return Math.abs(v) >= 1e5 && Number.isInteger(v) ? rsBr(v, 0) : rsBr(v, 2);
}
// sem travessão: "Preço justo — base" → "Preço justo (base)"; em frases, vira vírgula
function rsRot(nome) {
  const m = String(nome || "").match(/^(.*?)\s*[—–]\s*(.+)$/);
  return m ? `${m[1]} (${m[2]})` : String(nome || "");
}
function rsTxt(t) {
  return String(t || "").replace(/^\s*([-*_])\1{2,}\s*$/gm, "").replace(/\s+[—–]\s+/g, ", ").replace(/(\w)[—–](\w)/g, "$1-$2")
    .replace(/\s*[—–]\s*/g, ", ").replace(/,\s*([.;:)])/g, "$1");
}
// [F12] vira um link que abre o item
function rsCita(txt) {
  const docs = Object.fromEntries((RS?.documentos_ri || []).map((d) => [d.id, d]));
  return esc(txt).replace(/\[((?:[A-Z0-9]+\.)?[FMI]\d+)\]/g, '<a href="#" class="rs-cita" data-id="$1">[$1]</a>')
    .replace(/\[D(\d+)\s*p\.?\s*(\d+)\]/g, (m, d, p) => { const x = docs[d];  // página do relatório de RI na CVM
      return x?.url ? `<a href="${esc(x.url)}#page=${p}" target="_blank" rel="noopener" class="rs-cita-doc" title="${esc(`${x.tipo || ""}: ${x.assunto || ""} (${x.data_entrega || ""}), página ${p}`)}">[D${d} p${p}]</a>` : m; });
}
function rsTodos() {
  return ["financial", "market", "investment"].flatMap((k) => (RS[k] ? RS[k].itens.map((x) => ({ ...x, agente: k })) : []))
    .concat(Object.values(RS.pares_dossies || {}).flatMap((d) => d.itens.map((x) => ({ ...x, agente: "financial" }))));
}
// Markdown simples do texto do agente (títulos, listas, negrito, parágrafos), com as citações clicáveis
function rsInline(t) {
  return rsCita(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}
// Markdown do texto do agente: títulos, listas (com subníveis e numeradas), tabelas, separadores, negrito/itálico
function rsMd(md) {
  const out = [], pilha = [];  // pilha de listas abertas: {tipo, nivel}
  const fecharListas = (ate = -1) => { while (pilha.length && pilha[pilha.length - 1].nivel > ate) out.push(`</li></${pilha.pop().tipo}>`); };
  const linhas = md.replace(/\r/g, "").split("\n");
  for (let i = 0; i < linhas.length; i++) {
    const l = linhas[i];
    const h = l.match(/^(#{1,4})\s+(.*)/), it = l.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)/);
    if (/^\s*\|.*\|\s*$/.test(l) && /^\s*\|?\s*:?-{2,}/.test(linhas[i + 1] || "")) {  // tabela
      fecharListas();
      const cel = (x) => x.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const cab = cel(l); i += 2; const corpo = [];
      while (i < linhas.length && /^\s*\|/.test(linhas[i])) corpo.push(cel(linhas[i++]));
      i--;
      out.push(`<div class="tabela-scroll"><table><thead><tr>${cab.map((c) => `<th>${rsInline(c)}</th>`).join("")}</tr></thead><tbody>${
        corpo.map((r) => `<tr>${r.map((c) => `<td>${rsInline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (it) {
      const nivel = Math.floor(it[1].replace(/\t/g, "  ").length / 2), tipo = /\d/.test(it[2]) ? "ol" : "ul";
      const topo = pilha[pilha.length - 1];
      if (!topo || nivel > topo.nivel) { out.push(`<${tipo}>`); pilha.push({ tipo, nivel }); }
      else { fecharListas(nivel); if (pilha.length && pilha[pilha.length - 1].nivel === nivel) out.push("</li>"); else { out.push(`<${tipo}>`); pilha.push({ tipo, nivel }); } }
      out.push(`<li>${rsInline(it[3])}`);
      continue;
    }
    if (!l.trim()) continue;  // linha em branco não fecha a lista (listas "soltas")
    fecharListas();
    if (h) out.push(`<h${Math.min(h[1].length + 1, 5)} class="rs-md-h">${rsInline(h[2])}</h${Math.min(h[1].length + 1, 5)}>`);
    else if (/^\s*([-*_])\1{2,}\s*$/.test(l)) out.push("<hr>");
    else if (/^\s*>\s?/.test(l)) out.push(`<blockquote>${rsInline(l.replace(/^\s*>\s?/, ""))}</blockquote>`);
    else out.push(`<p>${rsInline(l)}</p>`);
  }
  fecharListas();
  return out.join("");
}
function rsPassos(passos) {
  const ic = { ferramenta: "⚙", pensamento: "💭", rascunho: "✎", erro: "⚠", info: "→" };
  return `<ol class="rs-passos">${passos.map((p) => p.tipo === "ferramenta"
    ? `<li class="rs-p-ferr"><span>${ic.ferramenta}</span><code>${esc(p.nome)}(${esc(Object.entries(p.args || {}).map(([k, v]) => `${k}=${v}`).join(", "))})</code> → ${esc(p.resumo)}</li>`
    : `<li class="rs-p-${p.tipo}"><span>${ic[p.tipo] || "·"}</span>${esc(p.texto)}</li>`).join("")}</ol>`;
}

async function rsRodar(ev) {
  ev?.preventDefault();
  const st = $("#status-research"), btn = $("#rs-rodar");
  const ticker = $("#rs-ticker").value.trim().toUpperCase();
  const agentes = [...document.querySelectorAll(".rs-agente:checked")].map((c) => c.value);
  const modo = document.querySelector('input[name="rs-modo"]:checked').value;
  if (!ticker) return;
  if (modo === "regras" && !agentes.length) { st.className = "status erro"; st.textContent = "Escolha pelo menos um agente."; return; }
  const pares = $("#rs-pares").value.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
  const premissas = {};
  for (const [id, k] of [["rs-erp", "erp"], ["rs-beta", "beta"], ["rs-creal", "cresc_real"]]) {
    const v = parseFloat($("#" + id).value.replace(",", "."));
    if (Number.isFinite(v)) premissas[k] = v;
  }
  btn.disabled = true; st.className = "status";
  st.textContent = modo === "agente"
    ? `O agente está investigando ${ticker}: escolhe as ferramentas, lê CVM, B3, Tesouro e Banco Central e escreve. Pode levar de 1 a 3 minutos…`
    : `Rodando ${agentes.map((a) => RS_AGENTE[a]).join(", ")} para ${ticker}… (lê CVM, B3, Tesouro e Banco Central; pode levar até 1 minuto)`;
  try {
    const r = await fetch(`/api/research/${encodeURIComponent(ticker)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modo, agentes, pares, premissas, ia: $("#rs-ia").checked }),
    });
    const corpo = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(corpo.detail || `Erro ${r.status}`);
    RS = corpo; st.textContent = ""; rsRender(); rsHistorico(); rsSub("analise");
  } catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { btn.disabled = false; }
}

function rsTabelaItens(d) {
  const por = Object.fromEntries(d.itens.map((x) => [x.id, x]));
  return Object.entries(d.secoes).map(([sec, ids]) => `<h4 class="rs-sec">${esc(sec)}</h4>
    <div class="tabela-scroll"><table class="rs-tab"><thead><tr><th>id</th><th>Item</th><th class="num">Valor</th><th>Tipo</th><th>Origem / fórmula</th></tr></thead><tbody>
    ${ids.map((i) => { const x = por[i]; const f = x.fonte || {};
      return `<tr class="rs-linha" data-id="${x.id}"><td><code>${x.id}</code></td><td>${esc(rsRot(x.nome))}</td><td class="num">${rsFmt(x.valor, x.unidade)}</td>
        <td><span class="rs-t rs-${x.tipo}">${RS_TIPO[x.tipo]}</span></td>
        <td>${f.fonte ? esc(`${f.fonte} · ${f.documento || ""}`) : esc(rsTxt(x.formula || x.nota || ""))}</td></tr>`; }).join("")}
    </tbody></table></div>`).join("");
}

function rsDossie(k) {
  const d = RS[k];
  if (!d) return "";
  const lei = d.leituras.length ? `<p class="rs-sub">Leituras (inferências a partir dos números)</p><ul>${d.leituras.map((l) =>
      `<li>${esc(rsTxt(l.texto))} ${l.ids.map((i) => `<a href="#" class="rs-cita" data-id="${i}">[${i}]</a>`).join(" ")}</li>`).join("")}</ul>` : "";
  const al = d.alertas.length ? `<ul class="rs-alertas">${d.alertas.map((a) => `<li class="rs-al-${a.nivel}">${esc(rsTxt(a.texto))}</li>`).join("")}</ul>` : "";
  const aus = d.ausentes.length ? `<p class="rs-sub">Dados não encontrados (${d.ausentes.length})</p><div class="tabela-scroll"><table><thead><tr><th>Dado</th><th>Motivo</th><th>Onde obter</th></tr></thead><tbody>
      ${d.ausentes.map((a) => `<tr><td>${esc(a.nome)}</td><td>${esc(rsTxt(a.motivo))}</td><td>${esc(a.fonte_sugerida || "")}</td></tr>`).join("")}</tbody></table></div>` : "";
  const cvm = (d.extras.noticias || []).filter((n) => String(n.fonte || "").startsWith("CVM"));  // relatórios antigos traziam manchetes gerais
  const nots = cvm.length ? `<p class="rs-sub">Comunicados da empresa na CVM</p><ul class="rs-noticias">${cvm.slice(0, 12).map((n) =>
      `<li><span>${esc(n.data || "")} · ${esc(n.fonte)}</span> <a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.titulo)} ↗</a></li>`).join("")}</ul>` : "";
  return `<details class="bloco rs-dossie" ${k === "investment" ? "" : ""}><summary><h2>${RS_AGENTE[k]}</h2>
      <span class="dica">${d.itens.length} itens · ${d.ausentes.length} ausentes · ${d.alertas.length} alertas</span></summary>
      ${al}${rsTabelaItens(d)}${lei}${nots}${aus}</details>`;
}

function rsSecao(md) { return md ? rsMd(rsTxt(md)) : ""; }

function rsRender() {
  const r = RS, inv = r.investment, fin = r.financial, mkt = r.market, red = r.redacao || {}, sec = red.secoes || {};
  const todos = rsTodos(), ach = (n) => todos.find((x) => x.nome === n);
  const cita = (x) => (x ? `<a href="#" class="rs-cita" data-id="${x.id}">[${x.id}]</a>` : "");
  const val = (x) => (x ? `${rsFmt(x.valor, x.unidade)} ${cita(x)}` : "n/d");
  const kpi = (rot, x) => `<div><span>${rot}</span><b>${x ? rsFmt(x.valor, x.unidade) : "n/d"}</b>${cita(x)}</div>`;
  const tese = inv?.extras.tese || {};
  const comp = inv?.extras.comparacao || [];
  const tks = comp.length ? Object.keys(comp[0].valores) : [];
  const s = inv?.extras.sensibilidade;
  const cen = ["pessimista", "base", "otimista"].map((c) => ({ c, roe: ach(`ROE sustentável — ${c}`), ke: ach(`Ke — ${c}`), pvp: ach(`P/VP justo — ${c}`),
    preco: ach(`Preço justo — ${c}`), pot: ach(`Potencial — ${c}`), peso: ach(`Peso do cenário ${c}`) }));
  const setor = fin?.extras?.setor;
  const pot = ach("Potencial ponderado") || ach("Potencial (base)");
  const leitura = rsTxt(sec.leitura || (tese.opiniao ? "Opinião: " + tese.opiniao : ""));
  const selo = pot ? (pot.valor > 15 ? ["abaixo", "Pelo modelo: preço abaixo do valor estimado"] : pot.valor < -15 ? ["acima", "Pelo modelo: preço acima do valor estimado"] : ["proximo", "Pelo modelo: preço próximo do valor estimado"]) : null;
  const mult = (inv?.itens || []).filter((x) => /^(Preço pelo|P\/L mediano|P\/VP mediano)/.test(x.nome));
  const premissas = ["Taxa livre de risco (juro prefixado 5 anos)", "Beta do banco", "Prêmio de risco de ações", "Ke (CAPM)",
    "g (crescimento nominal na perpetuidade)", "ROE sustentável implícito no preço", "Ke implícito no preço"].map(ach).filter(Boolean);
  const autor = red.modo === "agente" ? `agente de IA (${esc(red.modelo)})` : red.modo === "ia" ? `IA (${esc(red.modelo)})` : "regras fixas";

  $("#resultado-research").innerHTML = `
    <div class="rs-cabeca">
      <div><h2>${esc((fin || inv || {}).assunto || r.ticker)}</h2>
        <p class="rs-meta">${setor?.setor ? `<span class="rs-setor-tag">${esc(setor.macro)} › ${esc(setor.setor)}</span>` : ""}
          <span>Relatório de ${esc(r.gerado_em)}</span><span>Dados até ${esc(fin?.extras?.ref || "n/d")}</span><span>Texto: ${autor}</span>
          ${Object.keys(r.pares || {}).length ? `<span>Pares: ${esc(Object.keys(r.pares).join(", "))}</span>` : ""}</p></div>
      ${r.id ? `<div class="rs-baixar"><a class="botao-sec" href="/api/research/relatorio/${r.id}.md">Baixar Markdown</a>
        <a class="botao-sec" href="/api/research/relatorio/${r.id}.html" target="_blank" rel="noopener">Abrir para PDF ↗</a></div>` : ""}
    </div>
    ${red.aviso ? `<p class="aviso-box">${esc(rsTxt(red.aviso))}</p>` : ""}
    ${inv ? `<div class="kpis rs-kpis">${kpi("Preço atual", ach("Preço atual"))}${kpi("Preço justo ponderado", ach("Preço justo ponderado pelos cenários"))}
      ${kpi("Potencial", pot)}${kpi("ROE (12m)", ach("ROE atual (12 meses)") || ach("ROE — " + r.ticker))}${kpi("Ke (CAPM)", ach("Ke (CAPM)"))}
      ${kpi("P/VP", ach("P/VP atual") || ach("P/VP — " + r.ticker))}</div>` : ""}

    <div class="rs-grade2">
      <div class="bloco rs-analise"><h2>Destaques</h2>${rsSecao(sec.destaques) || "<p class='dica'>Sem destaques.</p>"}</div>
      <div class="bloco rs-analise"><h2>Tese</h2>${rsSecao(sec.tese) || "<p class='dica'>Sem tese.</p>"}
        ${leitura ? `<div class="rs-leitura ${selo ? "rs-l-" + selo[0] : ""}">${selo ? `<span class="rs-selo">${selo[1]}</span>` : ""}<p>${rsCita(leitura)}</p></div>` : ""}
      </div>
    </div>

    ${comp.length ? `<div class="bloco"><h2>Indicadores e pares</h2>
      <div class="tabela-scroll"><table class="rs-comp"><thead><tr><th>Indicador</th>${tks.map((t) => `<th class="num ${t === r.ticker ? "rs-alvo" : ""}">${t}</th>`).join("")}<th class="num">Mediana dos pares</th></tr></thead><tbody>
      ${comp.map((l) => `<tr><td>${esc(l.metrica)}</td>${tks.map((t) => `<td class="num ${t === r.ticker ? "rs-alvo" : ""}">${rsFmt(l.valores[t], l.unidade)}</td>`).join("")}<td class="num">${rsFmt(l.mediana_pares, l.unidade)}</td></tr>`).join("")}
      </tbody></table></div></div>` : ""}

    ${cen[1].preco || mult.length ? `<div class="bloco"><h2>Valuation</h2>
      ${cen[1].preco ? `<p class="dica">P/VP justificado: P/VP = (ROE − g) ÷ (Ke − g); preço justo = P/VP × VPA. Os pesos dos cenários são uma escolha declarada.</p>
      <div class="tabela-scroll"><table><thead><tr><th>Cenário</th><th class="num">Peso</th><th class="num">ROE</th><th class="num">Ke</th><th class="num">P/VP justo</th><th class="num">Preço justo</th><th class="num">Potencial</th></tr></thead><tbody>
      ${cen.map((c) => `<tr><td>${c.c[0].toUpperCase() + c.c.slice(1)}</td>${["peso", "roe", "ke", "pvp", "preco", "pot"].map((k) => `<td class="num">${val(c[k])}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div>` : ""}
      ${premissas.length ? `<details class="limpo-sec" open><summary>Premissas e leituras do preço</summary><div class="tabela-scroll"><table><tbody>
        ${premissas.map((x) => `<tr><td>${esc(rsRot(x.nome))}</td><td class="num">${val(x)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      ${mult.length ? `<details class="limpo-sec" open><summary>Por múltiplos dos pares</summary><div class="tabela-scroll"><table><tbody>
        ${mult.map((x) => `<tr><td>${esc(rsRot(x.nome))}</td><td class="num">${val(x)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      ${s ? `<details class="limpo-sec"><summary>Sensibilidade do preço justo (R$) · g = ${rsFmt(s.g, "%")}</summary>
      <div class="tabela-scroll"><table class="rs-sens"><thead><tr><th>Ke \\ ROE</th>${s.roe.map((x) => `<th class="num">${rsFmt(x, "%")}</th>`).join("")}</tr></thead><tbody>
      ${s.ke.map((k, i) => `<tr><th>${rsFmt(k, "%")}</th>${s.precos[i].map((p, j) => `<td class="num${i === 2 && j === 2 ? " rs-centro" : ""}">${p == null ? "n/d" : rsBr(p, 2)}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div><p class="dica">Centro = premissas do cenário base.</p></details>` : ""}
    </div>` : ""}

    ${mkt?.itens?.length ? `<div class="bloco"><h2>Cenário macro</h2>
      <div class="tabela-scroll"><table><thead><tr><th>Indicador</th><th class="num">Valor</th><th>Fonte</th><th>Data</th></tr></thead><tbody>
      ${mkt.itens.map((x) => `<tr><td>${esc(rsRot(x.nome))}</td><td class="num">${val(x)}</td><td>${esc(x.fonte?.fonte || "calculado")}</td><td>${esc(dataBR(x.fonte?.data_ref) || "")}</td></tr>`).join("")}
      </tbody></table></div></div>` : ""}

    <div class="rs-grade2">
      <div class="bloco rs-analise"><h2>Riscos</h2>${rsSecao(sec.riscos) || `<ul>${(tese.riscos || []).slice(0, 4).map((t) => `<li>${esc(rsTxt(t))}</li>`).join("")}</ul>`}</div>
      <div class="bloco rs-analise"><h2>Oportunidades</h2>${rsSecao(sec.oportunidades) || `<ul>${(tese.oportunidades || []).slice(0, 3).map((t) => `<li>${esc(rsTxt(t))}</li>`).join("") || "<li>Nenhuma identificada pelas regras.</li>"}</ul>`}</div>
    </div>
    ${sec.limitacoes ? `<div class="bloco rs-analise"><h2>Limitações</h2>${rsSecao(sec.limitacoes)}</div>` : ""}

    <h3 class="rs-anexos">Anexos</h3>
    ${tese.fatos ? `<details class="bloco"><summary><h2>Fatos e estimativas usados</h2></summary>
      <div class="tabela-scroll"><table><thead><tr><th>Tipo</th><th>Item</th><th class="num">Valor</th></tr></thead><tbody>
      ${[...tese.fatos.map((i) => ["Fato", i]), ...tese.estimativas.map((i) => ["Estimativa", i])].map(([t, i]) => { const x = todos.find((y) => y.id === i);
        return x ? `<tr><td>${t}</td><td>${esc(rsRot(x.nome))}</td><td class="num">${val(x)}</td></tr>` : ""; }).join("")}
      </tbody></table></div></details>` : ""}
    ${(r.documentos_ri || []).some((d) => d.paginas_lidas?.length) ? `<details class="bloco"><summary><h2>Relatórios da empresa lidos</h2> <span class="dica">entregues à CVM</span></summary>
      <div class="tabela-scroll"><table><thead><tr><th>id</th><th>Documento</th><th>Entregue em</th><th>Páginas lidas</th></tr></thead><tbody>
      ${r.documentos_ri.filter((d) => d.paginas_lidas?.length).map((d) => `<tr><td>D${d.id}</td><td>${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(rsTxt(`${d.tipo || ""}: ${d.assunto || ""}`))} ↗</a>` : esc(d.assunto || "")}</td>
        <td>${dataBR(d.data_entrega || "")}</td><td>${esc(d.paginas_lidas.join(", "))}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
    ${["financial", "market", "investment"].map(rsDossie).join("")}
    ${red.modo === "agente" && (r.passos || []).length ? `<details class="bloco"><summary><h2>Como o agente investigou</h2> <span class="dica">${(r.passos || []).filter((p) => p.tipo === "ferramenta").length} chamadas de ferramenta${r.metricas_agente?.segundos_ia != null ? ` · ${nf(0).format(r.metricas_agente.segundos)} s no total: IA ${nf(0).format(r.metricas_agente.segundos_ia)} s, dados ${nf(0).format(r.metricas_agente.segundos_ferramentas)} s` : ""}</span></summary>${rsPassos(r.passos || [])}</details>` : ""}
    <details class="bloco"><summary><h2>Registro da execução</h2></summary><pre class="rs-log">${esc(rsTxt((r.log || []).join("\n")))}</pre></details>
    <p class="dica rs-aviso-final">Estudo automatizado para fins educacionais, não é recomendação. Clique em qualquer [id] para ver de onde veio o número.</p>`;
}

function rsMostrarItem(id) {
  const x = rsTodos().find((i) => i.id === id);
  if (!x) return;
  const f = x.fonte || {};
  const comps = (x.componentes || []).map((c) => `<tr><td>${esc(c.papel || "")}</td><td>${esc(c.sinal || "")}</td><td>${esc(c.documento || "")}</td>
      <td><code>${esc(c.conta || "")}</code> ${esc(c.descricao || "")}</td><td>${esc(c.periodo || "")}</td><td class="num">${rsFmt(c.valor, "R$")}</td></tr>`).join("");
  const insumos = (x.insumos || []).map((i) => `<a href="#" class="rs-cita" data-id="${i}">[${i}]</a>`).join(" ");
  $("#rs-item").innerHTML = `<div class="painel-topo"><b>${esc(x.nome)}</b> <span class="rs-t rs-${x.tipo}">${RS_TIPO[x.tipo]}</span>
      <button type="button" class="fechar" aria-label="Fechar">×</button></div>
    <p class="rs-valor">${rsFmt(x.valor, x.unidade)} <code>${x.id}</code> · ${RS_AGENTE[x.agente]}</p>
    ${x.formula ? `<p><strong>Fórmula:</strong> ${esc(x.formula)} ${insumos ? `· usa ${insumos}` : ""}</p>` : ""}
    ${f.fonte ? `<p><strong>Fonte:</strong> ${f.url ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.fonte)} · ${esc(f.documento || "")} ↗</a>` : esc(`${f.fonte} · ${f.documento || ""}`)}
      ${f.conta ? `<br><strong>Conta:</strong> <code>${esc(f.conta)}</code> ${esc(f.descricao || "")}` : ""}
      ${f.periodo ? `<br><strong>Período:</strong> ${esc(f.periodo)}` : ""}${f.data_ref ? ` · <strong>Data:</strong> ${esc(f.data_ref)}` : ""}</p>` : ""}
    ${x.nota ? `<p class="dica">${esc(x.nota)}</p>` : ""}
    ${comps ? `<div class="tabela-scroll"><table><thead><tr><th>Parte</th><th></th><th>Documento</th><th>Conta</th><th>Período</th><th class="num">Valor</th></tr></thead><tbody>${comps}</tbody></table></div>` : ""}`;
  $("#rs-item").hidden = false;
}

function rsProvs(st, testes) {
  const t = Object.fromEntries((testes || []).map((x) => [x.provedor, x]));
  const prontos = st.provedores.filter((p) => !p.precisa_chave || p.chave);
  $("#rs-ia-status").textContent = prontos.length ? `· ${prontos.map((p) => p.id).join(" → ")}` : "· nenhuma configurada";
  $("#rs-provs").innerHTML = `<ul class="rs-provs">${st.provedores.map((p) => `<li><b>${esc(p.nome)}</b>
    ${p.precisa_chave ? (p.chave ? `chave ${esc(p.chave)}` : "<span class='dica'>sem chave</span>") : "<span class='dica'>local, sem chave</span>"}
    ${t[p.id] ? (t[p.id].ok ? ` · <span class="rs-ok">funcionando (${esc(t[p.id].modelo)})</span>` : ` · <span class="rs-falha">${esc(t[p.id].resposta)}</span>`) : ""}</li>`).join("")}</ul>`;
  if (!prontos.length) $("#rs-config").open = true;
}
async function rsSalvarIA() {
  const chaves = {};
  for (const p of ["gemini", "groq"]) { const v = $("#rs-k-" + p).value.trim(); if (v) chaves[p] = v; }
  const ordem = $("#rs-ordem").value.split(/[\s,>→]+/).map((x) => x.trim().toLowerCase()).filter(Boolean);
  const r = await fetch("/api/research-ia", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ordem, chaves }) });
  $("#rs-k-gemini").value = $("#rs-k-groq").value = "";
  rsProvs(await r.json());
}
async function rsTestarIA() {
  $("#rs-provs").insertAdjacentHTML("beforeend", "<p class='dica'>Testando…</p>");
  const [st, t] = await Promise.all([api("/api/research-ia"), api("/api/research-ia/testar")]);
  rsProvs(st, t.resultados);
}
function rsModo() {
  const regras = document.querySelector('input[name="rs-modo"]:checked').value === "regras";
  document.querySelectorAll(".rs-so-regras").forEach((e) => { e.hidden = !regras; });
}

// ---------- relatórios salvos: agrupados por empresa, o mais recente na frente e os anteriores recolhidos ----------
let RS_LISTA = [], RS_FILTRO = "";
const RS_ABERTOS = new Set();  // empresas com as versões anteriores à mostra

function rsQuando(q) {  // "2026-11-15 09:33" → "15/11/2026 09:33"
  const m = String(q || "").match(/^(\d{4})-(\d{2})-(\d{2})\s*(.*)$/);
  return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}`.trim() : esc(q || "");
}
function rsSeloPot(p) {
  if (p == null) return "";
  const [cls, txt] = p > 15 ? ["abaixo", "abaixo do valor"] : p < -15 ? ["acima", "acima do valor"] : ["proximo", "próximo do valor"];
  return `<span class="rs-pot rs-pot-${cls}" title="Potencial pelo modelo: ${esc(txt)}">${p > 0 ? "+" : ""}${rsBr(p, 0)}%</span>`;
}
function rsModoTag(x) {
  return x.modo === "agente" ? `<span class="rs-tag" title="Texto: ${esc(x.autor || "IA")}">IA</span>` : `<span class="rs-tag rs-tag-regras">Regras</span>`;
}
function rsLinhaSalvo(x, cab) {
  const ativo = RS?.id === x.id ? " rs-ativo" : "";
  return `<div class="rs-salvo${ativo}${cab ? "" : " rs-salvo-ant"}">
    <a href="#" class="rs-salvo-abrir" data-rid="${esc(x.id)}">
      ${cab ? `<b>${esc(x.ticker)}</b><span class="rs-salvo-emp">${esc(String(x.empresa || "").replace(/\s*\([A-Z0-9]+\)\s*$/, ""))}</span>` : ""}
      <span class="rs-salvo-data">${rsQuando(x.quando)}</span>
    </a>
    ${rsSeloPot(x.potencial)}${rsModoTag(x)}${x.aviso ? `<span class="rs-tag rs-tag-aviso" title="A IA não respondeu; texto por regras fixas">!</span>` : ""}
    <button type="button" class="rs-excluir" data-excluir="${esc(x.id)}" title="Excluir este relatório" aria-label="Excluir relatório de ${esc(x.ticker)} de ${esc(x.quando)}">×</button>
  </div>`;
}
// duas páginas dentro da seção: "Análise" (formulário + relatório aberto) e "Relatórios salvos"
function rsSub(nome) {
  document.querySelectorAll("[data-rs-sub]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.rsSub === nome)));
  $("#rs-pag-analise").hidden = nome !== "analise";
  $("#rs-pag-salvos").hidden = nome !== "salvos";
  $("#rs-item").hidden = true;
}
function rsSalvosRender() {
  const grupos = new Map();
  for (const x of RS_LISTA) { if (!grupos.has(x.ticker)) grupos.set(x.ticker, []); grupos.get(x.ticker).push(x); }
  const f = RS_FILTRO.trim().toUpperCase();
  const vis = [...grupos.entries()].filter(([t, v]) => !f || t.includes(f) || String(v[0].empresa || "").toUpperCase().includes(f));
  const antigos = RS_LISTA.length - grupos.size;
  const el = $("#rs-historico");
  $("#rs-salvos-n").textContent = RS_LISTA.length ? String(RS_LISTA.length) : "";
  if (!RS_LISTA.length) {
    el.innerHTML = `<div class="rs-salvos-cab"><h2>Relatórios salvos</h2></div><p class="dica">Nenhum relatório ainda. Cada análise rodada fica salva aqui.</p>`;
    return;
  }
  el.innerHTML = `<div class="rs-salvos-cab"><h2>Relatórios salvos</h2>
      <span class="dica">Clique num relatório para abrir. ${grupos.size} ${grupos.size === 1 ? "empresa" : "empresas"} · ${RS_LISTA.length} ${RS_LISTA.length === 1 ? "relatório" : "relatórios"}</span></div>
    ${grupos.size > 4 ? `<input type="search" id="rs-filtro" class="rs-filtro" placeholder="Filtrar por ticker ou empresa" value="${esc(RS_FILTRO)}" autocomplete="off" spellcheck="false">` : ""}
    <ul class="rs-salvos-lista">${vis.map(([t, v]) => `<li>
      ${rsLinhaSalvo(v[0], true)}
      ${v.length > 1 ? `<button type="button" class="rs-versoes" data-grupo="${esc(t)}" aria-expanded="${RS_ABERTOS.has(t)}">
          ${RS_ABERTOS.has(t) ? "Ocultar" : "Ver"} ${v.length - 1} ${v.length === 2 ? "versão anterior" : "versões anteriores"}</button>
        ${RS_ABERTOS.has(t) ? `<div class="rs-ant">${v.slice(1).map((x) => rsLinhaSalvo(x, false)).join("")}</div>` : ""}` : ""}
    </li>`).join("") || `<li class="dica">Nada encontrado para “${esc(RS_FILTRO)}”.</li>`}</ul>
    ${antigos ? `<div class="rs-salvos-rodape"><button type="button" class="botao-sec" id="rs-limpar">Manter só o mais recente de cada empresa</button>
      <span class="dica">apaga ${antigos} ${antigos === 1 ? "versão antiga" : "versões antigas"}</span></div>` : ""}`;
  const inp = $("#rs-filtro");
  if (inp) inp.addEventListener("input", () => { RS_FILTRO = inp.value; const pos = inp.selectionStart; rsSalvosRender();
    const novo = $("#rs-filtro"); novo.focus(); novo.setSelectionRange(pos, pos); });
}
async function rsHistorico() {
  try {
    api("/api/research-ia").then((st) => { rsProvs(st); $("#rs-ordem").value = st.ordem.join(", "); }).catch(() => {});
    RS_LISTA = (await api("/api/research")).relatorios || [];
    rsSalvosRender();
  } catch { /* sem histórico */ }
}
function rsVazio() {
  RS = null;
  $("#resultado-research").innerHTML = `<div class="vazio"><h3>Relatório excluído</h3><p>Escolha outro relatório salvo ou rode uma nova análise.</p></div>`;
}
async function rsExcluir(rid) {
  const x = RS_LISTA.find((r) => r.id === rid);
  if (!confirm(`Excluir o relatório de ${x?.ticker || ""} de ${x ? rsQuando(x.quando) : ""}? Não dá para desfazer.`)) return;
  const r = await fetch(`/api/research/relatorio/${encodeURIComponent(rid)}`, { method: "DELETE" });
  if (!r.ok && r.status !== 404) { $("#status-research").className = "status erro"; $("#status-research").textContent = `Não consegui excluir (erro ${r.status}).`; return; }
  if (RS?.id === rid) rsVazio();
  rsHistorico();
}
async function rsLimpar() {
  const n = RS_LISTA.length - new Set(RS_LISTA.map((x) => x.ticker)).size;
  if (!confirm(`Apagar ${n} ${n === 1 ? "relatório antigo" : "relatórios antigos"} e manter só o mais recente de cada empresa? Não dá para desfazer.`)) return;
  const r = await fetch("/api/research/relatorios/limpar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ manter: 1 }) });
  const corpo = await r.json().catch(() => ({}));
  if (RS?.id && (corpo.apagados || []).includes(RS.id)) rsVazio();
  RS_ABERTOS.clear();
  rsHistorico();
}

async function rsSetor(preencher = false) {
  const t = $("#rs-ticker").value.trim().toUpperCase();
  if (!t) { $("#rs-setor").textContent = ""; return; }
  try {
    const s = await api(`/api/setor/${encodeURIComponent(t)}?n=4`);
    $("#rs-setor").textContent = s.setor ? `${s.macro} › ${s.setor}${s.holding ? " (holding)" : ""}` : "sem classificação setorial";
    const sug = (s.sugestao?.pares || []).map((p) => p.ticker);
    $("#rs-pares-dica").textContent = sug.length ? `Sugestão (${s.sugestao.criterio}): ${sug.join(", ")}` : "";
    if (preencher) $("#rs-pares").value = sug.join(", ");
  } catch { $("#rs-setor").textContent = ""; }
}
$("#rs-ticker").addEventListener("change", () => rsSetor(false));
$("#rs-sugerir").addEventListener("click", () => rsSetor(true));
$("#form-research").addEventListener("submit", rsRodar);
$("#rs-salvar-ia").addEventListener("click", rsSalvarIA);
$("#rs-testar-ia").addEventListener("click", rsTestarIA);
document.querySelectorAll('input[name="rs-modo"]').forEach((e) => e.addEventListener("change", rsModo));
rsModo();
$("#aba-research").addEventListener("click", async (e) => {
  const c = e.target.closest(".rs-cita, .rs-linha");
  if (c) { e.preventDefault(); rsMostrarItem(c.dataset.id); return; }
  if (e.target.closest("#rs-item .fechar")) { $("#rs-item").hidden = true; return; }
  const del = e.target.closest("[data-excluir]");
  if (del) { rsExcluir(del.dataset.excluir); return; }
  const grp = e.target.closest("[data-grupo]");
  if (grp) { const t = grp.dataset.grupo; RS_ABERTOS.has(t) ? RS_ABERTOS.delete(t) : RS_ABERTOS.add(t); rsSalvosRender(); return; }
  if (e.target.closest("#rs-limpar")) { rsLimpar(); return; }
  const sub = e.target.closest("[data-rs-sub]");
  if (sub) { rsSub(sub.dataset.rsSub); if (sub.dataset.rsSub === "salvos") rsHistorico(); return; }
  const h = e.target.closest("[data-rid]");
  if (h) {
    e.preventDefault();
    try {
      RS = await api(`/api/research/relatorio/${h.dataset.rid}`); rsRender(); rsSalvosRender(); rsSub("analise");
      $("#resultado-research").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) { $("#status-research").textContent = err.message; }
  }
});
document.querySelector('[data-aba="research"]').addEventListener("click", () => { rsHistorico(); rsSetor(false); });
if (location.hash === "#research") { rsHistorico(); rsSetor(false); }
