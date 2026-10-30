# Instalação local

Esta é uma distribuição de fontes, não um instalador automático nem um plugin
publicado em marketplace. Leia a skill antes de instalá-la e preserve arquivos
que já existam no seu ambiente.

Para experimentar uma skill no Codex, solicite ao skill-installer a instalação
do diretório desejado deste repositório, por exemplo:

```text
Use skill-installer para instalar skills/desenvolvimento-solucoes de
https://github.com/imvictorsfriend-maker/skills-and-agents
```

Confira a [documentação oficial de skills](https://learn.chatgpt.com/docs/build-skills)
para as pastas de descoberta suportadas pela sua versão e para empacotamento
como plugin. Não substitua uma skill existente com contexto particular pela
distribuição genérica sem comparar as diferenças.

As skills não incluem credenciais, conexões, dados ou modelos. Referências a
conectores e recursos do executor exigem configuração própria. Instalar arquivos
não comprova acesso funcional a serviços nem autoriza ações externas.

## Agentes e versionamento

Os três arquivos TOML em agents podem ser copiados, após revisão, para a pasta
de agentes pessoais ou do projeto reconhecida pelo Codex. Eles herdam o modelo
e as permissões do executor principal; instrução de somente leitura não cria
sandbox. Confira a [documentação de subagentes](https://learn.chatgpt.com/docs/agent-configuration/subagents).

Os scripts de versionamento usam Git e o GitHub CLI oficial; GH_CLI pode indicar
o executável. O mapa de raízes, as autorizações exatas e os hooks são configurados
pelo operador. Sem mapa e autorização válidos, o push é bloqueado. Os testes
criam seus próprios mapas sintéticos em diretórios temporários. Instalar a skill
sozinha não instala hooks nem libera publicação.

A publicação pública requer uma decisão explícita adicional para uma distribuição
genérica auditada: projeto e destino exatos, árvore Git e manifesto revisados.
Todos os demais projetos preservam a política local/privada que o operador
definiu. Esses controles não são um isolamento de rede.
