// Interface "limpa": Modo direto (padrão) × Modo estudo, sem reescrever cada aba.
// - Explicações (dicas longas, fórmulas, parágrafos dos passos, ajudas dos controles) são marcadas como didáticas.
//   No modo direto ficam escondidas e cada bloco ganha um botão "ⓘ Saiba mais" que abre o conteúdo num painel lateral.
// - Subseções de detalhe (h3.sub + o que vem depois) viram seções recolhíveis: fechadas no modo direto.
// - Dois ou mais avisos seguidos viram um único "⚠ N pontos de atenção".
// Nada é movido de lugar: só se acrescentam classes e botões, então os ids que cada aba usa continuam funcionando.
const LIMPO = {
  chave: "indicadores-b3-modo",
  container: ".bloco, .card, .dc-cartao, .vazio, .kpi-bp, .premissa, details",
  didatico: ".dica, .eq, .p-ajuda, .passo > div > p, .vazio > p",
  fora: "#aba-estudos, .sen-mais, .artigo, .art-corpo, .art-caixa, dialog, #saiba-painel, .rs-analise, .dc-texto, .lateral, .barra, .rs-item, .status",
  minimo: 70, // dicas curtas (fonte, contagem) continuam visíveis
};

function modoAtual() {
  try { return localStorage.getItem(LIMPO.chave) || "direto"; } catch { return "direto"; }
}

