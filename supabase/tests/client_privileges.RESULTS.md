# C01–C03: patch de permissões para revisão

Data: 2026-10-16. Base: `faa3bd6fe3b18176d4df45045c4458cf75f6ba75`, branch local `work`.
**Estado: patch preparado, testes PostgreSQL bloqueados. Backend remoto NÃO corrigido.**

## Contrato e documentos

Lidos: AGENTS.md real do checkout, DECISIONS.md, ARCHITECTURE.md, AGENTS.md de transferência e
LOVABLE_PLAYBOOK.md anexados em 16/10. Não foram instalados no repositório. D08/D21 sustentam
perfis por tenant, RPCs controladas, RLS e testes com papéis reais. D13 resolve a ambiguidade
anterior: retornar `failed/rejected` em C03 é decisão aprovada; o rascunho `.lovable/plan.md`
está obsoleto nesse ponto. D22 e arquitetura §10 documentam o remix e o registo dos hashes
anteriores, sem provar que os privilégios foram preservados. A autorização atual permite
o patch local; substitui o limite documental da tarefa original, sem autorizar aplicação remota.

## Evidência e origem da divergência

Leituras remotas exclusivamente de catálogo no projeto `fb5e84e9-e3a9-40bf-a7ab-26c21ea1cf0a`:
PostgreSQL 17.11/aarch64; Lovable indica o mesmo SHA e `agentFinished=true`.
`privileges_remote_before.json` preserva ACLs, proprietários, defaults e memberships dos
papéis clientes, sem dados da aplicação. Consulta complementar: zero ACLs explícitas de
coluna em public. Não houve mudanças no catálogo remoto.

Comprovado:

- Objetos são propriedade de postgres. Os clientes não herdam outros papéis nesta fotografia.
- As 12 tabelas anteriores a C03 têm ALL para anon/authenticated, incluindo TRUNCATE,
  REFERENCES, TRIGGER e MAINTAIN; RLS permanece ligada.
- As 35 funções anteriores a C03 têm EXECUTE direto e herdado de PUBLIC. Os 4 helpers C03
  negam EXECUTE aos clientes; build_evidence_bundle concede-o só a authenticated.
- audit_log_id_seq concede SELECT/UPDATE/USAGE aos dois clientes; c03_refs_id_seq não concede.
- Defaults postgres/public e supabase_admin/public concedem privilégios amplos aos clientes.
  Defaults por schema acrescentam-se aos defaults globais; funções novas também recebem
  EXECUTE de PUBLIC por defeito PostgreSQL, salvo revogação global/por objeto.
- Grants históricos explícitos e o catálogo remoto divergem. O journal remoto tem os hashes
  locais, mas o relatório C03 diz que 0000–0009 foram registadas sem reexecutar no remix.

Não comprovado: quem/quando reaplicou grants ou recriou objetos. Os defaults explicam ACLs
de objetos novos, mas NÃO voltam a conceder privilégios a objetos existentes após REVOKE.
CREATE OR REPLACE FUNCTION também não repõe os privilégios revogados. Recriação de objetos
num remix/restauro sem replay dos REVOKEs, ou GRANT posterior amplo, continuam hipóteses.
Não existe evidência de que esta consulta tenha recuperado logs históricos que escolham uma.

Replay limpo de 0000–0010: preparado, NÃO executado neste ambiente. Pela leitura das migrações,
os REVOKEs devem remover grande parte da exposição observada, mesmo com defaults amplos.
Há lacunas históricas separadas: audit_log_id_seq não é restringida e _c02_cmp nunca revoga
EXECUTE de PUBLIC. Não confundir essas omissões com a exposição de todas as tabelas antigas.

## Matriz antes/depois

S=SELECT, I=INSERT, U=UPDATE, D=DELETE, X=EXECUTE. “Depois” é o alvo do patch, NÃO estado remoto.
Os três papéis de negócio usam authenticated; RLS e verificações internas distinguem-nos.
ALL abaixo inclui também TRUNCATE/REFERENCES/TRIGGER/MAINTAIN, sem grant option observado.

