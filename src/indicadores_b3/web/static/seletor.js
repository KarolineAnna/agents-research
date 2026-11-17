// Seletor de ativos: listagem por classe (Ações, FIIs, ETFs, Cripto/ouro/dólar, Renda fixa),
// com busca. Qualquer botão com data-seletor="#id-do-input" abre o seletor para aquele campo.

const SEL = {
  classes: [["acoes", "Ações"], ["fiis", "FIIs"], ["etfs", "ETFs"], ["outros", "Cripto, ouro e dólar"], ["renda_fixa", "Renda fixa"]],
  cache: {},
  alvo: null,
  classe: "acoes",
  escolhidos: new Set(),
  MAX: 3000, // mostra a lista inteira (algumas centenas de ações)
};

function abrirSeletor(alvo, classe) {
  SEL.alvo = $(alvo);
  SEL.escolhidos = new Set(SEL.alvo.value.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean));
  $("#seletor-busca").value = "";
  $("#seletor-classes").innerHTML = SEL.classes.map(([k, n]) =>
    `<button type="button" data-classe="${k}" aria-selected="false">${esc(n)}</button>`).join("");
  $("#seletor-classes").querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => trocarClasse(b.dataset.classe)));
  $("#seletor").showModal();
  trocarClasse(classe || "acoes");
}

async function trocarClasse(classe) {
  SEL.classe = classe;
  $("#seletor-classes").querySelectorAll("button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.classe === classe)));
  const lista = $("#seletor-lista");
  if (!SEL.cache[classe]) {
    lista.innerHTML = `<li class="dica">Carregando… ${classe === "acoes" || classe === "fiis"
      ? "na primeira vez o site baixa o cadastro da CVM." : ""}</li>`;
    try {
      SEL.cache[classe] = await api(`/api/lista/${classe}`);
    } catch (err) {
      lista.innerHTML = `<li class="status erro">${esc(err.message)}</li>`;
      return;
    }
  }
  $("#seletor-fonte").textContent = `Fonte da lista: ${SEL.cache[classe].fonte} · ${SEL.cache[classe].itens.length} ativos`
    + (classe === "acoes" ? " · setor: CVM (FCA)" : "");
  const sel = $("#seletor-setor"), itensC = SEL.cache[classe].itens;
  const macros = {};
  itensC.forEach((i) => { if (i.setor) (macros[i.macro] ||= new Set()).add(i.setor); });
  sel.hidden = !Object.keys(macros).length;
  sel.innerHTML = `<option value="">Todos os setores</option>` + Object.keys(macros).sort().map((m) =>
    `<optgroup label="${esc(m)}"><option value="m:${esc(m)}">${esc(m)} (todos)</option>${[...macros[m]].sort().map((s) =>
      `<option value="s:${esc(s)}">${esc(s)}</option>`).join("")}</optgroup>`).join("");
  renderLista();
}

function renderLista() {
  const termo = $("#seletor-busca").value.trim().toLowerCase();
  const fs = $("#seletor-setor").hidden ? "" : $("#seletor-setor").value;
  const itens = (SEL.cache[SEL.classe]?.itens || []).filter((i) =>
    (!termo || i.ticker.toLowerCase().includes(termo) || (i.nome || "").toLowerCase().includes(termo)
      || (i.setor || "").toLowerCase().includes(termo))
    && (!fs || (fs.startsWith("m:") ? i.macro === fs.slice(2) : i.setor === fs.slice(2))));
  const mostrar = itens.slice(0, SEL.MAX);
  $("#seletor-lista").innerHTML = mostrar.map((i) => `
    <li><label>
      <input type="checkbox" value="${esc(i.ticker)}" ${SEL.escolhidos.has(i.ticker) ? "checked" : ""}>
      <span class="s-tk">${esc(i.ticker.startsWith("TD-") ? i.nome : i.ticker)}</span>
      <span class="s-nome">${esc(i.ticker.startsWith("TD-") ? i.detalhe : i.nome)}</span>
      <span class="s-det">${esc(i.ticker.startsWith("TD-") ? i.ticker : i.detalhe)}${i.setor ? ` · <b>${esc(i.setor)}</b>` : ""}</span>
    </label></li>`).join("")
    + (itens.length > SEL.MAX ? `<li class="dica">Mostrando ${SEL.MAX} de ${itens.length}. Use a busca para filtrar.</li>` : "")
    + (!itens.length ? `<li class="dica">Nada encontrado.</li>` : "");
  $("#seletor-lista").querySelectorAll("input").forEach((c) => c.addEventListener("change", () => {
    c.checked ? SEL.escolhidos.add(c.value) : SEL.escolhidos.delete(c.value);
    contarEscolhidos();
  }));
  contarEscolhidos();
}

function contarEscolhidos() {
  $("#seletor-escolhidos").textContent = `${SEL.escolhidos.size} selecionado(s): ${[...SEL.escolhidos].join(", ")}`;
}

$("#seletor-busca").addEventListener("input", renderLista);
$("#seletor-setor").addEventListener("change", () => { $("#seletor-marcar").hidden = !$("#seletor-setor").value; renderLista(); });
// marca as empresas do setor filtrado (uma ação por empresa: a mais negociada no último pregão), até 12
$("#seletor-marcar").addEventListener("click", () => {
  const fs = $("#seletor-setor").value, vistos = new Set();
  (SEL.cache[SEL.classe]?.itens || []).filter((i) => fs.startsWith("m:") ? i.macro === fs.slice(2) : i.setor === fs.slice(2))
    .sort((a, b) => (b.volume || 0) - (a.volume || 0))
    .filter((i) => { const raiz = i.ticker.slice(0, 4); if (vistos.has(raiz)) return false; vistos.add(raiz); return (i.volume || 0) > 0; })
    .slice(0, 12).forEach((i) => SEL.escolhidos.add(i.ticker));
  renderLista();
});
$("#seletor-fechar").addEventListener("click", () => $("#seletor").close());
$("#seletor-ok").addEventListener("click", () => {
  SEL.alvo.value = [...SEL.escolhidos].join(", ");
  SEL.alvo.dispatchEvent(new Event("change"));
  $("#seletor").close();
});
document.querySelectorAll("[data-seletor]").forEach((b) =>
  b.addEventListener("click", () => abrirSeletor(b.dataset.seletor, b.dataset.classe)));
