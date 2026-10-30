# Skills and agents

[![Validate distribution](https://github.com/imvictorsfriend-maker/skills-and-agents/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/imvictorsfriend-maker/skills-and-agents/actions/workflows/validate.yml)

Reusable skills and agent profiles for solution architecture, AI engineering,
integrations, metric audits and evidence-based technical review.

Catálogo em português de instruções, contratos e ferramentas genéricas. Cada
skill carrega apenas o contexto necessário à tarefa. O conteúdo publicado é uma
distribuição revisada; configurações particulares e históricos de instalações
não fazem parte dela.

## Catálogo

| Skill | Uso |
| --- | --- |
| [desenvolvimento-solucoes](skills/desenvolvimento-solucoes/SKILL.md) | Arquitetura, implementacao e entrega proporcional |
| [engenharia-ia-empresarial](skills/engenharia-ia-empresarial/SKILL.md) | LLM, RAG, agentes, limites e avaliacao |
| [integracoes-apis](skills/integracoes-apis/SKILL.md) | APIs, contratos, idempotencia e falhas |
| [auditar-metricas](skills/auditar-metricas/SKILL.md) | Reconciliacao de formulas, graos e fontes |
| [revisao-mad](skills/revisao-mad/SKILL.md) | Autor, critica, replica e arbitragem com evidencia |
| [versionamento-projetos](skills/versionamento-projetos/SKILL.md) | Git local e publicacoes selecionadas auditadas |

Veja também o [catálogo legível por ferramentas](CATALOG.json) e as
[instruções de instalação e limites](docs/installation.md). A
[integração com GitHub](docs/github-integration.md) descreve as consultas à API,
as publicações selecionadas e o que permanece local. Para bugs e perguntas,
consulte [SUPPORT.md](SUPPORT.md).

Os perfis [autor](agents/mad-autor.toml), [crítico](agents/mad-critico.toml) e
[mapa técnico](agents/mapa-tecnico.toml) apoiam a delegação nativa. O principal
integra a entrega; a crítica pode terminar sem achados. Não há benchmark que
comprove superioridade geral do MAD nesta distribuição.

## Verificar

Requer Python 3.11 ou superior e Git. Os testes usam repositórios temporários e
respostas simuladas; não criam repositórios no GitHub nem executam sistemas de
negócio.

O indicador no topo acompanha o workflow de validação da branch `main`. Ele
mostra o estado de CI; não representa uma conquista pessoal ou certificação.

```sh
python scripts/validate_distribution.py
python -m unittest discover -s tests -v
python -m unittest discover -s skills/versionamento-projetos/tests -v
```

O manifesto fecha todos os arquivos versionados, exceto o próprio manifesto.
Após editar e preparar os arquivos no índice, regenere-o e confira o diff:

```sh
python scripts/validate_distribution.py --write-manifest
git add PUBLICATION_MANIFEST.json
python scripts/validate_distribution.py
```

## Proveniência e licença

Esta distribuição de autoria do projeto usa [licença MIT](LICENSE). Ela contém
somente métodos, perfis e ferramentas genéricos. Credenciais, dados, relatórios,
contextos de clientes e mapas de ambientes particulares ficam fora do catálogo.
Verificações automáticas são heurísticas e complementam a revisão de conteúdo.

Materiais de outros autores mantêm suas próprias licenças. Para exemplos
oficiais, consulte [OpenAI Plugins](https://github.com/openai/plugins) e a
[documentação de skills](https://learn.chatgpt.com/docs/build-skills). O catálogo
antigo [openai/skills](https://github.com/openai/skills) está marcado como
descontinuado pelo mantenedor. Nenhum pacote de terceiros é espelhado aqui.
