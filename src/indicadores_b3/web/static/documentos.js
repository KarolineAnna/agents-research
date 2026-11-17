// Aba "Documentos (IA)": base de comunicados da CVM, perguntas com citações conferidas e avaliação (evals).
let DC_RESP = null;

async function dcPost(url, corpo) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `Erro ${r.status}`);
  return j;
}
const dcPct = (v) => (v == null ? "—" : `${String(v).replace(".", ",")}%`);
const dcNum = (v, c = 2) => (v == null ? "—" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: c }));

// ---------- 1. base ----------
async function dcCarregarBase() {
  try {
    const b = await api("/api/docs");
    const e = b.estatisticas, emb = Object.entries(e.embeddings || {});
    $("#dc-base").innerHTML = `
      <div class="kpis dc-kpis"><div><span>Documentos</span><b>${e.documentos}</b></div><div><span>Páginas</span><b>${e.paginas}</b></div>
        <div><span>Trechos</span><b>${e.trechos}</b></div>
        <div><span>Embeddings</span><b>${emb.length ? emb.map(([m, n]) => `${n}`).join(" · ") : "—"}</b>${emb.length ? `<small>${esc(emb.map(([m]) => m).join(", "))}</small>` : "<small>só BM25</small>"}</div></div>
      ${b.documentos.length ? `<details ${b.documentos.length <= 12 ? "open" : ""}><summary>${b.documentos.length} documentos indexados${e.empresas.length ? ` · ${esc(e.empresas.join(", "))}` : ""}</summary>
      <div class="tabela-scroll"><table><thead><tr><th>Id</th><th>Empresa</th><th>Entrega</th><th>Categoria</th><th>Assunto</th><th class="num">Páginas</th><th></th></tr></thead><tbody>
      ${b.documentos.map((d) => `<tr><td><code>D${d.id}</code></td><td>${esc(d.ticker)}</td><td>${esc(dataBR(d.data_entrega?.slice(0, 10)))}</td>
        <td>${esc(d.categoria || "")}</td><td>${esc(d.assunto || "")}${d.status !== "ok" ? ` <span class="tag perde">${d.status === "sem_texto" ? "PDF sem texto" : esc(d.status)}</span>` : ""}</td>
        <td class="num">${d.paginas}</td><td>${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">PDF ↗</a>` : ""}</td></tr>`).join("")}
      </tbody></table></div></details>` : `<p class="dica">Nenhum documento ainda. Escolha as empresas e clique em <b>Baixar e indexar</b>.</p>`}`;
  } catch (err) { $("#dc-base").innerHTML = `<p class="status erro">${esc(err.message)}</p>`; }
}

async function dcIndexar(ev) {
  ev.preventDefault();
  const st = $("#dc-status-indexar"), btn = $("#dc-indexar");
  const tickers = $("#dc-tickers").value.split(/[\s,;]+/).filter(Boolean);
  const categorias = [...document.querySelectorAll(".dc-cats input[value]:checked")].map((c) => c.value);
  btn.disabled = true; st.className = "status";
  st.textContent = `Baixando os PDFs de ${tickers.join(", ")} na CVM e indexando… (alguns segundos por documento)`;
  try {
    const r = await dcPost("/api/docs/indexar", { tickers, categorias, por_empresa: Number($("#dc-qtd").value), ri: $("#dc-ri").checked });
    const emb = r.embeddings || {};
    st.textContent = `${r.novos.length} novo(s), ${r.pulados} já indexado(s)${r.falhas.length ? `, ${r.falhas.length} falha(s)` : ""}.`
      + (r.ri ? ` Relatórios de RI: ${r.ri.documentos.length}${r.ri.falhas.length ? ` (${r.ri.falhas.length} falha(s))` : ""}.` : "")
      + (emb.erro ? ` Embeddings: ${emb.erro}` : emb.novos ? ` ${emb.novos} trechos vetorizados (${emb.modelo}).` : emb.aviso ? ` ${emb.aviso}` : "");
    if (r.falhas.length) st.textContent += " Falhas: " + r.falhas.slice(0, 3).map((f) => `${f.assunto || f.protocolo}: ${f.erro}`).join(" | ");
    dcCarregarBase();
  } catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { btn.disabled = false; }
}

// ---------- 2. perguntas ----------
function dcCitar(html) {
  return html.replace(/\[D(\d+)[\s,·]*p\.?\s*(\d+)\]/g, '<a href="#" class="dc-cita" data-doc="$1" data-pag="$2">[D$1 p$2]</a>');
}

async function dcPerguntar(ev) {
  ev?.preventDefault();
  const st = $("#dc-status-perguntar"), btn = $("#dc-perguntar"), pergunta = $("#dc-pergunta").value.trim();
  if (!pergunta) return;
  btn.disabled = true; st.className = "status"; st.textContent = "O agente está buscando nos documentos…";
  try {
    DC_RESP = await dcPost("/api/docs/perguntar", { pergunta, ticker: $("#dc-ticker").value.trim().toUpperCase() || null });
    st.textContent = ""; dcRenderResposta();
  } catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { btn.disabled = false; }
}

function dcRenderResposta() {
  const r = DC_RESP, m = r.metricas || {};
  const tok = (m.tokens?.prompt_tokens || 0) + (m.tokens?.completion_tokens || 0);
  $("#dc-resposta").innerHTML = `
    ${r.texto ? `<div class="rs-analise dc-texto">${dcCitar(rsMd(r.texto))}</div>`
      : (r.passos || []).some((p) => p.tipo === "rascunho")
        ? `<p class="aviso-box">O agente não conseguiu uma resposta aprovada pelo validador (veja abaixo o que foi barrado).</p>`
        : `<p class="aviso-box">A IA não respondeu: ${esc((r.passos || []).filter((p) => p.tipo === "erro").map((p) => p.texto).pop() || "sem resposta")}.<br>
           Normalmente é passageiro: tente de novo em alguns minutos. Para não depender de um só provedor, cadastre também a chave gratuita do Groq em Research → Configurar IA gratuita.</p>`}
    <p class="dica">${esc((r.provedores || []).join(" → "))} · ${dcNum(m.segundos, 1)} s${m.segundos_ia != null ? ` (IA ${dcNum(m.segundos_ia, 0)} s, busca ${dcNum(m.segundos_ferramentas, 0)} s)` : ""} · ${m.chamadas_ferramenta || 0} buscas · ${r.paginas_lidas} páginas lidas
      · ${m.correcoes || 0} correção(ões) pedidas pelo validador${tok ? ` · ${dcNum(tok, 0)} tokens` : ""}</p>
    ${r.citacoes?.length ? `<div class="dc-fontes"><p class="rs-sub">Fontes citadas</p><ul>${r.citacoes.map((c) =>
      `<li><a href="#" class="dc-cita" data-doc="${c.doc_id}" data-pag="${c.pagina}">[${esc(c.id)}]</a> ${esc(c.assunto || "")}
        <span class="dica">${esc(dataBR(c.data?.slice(0, 10)) || "")}</span> ${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">PDF ↗</a>` : ""}</li>`).join("")}</ul></div>` : ""}
    <details class="dc-passos"><summary>Como o agente investigou</summary>${rsPassos(r.passos || [])}</details>`;
}

async function dcMostrarPagina(doc, pag) {
  const painel = $("#dc-pagina");
  painel.hidden = false; painel.innerHTML = `<p class="dica">Carregando a página…</p>`;
  try {
    const p = await api(`/api/docs/${doc}/pagina/${pag}`);
    let html = esc(p.texto);
    // destaca os trechos que a resposta pôs entre aspas
    const aspas = [...((DC_RESP?.texto || "").matchAll(/[“"]([^”"]{12,})[”"]/g))].map((m) => m[1].trim());
    for (const q of aspas) {
      const qe = esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
      html = html.replace(new RegExp(qe, "i"), (x) => `<mark>${x}</mark>`);
    }
    painel.innerHTML = `<div class="painel-topo"><b>D${doc} · página ${pag}</b><button type="button" class="fechar" aria-label="Fechar">×</button></div>
      <pre class="dc-pagina-texto">${html}</pre>`;
  } catch (err) { painel.innerHTML = `<p class="status erro">${esc(err.message)}</p>`; }
}

// ---------- 3. avaliação ----------
async function dcCarregarAvaliacoes() {
  try {
    const a = await api("/api/docs/avaliacoes");
    $("#dc-arquivo").textContent = a.arquivo_perguntas; $("#dc-n-perg").textContent = a.perguntas;
    const busca = a.execucoes.filter((e) => e.tipo === "busca"), resp = a.execucoes.filter((e) => e.tipo === "respostas");
    const barra = (v) => `<span class="dc-barra"><i style="width:${Math.max(0, Math.min(100, v || 0))}%"></i></span>`;
    const MODO = { bm25: "Palavras (BM25)", semantico: "Semântica", hibrido: "Híbrida (RRF)" };
    $("#dc-execucoes").innerHTML = `
      ${busca.length ? `<h3 class="rs-sec">Execuções de busca</h3><div class="tabela-scroll"><table><thead><tr><th>Quando</th><th>Perguntas geradas por</th><th class="num">n</th><th>Busca</th>
        <th>Recall@1</th><th>Recall@5</th><th class="num">MRR</th></tr></thead><tbody>
        ${busca.map((e) => Object.entries(e.modos).map(([m, v], i) => `<tr>${i === 0 ? `<td rowspan="${Object.keys(e.modos).length}">${esc(e.quando)}</td>
          <td rowspan="${Object.keys(e.modos).length}">${esc(e.geracao)}${e.embeddings ? `<br><small class="dica">emb.: ${esc(e.embeddings)}</small>` : ""}</td>
          <td class="num" rowspan="${Object.keys(e.modos).length}">${e.n}</td>` : ""}
          <td>${MODO[m] || m}</td><td>${barra(v["recall@1"])} ${dcPct(v["recall@1"])}</td><td>${barra(v[`recall@${e.k}`])} ${dcPct(v[`recall@${e.k}`])}</td>
          <td class="num">${dcNum(v.mrr, 3)}</td></tr>`).join("")).join("")}
        </tbody></table></div>` : ""}
      ${resp.length ? `<h3 class="rs-sec">Execuções de respostas</h3><div class="tabela-scroll"><table><thead><tr><th>Quando</th><th>Provedor</th><th class="num">Perguntas</th>
        <th class="num">Aprovadas</th><th class="num">Na 1ª</th><th class="num">Rascunhos barrados</th><th class="num">Contém esperado</th>
        <th class="num">Recusa correta</th><th class="num">Citações/resp.</th><th class="num">s/pergunta</th><th class="num">Tokens</th></tr></thead><tbody>
        ${resp.map((e) => { const s = e.resumo; return `<tr><td>${esc(e.quando)}</td><td>${esc(e.provedor || "")}</td><td class="num">${s.executadas}/${s.perguntas}</td>
          <td class="num">${dcPct(s["aprovadas_pelo_validador_%"])}</td><td class="num">${dcPct(s["aprovadas_na_1a_tentativa_%"])}</td>
          <td class="num">${s.rascunhos_barrados}</td><td class="num">${dcPct(s["contem_esperado_%"])}</td><td class="num">${dcPct(s["recusa_correta_%"])}</td>
          <td class="num">${dcNum(s.citacoes_por_resposta)}</td><td class="num">${dcNum(s.segundos_por_pergunta, 1)}</td><td class="num">${dcNum(s.tokens, 0)}</td></tr>`; }).join("")}
        </tbody></table></div>` : ""}
      ${!a.execucoes.length ? `<p class="dica">Nenhuma avaliação ainda.</p>` : ""}
      <details class="dc-glossario"><summary>O que cada métrica significa</summary><ul>
        <li><b>Recall@k</b>: em quantas perguntas o trecho certo (ou outro da mesma página) veio entre os k primeiros resultados.</li>
        <li><b>MRR</b>: média de 1/posição do trecho certo (1 = sempre em primeiro; 0,5 = em média em segundo).</li>
        <li><b>Aprovadas</b>: respostas que passaram no validador (citações existem, aspas e números batem com as páginas).</li>
        <li><b>Rascunhos barrados</b>: versões reprovadas pelo validador — alucinações que não chegaram até você.</li>
        <li><b>Contém esperado / Recusa correta</b>: conferem as respostas contra o que você escreveu em perguntas.jsonl.</li>
      </ul></details>`;
  } catch (err) { $("#dc-execucoes").innerHTML = `<p class="status erro">${esc(err.message)}</p>`; }
}

async function dcAvaliar(tipo) {
  const st = $("#dc-status-avaliar");
  const botoes = [$("#dc-avaliar-busca"), $("#dc-avaliar-resp")];
  botoes.forEach((b) => { b.disabled = true; });
  st.className = "status";
  st.textContent = tipo === "busca" ? "Gerando perguntas e medindo a busca…" : "Rodando o agente em cada pergunta (pode levar alguns minutos)…";
  try {
    const corpo = tipo === "busca" ? { n: Number($("#dc-n").value), usar_ia: $("#dc-ia").checked } : { provedor: $("#dc-prov").value || null };
    await dcPost(`/api/docs/avaliar/${tipo}`, corpo);
    st.textContent = "Pronto."; dcCarregarAvaliacoes();
  } catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { botoes.forEach((b) => { b.disabled = false; }); }
}

// ---------- eventos ----------
$("#dc-form-indexar").addEventListener("submit", dcIndexar);
$("#dc-form-perguntar").addEventListener("submit", dcPerguntar);
$("#dc-exemplos").addEventListener("click", (e) => {
  const b = e.target.closest("[data-q]");
  if (b) { $("#dc-pergunta").value = b.dataset.q; dcPerguntar(); }
});
$("#aba-docs").addEventListener("click", (e) => {
  const c = e.target.closest(".dc-cita");
  if (c) { e.preventDefault(); dcMostrarPagina(c.dataset.doc, c.dataset.pag); return; }
  if (e.target.closest("#dc-pagina .fechar")) $("#dc-pagina").hidden = true;
});
$("#dc-avaliar-busca").addEventListener("click", () => dcAvaliar("busca"));
$("#dc-avaliar-resp").addEventListener("click", () => dcAvaliar("respostas"));
document.querySelector('[data-aba="docs"]').addEventListener("click", () => { dcCarregarBase(); dcCarregarAvaliacoes(); });
if (location.hash === "#docs") { dcCarregarBase(); dcCarregarAvaliacoes(); }