function aplicarModo(modo) {
  document.body.classList.toggle("modo-direto", modo === "direto");
  document.body.classList.toggle("modo-estudo", modo !== "direto");
  document.querySelectorAll(".modo-alternar button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.modo === modo)));
  document.querySelectorAll("details.limpo-sec, details.avisos-grupo").forEach((d) => { d.open = modo !== "direto"; });
  try { localStorage.setItem(LIMPO.chave, modo); } catch { /* sem armazenamento: vale só nesta visita */ }
}

function ehDidatico(el) {
  if (el.closest(LIMPO.fora) || el.dataset.limpo) return false;
  if (el.querySelector("[id], input, select, textarea, button, canvas, svg, table") || el.id) return false;
  if (el.classList.contains("dica") && el.textContent.trim().length < LIMPO.minimo) return false;
  return el.textContent.trim().length > 0;
}

function processarLimpo(raiz = document.querySelector(".area")) {
  if (!raiz) return;
  const modo = modoAtual();
  // 1. explicações → escondidas no modo direto + botão "Saiba mais" no bloco
  raiz.querySelectorAll(LIMPO.didatico).forEach((el) => {
    if (!ehDidatico(el)) return;
    const bloco = el.closest(LIMPO.container);
    if (!bloco) return; // fora de um bloco: fica visível (não há onde pôr o botão)
    el.dataset.limpo = "1";
    el.classList.add("limpo-didatico");
    if ( bloco.querySelector(":scope > .saiba-btn, :scope > :is(h2,h3,summary) > .saiba-btn, :scope > div > :is(h2,h3) > .saiba-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "saiba-btn"; btn.textContent = "i";
    btn.title = "Saiba mais"; btn.setAttribute("aria-label", "Saiba mais");
    const titulo = bloco.querySelector(":scope > h2, :scope > h3, :scope > summary, :scope > div > h2, :scope > div > h3, :scope > .p-rotulo");
    (titulo || bloco).appendChild(btn);
  });
  // 2. subseções de detalhe → recolhíveis
  raiz.querySelectorAll(".aba-painel h3.sub").forEach((h) => {
    if (h.closest(LIMPO.fora) || h.closest("details.limpo-sec") || h.dataset.limpo) return;
    h.dataset.limpo = "1";
    const det = document.createElement("details");
    det.className = "limpo-sec"; det.open = modo !== "direto";
    const sum = document.createElement("summary"); sum.textContent = h.textContent;
    det.appendChild(sum);
    h.before(det);
    let n = h.nextElementSibling;
    while (n && !n.matches("h2, h3.sub, details.limpo-sec")) { const prox = n.nextElementSibling; det.appendChild(n); n = prox; }
    h.remove();
  });
  // 3. avisos seguidos → um grupo
  raiz.querySelectorAll(".aviso-box:not([data-limpo])").forEach((a) => {
    if (a.closest("details.avisos-grupo") || a.closest(LIMPO.fora)) return;
    const seguidos = [a];
    let n = a.nextElementSibling;
    while (n && n.classList.contains("aviso-box")) { seguidos.push(n); n = n.nextElementSibling; }
    seguidos.forEach((x) => { x.dataset.limpo = "1"; });
    if (seguidos.length < 2) return;
    const det = document.createElement("details");
    det.className = "avisos-grupo"; det.open = modo !== "direto";
    det.innerHTML = `<summary>⚠ ${seguidos.length} pontos de atenção</summary>`;
    a.before(det);
    seguidos.forEach((x) => det.appendChild(x));
  });
}

// degradê na borda direita das tabelas que têm conteúdo escondido à direita
// mensagens de andamento ("Calculando…") ganham o indicador de carregamento; resultados e erros, não
function marcarStatus() {
  document.querySelectorAll(".status").forEach((s) => s.classList.toggle("st-carregando", !s.classList.contains("erro") && /…\s*$/.test(s.textContent.trim())));
}

function marcarRolagem() {
  document.querySelectorAll(".tabela-scroll").forEach((t) => {
    // sobra de poucos pixels (bordas) não justifica barra de rolagem
    t.classList.toggle("sem-rolagem", t.scrollWidth - t.clientWidth <= 6);
    t.classList.toggle("tem-mais", t.scrollWidth - t.clientWidth - t.scrollLeft > 6);
    if (!t.dataset.rolagem) {
      t.dataset.rolagem = "1";
      t.addEventListener("scroll", () => t.classList.toggle("tem-mais", t.scrollWidth - t.clientWidth - t.scrollLeft > 6), { passive: true });
    }
  });
}
window.addEventListener("resize", () => requestAnimationFrame(marcarRolagem));

function abrirSaibaMais(bloco) {
  const painel = document.querySelector("#saiba-painel");
  const t = bloco.querySelector("h2, h3, summary, .p-rotulo");
  const titulo = (t ? [...t.childNodes].filter((n) => !(n.classList && n.classList.contains("saiba-btn"))).map((n) => n.textContent).join("") : "")
    .replace("ⓘ Saiba mais", "").trim() || "Saiba mais";
  const corpo = document.createElement("div");
  bloco.querySelectorAll(".limpo-didatico").forEach((el) => {
    if (el.closest(LIMPO.container) !== bloco) return;
    const c = el.cloneNode(true);
    c.classList.remove("limpo-didatico");
    c.querySelectorAll("[id]").forEach((x) => x.removeAttribute("id"));
    corpo.appendChild(c);
  });
  painel.querySelector(".saiba-titulo").textContent = titulo;
  const alvo = painel.querySelector(".saiba-corpo");
  alvo.innerHTML = ""; alvo.appendChild(corpo);
  painel.hidden = false; painel.querySelector(".fechar").focus();
}

function fecharSaibaMais() { document.querySelector("#saiba-painel").hidden = true; }

(function iniciarLimpo() {
  const painel = document.createElement("aside");
  painel.id = "saiba-painel"; painel.className = "saiba-painel"; painel.hidden = true;
  painel.setAttribute("aria-label", "Saiba mais");
  painel.innerHTML = `<div class="painel-topo"><b class="saiba-titulo">Saiba mais</b><button type="button" class="fechar" aria-label="Fechar">×</button></div>
    <div class="saiba-corpo"></div>`;
  document.body.appendChild(painel);
  painel.querySelector(".fechar").addEventListener("click", fecharSaibaMais);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharSaibaMais(); });

  const alt = document.createElement("div");
  alt.className = "modo-alternar"; alt.setAttribute("role", "group"); alt.setAttribute("aria-label", "Modo de exibição");
  alt.innerHTML = `<button type="button" data-modo="direto" title="Só números e decisões">Direto</button>
    <button type="button" data-modo="estudo" title="Mostra todas as explicações">Estudo</button>`;
  document.querySelector(".lateral-rodape")?.before(alt);
  alt.addEventListener("click", (e) => { const b = e.target.closest("[data-modo]"); if (b) aplicarModo(b.dataset.modo); });

  document.addEventListener("click", (e) => {
    const b = e.target.closest(".saiba-btn");
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    abrirSaibaMais(b.closest(LIMPO.container));
  }, true);

  aplicarModo(modoAtual());
  processarLimpo();
  marcarRolagem();
  let agendado = false;
  new MutationObserver(() => {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => { agendado = false; processarLimpo(); marcarRolagem(); marcarStatus(); });
  }).observe(document.querySelector(".area"), { childList: true, subtree: true, characterData: true });
})();
