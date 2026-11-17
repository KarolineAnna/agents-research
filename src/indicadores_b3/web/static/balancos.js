// Aba "Balanços": DRE, balanço patrimonial e DCF numa página só, com o mesmo código de ação.
let BAL_VISAO = "dre";

function abrirBalanco(visao) {
  const deDcf = BAL_VISAO === "dcf", paraDcf = visao === "dcf";
  BAL_VISAO = visao;
  document.querySelectorAll("[data-bal]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.bal === visao)));
  $("#bal-dem").hidden = paraDcf;
  $("#bal-dcf").hidden = !paraDcf;
  // leva o código digitado de uma visão para a outra e carrega se ainda não estiver carregado
  const origem = deDcf ? $("#ticker-dcf") : $("#ticker-dem"), destino = paraDcf ? $("#ticker-dcf") : $("#ticker-dem");
  if (origem !== destino) destino.value = origem.value;
  if (paraDcf) {
    if (!DCF || DCF.ticker !== destino.value.split(",")[0].trim().toUpperCase()) $("#form-dcf").requestSubmit();
  } else {
    document.querySelector(`[data-dem="${visao}"]`).click();
    if (!DEM || (DEM.ticker && DEM.ticker !== destino.value.trim().toUpperCase())) $("#form-dem").requestSubmit();
  }
}
document.querySelectorAll("[data-bal]").forEach((b) => b.addEventListener("click", () => abrirBalanco(b.dataset.bal)));
