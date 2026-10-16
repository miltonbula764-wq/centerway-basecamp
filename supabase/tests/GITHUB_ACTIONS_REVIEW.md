# Revisão: validação C01–C03 no GitHub Actions

Estado: preparado localmente; nenhum push, execução Actions ou teste PostgreSQL realizado.
Repositório público: miltonbula764-wq/centerway-basecamp. Consulta GitHub nesta tarefa:
main = faa3bd6fe3b18176d4df45045c4458cf75f6ba75; checkout local na branch work, mesmo SHA.
Branch proposta: **review/c01-c03-permissions-ci**. Não foi criada remotamente.

## Ficheiros e escopo

- `.github/workflows/permissions-review.yml`: evento push limitado à branch proposta;
  dois jobs independentes (sql/drizzle), ubuntu-24.04 padrão, timeout de 20 minutos por job,
  fail-fast desligado, cancela execução anterior da mesma branch.
- `scripts/ci/validate_permissions.py`: adaptação ao service container; não usa initdb,
  pg_ctl, socket do script local nem instala um servidor no host. Liga explicitamente a
  127.0.0.1:5432; verifica server_version_num 17 antes de aplicar SQL. Recusa execução fora
  de um runner github-hosted. Os testes SQL existentes continuam sem alterações.
- Este documento descreve execução, limites e evidência. O diff completo inclui também
  os oito ficheiros novos e a entrada 0011 do journal já preparados para revisão.

Cada job recebe um serviço postgres:17 novo, sem volumes persistentes. Porta publicada
apenas em loopback. Autenticação trust é exclusiva deste serviço descartável; não existe
password reutilizável nem secret configurado. O token automático do GitHub tem apenas
contents:read; checkout não persiste credenciais. Sem environments, OIDC, cache de dados,
self-hosted runners, deploy, publicação, chamadas Lovable ou conexão ao Supabase real.
A tag postgres:17 mantém a versão major e pode receber atualizações minor: a versão real
fica registada nos logs. As três actions usadas estão fixadas por SHA.

## Dados, permissões e cenários

| Via | Verificação |
|---|---|
| SQL | Bootstrap sintético, replay de 0000–0010, catálogo anterior à correção, simulação de drift/reaplicação, 0011 e matriz efetiva na mesma transação |
| SQL e Drizzle | Testes anon/authenticated com claims de viewer/operator/admin; operações legítimas e isolamento entre tenants, incluindo DELETE com IDs e ausência posterior, e os dois casos C03 revistos |
| SQL e Drizzle | Reaplicação repetida, comparação de ACLs/definições/dados, incluindo fixtures C01–C03 não vazias; rollback e confirmação de zero utilizadores/tenants de teste |
| SQL | Suites históricas permissions/ingestion/c02/c03; exige marcador fail=0, sem not_run positivo e exit 3 intencional, sem confundir erro genérico com sucesso |
| Drizzle | Aplica 0000–0010 através do runner, acrescenta 0011, verifica preservação exata dos 11 registos históricos e total de 12; nova execução deve deixar o journal SQL integralmente igual; valida ACLs e acessos depois |

Para testar o upgrade, apenas a cópia descartável de meta/_journal.json começa sem a última
entrada e é depois substituída pela cópia integral do checkout. O journal do repositório e
as migrações históricas não são alterados; os registos da base são criados pelo próprio
Drizzle. O teste não insere hashes manualmente.

Os subprocessos só recebem URLs de base local explícitas. O runner executa numa pasta
separada, com cópia de drizzle, testes SQL e drizzle.config.ts. **O .env versionado não é
copiado nem carregado**. Não se instala a aplicação completa: o bun.lock contém URLs do
registry Lovable. A via Drizzle extrai dele as versões exatas já usadas de drizzle-kit
(0.31.11), drizzle-orm (0.45.4) e postgres (3.4.9), instalando apenas essas ferramentas e
as suas dependências pelo registry npm público, sem scripts de instalação e sem tokens.
Não modifica package.json ou bun.lock do projeto. O package-lock efetivamente resolvido
no CI é guardado nos logs: as dependências transitivas não estão previamente fixadas por
um novo lock local. Disponibilidade pública dessas versões ainda não foi comprovada.

O bootstrap continua a ser uma interface auth mínima; resultados verdes não comprovam
GoTrue, JWT real, PostgREST, pooling ou equivalência completa à configuração Supabase.
O catálogo limpo fica disponível para a comparação com a fotografia remota anterior;
este workflow não consulta nem escreve no remoto.

