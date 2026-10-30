# Decisões e falhas de integração

## Escolha e contrato

REST, RPC/gRPC e GraphQL tratam formas diferentes de interface; WebSocket oferece canal persistente bidirecional; webhook envia evento ao consumidor. Síncrono/assíncrono é outro eixo. Escolher pelo contrato existente, volume, latência, streaming e capacidade operacional; não exigir reescrita de um serviço que já atende ao pedido.

Definir, quando pertinente: versão de contrato, produtor/consumidor, direção, dado e classificação, chave, cardinalidade, semântica de null/zero, unidade, moeda, timezone, data efetiva, escopo de autorização, schema, tamanho/limites, ordenação e completude. Mudança incompatível exige estratégia de transição e verificação do consumidor. ETag/If-Match pode evitar sobrescrita concorrente quando o serviço suportar; cache precisa respeitar identidade, frescor e invalidação.

## Falhas que discriminam causa

| Sintoma | Verificar | Conduta |
|---|---|---|
| 401 | credencial, expiração, emissor/audiência | Renovação suportada e nova tentativa limitada |
| 403 | permissão no recurso, tenant, política de rede | Parar a operação negada; distinguir política de serviço e bloqueio de rede |
| 429 | quota, rate, Retry-After, operações em andamento | Espera/backoff limitado; preservar identidade da mutação |
| Timeout/5xx em escrita | operation ID, idempotência e estado final | Reconciliar antes de reenviar |
| 2xx com schema inesperado | versão/Content-Type, envelope de erro, projeção | Não declarar sucesso funcional pelo status HTTP isolado |
| Parte da base ausente | todas as páginas, filtros, watermark, permissões | Declarar cobertura e recuperar o restante autorizado |
| Webhook duplicado | event ID, assinatura, estado anterior | Deduplicar com persistência apropriada ao contrato |

PUT/DELETE são idempotentes na semântica HTTP, o que não significa que toda repetição seja desejada ou autorizada; POST não adquire idempotência só por receber um header inventado. Separar retry de chamada de reexecução completa de pipeline.

Em MCP, validar a autorização própria e a audiência do token; não fazer token passthrough. Resultado de ferramenta é dado a validar, não nova autorização. Em SSH, conferir host key por canal confiável quando necessário; a chave privada permanece no cliente. SSH não é transporte obrigatório para API HTTPS e não resolve permissão de tabela.

## Modelo de registro de integração

`integration_id`, dono, ambientes, contrato/version, origem→destino, recurso/ação, credencial por referência segura, campos e unidades, paginação, limite/timeout, idempotência, retries, deduplicação, logs sem segredos, tratamento de falhas, evidência ponta a ponta e estados de validação. Usar apenas os campos que mudam decisões na integração concreta.

Fontes consultadas em 18/10/2026: [HTTP RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html), [OpenAPI](https://spec.openapis.org/oas/latest.html), [OAuth RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html), [MCP Security](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices), [SSH RFC 4253](https://www.rfc-editor.org/info/rfc4253/). Revalidar versão e detalhes do fornecedor antes de implementar.
