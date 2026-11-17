// Sub-aba "Estudos dos modelos" da aba Modelos: cada modelo usado no laboratório, explicado do jeito
// que está implementado (modelos.py e modelos.js), com o teste usado, como ler e onde o mercado usa.
// Campos: id, grupo, t, serve, intuicao, como (HTML), formula, teste, ler, limites, mercado, refs, aba (sub-aba)

const MOD_EST_GRUPOS = [
  ["regra", "A regra do laboratório"],
  ["carteira", "Carteira robusta"],
  ["vol", "Volatilidade"],
  ["mc", "Monte Carlo do DCF"],
  ["pares", "Pares e anomalias"],
];

const MOD_ESTUDOS = [
  // ---------------- regra ----------------
  { id: "fora-amostra", grupo: "regra", t: "Fora da amostra e referência simples",
    serve: "Saber se um modelo funciona de verdade, e não só no passado que ele já viu.",
    intuicao: "Qualquer modelo com parâmetros suficientes se ajusta bem ao passado. A pergunta que importa é: com o que se sabia NA ÉPOCA, ele teria acertado o que veio DEPOIS? E ganharia de uma alternativa simples?",
    como: `<p>Todo modelo do laboratório segue duas regras:</p>
      <ol><li><strong>Teste fora da amostra</strong>: os dados são divididos em "treino" (para estimar) e "teste" (para avaliar). O modelo nunca vê o teste enquanto é estimado.</li>
      <li><strong>Referência simples</strong>: cada modelo é comparado a um concorrente ingênuo (pesos iguais, volatilidade dos últimos 21 dias). Se não ganhar, a página mostra isso.</li></ol>`,
    ler: "Um modelo sofisticado que perde da referência simples fora da amostra está capturando ruído. É um resultado comum e útil: evita usar complexidade que não paga.",
    limites: "Um único período de teste pode ser sorte ou azar. Testar muitas variações e ficar com a melhor também gera excesso de ajuste (o teste vira treino).",
    mercado: "É a disciplina básica de gestoras quantitativas e de áreas de risco: nenhum modelo vai para produção sem backtest fora da amostra e comparação com um benchmark.",
    refs: ["Bailey, D.; Borwein, J.; López de Prado, M.; Zhu, Q. (2014). The Probability of Backtest Overfitting", "Harvey, C.; Liu, Y. (2015). Backtesting. Journal of Portfolio Management"] },

  // ---------------- carteira ----------------
  { id: "pesos-iguais", grupo: "carteira", aba: "carteira", t: "Pesos iguais (1/N): a referência",
    serve: "Ser a régua: a carteira mais simples possível, sem estimar nada.",
    intuicao: "Se você não sabe nada sobre os ativos, dividir igualmente é a escolha neutra. Como não estima retorno nem risco, não erra por causa de estimativas ruins.",
    como: `<p>Cada um dos N ativos recebe 1/N do dinheiro, rebalanceado a cada mês (21 dias úteis).</p>`,
    formula: "wᵢ = 1 ÷ N",
    teste: "Entra no mesmo backtest walk-forward dos outros métodos. O Sharpe dela é a linha de corte: a página marca quem ganha dela.",
    ler: "Se Markowitz clássico perde para 1/N, o ganho teórico da otimização foi comido pelo erro de estimação.",
    limites: "Ignora que alguns ativos são muito mais arriscados: uma cripto com 1/N pode dominar o risco da carteira.",
    mercado: "Usada como benchmark em pesquisa acadêmica e por gestoras para avaliar se a otimização agrega valor.",
    refs: ["DeMiguel, V.; Garlappi, L.; Uppal, R. (2009). Optimal Versus Naive Diversification: How Inefficient Is the 1/N Portfolio Strategy? Review of Financial Studies"] },

  { id: "markowitz-classico", grupo: "carteira", aba: "carteira", t: "Markowitz clássico (máximo Sharpe)",
    serve: "Encontrar a combinação com o maior retorno extra (acima do CDI) por unidade de risco.",
    intuicao: "Usa a média e a covariância do passado como se fossem o futuro, e otimiza. É o método do livro.",
    como: `<p>Com os últimos 252 dias de retorno: μ = média diária × 252, Σ = covariância amostral × 252. Depois maximiza o Sharpe com pesos entre 0 e o peso máximo, somando 100% (otimizador SLSQP do SciPy).</p>`,
    formula: "máx (wᵀμ − rf) ÷ √(wᵀΣw)   sujeito a Σwᵢ = 1, 0 ≤ wᵢ ≤ peso máx.",
    teste: "Walk-forward mensal e bootstrap dos pesos.",
    ler: "Costuma ter os pesos mais instáveis (faixas largas no bootstrap) e o maior giro: muda muito de um mês para o outro.",
    limites: "É um 'maximizador de erros' (Michaud): pequenos erros na média viram pesos extremos. A média histórica é a estimativa mais ruidosa de todas.",
    mercado: "Raramente usado puro. O mercado usa versões com premissas de retorno melhores (CMA, Black-Litterman) e muitas restrições.",
    refs: ["Markowitz, H. (1952). Portfolio Selection. Journal of Finance", "Michaud, R. (1989). The Markowitz Optimization Enigma: Is 'Optimized' Optimal? Financial Analysts Journal"] },

  { id: "ledoit-wolf-mod", grupo: "carteira", aba: "carteira", t: "Covariância de Ledoit-Wolf",
    serve: "Estimar o risco (a matriz de covariância) com menos ruído.",
    intuicao: "Com muitos ativos e poucos dias, a covariância amostral exagera relações que são acaso. Ledoit-Wolf 'encolhe' a matriz em direção a uma estrutura simples (variâncias na diagonal, correlação média fora dela), na intensidade que minimiza o erro esperado.",
    como: `<p>O site usa <code>sklearn.covariance.LedoitWolf</code>, que calcula a intensidade de encolhimento δ ótima a partir dos próprios dados. Aparece em dois métodos: "Markowitz + Ledoit-Wolf" (máximo Sharpe) e "Mínima variância + Ledoit-Wolf".</p>`,
    formula: "Σ̂ = δ·F + (1 − δ)·S   (S = amostral, F = alvo estruturado, δ entre 0 e 1)",
    teste: "Comparado com o Markowitz clássico no mesmo walk-forward: mesmo objetivo, só muda a covariância.",
    ler: "Se o Sharpe fora da amostra melhora e o giro cai em relação ao clássico, o encolhimento está tirando ruído.",
    limites: "Melhora o risco, mas não resolve o problema da média histórica no máximo Sharpe.",
    mercado: "Padrão em gestoras quantitativas e em sistemas de risco. Também é a opção recomendada no 'Montar minha carteira'.",
    refs: ["Ledoit, O.; Wolf, M. (2004). A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices. Journal of Multivariate Analysis", "Ledoit, O.; Wolf, M. (2004). Honey, I Shrunk the Sample Covariance Matrix. Journal of Portfolio Management"] },

  { id: "min-var-mod", grupo: "carteira", aba: "carteira", t: "Mínima variância",
    serve: "A carteira de menor oscilação possível, sem usar retorno esperado.",
    intuicao: "Se o retorno esperado é a parte mais difícil de estimar, ignore-o. Minimizar só o risco usa apenas a covariância, que é bem mais estável.",
    como: `<p>Minimiza wᵀΣw com Σ de Ledoit-Wolf, pesos entre 0 e o máximo, soma 100%.</p>`,
    formula: "mín wᵀΣw   sujeito a Σwᵢ = 1, 0 ≤ wᵢ ≤ peso máx.",
    teste: "Walk-forward mensal; costuma ter Sharpe fora da amostra competitivo e baixa volatilidade.",
    ler: "Tende a concentrar em ativos de baixa volatilidade e pouca correlação (FIIs, renda fixa, ouro). Use o peso máximo para não concentrar demais.",
    limites: "Não olha retorno: pode montar uma carteira segura mas de retorno baixo.",
    mercado: "Base de fundos e ETFs 'low volatility' / 'minimum variance' (ex.: índices MSCI Minimum Volatility).",
    refs: ["Clarke, R.; de Silva, H.; Thorley, S. (2006). Minimum-Variance Portfolios in the U.S. Equity Market. Journal of Portfolio Management"] },

  { id: "hrp-mod", grupo: "carteira", aba: "carteira", t: "HRP: Hierarchical Risk Parity",
    serve: "Diversificar o risco entre grupos de ativos parecidos, sem inverter a matriz de covariância.",
    intuicao: "Primeiro agrupa os ativos que andam juntos (como uma árvore genealógica). Depois divide o dinheiro de cima para baixo: entre dois grupos, quem tem menos risco recebe mais.",
    como: `<ol><li><strong>Distância</strong> entre ativos pela correlação: d = √((1 − ρ) ÷ 2).</li>
      <li><strong>Agrupamento hierárquico</strong> (ligação simples) e reordenação dos ativos pela árvore.</li>
      <li><strong>Bissecção recursiva</strong>: divide a lista ordenada ao meio; cada metade recebe peso inversamente proporcional à sua variância (calculada com pesos de variância inversa dentro dela); repete em cada metade.</li></ol>`,
    formula: "α = 1 − Var(A) ÷ (Var(A) + Var(B));  peso de A × α, peso de B × (1 − α)",
    teste: "Walk-forward mensal e bootstrap. Costuma ter pesos estáveis e giro baixo.",
    ler: "Pesos mais equilibrados que Markowitz; ativos muito voláteis recebem pouco.",
    limites: "Não usa retorno esperado. O resultado depende do método de agrupamento escolhido.",
    mercado: "Popularizado em gestão quantitativa a partir de 2016; usado em fundos multiestratégia e de paridade de risco.",
    refs: ["López de Prado, M. (2016). Building Diversified Portfolios that Outperform Out of Sample. Journal of Portfolio Management"] },

  { id: "walk-forward-mod", grupo: "carteira", aba: "carteira", t: "Backtest walk-forward",
    serve: "Simular como cada método teria se saído se você o seguisse mês a mês.",
    intuicao: "Volta no tempo, estima a carteira só com o passado daquele momento, segura por um mês, mede o resultado; anda um mês e repete.",
    como: `<p>Janela de estimação de 252 dias úteis (1 ano); rebalanceamento a cada 21 dias (1 mês). Os retornos de cada mês de teste são encadeados numa curva de R$ 100.</p>
      <p>Métricas: retorno anualizado, volatilidade, Sharpe (contra o CDI), pior queda (drawdown) e <strong>giro</strong> médio (quanto da carteira é trocado a cada rebalanceamento: Σ|w novo − w antigo| ÷ 2).</p>`,
    teste: "É o próprio teste.",
    ler: "Compare Sharpe e drawdown com a referência 1/N. Giro alto significa custo de corretagem e impostos que o backtest não desconta.",
    limites: "Não inclui custos de transação, impostos nem liquidez. Um único histórico: o futuro pode ser diferente.",
    mercado: "Padrão para avaliar estratégias. Gestoras descontam custos estimados e testam vários períodos e mercados.",
    refs: ["López de Prado, M. (2018). Advances in Financial Machine Learning, cap. 11–12 (Wiley)"] },

  { id: "bootstrap-mod", grupo: "carteira", aba: "carteira", t: "Bootstrap da estabilidade dos pesos",
    serve: "Medir o quanto os pesos mudariam se o histórico fosse um pouco diferente.",
    intuicao: "Os dados que temos são uma amostra entre muitas possíveis. Reamostrando os dias e reotimizando, vemos a faixa em que cada peso cai por puro acaso.",
    como: `<p>150 reamostragens: sorteia dias da janela com reposição (mesmo tamanho), reestima e reotimiza. Para cada ativo, mostra os percentis 5%, 50% e 95% do peso; a <strong>instabilidade</strong> é o desvio-padrão médio dos pesos.</p>`,
    ler: "Faixas estreitas = peso confiável. Faixas de 0% a 60% = o método está reagindo a ruído.",
    limites: "Sorteia dias de forma independente e desfaz agrupamentos de volatilidade; bootstrap em blocos preservaria essa estrutura.",
    mercado: "Base da 'otimização reamostrada' (Michaud), usada comercialmente em alocação.",
    refs: ["Efron, B. (1979). Bootstrap Methods: Another Look at the Jackknife. Annals of Statistics", "Michaud, R.; Michaud, R. (2008). Efficient Asset Management (Oxford)"] },

  // ---------------- volatilidade ----------------
  { id: "vol-hist", grupo: "vol", aba: "garch", t: "Volatilidade histórica de 21 dias: a referência",
    serve: "Prever a volatilidade de amanhã pela dos últimos 21 dias úteis (1 mês).",
    intuicao: "A volatilidade recente é uma boa pista da próxima. É simples e difícil de bater.",
    como: `<p>Variância dos retornos logarítmicos dos 21 dias anteriores, usada como previsão do dia seguinte.</p>`,
    formula: "σ²ₜ₊₁ = variância(rₜ₋₂₀ … rₜ)",
    ler: "Reage com atraso e de forma 'quadrada': um choque pesa igual por 21 dias e some de uma vez.",
    limites: "Todos os dias da janela pesam igual; não há tendência de voltar à média de longo prazo.",
    mercado: "A volatilidade histórica de 21 ou 63 dias aparece em todo terminal de mercado e serve de referência para a volatilidade implícita das opções.",
    refs: ["Hull, J. — Options, Futures, and Other Derivatives, cap. sobre volatilidade (Pearson)"] },

  { id: "garch-mod", grupo: "vol", aba: "garch", t: "GARCH(1,1)",
    serve: "Prever a volatilidade levando em conta que ela vem em ondas e volta para um nível médio.",
    intuicao: "Dias agitados vêm seguidos de dias agitados (agrupamento de volatilidade), mas a agitação passa. O GARCH mistura três coisas: um nível de longo prazo, o choque de ontem e a volatilidade de ontem.",
    como: `<p>Estimado por máxima verossimilhança com a biblioteca <code>arch</code> (média constante, distribuição normal), em retornos logarítmicos diários em %.</p>
      <ul><li><strong>α</strong>: quanto o choque de ontem pesa;</li><li><strong>β</strong>: quanto a volatilidade de ontem persiste;</li>
      <li><strong>persistência</strong> α + β: perto de 1 = choques demoram a passar;</li>
      <li><strong>meia-vida</strong> = ln(0,5) ÷ ln(α + β): em quantos dias metade do choque se dissipa;</li>
      <li><strong>volatilidade de longo prazo</strong> = √(ω ÷ (1 − α − β)), anualizada.</li></ul>`,
    formula: "σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁",
    teste: "Parâmetros estimados com os primeiros 75% dos dados; previsões de 1 dia à frente nos 25% finais, comparadas com a volatilidade de 21 dias pelas perdas MSE e QLIKE.",
    ler: "Se o GARCH vence no QLIKE, ele prevê melhor o risco do dia seguinte. A previsão de 21 dias mostra o caminho de volta ao nível de longo prazo.",
    limites: "Simétrico: quedas e altas do mesmo tamanho aumentam a volatilidade igualmente (na prática quedas pesam mais; modelos como GJR-GARCH capturam isso). Supõe distribuição normal.",
    mercado: "Usado em gestão de risco (VaR), precificação e controle de volatilidade de fundos. O RiskMetrics (J.P. Morgan) usa uma versão simplificada (EWMA, β = 0,94).",
    refs: ["Bollerslev, T. (1986). Generalized Autoregressive Conditional Heteroskedasticity. Journal of Econometrics", "Engle, R. (1982). Autoregressive Conditional Heteroscedasticity. Econometrica", "J.P. Morgan/Reuters (1996). RiskMetrics Technical Document"] },

  { id: "qlike", grupo: "vol", aba: "garch", t: "Como avaliar previsões de volatilidade: MSE e QLIKE",
    serve: "Decidir qual previsão de volatilidade foi melhor, sabendo que a volatilidade verdadeira não é observável.",
    intuicao: "Usamos o retorno ao quadrado do dia como 'gabarito'. Ele é muito ruidoso, então a régua precisa ser robusta a esse ruído.",
    como: `<ul><li><strong>MSE</strong>: média de (realizado − previsto)². Intuitivo, mas dominado por poucos dias extremos.</li>
      <li><strong>QLIKE</strong>: média de ln(previsto) + realizado ÷ previsto. Penaliza mais subestimar o risco e ordena os modelos corretamente mesmo com gabarito ruidoso.</li></ul>`,
    formula: "QLIKE = média[ ln(σ̂²) + r² ÷ σ̂² ]   (menor é melhor)",
    ler: "A página destaca o vencedor pelo QLIKE, que é a régua recomendada na literatura.",
    limites: "Avalia só a previsão de 1 dia. Um modelo pode ser melhor em horizontes mais longos.",
    mercado: "Usada em pesquisa e por áreas de risco para escolher modelos de volatilidade.",
    refs: ["Patton, A. (2011). Volatility Forecast Comparison Using Imperfect Volatility Proxies. Journal of Econometrics"] },

  // ---------------- monte carlo ----------------
  { id: "monte-carlo-mod", grupo: "mc", aba: null, t: "Monte Carlo do DCF",
    serve: "Trocar o 'valor justo' único por uma distribuição de valores, refletindo a incerteza das premissas.",
    intuicao: "Você não sabe o crescimento, a taxa de desconto e a perpetuidade exatos. Então sorteia milhares de combinações plausíveis e vê o que acontece com o valor da ação.",
    como: `<ol><li>Fica em Balanços → DCF, logo abaixo dos cenários, e usa as MESMAS premissas e o MESMO cálculo da tela: a média de cada premissa é o valor escolhido nos controles.</li>
      <li>Crescimento: desvio igual ao desvio do crescimento anual da receita da empresa nos últimos anos (CVM). Sem histórico suficiente, 3 pontos.</li>
      <li>Taxa de desconto: desvio tirado da faixa usual do prêmio de risco (4% a 6%, ±1 ponto) × β ajustado × peso das ações no WACC.</li>
      <li>g e taxa sorteados juntos (correlação 0,5), porque os dois carregam a inflação; r precisa ficar pelo menos 1 ponto acima de g.</li>
      <li>4.000 sorteios com semente fixa: mostra a faixa em que caem 80% dos valores, a mediana, a fração acima do preço e qual premissa mais move o resultado.</li></ol>`,
    teste: "Não é um modelo de previsão testável fora da amostra: é uma análise de sensibilidade. O cálculo é o mesmo do DCF, que é conferido por testes automáticos.",
    ler: "A fração acima do preço é a fração das suas premissas sorteadas em que o DCF supera o preço, não a chance de a ação subir. A premissa que mais move o resultado é a que mais merece estudo.",
    limites: "Só reflete a incerteza das três premissas sorteadas; o ponto de partida do fluxo de caixa e os desvios de taxa e g continuam sendo escolhas.",
    mercado: "Usado em project finance, valuation de empresas com muita incerteza e em comitês de investimento. Relatórios de análise costumam usar cenários (base, otimista, pessimista) com probabilidades, que é uma versão discreta da mesma ideia.",
    refs: ["Metropolis, N.; Ulam, S. (1949). The Monte Carlo Method. Journal of the American Statistical Association", "Damodaran, A. — Probabilistic Approaches: Scenario Analysis, Decision Trees and Simulations"] },

  // ---------------- pares ----------------
  { id: "padronizacao", grupo: "pares", aba: null, t: "Indicadores e padronização (z-score)",
    serve: "Colocar indicadores de escalas diferentes na mesma régua antes de comparar empresas.",
    intuicao: "Margem em %, giro em vezes e liquidez em vezes não são comparáveis diretamente. Padronizar mede cada um em 'desvios-padrão em relação à média de todas as empresas'.",
    como: `<p>Para todas as companhias que entregaram o mesmo ITR à CVM, calcula: margem bruta, margem EBIT, margem líquida, ROE, endividamento (passivo ÷ ativo), liquidez corrente e giro do ativo. Depois aplica <code>StandardScaler</code>: (valor − média) ÷ desvio-padrão.</p>`,
    formula: "z = (x − média) ÷ desvio-padrão",
    ler: "z = +2 numa margem significa margem muito acima da média do mercado.",
    limites: "Bancos e seguradoras têm outro plano de contas e distorcem as médias; valores extremos também.",
    mercado: "Base de 'screening' quantitativo e de modelos de fatores (qualidade, valor).",
    refs: ["Greenblatt, J. — The Little Book That Still Beats the Market (Wiley)"] },

  { id: "isolation-forest-mod", grupo: "pares", aba: null, t: "Isolation Forest: anomalias",
    serve: "Apontar empresas com combinação incomum de indicadores: pode ser algo real a investigar ou um erro de dado.",
    intuicao: "Se você corta os dados aleatoriamente, um ponto estranho fica isolado com poucos cortes; um ponto comum precisa de muitos. Quanto mais fácil de isolar, mais anômalo.",
    como: `<p><code>IsolationForest</code> do scikit-learn com 5% de contaminação esperada (as 5% mais isoladas são marcadas) e semente fixa, sobre os indicadores padronizados. A página mostra a pontuação de anomalia da empresa e quais indicadores mais a afastam da média.</p>`,
    ler: "Anomalia não é defeito: uma empresa excepcional também é anômala. Use como lista do que conferir.",
    limites: "A taxa de 5% é uma escolha; não diz se a anomalia é boa ou ruim.",
    mercado: "Usado em detecção de fraude, auditoria analítica e controle de qualidade de dados.",
    refs: ["Liu, F. T.; Ting, K. M.; Zhou, Z.-H. (2008). Isolation Forest. IEEE ICDM"] },

  { id: "identidades-mod", grupo: "pares", aba: null, t: "Identidades contábeis",
    serve: "Conferir se as contas do documento fecham entre si.",
    intuicao: "Algumas igualdades têm de valer sempre (Ativo = Passivo + PL; Lucro bruto = Receita + Custo…). Se não valem, há erro na entrega ou na leitura.",
    como: `<p>Seis regras sobre o balanço e a DRE do último ITR, com tolerância de 0,5% (+ R$ 1 mil de arredondamento): ativo = passivo; 3.03 = 3.01 + 3.02; 3.05 = 3.03 + 3.04; 3.07 = 3.05 + 3.06; 3.09 = 3.07 + 3.08; 3.11 = 3.09 + 3.10. O painel "Saúde dos dados" faz o mesmo para todas as empresas.</p>`,
    ler: "\"Não fecha\" numa empresa industrial merece atenção; em bancos é esperado (plano de contas diferente).",
    limites: "Confere só a aritmética, não se os números são verdadeiros.",
    mercado: "Primeiro passo de qualquer modelo de análise: analistas e auditores sempre 'amarram' as demonstrações antes de usar.",
    refs: ["CPC 26 — Apresentação das Demonstrações Contábeis"] },
];