## Logs e uso pelo telemóvel

Cada job mostra no Summary uma tabela de etapas e códigos de saída. A saída detalhada de
cada comando, catálogos, versão PostgreSQL, journal Drizzle e logs do container ficam em
artifacts separados por via e tentativa. Upload com always(), retenção de **3 dias**.
Não se envia .env, código completo da aplicação, node_modules ou diretório de dados.
Em caso de falha, a via independente continua; logs já produzidos são preservados. Falha
na inicialização do serviço/runner, anterior às steps, só pode ser vista nos logs nativos
do GitHub; não há como garantir upload se o job nunca chega a executar as steps.
Os artifacts são automaticamente compactados pelo GitHub, mas o Summary e os logs das
steps podem ser consultados no navegador do telemóvel. Os ficheiros de revisão são
entregues individualmente, sem exigir ZIP.
Como o repositório é público, os logs podem ser públicos: apenas dados sintéticos e
catálogo técnico devem entrar nos testes. Retenção de artifacts não altera a política
de retenção dos logs nativos da conta/repositório, que não foi modificada.

## Primeira execução, depois de autorização separada

1. Rever o diff completo e confirmar que main não avançou. Criar a branch proposta a
   partir do SHA revisto e incluir o patch de permissões + os três ficheiros desta etapa.
2. Enviar essa branch com uma identidade autorizada a escrever ficheiros de workflow.
   O **push à própria branch dispara a primeira execução**, sem PR nem merge em main.
   Não se depende de workflow_dispatch, que exige o workflow na branch predefinida.
3. Abrir https://github.com/miltonbula764-wq/centerway-basecamp/actions e selecionar
   “C01-C03 permissions review”. Ver os dois jobs e os seus Summary/logs no telemóvel.
4. Se houver falha, conservar os logs, corrigir na mesma branch e enviar novo commit;
   ou usar Re-run jobs na execução existente. Nada disto aplica mudanças ao backend real.

Comandos que seriam usados após autorização (não executados):

```sh
git switch -c review/c01-c03-permissions-ci
# Adicionar apenas os ficheiros enumerados no diff revisto, criar um commit e então:
git push -u origin review/c01-c03-permissions-ci
```

Um push com GITHUB_TOKEN de outro workflow não dispara normalmente uma nova execução;
usar a ligação de utilizador/App autorizada, sem colocar credenciais nos ficheiros.
Não há trigger em main, PR, schedule ou workflow_run; só a branch exata é testada.

## Acessos, custos e bloqueios conhecidos

- GitHub connector: metadata confirma visibility=public, archived=false, permissões
  pull/push/admin reportadas. Isto não prova autorização específica para modificar workflows.
- Consulta de Actions runs permitida: total_count=0. Ausência de runs não prova que Actions
  esteja ativado. Não houve consulta de segredos ou dados pessoais.
- Consulta CLI de actions/permissions bloqueada pelo socket do proxy deste ambiente.
  As ferramentas disponíveis não expõem essa configuração nem quota/faturação. Portanto,
  allowed actions, enablement, limite de armazenamento e permissão efetiva de workflow
  ainda não estão confirmados. Não se alterou nenhuma política para contornar o bloqueio.
- Runner Ubuntu padrão em repositório público enquadra-se na utilização gratuita de
  GitHub-hosted Actions. Não se ativam planos, larger runners ou serviços pagos. A execução
  continua sujeita às políticas e limites GitHub; nenhuma quota disponível foi inventada.
- Há acesso de leitura confirmado via connector, mas envio de workflow continua por
  confirmar e requer a próxima autorização do utilizador. O acesso git/CLI observado está
  bloqueado neste ambiente; não se deve assumir que a permissão metadata resolve o transporte.
- PostgreSQL local continua indisponível; não se repetiram Docker/downloads bloqueados.
  A execução real deste workflow e a instalação pública Drizzle continuam pendentes.

## Verificação local desta etapa

Apenas os novos ficheiros de automação foram verificados: parsing YAML, sintaxe Python,
comandos shell embutidos e consistência da branch, versões extraídas e restrições do
workflow. O diff inclui todos os ficheiros preparados. Essas verificações não executam
PostgreSQL, npm, Docker, o runner Drizzle ou GitHub Actions e não demonstram resultados SQL.
