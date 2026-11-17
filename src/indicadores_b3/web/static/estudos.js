// Aba "Estudos": artigos sobre os conceitos usados no site (conteúdo em estudos_artigos.js).
let EST_SEL = "como-ler", EST_Q = "", EST_CAT = "";
const NOMES_ABA = { indicadores: "Indicadores", minhas: "Minhas carteiras", carteira: "Carteira eficiente", dem: "Balanços",
  dcf: "Balanços → DCF", rf: "Renda fixa", der: "Derivativos", mod: "Modelos", sen: "Sensibilidade", comparar: "Comparar", comunicados: "Comunicados" };
const semAcento = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function renderEstudos() {
  const q = semAcento(EST_Q.trim());
  const lista = ESTUDOS.filter((a) => (!EST_CAT || a.cat === EST_CAT) &&
    (!q || semAcento(`${a.t} ${a.r} ${a.c} ${a.f || ""}`).includes(q)));
  $("#estudos-lista").innerHTML = ESTUDOS_CATS.map((cat) => {
    const itens = lista.filter((a) => a.cat === cat);
    return itens.length ? `<div class="est-grupo"><p>${esc(cat)}</p>${itens.map((a) =>
      `<button type="button" class="est-item ${a.id === EST_SEL ? "ativo" : ""}" data-est="${a.id}">${esc(a.t)}</button>`).join("")}</div>` : "";
  }).join("") || `<p class="dica">Nenhum artigo encontrado.</p>`;
  document.querySelectorAll("[data-est]").forEach((b) => b.addEventListener("click", () => abrirEstudo(b.dataset.est)));
  renderArtigo();
}

function renderArtigo() {
  const a = ESTUDOS.find((x) => x.id === EST_SEL);
  const rel = (a.ver || []).map((id) => ESTUDOS.find((x) => x.id === id)).filter(Boolean);
  $("#estudos-artigo").innerHTML = `<article class="artigo">
    <p class="art-cat">${esc(a.cat)}</p>
    <h2>${esc(a.t)}</h2>
    <p class="art-resumo">${esc(a.r)}</p>
    ${a.f ? `<div class="eq">${esc(a.f)}</div>` : ""}
    <div class="art-corpo">${a.c}</div>
    ${a.ex ? `<div class="art-caixa"><strong>Exemplo</strong><p>${esc(a.ex)}</p></div>` : ""}
    ${a.cu ? `<div class="aviso-box"><strong>Cuidados:</strong> ${esc(a.cu)}</div>` : ""}
    ${a.aba && ABAS.includes(["dem", "dcf"].includes(a.aba) ? "balancos" : a.aba) ? `<div class="art-caixa ok"><strong>Onde aparece no site</strong>
      <p>Veja com dados reais na aba <button type="button" class="link" data-ir="${a.aba}">${esc(NOMES_ABA[a.aba] || a.aba)} →</button></p></div>` : ""}
    ${rel.length ? `<div class="art-rel"><strong>Leia também</strong><div class="chips">${rel.map((r) =>
      `<button type="button" class="chip" data-est-rel="${r.id}">${esc(r.t)}</button>`).join("")}</div></div>` : ""}
    ${a.ref?.length ? `<div class="art-ref"><strong>Referências</strong><ul>${a.ref.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>` : ""}
  </article>`;
  document.querySelectorAll("[data-est-rel]").forEach((b) => b.addEventListener("click", () => abrirEstudo(b.dataset.estRel)));
  document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => {
    const ir = b.dataset.ir;
    if (ir === "dem" || ir === "dcf") { mostrarAba("balancos"); abrirBalanco(ir === "dcf" ? "dcf" : "dre"); }
    else document.querySelector(`[data-aba="${ir}"]`)?.click();
  }));
}

function abrirEstudo(id) {
  EST_SEL = id; renderEstudos();
  $("#estudos-artigo").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("#estudos-busca").addEventListener("input", (e) => { EST_Q = e.target.value; renderEstudos(); });
$("#estudos-cats").innerHTML = `<option value="">Todas as categorias</option>${ESTUDOS_CATS.map((c) => `<option>${esc(c)}</option>`).join("")}`;
$("#estudos-cats").addEventListener("change", (e) => { EST_CAT = e.target.value; renderEstudos(); });
$("#estudos-total").textContent = `${ESTUDOS.length} artigos`;
renderEstudos();
