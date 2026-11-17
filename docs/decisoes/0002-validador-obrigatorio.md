# 0002. Todo número do texto da IA é conferido contra as ferramentas

## Contexto

A proposta do projeto é que todo número seja rastreável até a fonte oficial. Modelos de linguagem erram contas, arredondam errado e inventam valores plausíveis, e o leitor não tem como distinguir um número inventado de um real.

## Decisão

O texto final de qualquer agente passa por um validador antes de chegar à tela ([`redator.validar`](../../src/indicadores_b3/agents/redator.py)):

- cada número do texto precisa existir nos resultados das ferramentas, com a mesma unidade (R$ com R$, % com %, x com x), aceitando o arredondamento compatível com as casas decimais escritas;
- anos, datas, tickers, ids de citação, números de normas e contagens pequenas são ignorados;
- no RAG e no agente de pesquisa, uma frase com citação `[D12 p3]` é conferida contra a página que o agente realmente leu.

Se o texto for reprovado, volta ao modelo com a lista de problemas (até 2 correções). Se o modelo repetir o mesmo erro, as frases reprovadas são retiradas e o resto é aceito, desde que passe inteiro e mantenha ao menos metade do texto. Senão, o texto é descartado e entra o texto por regras fixas.

## Consequências

- Medido em 9 execuções reais: 7 de 14 rascunhos foram reprovados, e em 1 execução o texto foi descartado ([`docs/resultados.md`](../resultados.md)). Sem o validador, esses números teriam chegado à tela.
- O modelo não pode fazer contas no texto: uma diferença ou razão que ele calcula sozinho é reprovada, a menos que uma ferramenta a devolva. Por isso as ferramentas já entregam os números derivados mais úteis (diferenças contra pares, potenciais, implícitos).
- Cada correção custa uma chamada a mais ao modelo, ou seja, mais tempo e mais consumo do limite gratuito.
- O validador confere números, não argumentos: uma conclusão errada escrita com números certos passa.
