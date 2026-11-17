# Agentes

Esta pasta tem duas coisas diferentes:

- **Agentes de IA** (3): um modelo de linguagem decide quais ferramentas chamar, lê os resultados e escreve a conclusão. São o agente de **pesquisa**, o de **carteira** e o de **qualidade de dados**.
- **Pipeline de regras fixas**: módulos Python determinísticos que fazem a análise sem IA. Eles servem de ferramentas para o agente de pesquisa e de reserva quando a IA não responde.

Em todos os casos vale a mesma regra: **a IA não cria números**. Todo número vem de uma ferramenta que lê fontes oficiais, e o texto final passa por um validador antes de chegar à tela.

## Estrutura

```
llm.py                  provedores de IA gratuitos (Gemini → Groq → Ollama), com troca automática
   │
nucleo.py               laço genérico de agente com ferramentas + validador da resposta final
   │
   ├── agente.py           Agente de pesquisa   (aba Research)
   ├── carteira_agente.py  Agente de carteira   (Carteira eficiente → "Por que ficou abaixo do Ibovespa?")
   │     └── laboratorio.py   treino/reserva e regras que a IA não consegue furar
   └── qualidade.py        Agente de qualidade  (Saúde dos dados)

Pipeline de regras fixas (orquestrador.py):
   financial.py → market.py → investment.py → redator.py → relatorio.py

Apoio:
   fatos.py            Dossiê: cada número com id, tipo, fonte e fórmula
   fontes_publicas.py  BCB (SGS, Focus), FRED, IPEA: tudo sem chave
   estilo.py           padrão de escrita dos relatórios
```

## Núcleo comum (`nucleo.py` e `llm.py`)

Um agente é a combinação de **instruções + ferramentas (funções Python) + validador**. O `AgenteFerramentas` roda o laço:

1. manda a conversa ao modelo, que responde com chamadas de ferramenta ou com o texto final;
2. executa as ferramentas e devolve os resultados, truncados para caber no contexto;
3. repete até o texto final, dentro dos limites de passos e de tempo;
4. passa o texto pelo validador. Se reprovar, devolve a lista de problemas ao modelo (até 2 correções).

**Robustez**

- Se um provedor falhar ou estourar o limite gratuito (erro 429), o laço passa para o próximo **no meio da conversa**, sem recomeçar.
- Chamadas repetidas com os mesmos argumentos reaproveitam o resultado.
- Uma exceção dentro de uma ferramenta vira `{"erro": ...}` para o modelo e nunca derruba o laço.
- Quando o modelo empaca no mesmo erro do validador, `podar=True` remove só as frases reprovadas e aceita o resto, se ele passar inteiro.
- Cada passo fica registrado (ferramenta, argumentos, duração, resumo), junto com o tempo de cada provedor. A tela mostra isso em *Como o agente investigou*.

**Provedores** (`llm.py`), todos gratuitos e na ordem configurada:

| Provedor | Chave | Observação |
|---|---|---|
| Gemini | <https://aistudio.google.com/apikey> | No nível gratuito, o Google pode usar o que é enviado para melhorar os modelos. Aqui só vão dados públicos de empresas. |
| Groq | <https://console.groq.com/keys> | O mais rápido. Bom como primeira opção ou reserva. |
| Ollama | sem chave | Roda no seu computador. Sem limite, mas lento sem GPU dedicada e mais fraco. |

As chaves são configuradas na aba Research (*Configurar IA gratuita*) e ficam em `data/config_ia.json`, só no seu computador. As variáveis de ambiente `GEMINI_API_KEY` e `GROQ_API_KEY` também funcionam.

## Agente de pesquisa (`agente.py`)

Analisa uma empresa: balanço, pares, macro, valuation e tese.

