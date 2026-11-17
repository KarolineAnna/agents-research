# 0003. Agente de carteira com treino e reserva, regras impostas pelo código

## Contexto

O agente de carteira investiga por que uma carteira ficou abaixo do Ibovespa e propõe mudanças. Um agente que testa muitas hipóteses nos mesmos dados sempre acha alguma que "teria funcionado": é sobreajuste, o mesmo problema de escolher um modelo pelo desempenho no conjunto de teste. Instruções no prompt ("não olhe o futuro") não são garantia, porque o modelo pode ignorá-las.

## Decisão

O período é dividido como num projeto de machine learning ([`agents/laboratorio.py`](../../src/indicadores_b3/agents/laboratorio.py)):

- **treino** (60% iniciais, em 3 janelas): o único trecho que o agente vê; o diagnóstico e todos os testes usam só ele;
- **reserva** (40% finais, em 2 janelas): escondida até o fim; o agente escolhe no máximo 3 propostas e as confirma uma única vez.

O critério de aprovação é fixo e decidido antes: render mais que a carteira atual na reserva inteira **e** nas duas janelas da reserva, sem volatilidade mais de 20% maior. Rendeu mais no total, mas perdeu numa janela, é inconclusivo.

As regras ficam no código, que devolve erro ao agente quando ele tenta furá-las: renda fixa no peso escolhido pela pessoa, peso máximo por ativo, até 3 ativos novos, até 12 testes, uma confirmação. Sem IA, regras fixas (pesos iguais, inverso do risco etc.) viram as hipóteses e passam pelo mesmo laboratório.

## Consequências

- Uma proposta aprovada sobreviveu a dados que não influenciaram sua escolha, o que vale mais que um bom resultado no treino.
- Poucas propostas são aprovadas, e "inconclusivo" é comum. Isso é esperado, não falha.
- A reserva é curta (40% de 3 anos), então um resultado ainda pode ser sorte. Aprovação não é previsão: o Histórico de acertos confere as propostas a 3, 6 e 12 meses.
- Rodar o agente várias vezes na mesma carteira e escolher a melhor execução reintroduz o sobreajuste que a reserva evita.
