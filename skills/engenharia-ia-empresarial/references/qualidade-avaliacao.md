# Fontes, recuperação e avaliação

## RAG e memória

Antes de indexar, identificar dono, classificação, permissão por usuário/grupo, versão e data de observação. Aplicar autorização na recuperação; texto do prompt ou filtro visual não substitui controle no backend. Propagar revogação e exclusão ao índice/cache. Preservar origem e trechos recuperáveis por documento/chunk; testar se divisão, top-k e reranking recuperam evidência suficiente e vigente. Embeddings não substituem a fonte nem garantem verdade.

Separar três problemas: evidência existe na fonte? Foi recuperada? A resposta é sustentada por ela? Medir recuperação e resposta separadamente; considerar cobertura e abstinência quando faltar evidência. Uma citação pode existir e não sustentar a afirmação. Recuperação estruturada por SQL, com contrato de entidade/grão/filtros, pode ser melhor que busca vetorial para números.

Memória de conversa, estado da tarefa e conhecimento de domínio têm finalidades diferentes. Guardar apenas o necessário, com origem, vigência e restrição de público. Preferências inferidas não se tornam decisões confirmadas. Não transportar dados pessoais de carreira para contexto empresarial. As regras locais de memória gerenciada continuam valendo; carregar a skill não autoriza gravá-la.

## Avaliação por tarefa

1. Definir sucesso observável e erros graves para a decisão. Comparar com baseline disponível (regra, consulta, processo humano ou versão anterior).
2. Montar casos representativos, de borda, ambiguidades, falta de dados, falha de ferramenta e entradas adversariais pertinentes. Separar desenvolvimento/calibração e teste; evitar que a solução veja as respostas reservadas. Massa sintética complementa casos reais autorizados, sem comprovar qualidade em produção.
3. Escolher oráculo: código para números/schema/permissões; julgamento por modelo para critérios qualitativos com rubrica; humano para ambiguidade, utilidade e aceite. Calibrar julgamentos automatizados com exemplos humanos; registrar discordância e viés. Um modelo não é seu próprio oráculo factual.
4. Avaliar caminho e resultado: fonte, filtros, ferramenta/argumentos, efeitos, resposta e falha segura. Repetir casos estocásticos o suficiente para avaliar variação pertinente; registrar número de repetições. Não impor um número universal de casos ou uma taxa de acerto para todas as áreas.

Campos úteis por caso: `case_id`, `task`, `domain`, `input`, `source_version`, `population_grain_period`, `expected_behavior`, `expected_evidence`, `allowed_actions`, `forbidden_actions`, `grader`, `severity`, `split`. Por execução: `run_id`, `case_id`, versões de modelo/prompt/código/dados, resultado, evidência, duração, consumo/custo quando disponível e status `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN` ou `NOT_APPLICABLE` justificado. Segredos e dados pessoais dispensáveis ficam fora do log.

Relatar total planejado, executado, aprovado, falho e bloqueado. Taxa de aprovação entre executados e cobertura do planejado usam denominadores separados; caso sem ocorrência/evidência não conta como aprovado. Não deixar média global esconder erro grave em permissão, cálculo ou escopo; critérios de bloqueio e limiares são definidos para a tarefa e aceitos pelo dono.

## Referência metodológica

Fonte metodológica: [Evaluation best practices, OpenAI](https://developers.openai.com/api/docs/guides/evaluation-best-practices). Definir critérios e limiares para cada tarefa com o responsável pelo domínio; esta distribuição não inclui contratos, resultados ou metas de ambientes privados.
