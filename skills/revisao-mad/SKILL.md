---
name: revisao-mad
description: Revisar decisoes de arquitetura, propostas e mudancas materiais com autor, critica, replica e arbitragem baseada em evidencia. Usar quando houver alternativas ou risco de erro relevante; tarefas simples e calculos deterministas continuam com verificacao direta.
---

# Revisão MAD

Recursos para revisão de decisões com agentes nativos. O protocolo está instalado; a superioridade sobre revisão simples ainda não foi demonstrada por avaliação com LLM.

## Selecionar e enquadrar

O principal continua dono da entrega. Identificar a skill da área, o componente canônico, a última decisão do usuário, os consumidores e o critério de aceite. Não carregar contexto de outras áreas sem necessidade.

Aplicar MAD a decisões ambíguas ou mudanças materiais em arquitetura, IA e soluções. Para edições pequenas, formatação e cálculos com oráculo direto, usar o processo proporcional. Quando MAD for pertinente, esta skill solicita explicitamente delegação a autor e crítico nativos; o principal arbitra. Se não houver delegação no executor, declarar revisão sequencial e não alegar independência.

## Executar

1. Preparar um pacote delimitado de fontes com origem, versão e lacunas; resumos derivados da mesma origem não contam como fontes independentes.
2. Autor produz proposta com afirmações identificadas e evidências. Pode ser o implementador já responsável pelo artefato; não criar uma segunda cópia canônica.
3. Crítico recebe tarefa, critérios e fontes em contexto próprio, sem o veredito do principal. Revisar a proposta anonimizada; cada achado identifica afirmação, evidência, severidade e teste/contraexemplo.
4. Autor responde a cada achado: aceitar, rejeitar com evidência ou pedir evidência. Entregar versão revisada.
5. Principal resolve os achados e verifica a cadeia e o artefato final. Um ciclo inicial; segundo apenas para questão material com nova evidência verificável, máximo dois.
6. Encerrar com resultado, mudanças, verificações e lacunas. Medir erros corrigidos e respostas corretas deterioradas quando estiver avaliando o protocolo.

Crítico pode não encontrar defeito. Não premiar discordância, maioria, fluência ou tamanho de texto. Hipótese sem evidência não autoriza alterar regra vigente. Não pedir ou arquivar raciocínio privado.

Papéis disponíveis: mad_autor e mad_critico; mapa_tecnico é opcional para localizar componentes e contratos antes de implementar. Herdar modelo do chat salvo escolha explícita do usuário.

## Limites

A configuração não autoriza carga, deploy, envio, exclusão ou agendamento de negócio. Validar fronteira técnica no executor; prompt não cria sandbox. Código local, teste local, Spark remoto, operação recorrente e aceite de negócio continuam sendo estados distintos.

A preparação histórica e os contratos de referência estão em [estado e fontes](references/estado.json). Não confundir testes de estrutura com avaliação de qualidade do modelo.
