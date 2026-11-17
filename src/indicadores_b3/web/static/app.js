// Front-end: busca na API local e monta comparativo + detalhe didático.
// Tudo que é "conteúdo" (fórmulas, explicações, fontes) vem de /api/catalogo,
// então indicadores novos aparecem aqui sem mexer neste arquivo.

let CAT = null;          // { tipos: { acao: {...}, fii: {...}, mercado: {...} } }
const EMPRESAS = [];     // resultados carregados

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// ---------- Formatação ----------
const nf = (d) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });

function abreviar(v) {
  const a = Math.abs(v);
  if (a >= 1e9) return nf(1).format(v / 1e9) + " bi";
  if (a >= 1e6) return nf(1).format(v / 1e6) + " mi";
  if (a >= 1e3) return nf(1).format(v / 1e3) + " mil";
  return nf(0).format(v);
}

function fmt(v, unidade) {
  if (v === null || v === undefined) return "—";
  switch (unidade) {
    case "R$":      return Math.abs(v) >= 1e4 ? "R$ " + abreviar(v) : "R$ " + nf(2).format(v);
    case "R$/ação":
    case "R$/cota": return "R$ " + nf(2).format(v);
    case "x":       return nf(2).format(v) + "x";
    case "%":       return nf(2).format(v) + "%";
    case "qtd":     return abreviar(v);
    case "dias":    return nf(0).format(v) + " dias";
    case "anos":    return nf(1).format(v) + " anos";
    case "decimal": return nf(4).format(v);
    default:        return nf(2).format(v);
  }
}

const tipoDe = (e) => CAT.tipos[e.tipo];
const metaDe = (e, id) => tipoDe(e).indicadores.find((i) => i.id === id);
const rotulo = (e, id) => tipoDe(e).rotulos[id] || { nome: id, fonte: "", unidade: "" };
const unidadeDe = (e, id) => rotulo(e, id).unidade || "R$";

const diasDesde = (data) => Math.floor((Date.now() - new Date(data + "T00:00:00")) / 864e5);
const dataBR = (s) => String(s ?? "").replace(/(\d{4})-(\d{2})-(\d{2})/g, "$3/$2/$1");

// ---------- API ----------
async function api(caminho) {
  const r = await fetch(caminho);
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corpo.detail || `Erro ${r.status}`);
  return corpo;
}

// ---------- Comparativo (uma tabela por tipo de ativo) ----------
function renderComparativo() {
  const grupos = {};
  EMPRESAS.forEach((e, idx) => (grupos[e.erro ? "erro" : e.tipo] ??= []).push(idx));

  const tabelas = Object.keys(CAT.tipos).filter((t) => grupos[t]).map((t) => {
    const cols = CAT.tipos[t].indicadores.filter((i) => i.unidade !== "R$");
    const linhas = grupos[t].map((idx) => {
      const e = EMPRESAS[idx];
      const val = Object.fromEntries(e.indicadores.map((i) => [i.id, i.valor]));
      return `<tr data-idx="${idx}"><td><strong>${esc(e.ticker)}</strong><span class="sub-tk">${esc(e.subtipo)}</span></td>${cols.map((c) =>
        `<td class="${val[c.id] < 0 ? "neg" : ""}">${fmt(val[c.id], c.unidade)}</td>`).join("")}</tr>`;
    }).join("");
    return `<h3 class="grupo">${esc(CAT.tipos[t].nome)}</h3>
      <div class="tabela-scroll"><table>
        <thead><tr><th>Ativo</th>${cols.map((c) => `<th title="${esc(c.nome)}">${esc(c.sigla)}</th>`).join("")}</tr></thead>
        <tbody>${linhas}</tbody></table></div>`;
  }).join("");

  const erros = (grupos.erro || []).map((idx) =>
    `<p class="status erro"><strong>${esc(EMPRESAS[idx].ticker)}:</strong> ${esc(EMPRESAS[idx].erro)}</p>`).join("");

  $("#tabela-wrap").innerHTML = tabelas + erros;
  $("#comparativo").hidden = false;
  $("#tabela-wrap").querySelectorAll("tr[data-idx]").forEach((tr) =>
    tr.addEventListener("click", () => renderDetalhe(+tr.dataset.idx)));
}

