---
name: integracoes-apis
description: "Construir ou diagnosticar integrações entre sistemas por APIs, webhooks e MCP: contrato, autenticação, paginação, idempotência e falhas. Usar em integrações concretas e reutilizar o conector autorizado do ambiente."
---

# Integrações de APIs

Antes de escolher um protocolo, definir produtor, consumidor, dono do dado, ambiente, operação e direção do fluxo. Usar o conector/SDK/CLI aprovado existente quando atender ao pedido. A disponibilidade de um endpoint não comprova permissão; não trocar identidade nem ampliar scopes para contornar negativa.

## Contrato mínimo conforme a operação

Identificar endpoint e versão, método, tipos de entrada/saída, campos obrigatórios/nulos, IDs, unidade, timezone, limites, paginação, erros e compatibilidade do consumidor. Conferir payload real autorizado e documentação atual. Usar OpenAPI/JSON Schema quando agregarem validação e contrato; schemas locais não comprovam funcionamento do serviço.

Separar autenticação de autorização por recurso/objeto/ação e tenant. Reusar OAuth/credenciais existentes sem exibi-los. Ao implementar fluxo novo, seguir o fluxo suportado pelo provedor e suas recomendações atuais; OAuth não é sinônimo de autenticação de usuário e JWT não é prova de autorização. Validar assinatura/emissor/audiência/expiração de tokens quando o componente tiver essa responsabilidade. Scopes são o mínimo necessário, sujeitos às políticas existentes.

## Operação confiável

- Timeout em escrita pode significar resultado desconhecido. Consultar operation ID/status ou reconciliar o estado antes de repetir. Reusar a chave de idempotência da mesma operação apenas conforme contrato; não inventar suporte no servidor nem reutilizar a chave para um novo payload.
- Retentar falhas transitórias elegíveis com backoff, jitter e limite; respeitar Retry-After quando aplicável. 401 pede diagnóstico/renovação suportada; 403 pede verificar permissão/política, não loop de retry. Não repetir mutações cegamente em 429/5xx.
- Em paginação, percorrer o cursor até o fim para alegar completude; tratar expiração, snapshot, ordenação e duplicações conforme contrato. Relatar parcial quando interrompido.
- Em webhooks, autenticar origem conforme o provedor, validar assinatura sobre o conteúdo original, tratar replay e deduplicar eventos. Considerar entrega repetida/fora de ordem; confirmar persistência antes de ACK quando o contrato exigir. Polling e webhook são escolhas de operação, não garantia de entrega única.

Para diagnóstico detalhado ou desenho, ler [contratos e falhas](references/contratos-falhas.md). Para conexões a plataformas de dados, reutilizar o conector autorizado e sua configuração privada local. MCP é um protocolo de integração, não um banco, executor autônomo ou aprovação de acesso.

## Evidência de conclusão

Verificar o caminho relevante ponta a ponta: requisição autorizada → efeito/resultado → leitura pelo consumidor. Registrar ID/status e campos necessários sem tokens ou dados dispensáveis. Distinguir configuração local, teste simulado, chamada real e aceite de negócio. Alterações no sistema externo continuam limitadas ao pedido.
