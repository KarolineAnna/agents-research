# Resultados medidos

Gerado em 15/11/2026 por `python -m indicadores_b3.resultados`. Os números mudam a cada execução (preços novos, novas análises salvas); o arquivo registra a última.

## Agente de pesquisa

9 execuções reais salvas em `data/research_out/`.

| Medida | Valor |
|---|---|
| Terminaram com texto aprovado pelo validador | 7 de 9 |
| ...das quais precisaram de ao menos uma correção | 4 |
| Rascunhos reprovados pelo validador (número sem fonte) | 7 de 14 |
| Texto descartado após 2 correções (entrou o texto por regras) | 1 |
| IA não respondeu (entrou o texto por regras) | 1 |
| Precisaram trocar de provedor no meio da conversa | 8 de 9 |
| Chamadas de ferramenta por execução (mediana) | 3 |
| Duração por execução (mediana) | 167 s |

Leitura: o validador é acionado com frequência; sem ele, esses rascunhos teriam chegado à tela com números sem fonte. A troca de provedor não é exceção, é o caso comum no nível gratuito. A amostra é pequena e depende das empresas analisadas.

## RAG dos documentos da CVM

**Busca** (2026-11-09 12:13, 40 perguntas, 1325 trechos no índice):

| Modo | recall@1 | recall@5 | MRR |
|---|---|---|---|
| bm25 | 95,0% | 100,0% | 0,969 |

Limitação: as perguntas desta rodada foram montadas com palavras do próprio trecho (a IA estava indisponível), o que favorece o BM25 e infla o recall. Não houve embeddings, então a busca semântica e a híbrida não foram medidas.

**Respostas** (2026-11-09 13:37, 3 perguntas, gemini · gemini-3.5-flash-lite):

| Medida | Valor |
|---|---|
| Aprovadas pelo validador de citações | 66,7% |
| Rascunhos barrados (citação inexistente ou número fora da página) | 3 |
| Recusa correta em pergunta sem resposta nos documentos | 100,0% |

Limitação: 3 perguntas não sustentam conclusão estatística; serve como teste de fumaça do validador.

## Modelos, fora da amostra

**Carteira robusta, walk-forward** (PETR4, VALE3, ITUB4, WEGE3, BBAS3, BOVA11; peso máximo 40%; janela de 252 dias, rebalanceamento a cada 21; 994 dias fora da amostra, 2022-11-21 a 2026-11-13):

| Método | Retorno a.a. | Volatilidade | Sharpe | Pior queda | Giro por rebalanceamento | Instabilidade dos pesos* |
|---|---|---|---|---|---|---|
| Pesos iguais (referência) | 16,8% | 16,7% | 0,19 | -18,3% | 0,0% | — |
| Markowitz clássico (máx. Sharpe) | 14,8% | 18,1% | 0,07 | -25,8% | 13,7% | 12,7 p.p. |
| Markowitz + Ledoit-Wolf (máx. Sharpe) | 15,0% | 18,1% | 0,07 | -25,7% | 13,7% | 12,6 p.p. |
| Mínima variância + Ledoit-Wolf | 13,2% | 16,2% | -0,03 | -14,9% | 5,3% | 3,7 p.p. |
| HRP (clusters hierárquicos) | 14,7% | 16,3% | 0,07 | -17,3% | 2,9% | 3,6 p.p. |

\* desvio-padrão médio dos pesos no bootstrap da última janela.

Leitura: nenhum otimizador ganhou da carteira de pesos iguais em Sharpe fora da amostra. Estimar retornos esperados com histórico é ruidoso; as versões que usam só risco (mínima variância, HRP) têm pesos bem mais estáveis e menos giro. Um período e uma cesta não generalizam.

**Volatilidade: GARCH(1,1) × histórica de 21 dias** (parâmetros estimados só nos primeiros 75% do período; perda medida nos 25% finais; QLIKE e MSE, menor é melhor):

| Ativo | Dias de teste | Maior variação diária no teste | QLIKE GARCH | QLIKE histórica | Melhor (QLIKE) | Melhor (MSE) |
|---|---|---|---|---|---|---|
| PETR4 | 311 | 8,2% (05/10/2026) | 2,132 | 2,160 | GARCH | histórica |
| VALE3 | 311 | -5,9% (29/04/2026) | 1,965 | 2,038 | GARCH | GARCH |
| ITUB4 | 311 | -13,7% (26/10/2026) | 2,171 | 2,176 | GARCH | GARCH |
| WEGE3 | 311 | 10,1% (22/07/2026) | 2,260 | 2,420 | GARCH | GARCH |
| BBAS3 | 311 | -29,3% (26/10/2026) | 3,348 | 2,875 | histórica | histórica |

Leitura: o GARCH teve menor QLIKE em 4 de 5 ativos. As diferenças são pequenas e não há teste de significância (ex.: Diebold-Mariano); a vantagem é consistente, não grande. Onde o teste inclui um choque de um dia muito maior que o histórico, nenhum dos dois modelos o antecipa e a perda passa a ser dominada por esse dia.

