---
name: desenvolvimento-solucoes
description: "Projetar e evoluir aplicações, pipelines e serviços empresariais com arquitetura proporcional, critérios de aceite, testes e operação. Usar em desenvolvimento com múltiplos componentes ou mudanças materiais; pequenas edições não exigem esse processo completo."
---

# Desenvolvimento de soluções empresariais

## Partir do problema e do componente responsável

Recuperar briefing, regras e estado na skill da área e inspecionar o código/contratos existentes. Traduzir a mudança em comportamento observável e exemplo de aceite. Separar decisão de negócio, hipótese técnica e implementação. Identificar dependências e a menor alteração coerente; um projeto futuro pode começar pela decisão/usuário sem herdar regras de outro produto.

Escolher arquitetura a partir de domínio, volume, consistência, latência, disponibilidade, custo, equipe e operação. Comparar modularização no sistema atual, worker/fila ou serviços independentes quando a necessidade justificar. Serverless descreve forma de execução/gestão de infraestrutura e pode combinar com microserviços; não é uma terceira escolha mutuamente exclusiva. Registrar alternativa/razão e gatilho de revisão quando houver decisão material.

## Implementar e comprovar

Alterar o artefato principal ou sua fonte geradora; preservar contratos ou planejar migração do consumidor. Em defeito relevante, construir caso que reproduza o problema e discriminá-lo da correção. Red → Green → Refactor é útil para comportamento testável, sem obrigar TDD em edição trivial ou criar teste que apenas repete a implementação.

Escolher verificação pelo risco: cálculo independente e bordas para regras; contrato entre componentes para integrações; interação renderizada para filtros/telas; engine real para compatibilidade e escrita. Mock não comprova Spark/serviço real, parse não comprova dado, build não comprova jornada e execução não comprova aceite. Rodar os checks exigidos pelo repositório; evitar repetição sem nova hipótese/falha.

Quando o usuário rejeitar um comportamento existente, derivar o aceite dessa decisão, não dos testes antigos. Incluir a ausência do comportamento rejeitado como regressão quando relevante, conferir fonte geradora e artefato emitido e revisar consumidores afetados. Não recolocar uma correção autorizada entre itens adiados porque fazia parte de um pacote maior. Separar limpeza restante do escopo já autorizado.

Aplicar a última decisão explícita sobre o mesmo tema; descrever impactos sem usá-los como motivo para manter silenciosamente a regra anterior. A menor alteração coerente cobre o pedido inteiro. Para mudança de campo, regra ou parâmetro, fechar uma matriz curta com produtor, leitores/filtros, schemas/tipos, geradores, consumidores, testes e documentação. Conferir os arquivos finais depois da última geração e impedir reintrodução local do comportamento removido. Se um teste antigo exige a regra rejeitada, substituí-lo por caso discriminante; não apenas apagá-lo ou enfraquecê-lo.

Para alterações materiais, definir tratamento de falha/rollback ou compensação, logs/IDs úteis e responsabilidade pela operação. Não prometer reversão de efeitos externos irreversíveis. Em observabilidade, medir o problema antes de sugerir balanceador, cache, microserviços ou compute novo. Ler [arquitetura e entrega](references/arquitetura-entrega.md) conforme a complexidade.

Essas práticas não autorizam introduzir persistência ou controles recusados pelo usuário. Usar os mecanismos aceitos no projeto; não preservar um componente rejeitado alegando genericamente rastreabilidade ou proteção.

## Colaborar e entregar

Conectar pedido, impacto, mudança e evidência. Informar o próximo marco de validação e as lacunas materiais. Não assumir que desenvolver código autoriza deploy, envio externo ou agenda recorrente; usar a autorização já dada no pedido. A delegação segue os critérios dos acordos globais e da skill revisao-mad, quando pertinente; tarefas pequenas continuam proporcionais.

Antes de entregar, confrontar todos os itens do pedido com a implementação e os testes. Pendência conhecida e autorizada dentro do escopo exige correção, não uma nota de conclusão parcial. Bloqueio externo real deve ser apresentado especificamente. Delegação, quando autorizada, não transfere a responsabilidade pela integração e verificação da cadeia completa.

Usar integracoes-apis para fluxos entre sistemas e engenharia-ia-empresarial quando o produto envolver LLM/RAG/agentes. Preservar a regra da área em cálculos, semântica e aceite. Registrar mudanças materiais de entendimento na evolução da skill dona.