// ---------- Detalhe ----------
function card(e, meta, res) {
  const vazio = res.valor === null;
  const entradas = Object.entries(res.entradas).map(([id, v]) =>
    `<dt>${esc(rotulo(e, id).nome)}</dt><dd>${fmt(v, unidadeDe(e, id))}</dd>`).join("");
  return `
    <article class="card" data-abrir="${esc(meta.id)}">
      <div class="cab"><span class="sigla">${esc(meta.sigla)}</span><span class="nome">${esc(meta.nome)}</span></div>
      <div class="valor ${vazio ? "vazio" : ""} ${res.valor < 0 ? "neg" : ""}">
        ${vazio ? "não calculado" : fmt(res.valor, meta.unidade)}
      </div>
      <div class="calculo">
        <div class="formula">${esc(meta.sigla)} = ${esc(meta.formula)}</div>
        <dl>${entradas}</dl>
      </div>
      <button type="button" class="abrir">Ver campos usados →</button>
    </article>`;
}

function renderDetalhe(idx) {
  const e = EMPRESAS[idx], T = tipoDe(e);
  document.querySelectorAll("#tabela-wrap tr").forEach((tr) => tr.classList.toggle("ativo", tr.dataset.idx == idx));

  const res = Object.fromEntries(e.indicadores.map((i) => [i.id, i]));
  const dias = diasDesde(e.balanco_ref);
  const refTxt = { acao: "Balanço de", fii: "Informe mensal de", tesouro: "Preço do Tesouro em" }[e.tipo] || "Último preço em";
  const limite = { acao: 150, fii: 75 }[e.tipo] || 7;

  const categorias = T.categorias.map((cat) => `
    <div class="categoria">
      <h3>${esc(cat)}</h3>
      <div class="grid">${T.indicadores.filter((i) => i.categoria === cat)
        .map((meta) => card(e, meta, res[meta.id])).join("")}</div>
    </div>`).join("");

  const base = Object.entries(e.valores).map(([id, v]) => `
    <tr data-abrir="${esc(id)}"><td>${esc(rotulo(e, id).nome)}</td><td>${fmt(v, unidadeDe(e, id))}</td>
        <td>${esc(rotulo(e, id).fonte)}</td></tr>`).join("");

  const avisos = (e.avisos || []).map((a) => `<div class="aviso-box">⚠ ${esc(a)}</div>`).join("");

  $("#detalhe").innerHTML = `
    <div class="empresa"><h2>${esc(e.empresa)}</h2><span class="tk">${esc(e.ticker)}</span></div>
    <div class="meta">
      <span class="pill">${esc(e.subtipo)}</span>
      <span class="pill">Preço: ${fmt(e.valores.preco, "R$/cota")}</span>
      <span class="pill ${dias > limite ? "aviso" : ""}">${refTxt} ${dataBR(e.balanco_ref)} · ${dias} dias atrás</span>
    </div>
    ${avisos}
    <div id="acao-extra"></div>
    ${categorias}
    <details class="base dcf-det">
      <summary>Dados de base (os números crus e a fonte de cada um)</summary>
      <div class="tabela-scroll"><table>
        <thead><tr><th>Dado</th><th>Valor</th><th>Fonte</th></tr></thead><tbody>${base}</tbody>
      </table></div>
    </details>`;
  $("#detalhe").hidden = false;
  if (typeof extrasAtivo === "function") extrasAtivo(e);
  $("#detalhe").querySelectorAll("[data-abrir]").forEach((el) =>
    el.addEventListener("click", () => abrirPainel(idx, el.dataset.abrir, true)));
  $("#detalhe").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- Painel: campos usados ----------
const PILHA = [];   // histórico para o botão "Voltar"
const ESCALAS = { MIL: "em milhares", "FRAÇÃO (×100)": "fração; ×100 para virar %" };

function linkFonte(c) {
  return c.url ? ` · <a href="${esc(c.url)}" target="_blank" rel="noopener">abrir fonte ↗</a>` : "";
}

function htmlComponente(c, unidade) {
  const menos = c.sinal === "−";
  const original = c.valor_original !== undefined && ESCALAS[c.escala]
    ? ` · no arquivo: <code>${esc(String(c.valor_original))}</code> (${ESCALAS[c.escala]})` : "";
  return `
    <div class="comp">
      <span class="sinal ${menos ? "menos" : ""}">${esc(c.sinal)}</span>
      <span class="papel">${esc(c.papel)}</span>
      <span class="cv">${fmt(c.valor, unidade)}</span>
      <span class="linha"><code>${esc(c.conta)}</code> ${esc(c.descricao)}</span>
      <span class="linha">${esc(c.fonte)} · ${esc(c.documento)}${c.versao ? ` · versão ${c.versao}` : ""} · ${esc(dataBR(c.periodo))}${original}${linkFonte(c)}</span>
      ${c.arquivo ? `<span class="linha arquivo">${esc(c.arquivo)}</span>` : ""}
    </div>`;
}

function htmlBase(e, id) {
  const r = e.rastreio[id], un = unidadeDe(e, id);
  const comps = r.componentes.map((c) => htmlComponente(c, un)).join("");
  const somados = r.componentes.filter((c) => c.sinal === "+" || c.sinal === "−").length;
  return `
    <div class="entrada">
      <div class="e-cab"><span class="e-nome">${esc(rotulo(e, id).nome)}</span>
        <span class="e-valor">${fmt(r.valor, un)}</span></div>
      ${r.nota ? `<p class="e-nota">${esc(r.nota)}</p>` : ""}
      ${comps || ""}
      ${somados > 1 ? `<div class="total"><span>=</span><span>${fmt(r.valor, un)}</span></div>` : ""}
    </div>`;
}

function htmlIndicadorEntrada(e, id) {
  const meta = metaDe(e, id);
  const v = e.indicadores.find((i) => i.id === id).valor;
  return `
    <div class="entrada">
      <div class="e-cab"><span class="e-nome">${esc(meta.sigla)}<span class="tag">indicador</span></span>
        <span class="e-valor">${fmt(v, meta.unidade)}</span></div>
      <p class="e-nota">${esc(meta.sigla)} = ${esc(meta.formula)}</p>
      <button type="button" class="link" data-ir="${esc(id)}">Ver como o ${esc(meta.sigla)} foi calculado →</button>
    </div>`;
}

function abrirPainel(idx, id, novo = false) {
  const e = EMPRESAS[idx];
  if (novo) PILHA.length = 0;
  PILHA.push(id);
  const meta = metaDe(e, id);

  let html;
  if (meta) {
    const res = e.indicadores.find((i) => i.id === id);
    const passos = meta.entradas.map((ent) =>
      e.rastreio[ent] ? htmlBase(e, ent) : htmlIndicadorEntrada(e, ent)).join("");
    html = `
      <div class="p-cab"><div class="sigla">${esc(meta.categoria)} · ${esc(e.ticker)}</div>
        <h2 id="painel-titulo">${esc(meta.sigla)} — ${esc(meta.nome)}</h2>
        <div class="valor ${res.valor < 0 ? "neg" : ""}">${res.valor === null ? "não calculado" : fmt(res.valor, meta.unidade)}</div></div>
      <div class="p-formula">${esc(meta.sigla)} = ${esc(meta.formula)}</div>
      <div class="p-sec">Campos usados no cálculo</div>
      ${passos}
      <div class="p-sec">Entenda</div>
      <div class="textos">
        <h4>O que é</h4><p>${esc(meta.o_que_e)}</p>
        <h4>Como ler</h4><p>${esc(meta.como_ler)}</p>
        <h4>Cuidados</h4><p>${esc(meta.cuidados)}</p>
      </div>`;
  } else {
    html = `
      <div class="p-cab"><div class="sigla">Dado de base · ${esc(e.ticker)}</div>
        <h2 id="painel-titulo">${esc(rotulo(e, id).nome)}</h2></div>
      <div class="p-sec">Campos usados</div>
      ${htmlBase(e, id)}`;
  }

  $("#painel-corpo").innerHTML = html;
  $("#painel-corpo").querySelectorAll("[data-ir]").forEach((b) =>
    b.addEventListener("click", () => abrirPainel(idx, b.dataset.ir)));
  $("#painel-voltar").hidden = PILHA.length < 2;
  $("#painel-voltar").onclick = () => { PILHA.pop(); abrirPainel(idx, PILHA.pop()); };
  $("#painel").scrollTop = 0;
  if (!$("#painel").open) $("#painel").showModal();
}

$("#painel-fechar").addEventListener("click", () => $("#painel").close());
$("#painel").addEventListener("click", (ev) => { if (ev.target === $("#painel")) $("#painel").close(); });

// ---------- Busca ----------
$("#busca")?.addEventListener("submit", async (ev) => {  // a aba Indicadores pode não existir (extras/)
  ev.preventDefault();
  const tickers = [...new Set($("#tickers").value.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean))];
  if (!tickers.length) return;

  const btn = $("#busca button"), status = $("#status");
  btn.disabled = true;
  status.className = "status";
  EMPRESAS.length = 0;
  $("#detalhe").hidden = true;

  try {
    CAT ??= await api("/api/catalogo");
    // um por vez: na primeira execução os arquivos da CVM são baixados
    for (const [n, tk] of tickers.entries()) {
      status.textContent = `Carregando ${tk} (${n + 1}/${tickers.length})… a primeira busca baixa os arquivos da CVM e pode levar alguns minutos.`;
      try {
        EMPRESAS.push(await api(`/api/empresa/${encodeURIComponent(tk)}`));
      } catch (err) {
        EMPRESAS.push({ ticker: tk, erro: err.message });
      }
      renderComparativo();
    }
    status.textContent = "";
    const primeiro = EMPRESAS.findIndex((e) => !e.erro);
    if (primeiro >= 0) renderDetalhe(primeiro);
  } catch (err) {
    status.className = "status erro";
    status.textContent = "Não consegui falar com o servidor: " + err.message;
  } finally {
    btn.disabled = false;
  }
});