| Objetos | Antes anon | Antes authenticated | Depois anon/PUBLIC | Depois authenticated |
|---|---|---|---|---|
| tenants, memberships, audit_log | ALL | ALL | nenhum | S |
| subjects | ALL | ALL | nenhum | S/I/U |
| tenant_value_profiles | ALL | ALL | nenhum | S em todas as versões; U/D só draft sob RLS |
| profile_indicators | ALL | ALL | nenhum | S/I/U/D, guards de imutabilidade |
| value_profiles, indicators (legado) | ALL | ALL | nenhum | nenhum |
| ingestion_batches, observations | ALL | ALL | nenhum | S |
| c02_runs, c02_results | ALL | ALL | nenhum | S |
| c03_bundles, c03_indicators, c03_refs, c03_attempts | nenhum | S | nenhum | S |
| audit_log_id_seq | S/U/USAGE | S/U/USAGE | nenhum | nenhum |
| c03_refs_id_seq | nenhum | nenhum | nenhum | nenhum |
| RPCs públicas anteriores a C03 | X, também PUBLIC | X | nenhum | X, com autorização interna |
| build_evidence_bundle | nenhum | X | nenhum | X, admin/operator no servidor |
| helpers privados, exceto dependência abaixo | X nas antigas; nenhum C03 | idem | nenhum | nenhum |
| _cw_is_privileged | X, também PUBLIC | X | nenhum | X, necessário a triggers invoker |

Allowlist completa de 16 funções executáveis por authenticated:
is_tenant_member, has_tenant_role, my_tenant_role, _cw_is_privileged, create_tenant,
add_tenant_member, set_member_role, remove_tenant_member, create_value_profile_draft,
create_value_profile_version, value_profile_approval_issues, approve_value_profile,
effective_value_profile, import_observations, run_deterioration_analysis, build_evidence_bundle.
As assinaturas completas e 24 funções privadas estão na migração/teste de ACL.

| Caminho | Viewer | Operator | Admin |
|---|---|---|---|
| Ler tenant autorizado e C01–C03 | sim | sim | sim |
| Subjects e drafts/indicadores | não | sim | sim |
| Aprovar perfil / administrar membros | não | não | sim |
| Importar / analisar / montar C03 | não | sim | sim |
| Escrita direta em observações, runs, bundles, auditoria | não | não | não |
| Ler/escrever outro tenant sem membership | não | não | não |

## Patch e dependências preservadas

0011 usa lista explícita de objetos. Revoga privilégios apenas de PUBLIC/anon/authenticated,
depois restabelece o contrato necessário. Não altera service_role/sandbox_exec, outros
papéis da plataforma, auth/storage/extensions, RLS, triggers, bodies, dados ou algoritmos.
Sem CASCADE. Helpers de RLS permanecem executáveis; _cw_is_privileged permanece acessível
porque triggers invoker de subjects/perfis o chamam no contexto authenticated. As sequências
são usadas por audit triggers/RPCs SECURITY DEFINER, não pela UI.

### Operações preservadas e fronteiras de autorização

| Permissão | Operação / evidência atual | Grants | RLS | Triggers / verificações internas |
|---|---|---|---|---|
| subjects S/I/U | Listar clientes; criar e editar nome em `src/components/app/subject-dialog.tsx:35–38` | authenticated pode S/I/U; sem DELETE | leitura por membership; escrita admin/operator do tenant (`0000:503–508`) | creator força actor; lock impede alterar identidade/tenant; touch e auditoria (`0000:352–355`) |
| tenant_value_profiles S/U | Ler versões; editar promessa e resultado em `src/routes/_authenticated/app.perfil.tsx:366–367` | sem INSERT direto; UPDATE permitido | leitura por membership em qualquer estado; UPDATE apenas draft por admin/operator (`0001:281–284`) | `_cw_tvp_guard` impede aprovação direta/alteração de versão e protege aprovados; lock/touch/audit (`0001:84–143`) |
| tenant_value_profiles D | **Sem chamada DELETE encontrada na UI atual.** Preserva o contrato SQL anterior (`0001:285–286`) e o caminho de manutenção de drafts, coberto no teste novo | DELETE permitido, sem alargar o grant histórico | só draft do tenant por admin/operator | guard recusa apagar approved/superseded; auditoria. Retirar este caminho seria mudança de contrato separada, não necessária para corrigir o drift |
| profile_indicators S/I/U/D | Editor cria/edita (`src/components/app/indicator-dialog.tsx:68–71`); UI apaga (`src/routes/_authenticated/app.perfil.tsx:173`) | CRUD authenticated | leitura membership; escrita admin/operator (`0001:287–294`) | guard bloqueia perfil pai FOR SHARE, exige draft, impede mover indicador; FKs compostas e lock preservam tenant; audit (`0001:117–147`) |
| _cw_is_privileged X | Dependência interna, sem chamada UI: `_cw_set_creator`, guards e lock invoker | EXECUTE só authenticated além dos papéis administrativos preservados | não depende de policy própria | função **SECURITY INVOKER**, devolve `current_user NOT IN ('authenticated','anon')` (`0000:164–168`); não eleva privilégios. authenticated recebe false mesmo com claim de admin. Os triggers invoker precisam de executar este helper; revogar EXECUTE nas funções de trigger não impede o disparo dos triggers já instalados |

