# Integração com GitHub

As ferramentas de versionamento usam Git local e o GitHub CLI oficial. A
integração faz consultas autenticadas à API REST para conferir conta, identidade
e visibilidade do repositório antes de uma publicação selecionada. Não há envio
automático de todos os projetos.

## Fluxo implementado

| Componente | Operação | Resultado verificado |
| --- | --- | --- |
| `guard.py` | `gh api user` e `gh api repos/OWNER/REPOSITORY` | Conta autenticada, identidade e visibilidade do destino selecionado |
| `ambiente.py` | As mesmas consultas antes do provisionamento | Destino existente validado ou resposta 404 estruturada tratada pelo helper |
| `ambiente.py ensure-remote --project ID` | `gh repo create` quando a criação foi autorizada individualmente | Repositório criado e relido antes de vincular um `origin` ausente |

As chamadas fixam `github.com` como host. O helper preserva um `origin` já
existente e bloqueia identidade divergente. Falha de autenticação, permissão,
limite ou resposta ambígua interrompe a operação; um timeout de criação não
provoca nova criação automática.

Uma resposta `404 Not Found` não distingue inexistência de falta de acesso a
um repositório privado. O helper pode tratar um 404 estruturado como condição
para tentar a criação já autorizada; essa tentativa pode falhar se o destino
existir ou a conta não tiver permissão. O 404 não amplia a autorização de criação.
Veja o [diagnóstico oficial de 404](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#404-not-found-for-an-existing-resource).

O operador mantém o mapa e as seleções em
`skills/versionamento-projetos/references/ambiente-repos.local.json`, que não faz
parte desta distribuição. No modo `PRIVATE_SELECTED`, a seleção identifica o
projeto, o repositório, o commit revisado, a ref remota e o SHA remoto esperado.
Uma criação selecionada usa `--private`. Somente a exceção explícita para uma
distribuição genérica pública auditada permite `--public` no destino aprovado.
Os detalhes desse contrato estão na [skill de versionamento](../skills/versionamento-projetos/SKILL.md).

O helper prepara ou confere o destino; ele não executa push. Com o hook instalado
pelo operador, o guard verifica a seleção e os objetos Git de saída. A exceção
pública também exige a árvore Git auditada e o manifesto que fecha os arquivos
e seus hashes. A autorização é relida após a inspeção do histórico. Hooks e
heurísticas complementam a revisão de conteúdo e não isolam a rede.

## Consultas de leitura

Com o GitHub CLI já autenticado, os exemplos abaixo permitem inspecionar campos
específicos. Substitua `OWNER/REPOSITORY` pelo destino autorizado. Leia o retorno
localmente e não publique informações de repositórios privados em issues.

```sh
gh api user --hostname github.com --jq '{login: .login}'
gh api repos/OWNER/REPOSITORY --hostname github.com --jq '{full_name: .full_name, private: .private}'
```

O mapa contém vínculos do ambiente, não credenciais. As credenciais permanecem
no mecanismo de autenticação do GitHub CLI; não devem ser copiadas para fontes,
URLs, mapas, exemplos ou relatórios públicos. O mapa e os históricos particulares
do operador também permanecem fora da distribuição.

## Evidência e suporte

Os testes locais usam repositórios temporários e respostas de API simuladas.
Eles verificam o comportamento dos scripts, inclusive os bloqueios, sem criar
repositórios no GitHub. Um teste simulado aprovado não comprova acesso à conta
ou sucesso de uma operação remota. Na utilização real, provisionamento, push
confirmado e execução de um sistema de negócio são estados separados.

Para reportar um problema, siga [SUPPORT.md](../SUPPORT.md), com exemplo sintético
e sem respostas privadas da API. O projeto oferece suporte por issues; nenhum
endereço pessoal é publicado como parte desta documentação.

O uso da API pode ser apresentado como integração em uma candidatura ao
[GitHub Developer Program](https://docs.github.com/en/integrations/concepts/github-developer-program).
A participação é um processo separado, com contato de suporte e aceite do
[Registered Developer Agreement](https://docs.github.com/en/site-policy/github-terms/github-registered-developer-agreement).
Este catálogo não declara filiação, aprovação do GitHub ou concessão garantida
de badge.

## Referências oficiais

- [GitHub CLI: gh api](https://cli.github.com/manual/gh_api)
- [GitHub CLI: gh repo create](https://cli.github.com/manual/gh_repo_create)
- [REST API: consultas com GitHub CLI](https://docs.github.com/en/rest/quickstart#using-github-cli-in-the-command-line)
- [REST API: obter repositório](https://docs.github.com/en/rest/repos/repos#get-a-repository)
- [Status de workflow no README](https://docs.github.com/en/actions/how-tos/monitor-workflows/add-a-status-badge)