| Ferramenta | O que devolve |
|---|---|
| `analise_financeira` | Dossiê financeiro da empresa ou de um par (usa `financial.py`) |
| `empresas_do_setor` | Pares do mesmo setor declarado à CVM (FCA) |
| `mercado_macro` | Juros, inflação, Focus, cenário externo e comunicados (usa `market.py`) |
| `valuation` | Comparação com pares, preço justo, cenários e sensibilidade (usa `investment.py`) |
| `relatorios_ri` | Busca nos relatórios de resultados entregues à CVM (RAG, em `rag/`) |
| `ler_pagina_ri` | Lê uma página de um desses relatórios |
| `detalhe_item` | Fórmula e insumos de um número, pelo id |

- **Limites:** 14 chamadas de ferramenta, 300 s e 2 correções.
- **Validador:** números são conferidos contra os dossiês, com unidade (R$ com R$, % com %). Frases com citação `[D12 p3]` são conferidas contra a página que o agente realmente leu.
- **Sem IA, ou se a IA falhar:** o relatório usa o texto por regras do `redator.py`, e a tela avisa o motivo.

## Agente de carteira (`carteira_agente.py` + `laboratorio.py`)

Investiga por que a carteira ficou abaixo (ou acima) do Ibovespa e propõe mudanças, como num projeto de machine learning.

```
|---------------- treino (60%) ----------------|------ reserva (40%) ------|
  janela 1   |   janela 2   |   janela 3          janela 4   |   janela 5
```

1. **Diagnóstico (código, sem IA):** resultado contra Ibovespa e CDI, quem somou e quem tirou, setores, risco e concentração.
2. **Investigação:** o agente vê **só o treino**, formula hipóteses (cortar quem puxou, trocar por par do setor, diversificar, BOVA11…) e testa cada uma nas 3 janelas do treino.
3. **Confirmação:** escolhe até 3 propostas e as mede na **reserva**, que ele nunca viu. Só pode confirmar uma vez.

| Ferramenta | O que faz |
|---|---|
| `diagnostico_treino` | Diagnóstico só do período de treino |
| `testar_carteira` | Testa uma proposta de pesos nas 3 janelas do treino |
| `confirmar_propostas` | Mede até 3 testes na reserva (uma única vez) |
| `buscar_substitutos` | Empresas do mesmo setor, mais negociadas primeiro |
| `cara_ou_barata` | Leitura de valuation de hoje para uma ação |
| `detalhe_item` | Fórmula de um número, pelo id |

**Regras impostas pelo código** (o agente não consegue furar):

- renda fixa no peso escolhido pela pessoa;
- peso máximo de 40% por ativo (ou o maior peso atual, se já for maior);
- no máximo 3 ativos novos por proposta;
- no máximo 12 testes e uma única confirmação;
- sem venda a descoberto.

**Critério de aprovação** (fixo, decidido antes): render mais que a carteira atual na reserva inteira **e** nas duas janelas da reserva, sem volatilidade mais de 20% maior. Se rendeu mais no total mas perdeu numa janela, o resultado é *inconclusivo*.

- **Limites:** 18 chamadas de ferramenta, 360 s e 2 correções.
- **Validador:** exige pelo menos um teste e a confirmação antes de aceitar o texto. Os números são conferidos contra os dossiês.
- **Sem IA:** regras fixas (pesos iguais, inverso do risco, limite por ativo, sem o pior, metade em BOVA11) viram as hipóteses e passam pelo mesmo laboratório. As melhores vão para a confirmação automaticamente.

## Agente de qualidade de dados (`qualidade.py`)

Investiga os problemas que as checagens automáticas apontam num ticker e classifica cada um como:

- `dado_real`: estranho, mas correto;
- `erro_fonte`: CVM ou yfinance com dado faltando ou errado;
- `erro_calculo`: problema no cálculo do projeto.

| Ferramenta | O que devolve |
|---|---|
| `contas_cvm` | Linhas brutas de um demonstrativo da CVM, filtradas por prefixo de conta |
| `dados_yfinance` | Campos do yfinance para comparação |
| `rastreio` | Como cada valor de base foi calculado |

- **Limites:** 10 chamadas de ferramenta.
- **Validador:** a resposta precisa ser um JSON com uma causa válida para cada problema.

