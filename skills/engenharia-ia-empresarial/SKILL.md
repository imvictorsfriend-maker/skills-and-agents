---
name: engenharia-ia-empresarial
description: "Projetar ou avaliar soluções com LLM, RAG e agentes empresariais: fontes, ferramentas, limites de ação e avaliações. Usar na engenharia de IA; propostas de portfólio e cálculos analíticos pertencem ao contexto do domínio."
---

# Engenharia de IA empresarial

Transformar uma necessidade de IA em um fluxo verificável, com limites e evidências de qualidade. Começar pela decisão/usuário e pela skill do domínio; esta skill não redefine fórmulas, população, autorização ou prioridade de negócio.

## Escolher o mecanismo

Comparar regra/código/SQL, chamada simples ao modelo, recuperação de documentos (RAG), workflow fixo e agente com escolha de ações. Usar o mecanismo de menor complexidade que cumpra o contrato. RAG pode apoiar uma chamada ou um agente; multiagentes só se houver benefício demonstrável e autorização para delegar. Uma skill descreve procedimentos; ferramentas executam; MCP conecta ferramentas; agenda e serviço persistente são componentes separados.

Definir entradas, saída esperada, fonte de verdade, frescor, público, ações permitidas, falhas toleráveis, orçamento e critério de parada proporcionais à tarefa. Em agentes, conservar estado explícito, IDs de efeitos externos e condições de término; parar loops sem progresso e acompanhar submissões existentes antes de repeti-las.

## Ler conforme o problema

- RAG, dados, memória, avaliação e saída estruturada: [qualidade e avaliação](references/qualidade-avaliacao.md).
- Conteúdo externo, ferramentas, ações ou dados restritos: [segurança e operação](references/seguranca-operacao.md).
- Tempos de resposta/custo medidos como problema: [desempenho](references/desempenho.md).

Para APIs e webhooks, usar integracoes-apis; para arquitetura, implementação e release, desenvolvimento-solucoes. Para detalhes atuais de OpenAI, usar openai-docs. Não presumir instalação ou acesso a uma ferramenta só porque aparece em um diagrama.

## Evidência de entrega

Entregar contrato, escolha e alternativas relevantes, casos de avaliação e resultado observado com versões e limitações. Distinguir teste local/sintético, execução no ambiente, avaliação de qualidade e aceite de negócio. Os exemplos desta skill são critérios de desenho; não são resultados nem metas empresariais aprovadas. Registrar mudança material na skill dona da frente, com fonte, motivo e estados separados.
