# Arquitetura, qualidade e entrega

## Decisão de arquitetura proporcional

Uma anotação suficiente pode conter contexto, restrições, opções, decisão, consequências, evidência e gatilho de revisão. Não criar um documento formal para toda edição. Um monólito modular pode atender ao produto; distribuir serviços acrescenta coordenação, consistência e observabilidade. Considerar fronteira de domínio, propriedade de dados, implantação/escala independente e capacidade de sustentação antes de dividir.

Balanceamento distribui tráfego e pode retirar instâncias sem saúde quando configurado. Terminação TLS requer proteção do trecho seguinte conforme o desenho. Afinidade de sessão pode introduzir desequilíbrio e não substitui gestão de estado. Balanceador isolado não garante alta disponibilidade, autoscaling ou mitigação DDoS; dependem de configuração, capacidade e serviços complementares. Esses componentes só são recomendados quando resolvem uma necessidade observada.

## Da especificação à evidência

| Etapa | Evidência útil | Limite |
|---|---|---|
| Decisão/regra | briefing e exemplo esperado, dono | Não prova implementação |
| Código/configuração | diff/versão e contrato afetado | Não prova execução |
| Estrutura/local | parse, build, testes de unidade/contrato | Não prova engine/dados reais |
| Execução no ambiente | ID, versão, período e resultado | Não prova reconciliação/aceite |
| Reconciliação | totais completos, bordas e oráculo independente | Limitada à população/competência/versão |
| Aceite/uso | confirmação identificada para escopo e data | Não se estende automaticamente a novas regras |

Em fonte→pipeline→extração→tela, verificar os limites onde o contrato muda. Escolher exemplos que detectem população errada, duplicação, null→zero, filtro ausente, unidade trocada ou reprocessamento destrutivo. Evitar usar só a função de produção para calcular o esperado. Em interfaces, validar a ação do usuário e os dados que ela muda; screenshot bonita não comprova comportamento.

## Operação e desempenho

Registrar apenas a observabilidade aceita no projeto, no local autorizado. Versão ou correlação podem ser úteis, mas não são obrigatórias e não justificam reintroduzir colunas, tabelas ou controles recusados. Duração, etapa e falha podem permanecer somente no console/retorno se esse for o acordo. Comparar cargas equivalentes antes/depois; gargalo de consulta não se resolve automaticamente com arquitetura web. Isolar efeito de cache, aquecimento e tamanho de dados. Distinguir sintoma, hipótese, medição, causa e correção verificada.

Para escrita/reprocessamento, verificar idempotência, partição/competência, concorrência e falha parcial. Reversão de código pode não reverter dado publicado; planejar recuperação/compensação conforme o mecanismo existente. Mudança de schema requer conferir projeção e consumidor antes de rodar carga. Para transação desconhecida, usar IDs/consulta de estado da integracoes-apis.

Fonte de enquadramento consultada em 18/10/2026: [Microsoft Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/). Os critérios de evidência acima são convenções locais de trabalho, não homologação do ambiente.
