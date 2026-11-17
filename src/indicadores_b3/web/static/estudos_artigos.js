// Conteúdo da aba "Estudos": um artigo para cada conceito usado no site.
// Campos: id, cat (categoria), t (título), r (resumo de uma linha), f (fórmula), c (texto, HTML),
// ex (exemplo numérico), cu (cuidados), aba (onde aparece no site), ver (artigos relacionados),
// ref (referências: leis, órgãos oficiais e artigos acadêmicos originais).

const ESTUDOS_CATS = [
  "Comece por aqui", "Demonstrações financeiras", "Indicadores", "Valuation", "Risco e retorno",
  "Carteiras", "Impostos", "Renda fixa", "Derivativos", "Estatística", "Machine learning", "Fontes de dados",
];

const ESTUDOS = [
  // ===================== Comece por aqui =====================
  { id: "como-ler", cat: "Comece por aqui", t: "Como usar este site para estudar",
    r: "Cada número tem fonte, fórmula e campos usados. Use isso para aprender fazendo.",
    c: `<p>O site foi feito para você <strong>conferir</strong> cada número. Nos cards de indicadores, clique em "Ver campos usados" para abrir a conta, as linhas exatas dos relatórios da CVM e o link do arquivo original.</p>
      <p>Uma boa ordem de estudo: (1) demonstrações financeiras, (2) indicadores, (3) valuation por DCF, (4) risco e retorno, (5) carteiras, (6) renda fixa, (7) derivativos, (8) estatística e modelos.</p>
      <p>Em cada artigo, o quadro "Onde aparece no site" leva direto à aba em que o conceito é calculado com dados reais.</p>`,
    cu: "Os cálculos são uma ferramenta de estudo, não recomendação de investimento. Dados de fontes abertas podem atrasar ou ter erros; por isso o site mostra a fonte.",
    ver: ["fontes-cvm", "dre", "pl"] },

  { id: "retorno-simples-log", cat: "Comece por aqui", t: "Retorno simples, acumulado e anualizado",
    r: "Como medir quanto um investimento rendeu e comparar prazos diferentes.",
    f: "Retorno = Pfinal ÷ Pinicial − 1 · Anualizado = (1 + R)^(1/anos) − 1",
    c: `<p>O <strong>retorno simples</strong> de um período é a variação percentual do preço (somando proventos, se houver). Retornos se <strong>compõem</strong>: dois meses de +10% dão +21%, não +20%.</p>
      <p>Para comparar prazos diferentes, use o retorno <strong>anualizado</strong>. No site, a média dos retornos diários é multiplicada por 252 (dias úteis no ano) para chegar a um retorno anual aproximado.</p>`,
    ex: "Um título comprado por R$ 800 e vendido por R$ 1.000 depois de 2 anos rendeu 25% no período, ou (1,25)^(1/2) − 1 = 11,8% ao ano.",
    cu: "Média aritmética anualizada (média × 252) é maior que o retorno composto realizado quando há volatilidade. Para resultados realizados, prefira o retorno composto.",
    aba: "comparar", ver: ["volatilidade", "retorno-real"] },

  { id: "retorno-real", cat: "Comece por aqui", t: "Retorno real e base 100",
    r: "Descontar a inflação mostra quanto seu poder de compra realmente cresceu.",
    f: "Retorno real = (1 + retorno nominal) ÷ (1 + inflação) − 1",
    c: `<p>O retorno <strong>nominal</strong> é o que aparece no extrato. O <strong>real</strong> desconta a inflação (no site, o IPCA do Banco Central). Se um ativo rendeu 10% e a inflação foi 5%, você ficou (1,10 ÷ 1,05) − 1 = 4,8% mais rico, e não 5%.</p>
      <p>A <strong>base 100</strong> põe todas as séries começando em 100 na mesma data. Assim dá para comparar uma ação de R$ 30 com o dólar a R$ 5 e o Ibovespa a 120 mil pontos no mesmo gráfico.</p>`,
    ex: "Ação de 100 para 130 em base 100 (+30%), com IPCA acumulado de 12%: retorno real de 1,30 ÷ 1,12 − 1 = 16,1%.",
    aba: "comparar", ver: ["retorno-simples-log", "fontes-bcb"] },

  // ===================== Demonstrações =====================
  { id: "dre", cat: "Demonstrações financeiras", t: "DRE: Demonstração do Resultado",
    r: "Mostra como a receita vira lucro, descontando custos, despesas, juros e impostos.",
    c: `<p>A DRE vai de cima para baixo: <strong>receita líquida</strong> − custo dos produtos = <strong>lucro bruto</strong>; − despesas operacionais (vendas, administrativas) = <strong>resultado operacional (EBIT)</strong>; ± resultado financeiro (juros) = lucro antes dos impostos; − IR e CSLL = <strong>lucro líquido</strong>.</p>
      <p>O lucro líquido se divide entre os <strong>controladores</strong> (acionistas da empresa) e os <strong>não controladores</strong> (sócios minoritários das controladas). Os indicadores por ação usam a parte dos controladores.</p>
      <p>Na CVM, a DRE consolidada tem o código de conta 3.xx (ex.: 3.01 Receita, 3.11 Lucro do período).</p>`,
    cu: "Itens não recorrentes (venda de um ativo, multa) distorcem o lucro de um trimestre. Olhe vários períodos e as notas explicativas.",
    aba: "dem", ver: ["balanco", "ebitda", "ttm"], ref: ["Lei 6.404/1976 (Lei das S.A.), art. 187", "CPC 26 — Apresentação das Demonstrações Contábeis"] },

  { id: "balanco", cat: "Demonstrações financeiras", t: "Balanço patrimonial",
    r: "Uma foto do que a empresa tem (ativos), deve (passivos) e o que é dos sócios (patrimônio).",
    f: "Ativo = Passivo + Patrimônio líquido",
    c: `<p>O <strong>ativo</strong> (contas 1.xx na CVM) é o que a empresa controla: caixa, contas a receber, estoques, imobilizado. O <strong>passivo</strong> (2.01 e 2.02) são as obrigações: fornecedores, empréstimos, impostos. O <strong>patrimônio líquido</strong> (2.03) é o que sobra para os sócios.</p>
      <p>"Circulante" quer dizer que vence ou vira caixa em até 12 meses; "não circulante", depois disso.</p>`,
    cu: "O balanço é uma data só (fim do trimestre). Compare com o mesmo trimestre do ano anterior para evitar sazonalidade.",
    aba: "dem", ver: ["dre", "divida-liquida", "vpa"], ref: ["Lei 6.404/1976, art. 178", "CPC 26"] },

  { id: "dfc", cat: "Demonstrações financeiras", t: "DFC: Fluxo de caixa",
    r: "Mostra o dinheiro que realmente entrou e saiu, separado em operação, investimento e financiamento.",
    c: `<p>Lucro não é caixa: uma venda a prazo entra na DRE, mas o dinheiro só chega depois. A DFC (contas 6.xx) separa:</p>
      <ul><li><strong>Operacional</strong> (6.01): caixa gerado pelo negócio;</li><li><strong>Investimento</strong> (6.02): compra de máquinas, aquisições (o capex);</li><li><strong>Financiamento</strong> (6.03): empréstimos, amortizações, dividendos.</li></ul>
      <p>O <strong>fluxo de caixa livre</strong> usado no DCF do site é, de forma simplificada, caixa operacional − capex.</p>`,
    aba: "dcf", ver: ["dcf", "dre"], ref: ["CPC 03 — Demonstração dos Fluxos de Caixa"] },

  { id: "ttm", cat: "Demonstrações financeiras", t: "Últimos 12 meses (TTM) e ITR/DFP",
    r: "Por que somamos quatro trimestres para os indicadores.",
    f: "TTM = DFP do último ano + ITR acumulado deste ano − ITR acumulado do ano anterior",
    c: `<p>A CVM publica o <strong>ITR</strong> (trimestral, acumulado no ano) e a <strong>DFP</strong> (anual). Para um P/L atualizado, o site soma os <strong>últimos 12 meses</strong> (TTM, <em>trailing twelve months</em>) das contas de resultado (DRE, DFC).</p>
      <p>Contas de balanço não são somadas: usa-se o saldo da data mais recente.</p>`,
    ex: "Lucro TTM em set/2026 = lucro de 2025 (DFP) + jan–set/2026 (ITR) − jan–set/2025 (ITR).",
    aba: "indicadores", ver: ["dre", "pl"], ref: ["CVM — Portal de Dados Abertos (ITR, DFP)"] },

  { id: "analise-vertical-horizontal", cat: "Demonstrações financeiras", t: "Análise vertical e horizontal",
    r: "Duas leituras clássicas das demonstrações: a estrutura (vertical) e a evolução (horizontal).",
    f: "Vertical = conta ÷ base do mesmo período · Horizontal = conta ÷ mesma conta no período anterior − 1",
    c: `<p><strong>Análise vertical (AV)</strong>: divide cada linha por uma base do <em>mesmo</em> período. Na DRE, a base é a receita líquida (assim o lucro bruto vira a margem bruta); no balanço, o ativo total (assim se vê quanto do ativo é estoque, caixa ou imobilizado, e quanto do financiamento vem de dívida ou dos sócios). Serve para entender a estrutura e comparar empresas de tamanhos diferentes.</p>
      <p><strong>Análise horizontal (AH)</strong>: compara a mesma linha entre períodos. Mostra o que cresceu mais rápido: se as despesas crescem acima da receita, a margem está sendo comprimida. Pode ser a variação de um período para o outro ou um índice <strong>base 100</strong> a partir do primeiro período.</p>
      <p>As duas se completam: a horizontal diz <em>o que</em> mudou; a vertical diz <em>quanto aquilo pesa</em>. Uma conta que dobrou (AH +100%) mas representa 0,5% da receita (AV) importa pouco.</p>`,
    ex: "Receita de R$ 38,0 bi para R$ 40,8 bi (AH +7,4%) e custo de R$ 25,2 bi para R$ 27,1 bi (AH +7,7%): o custo cresceu um pouco mais que a receita, e a margem bruta (AV) caiu de 33,7% para 33,5%.",
    cu: "Compare períodos equivalentes: trimestres ou acumulados do ano contra o mesmo intervalo do ano anterior, por causa da sazonalidade. Quando a conta muda de sinal (lucro vira prejuízo), a variação % não tem significado.",
    aba: "dem", ver: ["dre", "balanco", "margem"], ref: ["Assaf Neto, A. — Estrutura e Análise de Balanços (Atlas)", "Iudícibus, S. — Análise de Balanços (Atlas)"] },

  { id: "ebitda", cat: "Demonstrações financeiras", t: "EBITDA",
    r: "Lucro operacional antes de depreciação e amortização: uma aproximação da geração de caixa do negócio.",
    f: "EBITDA = EBIT (resultado antes do resultado financeiro e tributos) + Depreciação e amortização",
    c: `<p>O EBITDA (LAJIDA em português) tira da conta os juros, os impostos e as despesas que não saem do caixa (depreciação e amortização). Serve para comparar a operação de empresas com dívidas e ativos diferentes.</p>
      <p>No site, a depreciação vem da DVA (conta 7.04.01), porque a DRE não a mostra separada.</p>`,
    cu: "EBITDA não é caixa: ignora capex, capital de giro e impostos. Empresas que investem muito podem ter EBITDA alto e caixa livre baixo.",
    aba: "dem", ver: ["divida-ebitda", "dre"], ref: ["Resolução CVM 156/2022 (divulgação de EBITDA)"] },

  // ===================== Indicadores =====================
  { id: "lpa", cat: "Indicadores", t: "LPA: lucro por ação",
    r: "Quanto do lucro dos últimos 12 meses cabe a cada ação.",
    f: "LPA = Lucro líquido dos controladores (12m) ÷ Ações em circulação",
    c: `<p>Divide o lucro pelo número de ações em circulação (sem as ações em tesouraria). É a base do P/L.</p>`,
    ex: "Lucro de R$ 6,2 bilhões e 12,9 bilhões de ações: LPA = R$ 0,48.",
    aba: "indicadores", ver: ["pl", "ttm"] },

  { id: "vpa", cat: "Indicadores", t: "VPA: valor patrimonial por ação",
    r: "O patrimônio líquido contábil dividido pelas ações.",
    f: "VPA = Patrimônio líquido dos controladores ÷ Ações em circulação",
    c: `<p>Mostra quanto "vale no papel" cada ação, pela contabilidade. Em FIIs, o equivalente é o valor patrimonial da cota, informado no informe mensal da CVM.</p>`,
    cu: "Ativos são registrados pelo custo histórico ou por avaliações contábeis, que podem diferir muito do valor de mercado.",
    aba: "indicadores", ver: ["pvp", "balanco"] },

  { id: "pl", cat: "Indicadores", t: "P/L: preço sobre lucro",
    r: "Quantos anos de lucro atual você paga pela ação.",
    f: "P/L = Preço ÷ LPA",
    c: `<p>Um P/L de 10 significa que, se o lucro ficar igual, levaria 10 anos de lucro para "pagar" o preço. O inverso (L/P) é o <em>earnings yield</em>, útil para comparar com juros.</p>
      <p>P/L baixo pode ser barganha ou sinal de que o mercado espera queda do lucro. P/L alto pode refletir crescimento esperado.</p>`,
    cu: "Não faz sentido com lucro negativo. Compare empresas do mesmo setor e olhe o histórico.",
    aba: "indicadores", ver: ["lpa", "dcf"] },

  { id: "pvp", cat: "Indicadores", t: "P/VP: preço sobre valor patrimonial",
    r: "Quanto o mercado paga por real de patrimônio contábil.",
    f: "P/VP = Preço ÷ VPA",
    c: `<p>P/VP abaixo de 1 indica que a ação negocia abaixo do patrimônio contábil. É muito usado em bancos e em FIIs, cujo patrimônio é mais próximo do valor de mercado (imóveis reavaliados, carteiras de crédito).</p>`,
    cu: "Empresas de tecnologia ou serviços têm poucos ativos contábeis e P/VP naturalmente alto.",
    aba: "indicadores", ver: ["vpa", "roe"] },

  { id: "dy", cat: "Indicadores", t: "Dividend yield",
    r: "Quanto a ação ou cota pagou em proventos nos últimos 12 meses, sobre o preço.",
    f: "DY = Proventos por ação (12m) ÷ Preço × 100",
    c: `<p>Mede o "aluguel" do investimento. Em ações, inclui dividendos e JCP; em FIIs, os rendimentos mensais.</p>
      <p>No site, os proventos vêm do yfinance pela data-ex. Para FIIs, há também o DY patrimonial do informe mensal da CVM (rendimento ÷ valor patrimonial).</p>`,
    cu: "DY alto pode vir de um provento extraordinário ou de uma queda forte no preço. Veja se o pagamento é recorrente.",
    aba: "indicadores", ver: ["impostos-acoes", "pvp"] },

  { id: "roe", cat: "Indicadores", t: "ROE: retorno sobre o patrimônio",
    r: "Quanto de lucro a empresa gera para cada real do patrimônio dos sócios.",
    f: "ROE = Lucro líquido dos controladores (12m) ÷ Patrimônio líquido dos controladores",
    c: `<p>Mede a eficiência em gerar lucro com o capital próprio. Um ROE acima do custo de capital (por exemplo, a taxa de desconto do DCF) indica que a empresa cria valor.</p>`,
    cu: "Dívida alta aumenta o ROE (menos patrimônio). Olhe junto com a alavancagem.",
    aba: "indicadores", ver: ["margem", "divida-ebitda"] },

  { id: "margem", cat: "Indicadores", t: "Margem líquida",
    r: "Quanto de cada real de receita vira lucro.",
    f: "Margem líquida = Lucro líquido (12m) ÷ Receita líquida (12m)",
    c: `<p>Compara a lucratividade de empresas do mesmo setor. Varejo costuma ter margens baixas; software e bolsas, margens altas.</p>`,
    aba: "indicadores", ver: ["dre", "roe"] },

  { id: "divida-liquida", cat: "Indicadores", t: "Dívida líquida",
    r: "Empréstimos e financiamentos menos o caixa.",
    f: "Dívida líquida = Empréstimos e financiamentos (curto + longo prazo) − Caixa e aplicações",
    c: `<p>Se negativa, a empresa tem mais caixa do que dívida ("caixa líquido"). No DCF, a dívida líquida é subtraída do valor da empresa para chegar ao valor do acionista.</p>`,
    aba: "indicadores", ver: ["divida-ebitda", "dcf"] },

  { id: "divida-ebitda", cat: "Indicadores", t: "Dívida líquida / EBITDA",
    r: "Quantos anos de EBITDA seriam necessários para pagar a dívida líquida.",
    f: "Dívida líquida ÷ EBITDA (12m)",
    c: `<p>Indicador clássico de alavancagem, usado inclusive em cláusulas de contratos de dívida (<em>covenants</em>). Acima de 3x costuma acender um alerta, mas depende do setor: empresas de energia, com receita previsível, aguentam mais.</p>`,
    aba: "indicadores", ver: ["ebitda", "divida-liquida"] },

  // ===================== Valuation =====================
  { id: "dcf", cat: "Valuation", t: "DCF: fluxo de caixa descontado",
    r: "O valor de uma empresa é o valor presente do caixa que ela vai gerar no futuro.",
    f: "Valor = Σ FCLₜ ÷ (1 + r)ᵗ + Valor terminal ÷ (1 + r)ᴺ",
    c: `<p>Passos: (1) partir do fluxo de caixa livre (FCL) atual; (2) projetar o FCL por N anos com uma taxa de crescimento; (3) estimar o <strong>valor terminal</strong> (o que vem depois de N, pela perpetuidade); (4) trazer tudo a valor presente com a taxa de desconto <strong>r</strong>; (5) subtrair a dívida líquida e dividir pelo número de ações.</p>
      <p>Dinheiro no futuro vale menos que hoje, porque você poderia aplicá-lo e porque há risco. A taxa r reflete esse custo de oportunidade e o risco.</p>`,
    ex: "FCL de R$ 100 no ano 1 com r = 12%: vale hoje 100 ÷ 1,12 = R$ 89,29.",
    cu: "O resultado é extremamente sensível a r e g. Use a tabela de sensibilidade da aba para ver a faixa de valores, e não um número só.",
    aba: "dcf", ver: ["perpetuidade", "taxa-desconto", "monte-carlo"], ref: ["Damodaran, A. — Investment Valuation (Wiley)"] },

  { id: "perpetuidade", cat: "Valuation", t: "Perpetuidade e modelo de Gordon",
    r: "Como calcular o valor de um fluxo que cresce a uma taxa constante para sempre.",
    f: "Valor terminal = FCLₙ × (1 + g) ÷ (r − g)",
    c: `<p>Depois do período projetado, supõe-se que o caixa cresça a uma taxa <strong>g</strong> constante para sempre. A soma infinita de uma série que cresce a g e é descontada a r tem esta fórmula fechada, desde que <strong>r &gt; g</strong>.</p>
      <p>g costuma ficar perto da inflação ou do crescimento de longo prazo da economia. Em muitos DCFs, o valor terminal é mais da metade do valor total.</p>`,
    ex: "FCL de R$ 100, g = 4%, r = 12%: 100 × 1,04 ÷ 0,08 = R$ 1.300.",
    cu: "Se g se aproxima de r, o valor explode. Por isso o site exige r > g.",
    aba: "dcf", ver: ["dcf"], ref: ["Gordon, M. J. (1959). Dividends, Earnings, and Stock Prices. Review of Economics and Statistics"] },

  { id: "taxa-desconto", cat: "Valuation", t: "Taxa de desconto (custo de capital)",
    r: "O retorno mínimo exigido para compensar o tempo e o risco.",
    f: "Custo do capital próprio (CAPM) = rf + β × prêmio de mercado",
    c: `<p>Na prática, a taxa de desconto vem do custo de capital: o retorno exigido pelos acionistas (pelo CAPM, por exemplo) combinado com o custo da dívida (WACC). No DCF do site, você escolhe r diretamente, para entender o efeito.</p>
      <p>No Brasil, a taxa livre de risco (CDI, Tesouro) é alta, o que puxa r para cima e os valores justos para baixo.</p>`,
    aba: "dcf", ver: ["capm", "dcf"] },

  { id: "monte-carlo", cat: "Valuation", t: "Simulação de Monte Carlo",
    r: "Sortear milhares de cenários de premissas para ver a distribuição de resultados.",
    c: `<p>Em vez de um único valor justo, sorteia-se crescimento, r e g de distribuições (por exemplo, normal em torno da sua premissa) e recalcula-se o DCF milhares de vezes. O resultado é um histograma com a probabilidade de o valor justo ficar acima do preço.</p>`,
    cu: "A simulação só é tão boa quanto as distribuições escolhidas. Ela mostra incerteza das premissas, não acerta o futuro.",
    aba: "mod", ver: ["dcf"], ref: ["Metropolis, N.; Ulam, S. (1949). The Monte Carlo Method. JASA"] },

  // ===================== Risco e retorno =====================
  { id: "volatilidade", cat: "Risco e retorno", t: "Volatilidade",
    r: "O desvio-padrão dos retornos: quanto o preço oscila em torno da média.",
    f: "σ anual = desvio-padrão dos retornos diários × √252",
    c: `<p>É a medida de risco mais usada. Multiplica-se por √252 porque a variância cresce com o tempo (supondo retornos independentes), e o desvio-padrão cresce com a raiz.</p>
      <p>Volatilidade de 30% ao ano significa, grosso modo, que em dois de cada três anos o retorno fica entre média − 30% e média + 30%.</p>`,
    cu: "Trata altas e quedas igualmente e supõe retornos parecidos com uma normal. Quedas extremas acontecem mais do que a normal prevê.",
    aba: "carteira", ver: ["correlacao", "garch", "sharpe"] },

  { id: "correlacao", cat: "Risco e retorno", t: "Covariância e correlação",
    r: "Quanto dois ativos andam juntos. É a base da diversificação.",
    f: "ρ = Cov(A, B) ÷ (σA × σB), entre −1 e 1",
    c: `<p>Correlação 1: sobem e caem juntos. 0: sem relação linear. −1: um sobe quando o outro cai. Ativos pouco correlacionados se compensam e reduzem o risco da carteira.</p>`,
    cu: "Correlações mudam com o tempo e costumam subir em crises, justamente quando a diversificação faria mais falta.",
    aba: "carteira", ver: ["markowitz", "volatilidade"] },

  { id: "sharpe", cat: "Risco e retorno", t: "Índice de Sharpe",
    r: "Retorno acima da renda fixa por unidade de risco.",
    f: "Sharpe = (E[R] − rf) ÷ σ",
    c: `<p>Compara investimentos com riscos diferentes. Sharpe 0,5: cada 1% de volatilidade trouxe 0,5% de retorno acima do CDI. A carteira de máximo Sharpe é a "carteira tangente" de Markowitz.</p>`,
    aba: "carteira", ver: ["markowitz", "cml"], ref: ["Sharpe, W. F. (1966). Mutual Fund Performance. Journal of Business"] },

  { id: "capm", cat: "Risco e retorno", t: "CAPM",
    r: "O retorno esperado de um ativo depende só do risco de mercado (β).",
    f: "E[Rᵢ] = rf + βᵢ × (E[Rm] − rf)",
    c: `<p>O <em>Capital Asset Pricing Model</em> diz que o risco específico de uma empresa some com a diversificação e, por isso, não é remunerado. Só o risco que vem do mercado como um todo, medido pelo β, exige prêmio.</p>
      <p>No site, ao escolher CAPM na carteira eficiente, o retorno esperado de cada ativo passa a ser este, no lugar da média histórica (que é muito instável).</p>`,
    cu: "Na prática, o CAPM explica mal os retornos observados (há efeitos de tamanho, valor, momentum). E o prêmio de mercado esperado é uma premissa, não um dado.",
    aba: "carteira", ver: ["beta", "alfa-jensen", "sml"], ref: ["Sharpe, W. F. (1964). Capital Asset Prices. Journal of Finance", "Lintner, J. (1965). Review of Economics and Statistics"] },

  { id: "beta", cat: "Risco e retorno", t: "Beta (β)",
    r: "Quanto o ativo se move quando o mercado se move 1%.",
    f: "β = Cov(Rᵢ, Rm) ÷ Var(Rm)",
    c: `<p>β = 1: acompanha o Ibovespa. β &gt; 1: amplifica (bancos e varejo costumam ter). β &lt; 1: amortece (energia, saneamento). β perto de 0: quase independe da bolsa (dólar, ouro).</p>
      <p>É o coeficiente angular da regressão dos retornos do ativo contra os do mercado. O R² dessa regressão diz quanto da variação o mercado explica.</p>`,
    cu: "Ativos negociados em outros horários (cripto, ouro em Nova York) têm β subestimado com dados diários.",
    aba: "carteira", ver: ["capm", "regressao"] },

  { id: "alfa-jensen", cat: "Risco e retorno", t: "Alfa de Jensen",
    r: "O retorno além do que o CAPM explicaria pelo β.",
    f: "α = Rᵢ − [rf + β × (Rm − rf)]",
    c: `<p>Usa retornos realizados. Alfa positivo: o ativo rendeu mais do que seu risco de mercado justificaria; fica acima da Security Market Line.</p>`,
    cu: "Alfa passado não garante alfa futuro, e com poucos anos de dados o erro de estimação é grande.",
    aba: "carteira", ver: ["sml", "capm"], ref: ["Jensen, M. C. (1968). The Performance of Mutual Funds in the Period 1945–1964. Journal of Finance"] },

  { id: "sml", cat: "Risco e retorno", t: "Security Market Line",
    r: "A reta do CAPM: retorno esperado em função do β.",
    c: `<p>Vai da taxa livre de risco (β = 0) até o mercado (β = 1). Ativos acima da reta tiveram alfa positivo; abaixo, negativo.</p>
      <p>Não confunda com a <strong>linha de mercado de capitais</strong> (CML), que usa a volatilidade (σ) no eixo horizontal e vale para carteiras eficientes.</p>`,
    aba: "carteira", ver: ["alfa-jensen", "cml"] },

  // ===================== Carteiras =====================
  { id: "markowitz", cat: "Carteiras", t: "Markowitz e a fronteira eficiente",
    r: "Escolher os pesos que dão o menor risco para cada retorno esperado.",
    f: "mín wᵀΣw  sujeito a  wᵀμ = alvo, Σw = 1, w ≥ 0",
    c: `<p>Harry Markowitz mostrou que o risco de uma carteira depende das <strong>covariâncias</strong>, não só do risco de cada ativo. Resolvendo a otimização para vários retornos-alvo, obtém-se a <strong>fronteira eficiente</strong>: qualquer carteira abaixo dela é pior.</p>
      <p>Pontos de destaque: <strong>mínima variância</strong> (menor risco possível) e <strong>máximo Sharpe</strong>.</p>`,
    cu: "Muito sensível ao retorno esperado (μ): pequenas mudanças geram pesos extremos. Por isso o site oferece peso máximo, CAPM e os modelos robustos.",
    aba: "carteira", ver: ["correlacao", "sharpe", "black-litterman", "cma"], ref: ["Markowitz, H. (1952). Portfolio Selection. Journal of Finance"] },

  { id: "cml", cat: "Carteiras", t: "Linha de mercado de capitais",
    r: "Combinar a carteira de máximo Sharpe com renda fixa.",
    f: "E[R] = rf + Sharpeₘₐₓ × σ",
    c: `<p>Com um ativo sem risco disponível, o melhor que se pode fazer é misturar renda fixa com a carteira tangente (máximo Sharpe). Mais renda fixa = menos risco e menos retorno, ao longo de uma reta.</p>`,
    aba: "carteira", ver: ["markowitz", "sharpe"], ref: ["Tobin, J. (1958). Liquidity Preference as Behavior Towards Risk. Review of Economic Studies"] },

  { id: "processo-gestora", cat: "Carteiras", t: "Como uma gestora monta uma carteira",
    r: "O processo de alocação usado no mercado, do retorno esperado ao rebalanceamento.",
    c: `<ol><li><strong>Premissas de mercado (CMA)</strong>: retorno, risco e correlação esperados de cada classe para o horizonte (normalmente 5 a 10 anos), revistos uma ou duas vezes por ano.</li>
      <li><strong>Visões táticas</strong>: o comitê de investimentos registra convicções de curto e médio prazo e o grau de confiança nelas. O Black-Litterman transforma isso em retornos ajustados.</li>
      <li><strong>Política de investimento</strong>: objetivo (retorno-alvo, risco máximo), limites por classe e por ativo, liquidez mínima. Fundos de pensão seguem também regras legais.</li>
      <li><strong>Otimização com restrições</strong>: Markowitz (ou variantes) dentro dos limites, muitas vezes com faixas em torno de uma carteira de referência (benchmark).</li>
      <li><strong>Implementação</strong>: transformar pesos em ordens, considerando lote, liquidez, custos e impostos.</li>
      <li><strong>Monitoramento e rebalanceamento</strong>: acompanhar o desvio em relação aos pesos-alvo e rebalancear por calendário ou quando passar de uma banda.</li></ol>
      <p>A aba "Montar minha carteira" segue essa ordem, e "Minhas carteiras" faz o acompanhamento.</p>`,
    cu: "Na prática, a maior parte do resultado de longo prazo vem da alocação estratégica entre classes, não da escolha de ativos individuais.",
    aba: "carteira", ver: ["cma", "black-litterman", "markowitz"], ref: ["Brinson, G.; Hood, L.; Beebower, G. (1986). Determinants of Portfolio Performance. Financial Analysts Journal", "Maginn, J. et al. — Managing Investment Portfolios (CFA Institute)"] },

  { id: "cma", cat: "Carteiras", t: "Premissas de mercado (Capital Market Assumptions)",
    r: "Como o mercado estima o retorno esperado de cada classe: por blocos observáveis hoje.",
    c: `<p>Em vez da média do passado, cada classe tem o retorno decomposto em partes que se observam hoje:</p>
      <ul><li><strong>Renda fixa</strong>: a taxa atual do título é o retorno até o vencimento. IPCA+ = taxa real + inflação esperada.</li>
      <li><strong>Ações</strong>: dividendos + crescimento do lucro + mudança de múltiplo (Grinold-Kroner).</li>
      <li><strong>Imóveis/FIIs</strong>: rendimento de aluguel + reajuste pela inflação.</li>
      <li><strong>Câmbio</strong>: diferença de juros entre os países (paridade de juros).</li>
      <li><strong>Inflação esperada</strong>: implícita na curva (prefixado ÷ IPCA+) ou pesquisas como o Focus do Banco Central.</li></ul>
      <p>Grandes casas publicam as suas CMAs todo ano (J.P. Morgan, BlackRock, Vanguard). As diferenças entre elas são uma boa medida de quanto essas estimativas são incertas.</p>`,
    ex: "Prefixado de 5 anos a 13,6% e inflação implícita de 5,7%: uma ação com dividend yield de 4% e crescimento real de 2% teria retorno esperado ≈ 4 + 5,7 + 2 = 11,7% a.a.",
    cu: "São estimativas de longo prazo, com erro grande no curto prazo. Revise quando a curva de juros ou os preços mudarem muito.",
    aba: "carteira", ver: ["grinold-kroner", "black-litterman", "inflacao-implicita"], ref: ["J.P. Morgan Asset Management — Long-Term Capital Market Assumptions (anual)", "Vanguard — Capital Markets Model"] },

  { id: "grinold-kroner", cat: "Valuation", t: "Grinold-Kroner: retorno esperado das ações",
    r: "Retorno = renda + crescimento + reprecificação.",
    f: "E[R] ≈ dividend yield + inflação + crescimento real do lucro − diluição ± mudança de múltiplo",
    c: `<p>O retorno de uma ação no longo prazo vem de três fontes: o que ela paga (<strong>renda</strong>), o quanto o lucro cresce (<strong>crescimento nominal</strong> = inflação + crescimento real − diluição por novas ações) e se o mercado vai pagar mais ou menos por cada real de lucro (<strong>reprecificação</strong> do P/L).</p>
      <p>É a versão de mercado do modelo de Gordon. Empresas que distribuem pouco reinvestem mais e tendem a crescer mais: a soma é que importa.</p>`,
    cu: "Um provento extraordinário infla o dividend yield. Para empresas cíclicas, use lucros e dividendos médios de um ciclo.",
    aba: "carteira", ver: ["cma", "perpetuidade", "dy"], ref: ["Grinold, R.; Kroner, K. (2002). The Equity Risk Premium. Investment Insights, Barclays Global Investors"] },

  { id: "black-litterman", cat: "Carteiras", t: "Black-Litterman",
    r: "Combinar as premissas de mercado com as suas convicções, na medida da confiança.",
    f: "μ = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ · [(τΣ)⁻¹π + PᵀΩ⁻¹Q]",
    c: `<p>Criado na Goldman Sachs no início dos anos 1990 para resolver o problema clássico do Markowitz: pesos extremos e instáveis. Parte de um retorno de referência <strong>π</strong> (no artigo original, o retorno implícito de equilíbrio do mercado; aqui, as premissas por blocos) e acrescenta as <strong>visões</strong>:</p>
      <ul><li><strong>P</strong>: quais ativos cada visão envolve (ex.: +1 em WEGE3 e −1 em ITUB4 para "WEGE3 rende mais que ITUB4");</li>
      <li><strong>Q</strong>: o retorno que você espera (ex.: 3 p.p. ao ano);</li>
      <li><strong>Ω</strong>: a incerteza da visão. Quanto menor a confiança, maior Ω e menos o resultado se move;</li>
      <li><strong>τ</strong>: a incerteza da própria referência (costuma ser 0,025 a 0,05).</li></ul>
      <p>O resultado é uma média ponderada pela precisão. Sem visões, nada muda. Uma visão sobre um ativo também move os ativos correlacionados com ele.</p>`,
    cu: "As visões precisam ser coerentes e poucas. Muitas visões com confiança alta voltam a gerar pesos extremos.",
    aba: "carteira", ver: ["cma", "markowitz", "processo-gestora"], ref: ["Black, F.; Litterman, R. (1992). Global Portfolio Optimization. Financial Analysts Journal", "He, G.; Litterman, R. (1999). The Intuition Behind Black-Litterman Model Portfolios. Goldman Sachs", "Idzorek, T. (2005). A Step-by-Step Guide to the Black-Litterman Model"] },

  { id: "ledoit-wolf", cat: "Carteiras", t: "Covariância de Ledoit-Wolf",
    r: "Uma estimativa da covariância mais estável que a amostral.",
    c: `<p>A covariância calculada direto dos dados tem muito ruído quando há muitos ativos e poucos dias. Ledoit e Wolf "encolhem" a matriz em direção a uma estrutura simples, escolhendo a intensidade ótima. O resultado gera pesos menos extremos.</p>`,
    aba: "mod", ver: ["markowitz", "hrp"], ref: ["Ledoit, O.; Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. Journal of Multivariate Analysis"] },

  { id: "hrp", cat: "Carteiras", t: "Hierarchical Risk Parity (HRP)",
    r: "Montar a carteira agrupando ativos parecidos e dividindo o risco entre os grupos.",
    c: `<p>Em vez de inverter a matriz de covariância (o que amplifica erros), o HRP: (1) agrupa os ativos por correlação, como numa árvore; (2) reordena a matriz; (3) divide o capital de cima para baixo, dando mais peso ao grupo de menor variância. Não usa retornos esperados.</p>`,
    cu: "Não busca o máximo retorno; o objetivo é estabilidade e diversificação.",
    aba: "mod", ver: ["ledoit-wolf", "walk-forward"], ref: ["López de Prado, M. (2016). Building Diversified Portfolios that Outperform Out of Sample. Journal of Portfolio Management"] },

  { id: "walk-forward", cat: "Carteiras", t: "Backtest walk-forward",
    r: "Testar um método só com dados que estariam disponíveis na época.",
    c: `<p>A cada rebalanceamento, estima-se a carteira com a janela passada (por exemplo, 252 dias) e mede-se o resultado nos dias seguintes, que o modelo não viu. Repete-se andando no tempo. Assim se evita o viés de "olhar o futuro".</p>`,
    cu: "Mesmo fora da amostra, testar muitas variações e escolher a melhor cria sobreajuste (overfitting).",
    aba: "mod", ver: ["bootstrap", "hrp"], ref: ["Bailey, D.; López de Prado, M. et al. (2014). The Probability of Backtest Overfitting"] },

  { id: "bootstrap", cat: "Carteiras", t: "Bootstrap e estabilidade dos pesos",
    r: "Reamostrar os dados para ver quanto os pesos mudariam por acaso.",
    c: `<p>Sorteiam-se dias do histórico com reposição, monta-se uma nova amostra do mesmo tamanho e otimiza-se de novo, centenas de vezes. Se o peso de um ativo varia de 0% a 60% entre as reamostras, ele não é confiável.</p>`,
    aba: "mod", ver: ["markowitz", "walk-forward"], ref: ["Efron, B. (1979). Bootstrap Methods: Another Look at the Jackknife. Annals of Statistics"] },

  // ===================== Impostos =====================
  { id: "impostos-acoes", cat: "Impostos", t: "IR em ações, FIIs, ETFs e cripto",
    r: "As alíquotas e isenções usadas na carteira com impostos.",
    c: `<ul><li><strong>Ações</strong>: 15% sobre o ganho em operações comuns; isenção para vendas de até R$ 20 mil no mês. Dividendos isentos até R$ 50 mil/mês por empresa (acima disso, 10% retido, Lei 15.270/2025). JCP com retenção na fonte.</li>
      <li><strong>FIIs</strong>: 20% sobre o ganho, sem isenção; rendimentos isentos para pessoa física se cumpridas as condições da lei.</li>
      <li><strong>ETFs de renda variável</strong>: 15%, sem a isenção de R$ 20 mil.</li>
      <li><strong>Cripto</strong>: isenção para vendas de até R$ 35 mil no mês em corretora nacional; acima, 15% (progressiva para ganhos muito altos).</li></ul>
      <p>O site aplica essas regras de forma simplificada; a aba mostra a base legal de cada uma.</p>`,
    cu: "Regras tributárias mudam. Confirme a sua situação com um contador e na Receita Federal.",
    aba: "carteira", ver: ["tabela-regressiva"], ref: ["Lei 11.033/2004", "Lei 8.668/1993, art. 18", "Lei 15.270/2025", "IN RFB 1.585/2015"] },

  { id: "tabela-regressiva", cat: "Impostos", t: "Tabela regressiva, IOF e custódia",
    r: "Os custos da renda fixa: quanto mais tempo, menor o IR.",
    f: "IR: 22,5% (até 180 dias) · 20% (até 360) · 17,5% (até 720) · 15% (acima)",
    c: `<p>Vale para Tesouro, CDB e fundos de renda fixa. O IR incide só sobre o rendimento. Nos primeiros 30 dias também há <strong>IOF</strong> regressivo (96% do rendimento no dia 1, chegando a zero no dia 30).</p>
      <p>No Tesouro Direto a B3 cobra <strong>taxa de custódia</strong> anual sobre o valor investido, que é deduzida da base do IR. Os cupons semestrais pagam IR na data do pagamento.</p>`,
    ex: "Ganho de R$ 1.000 em 400 dias: IR de 17,5% = R$ 175.",
    cu: "Confira a taxa de custódia vigente no site da B3; há regras específicas para o Tesouro Selic.",
    aba: "rf", ver: ["tesouro", "simulador-rf"], ref: ["Lei 11.033/2004, art. 1º", "Decreto 6.306/2007 (IOF)"] },

  // ===================== Renda fixa =====================
  { id: "tesouro", cat: "Renda fixa", t: "Títulos do Tesouro Direto",
    r: "Prefixado, IPCA+, Selic e suas versões com juros semestrais.",
    c: `<ul><li><strong>Prefixado (LTN)</strong>: paga R$ 1.000 no vencimento. Você sabe hoje quanto vai receber.</li>
      <li><strong>Prefixado com juros semestrais (NTN-F)</strong>: cupom de 10% a.a. sobre R$ 1.000, pago a cada 6 meses.</li>
      <li><strong>IPCA+ (NTN-B Principal)</strong>: paga o VNA (valor corrigido pela inflação) no vencimento; a taxa é o ganho real.</li>
      <li><strong>IPCA+ com juros semestrais (NTN-B)</strong>: cupom de 6% a.a. sobre o VNA.</li>
      <li><strong>Selic (LFT)</strong>: acompanha a Selic; quase não sofre com alta de juros.</li>
      <li><strong>Renda+ e Educa+</strong>: pagam mensalmente por vários anos, para aposentadoria ou educação.</li></ul>`,
    aba: "rf", ver: ["pu-taxa", "vna", "marcacao"], ref: ["Tesouro Direto — tesourodireto.com.br", "Tesouro Transparente — dados abertos"] },

  { id: "pu-taxa", cat: "Renda fixa", t: "Preço (PU), taxa e dias úteis",
    r: "Como a taxa de um título vira o preço que você paga.",
    f: "PU = Σ fluxoᵢ ÷ (1 + taxa)^(dias úteisᵢ ÷ 252)",
    c: `<p>O preço é o valor presente dos pagamentos futuros, descontados pela taxa do título. No Brasil, a convenção usa <strong>dias úteis</strong> sobre 252, contando feriados nacionais.</p>
      <p>Taxa e preço andam em sentidos opostos: se a taxa sobe, cada pagamento futuro vale menos hoje, e o preço cai.</p>`,
    ex: "Prefixado com 293 dias úteis a 14,1%: PU = 1.000 ÷ 1,141^(293/252) ≈ R$ 857,82.",
    aba: "rf", ver: ["duration", "marcacao"], ref: ["ANBIMA — metodologia de precificação de títulos públicos"] },

  { id: "vna", cat: "Renda fixa", t: "VNA: valor nominal atualizado",
    r: "O valor de face dos títulos indexados, corrigido pelo indexador.",
    c: `<p>Títulos IPCA+ começaram com valor de R$ 1.000 numa data-base e esse valor é corrigido mês a mês pelo IPCA. O preço é calculado em % do VNA. No Tesouro Selic, o VNA é corrigido pela Selic diária.</p>
      <p>O site calcula o VNA implícito: PU publicado ÷ (preço em % do VNA).</p>`,
    aba: "rf", ver: ["tesouro", "inflacao-implicita"] },

  { id: "duration", cat: "Renda fixa", t: "Duration de Macaulay e modificada",
    r: "O prazo médio do título e quanto o preço muda quando a taxa muda.",
    f: "D = Σ (tᵢ × VPᵢ) ÷ PU · Dmod = D ÷ (1 + taxa) · ΔP/P ≈ −Dmod × Δtaxa",
    c: `<p>A <strong>duration de Macaulay</strong> é o prazo médio em que o dinheiro volta, ponderado pelo valor presente. Títulos com cupom devolvem parte antes, por isso têm duration menor que o prazo.</p>
      <p>A <strong>duration modificada</strong> é a sensibilidade: Dmod = 5 quer dizer que, se a taxa subir 1 ponto, o preço cai cerca de 5%.</p>`,
    aba: "rf", ver: ["convexidade", "dv01"], ref: ["Macaulay, F. (1938). Some Theoretical Problems Suggested by the Movements of Interest Rates… NBER"] },

  { id: "convexidade", cat: "Renda fixa", t: "Convexidade",
    r: "A curvatura do preço em relação à taxa: corrige a duration em choques grandes.",
    f: "ΔP/P ≈ −Dmod × Δy + ½ × C × Δy²",
    c: `<p>A relação preço × taxa é uma curva, não uma reta. A convexidade faz o preço subir mais na queda dos juros do que cai na alta. Títulos longos e sem cupom têm mais convexidade.</p>`,
    aba: "rf", ver: ["duration"] },

  { id: "dv01", cat: "Renda fixa", t: "DV01",
    r: "Quanto o preço muda, em reais, para cada 0,01 ponto de alta na taxa.",
    f: "DV01 = PU(taxa + 0,01%) − PU(taxa)",
    c: `<p>Também chamado de PV01 ou "valor do ponto-base". Na comparação de títulos, o site mostra o DV01 por R$ 1.000 investidos, para comparar títulos de preços diferentes.</p>`,
    aba: "rf", ver: ["duration"] },

  { id: "marcacao", cat: "Renda fixa", t: "Marcação a mercado",
    r: "Por que um título \"seguro\" pode dar prejuízo se vendido antes do vencimento.",
    c: `<p>O preço de venda antecipada é recalculado todo dia com a taxa do mercado. Se as taxas subiram desde a compra, o preço caiu, e vender antes realiza a perda. Levando até o vencimento, você recebe exatamente a taxa contratada.</p>`,
    aba: "rf", ver: ["simulador-rf", "duration"] },

  { id: "simulador-rf", cat: "Renda fixa", t: "Simulação de investimento no Tesouro",
    r: "Como o site calcula quanto você recebe, líquido, numa data de venda.",
    c: `<ol><li>Quantidade de títulos = valor ÷ PU de hoje.</li>
      <li>O indexador (VNA) é projetado com a premissa de IPCA ou Selic.</li>
      <li>Cupons recebidos pagam IR e são reinvestidos à taxa do próprio título até a saída.</li>
      <li>Na venda antes do vencimento, o preço é recalculado com a taxa que você informar (marcação a mercado).</li>
      <li>Descontam-se custódia, IOF (se menos de 30 dias) e IR pela tabela regressiva.</li></ol>
      <p>Para comparar títulos de prazos diferentes, olhe a rentabilidade líquida <strong>ao ano</strong>.</p>`,
    cu: "IPCA+ e Selic dependem de premissas sobre o futuro; prefixados não.",
    aba: "rf", ver: ["tabela-regressiva", "marcacao"] },

  { id: "curva-juros", cat: "Renda fixa", t: "Curva de juros e DI futuro",
    r: "As taxas para cada prazo, lado a lado.",
    c: `<p>A curva mostra a taxa de títulos de prazos diferentes. Inclinada para cima: o mercado cobra mais para prazos longos (risco, expectativa de alta). Invertida: espera queda dos juros.</p>
      <p>O <strong>DI futuro</strong> da B3 é o contrato mais negociado de juros no Brasil; a curva DI é a referência de preço para crédito e renda fixa.</p>`,
    aba: "rf", ver: ["inflacao-implicita", "futuros"], ref: ["B3 — Taxas referenciais"] },

  { id: "inflacao-implicita", cat: "Renda fixa", t: "Inflação implícita",
    r: "A inflação que o mercado embute ao comparar prefixados e IPCA+.",
    f: "Inflação implícita = (1 + taxa prefixada) ÷ (1 + taxa real) − 1",
    c: `<p>Se o prefixado de 5 anos paga 13% e o IPCA+ de 5 anos paga 7%, o mercado está "cobrando" cerca de 5,6% de inflação média. Se você acha que a inflação será maior que isso, o IPCA+ tende a render mais; se menor, o prefixado.</p>`,
    cu: "Inclui um prêmio de risco de inflação, então não é exatamente a expectativa do mercado.",
    aba: "rf", ver: ["curva-juros", "tesouro"] },

  // ===================== Derivativos =====================
  { id: "opcoes", cat: "Derivativos", t: "Opções: call e put",
    r: "Direito (não obrigação) de comprar ou vender um ativo a um preço combinado.",
    c: `<p><strong>Call</strong>: direito de comprar pelo preço de exercício (<em>strike</em>). <strong>Put</strong>: direito de vender. Quem compra paga um <strong>prêmio</strong>; quem vende (lançador) recebe o prêmio e assume a obrigação.</p>
      <p><strong>Dentro do dinheiro</strong> (ITM): exercer daria lucro hoje. <strong>No dinheiro</strong> (ATM): strike perto do preço. <strong>Fora</strong> (OTM): exercer não compensaria hoje.</p>
      <p>Na B3, as calls de ações costumam ser americanas (podem ser exercidas a qualquer momento) e as puts, europeias (só no vencimento). Os códigos têm com letras que indicam o mês (A–L calls, M–X puts).</p>`,
    aba: "der", ver: ["black-scholes", "estrategias"], ref: ["B3 — COTAHIST (série histórica de cotações)"] },

  { id: "black-scholes", cat: "Derivativos", t: "Black-Scholes",
    r: "A fórmula que precifica uma opção europeia a partir de 5 variáveis.",
    f: "C = S·N(d1) − K·e^(−rT)·N(d2), d1 = [ln(S/K) + (r + σ²/2)T] ÷ (σ√T), d2 = d1 − σ√T",
    c: `<p>Entradas: preço do ativo (S), strike (K), prazo (T), juros (r) e volatilidade (σ). A ideia central: é possível montar uma carteira de ação + renda fixa que replica a opção, então o preço não depende do retorno esperado da ação.</p>
      <p><strong>Volatilidade implícita</strong> é a σ que, colocada na fórmula, reproduz o preço de mercado.</p>`,
    cu: "Supõe volatilidade constante e preços sem saltos. O 'sorriso de volatilidade' observado no mercado mostra que isso não vale exatamente.",
    aba: "der", ver: ["gregas", "opcoes"], ref: ["Black, F.; Scholes, M. (1973). The Pricing of Options and Corporate Liabilities. Journal of Political Economy", "Merton, R. (1973). Bell Journal of Economics"] },

  { id: "gregas", cat: "Derivativos", t: "Gregas",
    r: "Sensibilidades do preço da opção.",
    c: `<ul><li><strong>Delta</strong>: quanto a opção muda para R$ 1 no ativo.</li><li><strong>Gama</strong>: quanto o delta muda.</li>
      <li><strong>Theta</strong>: perda de valor por dia que passa.</li><li><strong>Vega</strong>: efeito de +1 ponto de volatilidade.</li><li><strong>Rho</strong>: efeito dos juros.</li></ul>`,
    aba: "der", ver: ["black-scholes"] },

  { id: "estrategias", cat: "Derivativos", t: "Estratégias com opções",
    r: "Venda coberta, put de proteção, travas e collar.",
    c: `<ul><li><strong>Venda coberta</strong>: tem a ação e vende uma call. Ganha o prêmio, mas limita a alta.</li>
      <li><strong>Put de proteção</strong>: tem a ação e compra uma put. Funciona como seguro contra queda.</li>
      <li><strong>Trava de alta</strong>: compra uma call e vende outra de strike maior. Custo e ganho limitados.</li>
      <li><strong>Collar</strong>: put de proteção financiada pela venda de uma call.</li></ul>
      <p>O gráfico de resultado no vencimento mostra o lucro ou prejuízo para cada preço da ação, e os pontos de equilíbrio (breakeven).</p>`,
    aba: "der", ver: ["opcoes"] },

  { id: "futuros", cat: "Derivativos", t: "Contratos futuros e ajuste diário",
    r: "Compromisso de comprar ou vender no futuro a um preço de hoje.",
    c: `<p>Diferente da opção, o futuro é uma <strong>obrigação</strong> dos dois lados. Na B3, os ganhos e perdas são liquidados todo dia (<strong>ajuste diário</strong>), e é exigida uma margem de garantia.</p>
      <p>Contratos populares: dólar (DOL/WDO), Ibovespa (IND/WIN) e DI1 (taxa de juros).</p>`,
    aba: "der", ver: ["curva-juros"], ref: ["B3 — Mercado de derivativos"] },

  // ===================== Estatística =====================
  { id: "regressao", cat: "Estatística", t: "Regressão linear (MQO)",
    r: "Estimar quanto uma variável muda quando outra muda.",
    f: "Rₐₜᵢᵥₒ = α + β₁·fator₁ + β₂·fator₂ + … + ε",
    c: `<p>Mínimos quadrados ordinários escolhe os coeficientes que minimizam a soma dos erros ao quadrado. Na aba Sensibilidade, cada β diz quanto o ativo reage a um fator (Ibovespa, dólar, IPCA, Selic, petróleo).</p>
      <p><strong>Simples</strong>: um fator por vez. <strong>Múltipla</strong>: todos juntos, isolando o efeito de cada um. O <strong>R²</strong> é a fração da variação explicada. O intervalo de confiança mostra a incerteza de cada β.</p>`,
    cu: "Correlação não é causalidade. Fatores muito correlacionados entre si (multicolinearidade) deixam os betas da regressão múltipla instáveis.",
    aba: "sen", ver: ["estacionariedade", "beta"] },

  { id: "estacionariedade", cat: "Estatística", t: "Estacionariedade, ADF e KPSS",
    r: "Por que a regressão usa variações e não preços.",
    c: `<p>Uma série é <strong>estacionária</strong> quando média e variância não mudam com o tempo. Preços e índices costumam não ser: andam sem voltar a uma média. Regredir duas séries assim gera a <strong>regressão espúria</strong>: R² alto e relação que não existe.</p>
      <p>Testes: <strong>ADF</strong> (hipótese nula: não estacionária; p &lt; 0,05 rejeita) e <strong>KPSS</strong> (hipótese nula: estacionária; p &gt; 0,05 não rejeita). O site só chama de estacionária quando os dois concordam.</p>`,
    aba: "sen", ver: ["regressao"], ref: ["Granger, C.; Newbold, P. (1974). Spurious Regressions in Econometrics. Journal of Econometrics", "Dickey, D.; Fuller, W. (1979). JASA", "Kwiatkowski, D. et al. (1992). Journal of Econometrics"] },

  { id: "garch", cat: "Estatística", t: "GARCH: volatilidade que muda",
    r: "Modelar a volatilidade de amanhã a partir dos choques recentes.",
    f: "σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁",
    c: `<p>A volatilidade vem em ondas: dias agitados tendem a ser seguidos por dias agitados. O GARCH(1,1) estima a variância de amanhã como uma média entre um nível de longo prazo, o choque de ontem (α) e a variância de ontem (β). α + β perto de 1 indica volatilidade persistente.</p>
      <p>No site, o modelo é avaliado fora da amostra com a perda <strong>QLIKE</strong> e comparado com a volatilidade histórica simples.</p>`,
    aba: "mod", ver: ["volatilidade"], ref: ["Bollerslev, T. (1986). Generalized Autoregressive Conditional Heteroskedasticity. Journal of Econometrics", "Patton, A. (2011). Volatility forecast comparison using imperfect volatility proxies. Journal of Econometrics"] },

  // ===================== Machine learning =====================
  { id: "isolation-forest", cat: "Machine learning", t: "Isolation Forest: detectar anomalias",
    r: "Achar empresas com indicadores fora do padrão.",
    c: `<p>O algoritmo sorteia cortes aleatórios nos dados. Pontos anômalos ficam isolados com poucos cortes; pontos comuns precisam de muitos. Na aba Saúde dos dados, ele aponta empresas com combinação incomum de indicadores, que valem uma investigação (ou um erro de dado).</p>`,
    aba: "saude", ver: [], ref: ["Liu, F. T.; Ting, K. M.; Zhou, Z.-H. (2008). Isolation Forest. IEEE ICDM"] },

  // ===================== Fontes =====================
  { id: "fontes-cvm", cat: "Fontes de dados", t: "CVM: dados abertos",
    r: "Demonstrações, cadastro, FIIs e comunicados, direto do regulador.",
    c: `<p>O portal de dados abertos da CVM publica arquivos CSV com o ITR, a DFP, o FCA (cadastro e valores mobiliários), o informe mensal dos FIIs e o IPE (fatos relevantes e comunicados). O site baixa esses arquivos e guarda uma cópia local (pasta <code>cache_cvm</code>).</p>`,
    aba: "indicadores", ver: ["ttm", "fontes-bcb"], ref: ["dados.cvm.gov.br"] },

  { id: "fontes-bcb", cat: "Fontes de dados", t: "Banco Central (SGS), Tesouro e B3",
    r: "De onde vêm CDI, Selic, IPCA, câmbio, títulos públicos e opções.",
    c: `<ul><li><strong>SGS do Banco Central</strong>: CDI (séries 12 e 4389), IPCA (433), PTAX (1), Selic (432, 4189).</li>
      <li><strong>Tesouro Transparente</strong>: preços e taxas diários do Tesouro Direto.</li>
      <li><strong>B3</strong>: arquivo COTAHIST (cotações, inclusive opções) e taxas referenciais de DI.</li>
      <li><strong>yfinance</strong>: preços históricos e proventos (fonte não oficial, usada com conferência).</li></ul>`,
    aba: "comparar", ver: ["fontes-cvm"], ref: ["Banco Central — SGS", "Tesouro Transparente", "B3 — Market data"] },
];
