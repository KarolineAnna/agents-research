# 0001. Núcleo próprio de agente com ferramentas, sem LangChain/LangGraph

## Contexto

Os três agentes (pesquisa, carteira e qualidade de dados) têm a mesma forma: o modelo chama ferramentas em laço até escrever uma resposta, e a resposta passa por um validador. O laço precisa:

- trocar de provedor **no meio da conversa** quando um nível gratuito estoura (ver [0004](0004-ia-gratuita-com-troca-de-provedor.md));
- devolver a resposta reprovada ao modelo com a lista de problemas e, se ele empacar, retirar só as frases reprovadas (ver [0002](0002-validador-obrigatorio.md));
- respeitar orçamento de passos e de tempo, reaproveitar chamadas repetidas e transformar exceções de ferramenta em mensagens para o modelo;
- registrar cada passo e o tempo de cada provedor, para mostrar na tela.

## Decisão

Um laço próprio em [`agents/nucleo.py`](../../src/indicadores_b3/agents/nucleo.py) (cerca de 220 linhas), falando com todos os provedores pelo mesmo formato de chat compatível com a API da OpenAI, via `requests`. Um agente é instruções + ferramentas (funções Python com esquema JSON) + validador.

Alternativa avaliada: LangGraph. Ele resolveria o laço básico, mas a troca de provedor no meio da conversa, o validador com correção e poda, e o rastro sem serviço externo continuariam sendo código próprio. Entrariam `langgraph`, `langchain-core` e integrações por provedor, com API que muda com frequência, para ganhar pouco.

## Consequências

- Poucas dependências e controle total do que vai ao modelo e volta dele; o laço é testado com provedores falsos (`tests/test_agentes.py`).
- Novas tentativas, backoff e troca de provedor são mantidos aqui, não por uma biblioteca.
- Não há checkpoint (retomar uma execução interrompida) nem pausa para aprovação humana no meio do fluxo.

## Quando rever

Se surgirem agentes que colaboram entre si com estado compartilhado, execuções longas que precisem ser retomadas, ou aprovação humana entre etapas.
