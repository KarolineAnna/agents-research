// Histórico de acertos: as conclusões do software conferidas contra o que aconteceu depois.
let ACERTOS = null;
const AC_ORIGENS = {
  cara_ou_barata: { nome: "Cara ou barata", desc: "Veredito da aba Indicadores. Acerto: \"barata\" bateu o Ibovespa; \"cara\" ficou atrás.", alto: "barata", baixo: "cara", contra: "Ibovespa" },
  research: { nome: "Research", desc: "Leitura do preço justo do Research (potencial acima de +15% = barata, abaixo de −15% = cara).", alto: "barata", baixo: "cara", contra: "Ibovespa" },
  carteira: { nome: "Agente de carteira", desc: "Propostas confirmadas pelo agente. Acerto: \"aprovada\" rendeu mais que a carteira atual daquele dia; \"reprovada\" rendeu menos.", alto: "aprovada", baixo: "reprovada", contra: "carteira atual" },
};
const AC_H = { "3m": "3 meses", "6m": "6 meses", "12m": "12 meses" };
const AC_MIN = 30; // abaixo disso a taxa de acerto é quase só ruído

async function rodarAcertos() {
  const st = $("#status-acertos"), btn = $("#acertos-rodar");
  btn.disabled = true; st.className = "status"; st.textContent = "Conferindo as previsões com os preços de hoje…";
  try { ACERTOS = await api("/api/acertos"); st.textContent = ""; renderAcertos(); }
  catch (err) { st.className = "status erro"; st.textContent = err.message; }
  finally { btn.disabled = false; }
}

function acPp(v) { return v == null ? "n/d" : `${v > 0 ? "+" : ""}${nf(1).format(v)} p.p.`; }

function acBloco(id, r) {
  const o = AC_ORIGENS[id], g = ACERTOS.grupos;
  if (!r.previsoes) return "";
  const cards = ACERTOS.horizontes.map((h) => {
    const x = r.horizontes[h];
    if (!x.conferidas) return `<div class="ac-h"><h3>${AC_H[h]}</h3><p class="dica">${x.pendentes} aguardando.</p></div>`;
    const linhas = Object.entries(x.grupos).map(([k, v]) => `<tr><td>${esc(g[k])}</td><td class="num">${v.n}</td>
      <td class="num ${v.excesso_medio < 0 ? "neg" : ""}">${(v.excesso_medio > 0 ? "+" : "") + nf(1).format(v.excesso_medio)}</td><td class="num">${v.taxa_acerto == null ? "" : pct(v.taxa_acerto, 0)}</td></tr>`).join("");
    return `<div class="ac-h"><h3>${AC_H[h]}</h3>
      <table class="ac-tab"><thead><tr><th>Conclusão</th><th class="num">N</th><th class="num" title="retorno contra ${esc(o.contra)}, em pontos percentuais">Excesso</th><th class="num">Acerto</th></tr></thead><tbody>${linhas}</tbody></table>
      <div class="ac-linha"><span>Diferença ${esc(g[o.alto]).toLowerCase()} − ${esc(g[o.baixo]).toLowerCase()}</span><b class="${(x.diferenca_grupos ?? 0) < 0 ? "neg" : ""}">${acPp(x.diferenca_grupos)}</b></div>
      ${id !== "carteira" ? `<div class="ac-linha"><span>Taxa base (todas que bateram o Ibovespa)</span><b>${x.taxa_base == null ? "n/d" : pct(x.taxa_base, 0)}</b></div>` : ""}
      ${x.conferidas < AC_MIN ? `<p class="ac-aviso">Só ${x.conferidas} conferidas: com menos de ${AC_MIN}, a taxa ainda é quase só sorte.</p>` : ""}
    </div>`;
  }).join("");
  return `<div class="bloco ac-bloco"><h2>${o.nome}</h2><p class="dica">${esc(o.desc)}</p>
    <div class="ac-meta">${r.previsoes} ${r.previsoes === 1 ? "conclusão contada" : "conclusões contadas"} · excesso = retorno contra ${esc(o.contra)}, em p.p.${r.proxima_conferencia ? ` · próxima conferência em ${dataBR(r.proxima_conferencia)}` : ""}</div>
    <div class="ac-grade">${cards}</div></div>`;
}

function acCelula(x) {
  if (x.status === "pendente") return `<span class="sub-tk">em ${dataBR(x.pronto_em)}</span>`;
  if (x.status === "sem_dados") return '<span class="sub-tk">sem preço</span>';
  const s = x.acerto === true ? '<span class="ac-ok">acertou</span>' : x.acerto === false ? '<span class="ac-erro">errou</span>' : "";
  return `<span class="${x.excesso < 0 ? "neg" : ""}">${acPp(x.excesso)}</span> ${s}`;
}

function renderAcertos() {
  const A = ACERTOS;
  const nomeAlvo = (p) => p.origem === "carteira" ? `Proposta ${esc(p.alvo.split("#").pop())}${p.motivo ? `<span class="sub-tk">${esc(p.motivo)}</span>` : ""}` : `<strong>${esc(p.alvo)}</strong>`;
  const lista = A.previsoes.length ? `<div class="bloco"><h2>Todas as conclusões</h2>
    <p class="dica">Uma por ativo por mês e por origem (a primeira do mês), para a mesma ideia repetida não pesar várias vezes. ${A.total_registros} registros no total.</p>
    <div class="tabela-scroll"><table class="ac-lista"><thead><tr><th>Data</th><th>Origem</th><th>Ativo</th><th>Conclusão</th>${A.horizontes.map((h) => `<th>${AC_H[h]}</th>`).join("")}</tr></thead>
    <tbody>${A.previsoes.map((p) => `<tr><td>${dataBR(p.data)}</td><td>${esc(AC_ORIGENS[p.origem]?.nome || p.origem)}</td><td>${nomeAlvo(p)}</td>
      <td><span class="ac-prev ac-${p.previsao}">${esc(A.grupos[p.previsao] || p.previsao)}</span></td>
      ${A.horizontes.map((h) => `<td>${acCelula(p.resultado[h])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>` : "";
  $("#resultado-acertos").innerHTML = `
    <div class="bloco ac-intro">
      <p>Cada conclusão do site é conferida 3, 6 e 12 meses depois: ação contra o Ibovespa, proposta contra a carteira atual.</p>
      <p class="dica">A taxa de acerto sozinha engana. Compare com a <b>taxa base</b> (quantas de todas as ações bateram o Ibovespa) e olhe a
        <b>diferença entre os grupos</b>: se as "baratas" renderam mais que as "caras", o critério tem valor. Retornos do yfinance, com proventos.</p>
    </div>
    ${A.previsoes.length ? "" : '<p class="status">Nenhuma conclusão registrada ainda. Elas aparecem aqui quando você usa o "Cara ou barata?", o Research ou o agente de carteira.</p>'}
    ${Object.keys(AC_ORIGENS).map((id) => acBloco(id, A.resumo[id])).join("")}
    ${lista}`;
}

$("#acertos-rodar").addEventListener("click", rodarAcertos);
document.querySelector('[data-aba="acertos"]').addEventListener("click", () => { if (!ACERTOS) rodarAcertos(); });
if (location.hash === "#acertos") rodarAcertos();
