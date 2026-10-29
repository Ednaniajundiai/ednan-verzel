# Uso de IA

Usei o Claude (Claude Code) como par de programação, dentro de um
processo proprio meu usando a base do Spec Driven Development: para cada etapa, uma especificação, um plano e uma lista
de tarefas revisados por mim antes do código, com o teste de cada requisito escrito e visto
falhando antes da implementação.

## Onde usei

- análise do desafio e priorização por risco (concorrência, dinheiro e auditoria primeiro);
- desenho das decisões centrais: lock pessimista com ordem fixa, saldo comprometido derivado,
  cadeia de hashes assinada com testemunha fora do banco e pseudônimo HMAC;
- geração do código e dos testes, back e front;
- revisões de consistência entre spec, plano e tarefas antes de implementar;
- migração do backend de Node/TypeScript para Python, mantendo o contrato da API e da
  auditoria byte a byte.

## O que revisei e corrigi

- **Testes de concorrência pegaram bugs no código gerado** que passariam numa revisão comum:
  um reenvio com a mesma `Idempotency-Key` recusado como "já está ganhando", e um lance
  gravado com carimbo após o fim (cerca de 1 em 5 execuções) porque a decisão e o `INSERT`
  usavam relógios diferentes.
- **Precisão de relógio:** a comparação da janela do lance foi movida para o SQL para não
  perder microssegundos.
- **Segurança:** recusei aceitar SVG baixado da fonte externa (permitiria script na mesma
  origem) e troquei o React Router 6 pelo 7 por alertas do `npm audit`.
- **Revisões independentes** acharam, antes da implementação, um teste que nunca terminaria
  com a prorrogação e helpers que mexiam no fim do lote fora da trilha.
- **Rejeitei** lock otimista e cadeia de auditoria global, por contenção e complexidade.
