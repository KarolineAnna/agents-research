# 0004. Só IA gratuita, com troca de provedor no meio da conversa e modo sem IA

## Contexto

O projeto roda no computador da pessoa e deve continuar gratuito. Os níveis gratuitos têm limites por minuto e por dia, instabilidade e modelos mais fracos que os pagos.

## Decisão

- Três provedores, todos pelo formato de chat compatível com a API da OpenAI ([`agents/llm.py`](../../src/indicadores_b3/agents/llm.py)): Gemini (Google AI Studio), Groq e Ollama (local), na ordem configurada.
- Erro 429, 5xx ou demora: até 3 tentativas com backoff; depois, a mesma conversa continua no próximo provedor, sem recomeçar.
- Sempre existe o modo **Regras fixas**, que gera o relatório sem IA, e ele também é a reserva quando a IA falha ou o validador descarta o texto.

## Consequências

- Medido em 9 execuções reais: 8 precisaram trocar de provedor no meio da conversa ([`docs/resultados.md`](../resultados.md)). A troca é o caso comum, não exceção.
- A qualidade do texto varia com o provedor que respondeu; o relatório mostra qual foi.
- No nível gratuito do Gemini, o Google pode usar o que é enviado para treinar modelos. Só vão dados públicos de empresas, e o aviso está na tela de configuração.
- O Ollama evita limites e envio de dados, mas sem GPU dedicada é lento demais para o agente (minutos por resposta).
- Uma execução leva minutos (mediana de 167 s), boa parte esperando provedores.