## Pipeline de regras fixas (`orquestrador.py`)

Roda a análise de uma empresa sem IA. Os três primeiros módulos também são as ferramentas do agente de pesquisa.

| Etapa | O que faz | Fontes |
|---|---|---|
| `financial.py` | DRE e balanço em 12 meses, rentabilidade, crédito e múltiplos | CVM (DFP/ITR/FCA), B3 COTAHIST, yfinance como reserva |
| `market.py` | Juros, inflação, Focus, cenário externo e comunicados | Tesouro, BCB (SGS e Focus), FRED, CVM IPE |
| `investment.py` | Pares, valuation, cenários, divergências e tese | Os dois dossiês acima |
| `redator.py` | Escreve o texto e valida cada número contra os dossiês | Regras fixas (ou Ollama local, opcional) |
| `relatorio.py` | Gera o Markdown e o HTML para impressão | — |

## Como rodar

| O quê | No site | No terminal |
|---|---|---|
| Pesquisa | aba **Research** → *Rodar análise* | `python -m indicadores_b3.agents.orquestrador ITUB4` |
| Carteira | **Carteira eficiente** → *Diagnosticar com o agente de IA* | — |
| Qualidade | **Saúde dos dados** | `python -m indicadores_b3.agents.qualidade PETR4 ITUB4` |

Os relatórios de pesquisa ficam em `data/research_out/`, em `.json` (dossiês completos) e `.md` (texto). Para ter o PDF, use *Abrir para PDF* e depois *Salvar em PDF* no navegador.

## Rastreabilidade (`fatos.py`)

Cada número é um item com `id` e um tipo:

- **fato:** lido de uma fonte, com documento, conta e data;
- **calculado:** tem fórmula e os ids dos números que usou;
- **premissa:** valor escolhido, com justificativa;
- **estimativa:** resultado de um modelo (valuation, cenário).

Prefixos dos ids: F = financeiro, M = mercado, I = investimento, E = laboratório da carteira, T = diagnóstico do treino.

Um dado que não foi encontrado vai para **ausentes**, com o motivo e onde obtê-lo. Ele nunca é estimado em silêncio.

**Opinião** é uma regra explícita sobre o potencial: acima de +15%, abaixo do valor; abaixo de −15%, acima do valor; entre os dois, próximo do valor. Não é recomendação.

## Valuation de bancos

- **Ke** = juro prefixado de 5 anos (curva do Tesouro) + β × prêmio de risco. Por padrão, β = 1 e prêmio de 5%.
- **g** = (1 + inflação implícita) × (1 + crescimento real de 1%) − 1
- **P/VP justo** = (ROE − g) ÷ (Ke − g)
- **Preço justo** = P/VP justo × VPA
- **Cenários** (pesos 25/50/25):
  - pessimista: ROE − 4 p.p. e Ke + 1 p.p.;
  - base: ROE e Ke atuais;
  - otimista: ROE + 2 p.p. e Ke − 1 p.p.

O relatório também mostra o **ROE implícito** e o **Ke implícito** no preço, para comparar com as premissas.

## Limitações conhecidas

- A CVM não traz inadimplência acima de 90 dias, índice de Basileia nem lucro recorrente nos demonstrativos. O agente de pesquisa procura esses dados nos relatórios de RI (`relatorios_ri`). Se não encontrar, eles ficam como ausentes, com o IF.data do BCB ou o RI do banco como fonte sugerida.
- Cada banco usa contas diferentes para despesas. Por isso, o índice de eficiência não entra na comparação entre bancos.
- A partir de 2025, a Resolução CMN 4.966 mudou a provisão para perdas. Comparações com anos anteriores não são diretas.
- No arquivo de capital da CVM, alguns bancos (o Itaú, por exemplo) informam as ações em milhares. O sistema detecta isso e avisa.
- O agente de carteira usa preços passados: uma proposta aprovada na reserva não garante resultado futuro. O *Histórico de acertos* confere as propostas a 3, 6 e 12 meses.