Nesta tabela, `0000` é `drizzle/migrations/0000_centerway_foundation.sql` e `0001` é
`drizzle/migrations/0001_tenant_value_profiles.sql`. Grants abrem operações sobre a tabela,
não escolhem tenants nem estados. RLS limita linhas; triggers e RPCs limitam transições.
Os grants de UPDATE são de tabela, não apenas das colunas usadas pela UI; a 0011 preserva
essa fronteira existente, sem introduzir uma política nova de edição de colunas.

Restantes permissões preservadas:

- tenants/memberships SELECT sustentam seleção do tenant e controlo de acesso
  (`src/lib/memberships.ts:11`); audit_log SELECT sustenta configurações
  (`src/routes/_authenticated/app.configuracoes.tsx:41`). RLS filtra membership.
- ingestion_batches/observations SELECT sustentam dados e detalhe do cliente
  (`src/routes/_authenticated/app.dados.tsx:386`, `app.clientes.$subjectId.tsx:51`).
  import_observations é chamado em `app.dados.tsx:224`; valida admin/operator no servidor.
- c02_runs/results SELECT e run_deterioration_analysis sustentam
  `src/components/app/deterioration-panel.tsx:41–67`.
- C03 SELECT e build_evidence_bundle preservam o contrato backend da 0010;
  **a interface C03 ainda não existe**, não são chamadas atuais da UI.
- create_tenant sustenta onboarding (`src/routes/_authenticated/onboarding.tsx:39`):
  qualquer utilizador autenticado pode criar o seu tenant, incluindo quem é viewer noutro.
  add_tenant_member/set_member_role/remove_tenant_member preservam administração por RPC;
  sem chamada UI encontrada para estas mutações, mantêm o contrato backend e testes existentes.
- create_value_profile_draft/approve_value_profile/create_value_profile_version são chamados
  em `app.perfil.tsx:101,183,193`; aprovação exige admin, criação/cópia admin/operator.
  value_profile_approval_issues é chamado em `src/lib/queries.ts:38`.
  effective_value_profile mantém resolução backend do perfil; não foi encontrada chamada UI.
- is_tenant_member/has_tenant_role/my_tenant_role são helpers de autorização usados pelas
  policies/RPCs; precisam de EXECUTE para avaliar os caminhos invoker. EXECUTE não substitui
  as verificações de auth.uid e membership nas funções SECURITY DEFINER.
- Nenhum grant cliente nas sequências é necessário: a escrita que as utiliza corre em
  triggers/RPCs SECURITY DEFINER. Tabelas legadas continuam sem acesso cliente.

Pré-condições recusam memberships de papéis clientes ou ACLs de coluna inesperadas, em vez
de revogar heranças/colunas indiscriminadamente. Executar integralmente numa transação.
Defaults não alterados: atuam sobre objetos futuros de criadores da plataforma, fora da lista
deste bloco. Migrações futuras devem declarar ACLs explicitamente; recriação externa pode
reintroduzir drift. Nenhum papel de plataforma recebe novas permissões nesta correção.