// modelos usados em outras partes do site (com link para o artigo da aba Estudos)
const MOD_OUTROS = [
  ["Markowitz e fronteira eficiente", "markowitz", "Carteira eficiente"],
  ["Premissas de mercado (CMA)", "cma", "Carteira eficiente"],
  ["Black-Litterman", "black-litterman", "Carteira eficiente"],
  ["CAPM, beta e alfa de Jensen", "capm", "Carteira eficiente"],
  ["DCF, WACC e perpetuidade", "dcf", "Balanços → DCF"],
  ["Regressão de fatores", "regressao", "Sensibilidade"],
  ["Estacionariedade (ADF e KPSS)", "estacionariedade", "Sensibilidade"],
  ["Black-Scholes e gregas", "black-scholes", "Derivativos"],
  ["Duration e convexidade", "duration", "Renda fixa"],
  ["Análise vertical e horizontal", "analise-vertical-horizontal", "Balanços"],
];

function htmlEstudosModelos() {
  const card = (m) => `<details class="me-card" id="me-${m.id}">
    <summary><span class="me-t">${esc(m.t)}</span><span class="me-serve">${esc(m.serve)}</span></summary>
    <article class="me-corpo artigo">
      <p class="art-cat">${esc((MOD_EST_GRUPOS.find(([g]) => g === m.grupo) || [])[1] || "")}</p>
      <h2>${esc(m.t)}</h2>
      <p class="art-resumo">${esc(m.serve)}</p>
      <h3>O conceito</h3>
      <div class="art-corpo">${MOD_CONCEITOS[m.id] || `<p>${esc(m.intuicao)}</p>`}</div>
      <div class="art-caixa"><strong>Em uma frase</strong><p>${esc(m.intuicao)}</p></div>
      <h3>Como o site faz</h3><div class="art-corpo">${m.como}</div>
      ${m.formula ? `<div class="eq">${esc(m.formula)}</div>` : ""}
      ${m.teste ? `<h3>Como é testado</h3><p>${esc(m.teste)}</p>` : ""}
      <h3>Como ler o resultado</h3><p>${esc(m.ler)}</p>
      <div class="me-dupla">
        <div class="aviso-box"><strong>Limitações:</strong> ${esc(m.limites)}</div>
        <div class="art-caixa ok"><strong>No mercado</strong><p>${esc(m.mercado)}</p></div>
      </div>
      <div class="art-ref"><strong>Referências</strong><ul>${m.refs.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
      ${m.aba ? `<button type="button" class="secundario" data-ir-mod="${m.aba}">Abrir ${esc({ carteira: "Carteira robusta", garch: "Volatilidade (GARCH)" }[m.aba])} →</button>` : ""}
    </article></details>`;
  return `<div class="mod-estudos">
    <p class="dica formatos">Cada modelo do laboratório explicado como está implementado: a ideia, a conta, como é testado, como ler e onde o mercado usa. Clique para abrir.</p>
    <nav class="me-indice">${MOD_EST_GRUPOS.map(([g, n]) => `<a href="#me-g-${g}" data-me-ir="${g}">${n}</a>`).join("")}<a href="#me-g-outros" data-me-ir="outros">Outros modelos do site</a></nav>
    ${MOD_EST_GRUPOS.map(([g, n]) => `<section class="me-grupo" id="me-g-${g}"><h2>${n}</h2>${MOD_ESTUDOS.filter((m) => m.grupo === g).map(card).join("")}</section>`).join("")}
    <section class="me-grupo" id="me-g-outros"><h2>Outros modelos do site</h2>
      <p class="dica">Estão explicados na aba Estudos.</p>
      <div class="me-outros">${MOD_OUTROS.map(([n, id, onde]) => `<button type="button" class="mc-card" data-artigo-mod="${id}"><b>${esc(n)}</b><span class="sub-tk">${esc(onde)}</span></button>`).join("")}</div>
    </section>
  </div>`;
}

