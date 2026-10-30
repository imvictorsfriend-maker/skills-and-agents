# Desempenho: medir antes de sofisticar

Separar tempo até o primeiro conteúdo útil, duração total, fila, recuperação, ferramenta, tokens de entrada/saída e erros. Comparar qualidade e custo na mesma carga e com as mesmas versões; usar percentis e volume quando houver tráfego suficiente.

Em APIs gerenciadas, atuar primeiro no desenho: reduzir etapas e contexto redundantes, reutilizar resultados válidos, paralelizar somente independências, limitar saídas e avaliar um modelo apropriado à tarefa. Streaming melhora percepção e permite consumo antecipado, mas não prova menor tempo total de geração. Proteger qualquer conteúdo parcial que precise de validação antes de exibição/ação.

Prefix caching depende das regras e do mecanismo do provedor; conferir elegibilidade, invalidação, isolamento e custo na documentação atual. Batch API de tarefas assíncronas é diferente de continuous batching do servidor de inferência.

Quantização, continuous batching, paged KV cache e speculative decoding são majoritariamente decisões do runtime/provedor de inferência. Só projetar sua configuração quando o projeto controlar esse runtime. Avaliar memória, throughput, latência e qualidade; não prometer ganho ou equivalência numérica sem medição. Não configurar GPU própria apenas porque essas técnicas aparecem em um infográfico.

Fontes consultadas em 18/10/2026: [OpenAI, Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization); [vLLM, Paged Attention](https://docs.vllm.ai/en/latest/design/paged_attention/). Parâmetros concretos exigem verificação na versão implantada.