### Integração no mecanismo de migrações

`drizzle.config.ts:3–9` aponta para `drizzle/migrations` e usa LOVABLE_DB_MIGRATION_URL;
`bun.lock:772` fixa drizzle-kit 0.31.11. Não existe script migrate em package.json nem foi
verificada a implementação privada do executor gerido Lovable. O mecanismo verificável no
checkout é o journal Drizzle: um ficheiro SQL solto não é descoberto automaticamente.

Foi **acrescentada** a entrada idx=11, tag=0011_restore_client_privileges,
when=1792108800000, version=7, breakpoints=true em `meta/_journal.json`.
As onze entradas idx 0–10 e todos os SQL históricos permanecem iguais ao HEAD.
Isto atualiza a decisão anterior de deixar a integração pendente, conforme a autorização
atual; não reescreve o histórico nem marca migrações antigas como reaplicadas.
O timestamp é posterior a todos os existentes. O runner lê journal+SQL; não é necessário
snapshot de geração para uma alteração só de ACL, sem mudança de schema.
Não usar drizzle-kit push ou generate para esta correção (schema.ts está vazio).

No ambiente adequado com dependências do lock já instaladas, o comando do runner é
`./node_modules/.bin/drizzle-kit migrate --config=drizzle.config.ts`, com a variável de
conexão apontada **explicitamente para a base local descartável**. Não foi executado aqui.
Na aplicação futura, confirmar primeiro que o executor Lovable usa este journal e que o
journal SQL da base contém exatamente as migrações históricas esperadas. Usar um único
caminho de aplicação que registe 0011 através do runner; não aplicar manualmente e depois
falsificar ou reescrever registos históricos. A reexecução direta do SQL é testada separadamente
da segunda invocação do runner (esta deve reconhecer 0011 já aplicada e não a repetir).

## Validação e bloqueios

Verificações locais estáticas: cobertura das 40 assinaturas do catálogo pela migração,
preservação das 16 funções necessárias, ausência de instruções de mutação de dados/schema/
bodies na migração e whitespace dos ficheiros novos. Não equivalem a parser/execução SQL. Nesta revisão também passaram: `bash -n` dos
comandos entregues, compilação dos trechos Python, construção do teste populated (sem
execução SQL), preservação das 11 entradas históricas do journal e aplicação do diff
numa cópia descartável do HEAD, com comparação byte a byte dos nove ficheiros.

Ambiente: Debian 13, UID 1000. Sem postgres/psql e sem node_modules. Docker existe, mas o
acesso explícito ao socket local falha com `operation not permitted`; dockerd está em execução.
Download para preparar PostgreSQL também falhou na conexão ao proxy; pedidos de permissões
adicionais foram interrompidos antes de concluir. Nada foi instalado e nenhuma base local foi
criada. Créditos Lovable disponíveis não corrigem essas restrições nem autorizam testes remotos.

NÃO executados: replay SQL, comparação empírica clean-vs-remoto, testes de ACL, caminhos reais,
reaplicação, suites SQL históricas. Nenhum número de PASS SQL é alegado.
Build/lint/Vitest não executados: mudança exclusivamente SQL/documentação, sem dependências
instaladas; esses checks não demonstrariam a correção de privilégios PostgreSQL.

## Reprodução local preparada

Requisitos: Linux/macOS, utilizador não-root, PostgreSQL **17** já instalado e `initdb`,
`pg_ctl`, `createdb`, `psql` no PATH, Python 3, Bash e tar. O servidor deve incluir as
extensões exigidas pelas migrações. Usar checkout com este patch, sem .env remoto carregado.
Não é necessário Docker nem instalar dependências JavaScript para a via psql.
Não foi encontrada alternativa PostgreSQL local utilizável neste ambiente; não se repetiram
Docker/downloads bloqueados. Os comandos seguintes são instruções, **não resultados**.

### O que o bootstrap reproduz