// ---------- Abas ----------
function mostrarAba(nome, semHistorico = false) {
  if (!document.querySelector(`#aba-${nome}`)) return;  // aba privada ausente (sem extras/)
  document.querySelectorAll("[data-aba]").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.aba === nome)));
  document.querySelectorAll(".aba-painel").forEach((s) => (s.hidden = s.id !== `aba-${nome}`));
  const botao = document.querySelector(`[data-aba="${nome}"]`);
  if (botao) {
    const nomeAba = botao.textContent.replace(botao.querySelector(".ico")?.textContent || "", "").trim();
    $("#titulo-pagina").textContent = nomeAba;
    $("#desc-pagina").textContent = botao.dataset.desc || "";
    document.title = `${nomeAba} · Indicadores B3`;
  }
  menuMobile(false);
  window.scrollTo({ top: 0 });
  const url = nome === ABA_PADRAO ? location.pathname : `#${nome}`;
  // voltar/avançar do navegador passam a trocar de aba
  if (!semHistorico && (location.hash.slice(1) || ABA_PADRAO) !== nome) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
}

// menu lateral no celular
function menuMobile(abrir) {
  $("#lateral").classList.toggle("aberto", abrir);
  $("#fundo-menu").hidden = !abrir;
}
$("#abrir-menu").addEventListener("click", () => menuMobile(true));
$("#fundo-menu").addEventListener("click", () => menuMobile(false));
document.querySelectorAll("[data-aba]").forEach((b) => b.addEventListener("click", () => mostrarAba(b.dataset.aba)));
// as abas vêm do menu: sem a pasta extras/, só as públicas existem
const ABAS = [...document.querySelectorAll("[data-aba]")].map((b) => b.dataset.aba);
const ABA_PADRAO = ["indicadores", "research"].find((a) => ABAS.includes(a)) || ABAS[0];
document.body.classList.toggle("sem-minhas", !ABAS.includes("minhas"));
document.body.classList.toggle("sem-estudos", !ABAS.includes("estudos"));
const HASH_ANTIGO = { dem: "balancos", dcf: "balancos" };
const ABA_INICIAL = HASH_ANTIGO[location.hash.slice(1)] || location.hash.slice(1);
mostrarAba(ABAS.includes(ABA_INICIAL) ? ABA_INICIAL : ABA_PADRAO, true);
window.addEventListener("hashchange", () => {
  const h = HASH_ANTIGO[location.hash.slice(1)] || location.hash.slice(1);
  if (ABAS.includes(h) && document.querySelector(`#aba-${h}`)?.hidden) document.querySelector(`[data-aba="${h}"]`)?.click();
});
window.addEventListener("popstate", () => {
  const h = HASH_ANTIGO[location.hash.slice(1)] || location.hash.slice(1);
  mostrarAba(ABAS.includes(h) ? h : ABA_PADRAO, true);
  document.querySelector(`[data-aba="${ABAS.includes(h) ? h : ABA_PADRAO}"]`)?.dispatchEvent(new Event("aba-aberta"));
});


// ---------- estados vazios com exemplos ----------
document.querySelectorAll("[data-vazio-form]").forEach((caixa) => {
  const form = $(caixa.dataset.vazioForm), input = $(caixa.dataset.vazioInput);
  form.addEventListener("submit", () => { caixa.hidden = true; });
  caixa.querySelectorAll("[data-exemplo]").forEach((b) => b.addEventListener("click", () => {
    input.value = b.dataset.exemplo;
    form.requestSubmit();
  }));
});
