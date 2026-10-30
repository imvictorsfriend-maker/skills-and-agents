---
name: auditar-metricas
description: Investigar divergências e reconciliar indicadores entre regras de negócio, SQL, notebooks, Excel, Metric Views e interfaces. Usar em auditorias ou conflitos materiais; carregar o contexto da área pertinente.
---

# Auditoria de métricas

Começar pela pergunta de negócio e pela skill de área. Definir população, entidade/grão, período, numerador, denominador, unidade, aditividade, exceções e fonte. Não transferir uma fórmula de outro produto sem comparar o contrato.

Rastrear somente a cadeia pertinente: origem → transformação → mart/view → extração → interface. Comparar implementação e regra acordada; fonte com data nova não é automaticamente autoridade. Conferir cardinalidade, nulos, sentinelas, tipos e chaves, além dos filtros que efetivamente atingem cada componente.

Quando aparecer conflito, apresentar as duas versões/fontes, diferença, impacto e evidência que decide ou falta. Uma diferença legítima de grão, janela, população ou finalidade não deve ser corrigida como bug. Regra substituída permanece histórica e não deve voltar a instruir o trabalho atual.

Preparar evidência discriminante: totais reconciliados, distribuição, casos de borda, duplicidade, cobertura e comparáveis. Limitar a exibição depois de calcular agregações completas; amostra não prova o total. Não somar distincts sobrepostos nem transformar associação em causalidade.

Separar estados: verificação estrutural, execução no engine, reconciliação dos resultados e aceite do negócio. Indicar exatamente a evidência disponível. Diagnóstico de desempenho requer medição comparável; suspeita de manutenção física não é causa provada.

Entregar achado → impacto → correção ou decisão necessária → critério de validação. Registrar mudanças materiais no contexto da área; trabalho simples pode terminar inline. Para execução remota, usar o conector autorizado dentro do pedido. Para arquivos, respeitar o repositório e o destino indicados pelo operador, além da ferramenta de formato aplicável.

## Apoio transversal conforme a tarefa

Para engenharia, avaliação e aprendizagem pertinentes a esta área, consultar [apoio aplicado](references/apoio-engenharia-ia.md). A referência compõe capacidades técnicas sem alterar regras, prioridades ou autorizações da frente.