Cria roles anon/authenticated NOLOGIN e service_role BYPASSRLS, schema auth, uma auth.users
mínima e auth.uid lendo sub de request.jwt.claims. Reproduz os defaults observados de
postgres/public para tabelas, sequências e funções, incluindo o default PostgreSQL PUBLIC
EXECUTE. Depois executa os SQL reais do projeto: RLS, triggers e SECURITY DEFINER não são mocks.
A sessão postgres instala schema e fixtures; os testes funcionais mudam efetivamente para
anon/authenticated e claims sintéticas de viewer/operator/admin de dois tenants.

Limitações: não reproduz GoTrue, verificação de JWT, PostgREST, autenticação HTTP, pooling,
proprietários/defaults supabase_admin, sandbox_exec, event triggers nem configuração completa
de schemas/extensões da plataforma. auth.users não tem constraints/triggers Supabase reais;
auth.uid não reproduz todas as fontes/fallbacks de GUC do Supabase. Não testa SET ROLE via
PostgREST nem credenciais de utilizadores. Os defaults modelados só valem para objetos criados
por postgres. Roles são globais ao cluster: **uma base nova num cluster partilhado não basta**.
Resultados verdes provam os caminhos SQL modelados no PostgreSQL 17, não equivalência total
ao backend remoto nem integração HTTP/browser. Não usar identidades/dados reais.

### Comandos exatos (na raiz do checkout)

O script cria cluster exclusivo, só socket Unix num diretório privado, e desliga-o mesmo
em falha. Logs ficam no diretório anunciado. Não inicia ligação TCP nem lê a URL remota.

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077
for tool in initdb pg_ctl createdb psql python3 tar; do command -v "$tool" >/dev/null; done
[[ $(id -u) != 0 ]]
[[ $(pg_ctl --version) == *' 17.'* ]]
CW_RUN=$(mktemp -d /tmp/cw-acl.XXXXXX)
mkdir "$CW_RUN/socket" "$CW_RUN/logs"
export PGHOST="$CW_RUN/socket" PGPORT=55432 PGUSER=postgres PGDATABASE=cw_permissions_review
unset PGHOSTADDR PGSERVICE PGSERVICEFILE PGPASSWORD PGOPTIONS
export PGPASSFILE="$CW_RUN/no-password-file"
trap 'pg_ctl -D "$CW_RUN/data" -m fast stop >"$CW_RUN/stop.log" 2>&1 || true; tar -czf "$CW_RUN/validation-logs.tar.gz" -C "$CW_RUN" logs; printf "Logs: %s/validation-logs.tar.gz\n" "$CW_RUN"' EXIT
initdb -D "$CW_RUN/data" -U postgres --auth-local=trust --auth-host=reject >"$CW_RUN/init.log" 2>&1
pg_ctl -D "$CW_RUN/data" -l "$CW_RUN/server.log" -o "-c listen_addresses='' -k $PGHOST -p $PGPORT" start >"$CW_RUN/start.log" 2>&1
createdb "$PGDATABASE"
psql -X -Atc 'SELECT version()' >"$CW_RUN/logs/version.txt"
run_sql() {
  local name=$1
  shift
  psql -X -v ON_ERROR_STOP=1 "$@" >"$CW_RUN/logs/$name.log" 2>&1
}
run_sql bootstrap -f supabase/tests/local_privileges_bootstrap.sql
for migration in drizzle/migrations/000[0-9]_*.sql drizzle/migrations/0010_*.sql; do
  run_sql "$(basename "$migration" .sql)" --single-transaction -f "$migration"
done
psql -X -At -v ON_ERROR_STOP=1 -f supabase/tests/client_privileges_catalog.sql >"$CW_RUN/logs/clean-catalog.json"
run_sql reapply-before -f supabase/tests/client_privileges_reapply_test.sql
run_sql correction --single-transaction -f drizzle/migrations/0011_restore_client_privileges.sql -f supabase/tests/client_privileges_test.sql
run_sql access -f supabase/tests/client_access_test.sql
run_sql reapply-after -f supabase/tests/client_privileges_reapply_test.sql
psql -X -At -v ON_ERROR_STOP=1 -f supabase/tests/client_privileges_catalog.sql >"$CW_RUN/logs/corrected-catalog.json"
# Reapply with non-empty synthetic C01-C03 fixtures, inside ONE rolled-back transaction.
python3 - "$CW_RUN/populated.sql" <<'PYTEST'
import pathlib, sys
root = pathlib.Path.cwd()
tests = root / 'supabase/tests'
access = (tests / 'client_access_test.sql').read_text()
assert access.rstrip().endswith('ROLLBACK;')
access = access.rstrip()[:-len('ROLLBACK;')]
reapply = (tests / 'client_privileges_reapply_test.sql').read_text()
assert reapply.count('BEGIN;') == 1
reapply = reapply.replace('BEGIN;', '', 1)
reapply = reapply.replace(r'\ir ../../drizzle/migrations/0011_restore_client_privileges.sql',
    "\\ir '" + str(root / 'drizzle/migrations/0011_restore_client_privileges.sql') + "'")