function ligarEstudosModelos() {
  document.querySelectorAll("[data-ir-mod]").forEach((b) => b.addEventListener("click", () =>
    document.querySelector(`[data-mod="${b.dataset.irMod}"]`).click()));
  document.querySelectorAll("[data-artigo-mod]").forEach((b) => b.addEventListener("click", () => {
    mostrarAba("estudos"); abrirEstudo(b.dataset.artigoMod);
  }));
  document.querySelectorAll("[data-me-ir]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById(`me-g-${a.dataset.meIr}`).scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

// ---------- "O conceito": a explicação em forma de artigo, antes dos detalhes de implementação ----------
const MOD_CONCEITOS = {
  "fora-amostra": `
    <p>Imagine um aluno que decora as respostas de uma prova antiga. Na mesma prova ele tira 10; numa prova nova, pode tirar 3. Modelos estatísticos têm o mesmo problema: com parâmetros suficientes, eles "decoram" o passado, inclusive o ruído, e parecem ótimos. Isso se chama <strong>sobreajuste</strong> (<em>overfitting</em>).</p>
    <p>A defesa é separar os dados em duas partes. Na <strong>amostra de treino</strong> o modelo aprende; na <strong>amostra de teste</strong>, que ele nunca viu, medimos o desempenho. Em finanças, a separação respeita o tempo: treina-se com o passado e testa-se no período seguinte, porque na vida real ninguém conhece o futuro.</p>
    <p>A segunda defesa é ter uma <strong>régua simples</strong>. Um modelo só merece a complexidade extra se ganhar, fora da amostra, de uma alternativa ingênua. Surpreendentemente, em finanças isso falha com frequência: o sinal útil nos preços é pequeno perto do ruído.</p>`,
  "pesos-iguais": `
    <p>Toda otimização de carteira depende de estimativas: quanto cada ativo vai render, quanto oscila, como se move em relação aos outros. Cada estimativa tem erro. A carteira de <strong>pesos iguais</strong> não estima nada, e por isso não sofre com esses erros.</p>
    <p>Em 2009, DeMiguel, Garlappi e Uppal compararam 14 métodos de otimização com a regra 1/N em vários conjuntos de dados. Nenhum ganhou de forma consistente fora da amostra. A explicação: o ganho teórico de otimizar é menor do que a perda causada pelo erro de estimação, a menos que se tenha um histórico muito longo ou estimativas muito boas.</p>
    <p>Por isso a 1/N é a régua natural: se um método sofisticado não supera "dividir igualmente", ele não está agregando informação.</p>`,
  "markowitz-classico": `
    <p>Harry Markowitz mostrou em 1952 que o risco de uma carteira não é a média dos riscos dos ativos: depende de como eles se movem juntos (a <strong>covariância</strong>). Dois ativos arriscados que se compensam formam uma carteira menos arriscada que cada um. Essa é a matemática da diversificação, e rendeu a ele o Nobel.</p>
    <p>Com o retorno esperado e a covariância de cada ativo, dá para calcular, para cada nível de risco, a carteira com o maior retorno: a <strong>fronteira eficiente</strong>. Somando a renda fixa, a melhor carteira de risco é a que maximiza o <strong>índice de Sharpe</strong> (retorno acima do CDI por unidade de risco).</p>
    <p>O problema prático é a entrada. Usar a média do passado como retorno esperado é a estimativa mais ruidosa possível, e o otimizador aposta pesado justamente nos ativos cuja média saiu alta por acaso. Richard Michaud chamou isso de "maximizador de erros". As versões a seguir atacam esse problema por partes.</p>`,
  "ledoit-wolf-mod": `
    <p>A <strong>matriz de covariância</strong> guarda a variância de cada ativo e a covariância de cada par. Com 10 ativos são 55 números a estimar; com 50 ativos, 1.275. Com um ou dois anos de dados, muitos desses números são essencialmente ruído: correlações que apareceram por acaso.</p>
    <p>O <strong>encolhimento</strong> (<em>shrinkage</em>) é uma ideia estatística geral: quando uma estimativa é muito ruidosa, puxá-la em direção a um valor mais simples e estável reduz o erro total, mesmo introduzindo um pequeno viés. É a troca entre viés e variância.</p>
    <p>Olivier Ledoit e Michael Wolf mostraram como fazer isso com a covariância de forma ótima: misturar a matriz amostral com uma matriz estruturada, numa proporção calculada pelos próprios dados. Quanto mais ruidosa a amostra, mais peso vai para a estrutura simples. O resultado é uma matriz mais estável, que gera pesos menos extremos.</p>`,
  "min-var-mod": `
    <p>Se estimar retorno é tão difícil, por que não ignorá-lo? A carteira de <strong>mínima variância</strong> é o ponto mais à esquerda da fronteira eficiente: a combinação que menos oscila, considerando só a covariância entre os ativos.</p>
    <p>Há um motivo empírico para ela funcionar bem: a chamada <strong>anomalia de baixa volatilidade</strong>. Em muitos mercados e períodos, ações menos voláteis tiveram retorno ajustado ao risco maior do que a teoria previa. Uma explicação comum é que investidores com restrição de alavancagem compram ativos arriscados para buscar retorno, encarecendo-os.</p>
    <p>A contrapartida é a concentração: sem limites, a mínima variância tende a ficar só com poucos ativos muito estáveis. Por isso o peso máximo por ativo é importante nela.</p>`,
  "hrp-mod": `
    <p>Os métodos de Markowitz precisam <strong>inverter</strong> a matriz de covariância. Quando os ativos são muito correlacionados, essa inversão é instável: pequenas mudanças nos dados viram grandes mudanças nos pesos. Marcos López de Prado propôs evitar a inversão.</p>
    <p>A ideia do <strong>HRP</strong> vem do aprendizado de máquina: primeiro, organizar os ativos numa <strong>árvore</strong> por semelhança (quem anda junto fica no mesmo galho), como numa árvore genealógica. Ações de bancos ficam juntas, FIIs ficam juntos, e assim por diante.</p>
    <p>Depois, o dinheiro desce pela árvore. Em cada bifurcação, o galho menos arriscado recebe mais, na proporção inversa do risco. Isso é <strong>paridade de risco</strong>: em vez de dividir o dinheiro igualmente, divide-se o risco. O resultado costuma ser mais diversificado e mais estável que Markowitz, sem usar retorno esperado.</p>`,
  "walk-forward-mod": `
    <p>Um <strong>backtest</strong> simula como uma estratégia teria se saído no passado. O erro mais comum é o <strong>viés de antecipação</strong> (<em>look-ahead bias</em>): usar, sem perceber, informação que não existia na data da decisão, como estimar a carteira com o histórico inteiro e testá-la nesse mesmo histórico.</p>
    <p>O <strong>walk-forward</strong> evita isso andando no tempo. Em cada data de decisão, o método vê só o passado (aqui, o último ano), escolhe os pesos, e esses pesos ficam valendo pelo próximo mês. Depois a janela anda um mês e tudo se repete. A curva final é a concatenação de vários meses que o método nunca tinha visto.</p>
    <p>Duas métricas merecem atenção além do retorno: a <strong>pior queda</strong> (o que você teria de aguentar) e o <strong>giro</strong> (quanto você teria de comprar e vender por mês, e portanto quanto pagaria de custos e impostos).</p>`,
  "bootstrap-mod": `
    <p>O histórico que temos é uma das muitas histórias que poderiam ter acontecido. Se fosse ligeiramente diferente, os pesos ótimos mudariam? O <strong>bootstrap</strong>, criado por Bradley Efron em 1979, responde isso sem precisar de fórmulas: usa a própria amostra para simular outras amostras.</p>
    <p>A técnica é sortear, com reposição, dias do histórico até formar uma nova amostra do mesmo tamanho. Alguns dias aparecem duas vezes, outros nenhuma. Repetindo isso centenas de vezes e reotimizando em cada uma, obtemos a <strong>distribuição</strong> dos pesos.</p>
    <p>Se o peso de um ativo fica entre 18% e 22% em quase todas as reamostragens, ele é robusto. Se vai de 0% a 60%, a otimização está escolhendo esse ativo por acaso. É a melhor forma de enxergar o erro de estimação que a fronteira eficiente esconde.</p>`,
  "vol-hist": `
    <p><strong>Volatilidade</strong> é o desvio-padrão dos retornos: mede o tamanho típico das oscilações, para cima ou para baixo. Ela não é constante: há meses calmos e meses turbulentos.</p>
    <p>A forma mais simples de estimar a volatilidade de amanhã é olhar a de ontem: o desvio-padrão dos últimos 21 dias úteis (um mês). Funciona porque a volatilidade é <strong>persistente</strong>: um período agitado tende a continuar agitado por um tempo.</p>
    <p>A limitação é a janela fixa. Um choque forte pesa o mesmo durante 21 dias e, no 22º, desaparece de uma vez, criando degraus artificiais na estimativa. É isso que modelos como o GARCH tentam melhorar.</p>`,
  "garch-mod": `
    <p>Olhando um gráfico de retornos diários, salta aos olhos o <strong>agrupamento de volatilidade</strong>: dias de grandes movimentos vêm em sequência, e dias calmos também. Robert Engle formalizou isso em 1982 (o modelo ARCH, que lhe deu o Nobel) e Tim Bollerslev generalizou em 1986 (GARCH).</p>
    <p>O GARCH(1,1) diz que a variância de hoje é uma média ponderada de três coisas: um <strong>nível de longo prazo</strong>, a <strong>surpresa de ontem</strong> (o retorno ao quadrado) e a <strong>variância de ontem</strong>. Depois de um choque, a volatilidade sobe; com o tempo, volta ao nível de longo prazo, num ritmo dado pela persistência α + β.</p>
    <p>Isso permite responder perguntas úteis: qual a volatilidade esperada para amanhã, em quantos dias metade do choque atual terá passado (a meia-vida) e qual o nível "normal" de volatilidade desse ativo.</p>`,
  "qlike": `
    <p>Para avaliar uma previsão, comparamos com o que aconteceu. Mas a volatilidade não é observável: só vemos o retorno de cada dia. O retorno ao quadrado é uma medida não viesada da variância do dia, porém extremamente ruidosa. Um dia calmo pode ter um retorno grande por acaso.</p>
    <p>Andrew Patton mostrou em 2011 que, com um gabarito ruidoso assim, algumas réguas de erro podem escolher o modelo errado. O <strong>erro quadrático médio (MSE)</strong> é dominado por poucos dias extremos. A perda <strong>QLIKE</strong> (de quase-verossimilhança) é robusta: na média, escolhe o modelo certo mesmo com o ruído.</p>
    <p>A QLIKE também pune mais subestimar o risco do que superestimá-lo, o que faz sentido para quem gerencia risco: ser pego de surpresa por uma volatilidade maior custa mais caro.</p>`,
  "monte-carlo-mod": `
    <p>O método de <strong>Monte Carlo</strong> nasceu nos anos 1940, em Los Alamos, quando Stanislaw Ulam e John von Neumann usaram sorteios para resolver problemas difíceis demais para fórmulas. O nome é uma homenagem ao cassino.</p>
    <p>A ideia é simples: quando o resultado depende de várias entradas incertas, em vez de escolher um valor para cada uma, sorteia-se cada entrada de uma distribuição plausível, calcula-se o resultado, e repete-se milhares de vezes. O conjunto de resultados forma uma <strong>distribuição</strong>, que mostra não só o valor central mas a faixa de possibilidades.</p>
    <p>No valuation, isso muda a pergunta de "quanto vale a ação?" para "qual a chance de ela valer mais que o preço, dadas as minhas incertezas?". E a correlação de cada premissa com o resultado mostra onde concentrar o estudo.</p>`,
  "padronizacao": `
    <p>Para comparar empresas por vários indicadores ao mesmo tempo, eles precisam estar na mesma escala. Uma margem de 20% e um giro do ativo de 0,8 vezes não são comparáveis; somar ou medir distâncias entre eles daria peso desproporcional a quem tem números maiores.</p>
    <p>A <strong>padronização</strong> (z-score) mede cada valor em desvios-padrão em relação à média de todas as empresas. z = 0 é exatamente a média; z = +1, um desvio acima; z = −2, bem abaixo. Depois disso, todos os indicadores pesam igual e podem ser combinados.</p>
    <p>É o passo inicial de quase toda análise quantitativa de empresas: screening, modelos de fatores, agrupamento e detecção de anomalias.</p>`,
  "isolation-forest-mod": `
    <p>Detectar <strong>anomalias</strong> é achar os pontos que não se parecem com o resto. A maioria dos métodos tenta descrever o "normal" e mede a distância até ele. O Isolation Forest, de 2008, inverte a lógica: tenta isolar cada ponto.</p>
    <p>Ele constrói muitas árvores aleatórias: em cada nó, escolhe um indicador ao acaso e um valor de corte ao acaso. Um ponto comum, cercado de outros parecidos, precisa de muitos cortes até ficar sozinho. Um ponto estranho fica isolado em poucos cortes. A média de cortes necessários, em muitas árvores, é a <strong>pontuação de anomalia</strong>.</p>
    <p>É rápido, funciona bem com muitos indicadores e não exige definir o que é "normal". Em análise de empresas, sinaliza tanto oportunidades (uma empresa excepcional) quanto problemas (um dado errado ou uma situação atípica).</p>`,
  "identidades-mod": `
    <p>As demonstrações financeiras são feitas por <strong>partidas dobradas</strong>: todo valor que entra num lugar sai de outro. Por isso algumas igualdades têm de valer sempre: o ativo é igual ao passivo mais o patrimônio líquido, e cada linha da DRE é a soma das anteriores.</p>
    <p>Conferir essas <strong>identidades</strong> é a forma mais barata de pegar erros: na entrega da empresa, no arquivo da CVM ou na leitura feita pelo site. Se a DRE não fecha, qualquer indicador calculado sobre ela está comprometido.</p>
    <p>Analistas chamam isso de "amarrar" as demonstrações, e é o primeiro passo antes de montar qualquer modelo.</p>`,
};
