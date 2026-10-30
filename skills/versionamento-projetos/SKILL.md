---
name: versionamento-projetos
description: Preservar historico Git local e permitir publicacoes selecionadas de codigo revisado com autorizacoes exatas.
---

# Versionamento local e publicação selecionada

Desenvolver localmente, com branch, revisão do índice, checks proporcionais e commits coerentes. Histórico preservado continua evoluindo no mesmo repositório. Não mover o legado para organizar nem misturar mudanças de outras tarefas.

O mapa `references/ambiente-repos.local.json` pertence ao operador e não é distribuído. Identifica raízes e repositórios; cada raiz real precisa de cadastro. Mapas ausentes/invalidos bloqueiam push. Configurar o GitHub CLI oficial e autenticação no destino; `GH_CLI` pode indicar seu executável. Nunca gravar credenciais em fontes ou URLs.

`LOCAL_ONLY` bloqueia envios. `PRIVATE_SELECTED` mantém `create_remote=false` e `push=false` nos defaults e permite somente seleções explícitas por projeto, repositório privado, SHA completo, ref remota e SHA remoto esperado. Novo SHA requer seleção nova. O hook confere a conta e a privacidade atuais no github.com, a identidade do destino e a atualização exata, e inspeciona o histórico de saída. Falha de verificação bloqueia. Criação privada selecionada usa --private; ensure-remote exige projeto explícito, sem lote all. Encerrar a seleção após envio confirmado.

`scripts/ambiente.py status` consulta o mapa; `scan --project ID` lista candidatos sem adicioná-los; `ensure-remote --project ID` só verifica/cria o destino selecionado. Não existe push automático. Preservar origin e histórico, sem force, --all ou bypass de hook. Hooks não são firewall nem substituem revisão humana. Excluir dados, credenciais, documentos privados, outputs, work, caches e resultados de notebooks.

Fontes operacionais, contexto privado e configuração do operador permanecem fora desta distribuição. Um commit não comprova execução, deploy ou aceite. Medir qualidade por validação e entregas reais, sem fabricar contribuição, data ou coautoria.

Uma distribuição genérica pública exige exceção adicional explícita em `publication_policy.public_exceptions` (no máximo uma). Seus campos são `project_id`, `repository`, `source=DIRECT_USER_DECISION`, `scope=AUDITED_GENERIC_SKILLS_AGENTS`, `audited_tree` (SHA da árvore Git) e `manifest_sha256`. O projeto deve ter `classification=public_generic_distribution` e a seleção correspondente deve declarar `visibility=public`. Só esse destino pode usar --public; os demais continuam privados ou locais.

O arquivo `PUBLICATION_MANIFEST.json` usa `{schema_version:1,files:[{path,sha256}]}` e lista exatamente os arquivos da árvore, excluindo apenas si mesmo. O gate verifica os blobs imutáveis e bloqueia divergências, symlinks e gitlinks. Novo conteúdo exige nova auditoria e seleção; a exceção não é permissão permanente para qualquer commit. Auditoria semântica e revisão dos metadados/histórico continuam necessárias.