reapply = reapply.replace(r'\ir client_privileges_test.sql',
    "\\ir '" + str(tests / 'client_privileges_test.sql') + "'")
pathlib.Path(sys.argv[1]).write_text(access + '\n' + reapply)
PYTEST
run_sql reapply-populated -f "$CW_RUN/populated.sql"
# Older suites deliberately raise an exception to roll back: inspect their result marker.
for suite in permissions ingestion c02 c03; do
  code=0
  run_sql "historical-$suite" -f "supabase/tests/${suite}_test.sql" || code=$?
  printf '%s\n' "$code" >"$CW_RUN/logs/historical-$suite.exit"
done
python3 - "$CW_RUN/logs" <<'PYRESULT'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
for name, marker in [('correction','CW_ACL_PASS checks=812'),
                     ('access','CW_ACCESS_PASS'), ('reapply-before','CW_REAPPLY_PASS'),
                     ('reapply-after','CW_REAPPLY_PASS'), ('reapply-populated','CW_REAPPLY_PASS')]:
    assert marker in (p / (name + '.log')).read_text(), (name, 'missing marker')
for name, marker in [('permissions','CW_TEST_RESULTS'), ('ingestion','CW_INGEST_RESULTS'),
                     ('c02','CW_C02_RESULTS'), ('c03','CW_C03_RESULTS')]:
    text = (p / ('historical-' + name + '.log')).read_text()
    assert re.search(marker + r' pass=\d+ fail=0(?: |$)', text), (name, 'inspect log')
    assert not re.search(r'not_run=[1-9]', text), (name, 'incomplete coverage')
print('Expected SQL markers present; inspect raw logs and clean-vs-remote catalogue separately.')
PYRESULT
psql -X -At -v ON_ERROR_STOP=1 -c 'SELECT (SELECT count(*) FROM auth.users), (SELECT count(*) FROM public.tenants)' >"$CW_RUN/logs/fixtures-after.txt"
[[ $(cat "$CW_RUN/logs/fixtures-after.txt") == '0|0' ]]
```

Resultado esperado: exit 0 do script; `CW_ACL_PASS checks=812`; marcadores
CW_ACCESS_PASS e CW_REAPPLY_PASS; suites antigas com fail=0 e sem not_run positivo;
fixtures-after.txt = 0|0. Se uma suite antiga falhar, conservar os logs e diagnosticar:
não tratar uma exceção qualquer como sucesso nem alterar expectativas para ocultar falhas.
O teste populated usa as fixtures sintéticas do teste funcional antes do rollback e compara
hashes de dados/definições ao reaplicar; não altera o teste guardado nem dados remotos.

Devolver `validation-logs.tar.gz`, a identificação do commit e o diff efetivamente testado.
Antes de enviar, rever os logs por caminhos pessoais ou informações inesperadas e expurgá-los;
não incluir .env, URLs de conexão, credenciais, data directory nem logs do cluster de produção.
O pacote de logs inclui catálogos de objetos e dados de teste sintéticos, não dados reais.
Comparar clean-catalog.json com privileges_remote_before.json por objeto/grantee/privilégio,
não pela ordem textual das ACLs. Essa comparação empírica permanece pendente: defaults e
papéis de plataforma não modelados não constituem automaticamente drift dos clientes.

### Validação adicional do runner (mesmo cluster descartável, antes de o desligar)

Requer dependências do bun.lock **já instaladas**, incluindo drizzle-kit 0.31.11. Não fazer
instalações/downloads neste ambiente bloqueado. Em execução separada do script acima,
inserir o bloco seguinte antes do fim, para usar o cluster ainda ativo:

```bash
createdb cw_runner
PGDATABASE=cw_runner psql -X -v ON_ERROR_STOP=1 -f supabase/tests/local_privileges_bootstrap.sql >"$CW_RUN/logs/runner-bootstrap.log" 2>&1
LOVABLE_DB_MIGRATION_URL="postgresql://postgres@localhost:$PGPORT/cw_runner?host=$PGHOST" ./node_modules/.bin/drizzle-kit migrate --config=drizzle.config.ts >"$CW_RUN/logs/runner-first.log" 2>&1
PGDATABASE=cw_runner psql -X -At -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM drizzle.__drizzle_migrations' >"$CW_RUN/logs/runner-count-first.txt"
LOVABLE_DB_MIGRATION_URL="postgresql://postgres@localhost:$PGPORT/cw_runner?host=$PGHOST" ./node_modules/.bin/drizzle-kit migrate --config=drizzle.config.ts >"$CW_RUN/logs/runner-second.log" 2>&1
PGDATABASE=cw_runner psql -X -At -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM drizzle.__drizzle_migrations' >"$CW_RUN/logs/runner-count-second.txt"
[[ $(cat "$CW_RUN/logs/runner-count-first.txt") == 12 ]]
[[ $(cat "$CW_RUN/logs/runner-count-second.txt") == 12 ]]
PGDATABASE=cw_runner psql -X -v ON_ERROR_STOP=1 -f supabase/tests/client_privileges_test.sql >"$CW_RUN/logs/runner-acl.log" 2>&1
```

A URL usa host de socket local explícito; o servidor não aceita TCP. Não substituir pela
variável de ambiente do projeto remoto. Esperado: 12 registos após a primeira e segunda
execuções e ACL_PASS. Esta prova ainda não foi executada e não atesta o executor privado
Lovable. Se a instalação do driver não aceitar socket nessa URL, parar e ajustar a conexão
local; nunca recorrer à URL remota como alternativa.

## Procedimento remoto proposto — NÃO executado

1. Resolver o bloqueio local e obter resultados SQL verdes; rever patch e mecanismo de
   integração da nova migração. Confirmar projeto/commit e que não há outra tarefa a escrever.
2. Recolher client_privileges_catalog.sql, journal, contagens de dados e matriz efetiva;
   comparar com a fotografia. Rever novos objetos, papéis herdados ou ACLs de coluna antes
   de aplicar. Confirmar backup/recuperação e executor proprietário dos objetos.
3. Após autorização separada e confirmação do runner, aplicar a entrada 0011 pelo mecanismo
   Drizzle compatível, que deve registar a migração atomicamente com o SQL. Verificar a
   matriz com client_privileges_test.sql. Ensaiar localmente o wrapper do executor caso se
   exija a asserção na mesma transação; um psql posterior NÃO partilha a transação do runner.
   Não reescrever bodies nem registos históricos. Falha de verificação posterior ao commit
   exige diagnóstico e nova ação revista; já não pode ser resolvida com ROLLBACK.
4. Reconsultar catálogo e comparar: apenas ACLs clientes nos objetos enumerados mudam;
   RLS, policies, triggers, definições e contagens permanecem. Verificar também grant options,
   privilégios efetivos PUBLIC/herdados e sequências.
5. Validar leituras existentes com contas autorizadas e papéis reais. Testes que criam fixtures,
   imports ou runs no remoto exigem autorização específica; os ficheiros de testes locais
   NÃO são uma receita para executar em produção nesta tarefa.
6. Só declarar o remoto corrigido após aplicação/verificação. Se houver falha antes do commit, rollback da
   transação e diagnóstico; não restaurar automaticamente os grants excessivos como solução.

Riscos restantes: testes SQL bloqueados; causa operacional do drift não provada; defaults
permissivos da plataforma permanecem; nenhum teste HTTP/browser feito. Replay de correções,
corte temporal, UI C03 e concorrência semântica não foram alterados, conforme o escopo.
