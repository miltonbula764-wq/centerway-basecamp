# CENTERWAY 3.0 — M00: inventário e decisões (2026-11-03)

> Estado da auditoria, não prova de integração real nem autorização de publicação. As secções históricas abaixo pertencem a missões anteriores e podem ter limites já desatualizados. Fonte: código na branch de referência `recovery-mvp/mvp-first-functional-proof` (commit `cab5268`), PR #83 e documentos F01–F06.

## Objetivo único do novo MVP

Uma SaaS autorizada → recolha automática → avaliação de resultados verificáveis → deteção/investigação → **uma ação externa permitida** → nova medição → dashboard de leitura. Sem formulários diários para o fundador. Não interpretar login/cliques como valor comprovado; ausência ou contradição de dados significa inconclusivo, nunca ausência de valor. Melhorias observadas não provam causalidade.

## Inventário de retenção (verificação de deployment ainda pendente)

| Área | Decisão M00 | Justificação |
| --- | --- | --- |
| `recovery-mvp/sql/001–008` (F01–F06) | REUTILIZAR, adaptar somente onde necessário | Versionamento, deteção, investigação, controlo de intervenção e verificação já existem. |
| `recovery-mvp/api/` | REUTILIZAR | API autenticada L01 e isolamento por principal PostgreSQL; sem ingestão SaaS automática conhecida. |
| `recovery-mvp/managed/` + Neon/Render | PRESERVAR E VERIFICAR | Perfil de backend sintético documentado; ligação à implantação efetiva não verificada nesta auditoria. |
| `recovery-mvp/lovable-ui/` | ADAPTAR na M06 | UI existente privilegia operações manuais; futura UI founder deverá ser de leitura, baseada em evidências. |
| `recovery-mvp/sql/006_synthetic_interventions.sql` | PRESERVAR COMO TESTE; NÃO VENDER COMO REAL | F04 só altera uma flag sintética; primeira ação real requer conector/credenciais/autorizações limitadas. |
| `recovery-mvp/tests/`, API/testes, browser CI | MANTER | Prova de regressão, isolamento e segurança; não eliminar só por serem testes sintéticos. |
| `recovery-mvp/gate1/`, `operations/`, `infra/` | CONGELAR DESENVOLVIMENTO, SEM APAGAR AINDA | Documentos e utilitários de segurança/recuperação podem ser necessários; dependências/implantação ainda não verificados. |
| Aplicação legada na raiz `src/`, `supabase/`, `drizzle/` | CANDIDATA A REMOÇÃO FUTURA, BLOQUEADA | Ligação Lovable/main e possíveis dependências de publicação não foram descartadas; não apagar prematuramente. |
| `recovery-mvp/manual/` e UI T02 | CANDIDATO A RETIRAR DO FLUXO DO FOUNDER | Ainda utilizados no teste sintético completo; substituir por execução autónoma antes de remover. |
| Variáveis locais de frontend no `.env` versionado | RETIRAR DA BRANCH M00; manter `.env.example` | Configuração específica não deve ficar versionada na base do MVP; passar por configuração do ambiente. |


## Bloqueios semânticos prioritários revelados na auditoria

- **F01/F02** chamam estados `valor_demonstrado` e `deterioracao_demonstrada`,
  mas apenas avaliam critérios contratuais sob evidências declaradas pelo produtor;
  `verified` não é verificação independente. **M02 deverá impedir o dashboard de
  traduzir esses estados em prova de benefício empresarial externo.**
- **F02** compara janelas rígidas e não infere sazonalidade, maturidade,
  normalização ou causalidade. A primeira SaaS precisa de cadência, política de
  suficiência e testes de falsos positivos específicos do indicador.
- **F03** só investiga fatores explícitos ou regras configuradas; não recolhe
  automaticamente provas de sistemas externos nem demonstra causas.
- **F04** só altera `set_synthetic_flag`; qualquer integração com APIs reais
  requer um novo executor externo sob política específica, observabilidade
  e autorização efetiva. Não reutilizar a flag como prova de intervenção real.
- **F05** observa antes/depois mas não atribui causalidade; a métrica comercial
  do MVP será "melhorias observadas em casos elegíveis", com denominador e
  inconclusivos expostos, nunca "clientes recuperados" sem definição e prova.
- **F06** oferece portas idempotentes, mas **não** possui worker ou scheduler
  autónomo. Conectar os motores requer coordenador simples e retomável.

## Lacunas comprovadas — missão seguinte

1. **M01:** escolher uma única SaaS com fonte de resultados e permissão contratual; implementar importação histórica + atualização incremental, proveniência e recuperação de falhas, sem dados reais antes de consentimento.
2. **M02:** adaptar critérios de suficiência e tendência por indicador; usar `inconclusivo` onde não há provas; evitar falsos positivos de redução de uso.
3. **M03:** automatizar descoberta e investigação somente dentro de regras verificáveis; distinguir causas, hipóteses e desconhecidos.
4. **M04:** adicionar **um adaptador de intervenção real** autorizado, idempotente e auditável; F04 atual é estritamente sintético.
5. **M05:** verificar resultado após ação com janelas comparáveis, sem prometer causalidade ou taxa de recuperação.
6. **M06:** agendar execução confiável e criar dashboard read-only; só depois desligar componentes antigos.

## Regras de eliminação

Remover código antigo **somente** após: (a) identificar consumidores/referências, (b) validar o caminho substituto, (c) correr testes relevantes, (d) confirmar que nenhum deploy usa a versão removida. Não apagar históricos ou migrações aplicadas, RLS, auditoria, backups necessários ou testes de segurança. Fazer alterações numa branch e PR; nunca reescrever histórico, merge automático ou deploy. Não gastar créditos de agentes pagos nem contratar infraestrutura.

## Resultado M00, primeira passagem

- Branch isolada criada a partir do candidato F01–F06 testado; `main` não modificada.
- A cadeia de PRs F01–F06 ainda não está integrada na `main`, que continua com a aplicação legada.
- O teste sintético da PR #83 documenta o ciclo completo na interface, mas **não** prova integração com SaaS real, intervenção externa real, agendamento ou atribuição causal.
- O serviço implantado no Render e o frontend Lovable efetivo ainda necessitam de identificação antes de remover código e workflows que possam alimentá-los.
- A grande poda de código legado fica **deliberadamente bloqueada** até essa verificação; nada é classificado como inútil apenas por ser antigo.

---

# Confirmed CENTERWAY MVP state

## T03-G1 — diagnóstico preparado (issue #74)

Base T02/PR #72, aecc8aca64a9d7ce333dc1a907b5661132ba1ccd.
See GATE1_CONNECTIVITY.md. New dispatch-only workflow for a future protected-environment
DNS/TCP5432 diagnostic; no PostgreSQL protocol, login, SQL, backup or credential input.
Hostname secret only; bounded subprocess, fixed sanitized status codes, no DNS/IP output
or artifacts. Separate PR CI performs only lint/contract and simulated security tests
without secrets or live DNS/TCP. Engines, API, frontend and prior workflows unchanged.
GitHub default-branch workflow registration, protected environment, actual dispatch
authorization and hostname configuration remain pending; no main changes to enable them.
No connectivity to Neon from Actions, encrypted external backup or isolated restore is
asserted. Private durable destination and holder's public age recipient remain pending.
T03 Gate 1 is NOT complete; Gates 2–5 remain blocked. No Neon/Render/Lovable changes,
real secrets, public database mutations, paid infrastructure or Lovable credits.
Local validation: actionlint 1.7.7 and 15 tests passed (Python3.12); no live Neon
probe. Remote CI proof must be read on the delivery PR's exact commit.

## Work Mode continuation — 2026-10-31

The historical mission-specific exclusions below describe their original deliveries.
Current integrated candidate: PR #64, `705db9cb009ca672aab407c86d82ea5c05614903`,
containing #49–#62 by ancestry; no main merge. Six workflows succeeded on that SHA:
97 backend tests and eight real-Chromium compatibility tests twice on fresh stacks.
The actual Lovable frontend remains at `149ee23a60618b577e9535ce8c121d34813741a2`:
178 tests, frozen lockfile, TypeScript and build independently validated in Work Mode.
Session lifecycle fixes were applied there; the live UI transport is still inactive.

PR #65 adds `recovery-mvp/operations/`: age-encrypted cold backup of the synthetic
C03 profile, physical restore to new volumes, fail-closed archive checks and a
read-only readiness probe. The first six actual PostgreSQL/HTTPS recovery tests
passed on `ff06eab7994ba528262c366b570288689d5f3e85`; consult PR checks for the final
revision. New systemd readiness templates are prepared, not installed or activated.
No existing engine, migration, API, Caddy or C03 lifecycle implementation changed.

Hosting remains blocked on an authorized persistent host/account. No public backend,
hosted frontend-to-API proof, external backup copy, real data, real intervention,
customer pilot or production readiness is asserted. No new Lovable credits or
infrastructure expense in this continuation. See WORK_MODE_AUDIT.md and
recovery-mvp/operations/README.md for boundaries and operating instructions.

Independent implementation is in recovery-mvp/. Legacy application remains separate.

| Mission | Implemented base | Scope |
|---|---|---|
| F01 | PR #49, 2a06c47 | Versioned value contracts, provenance, isolation and audit |
| F02 | PR #50, 45f7555 | Deterministic deterioration detection and frozen snapshots |
| F03 | PR #51, 9d0a28e | Structured investigation and recorded verification |
| F03.1 | PR #52, 074630f | Rule discovery and batch routing to F03 |
| F04 | PR #53, 9f964c2 | Authorized decisions, isolated reversible synthetic execution |
| F05 | PR #54, 1523a18 | Versioned before/after verification of contractual value |
| F06 | PR #55, c4d9756 | Idempotent operations and client journey projection |
| L01 | PR #56, d32c6e8 (CI run 40902550601 succeeded) | Authenticated HTTP transport, per-user PostgreSQL identity, local synthetic demo and independent CI |
| L02.2 | Interface prepared, reported by user; not inspected in C01 | External Lovable project remains untouched |
| C01 | PR #57, 3b9d3a2 (both CI workflows succeeded) | HTTPS configurations and local synthetic TLS tests; no publication/external verification |
| C02 | PR #58, 9d8c124 (both CI workflows succeeded) | Authenticated, bounded client directory with persisted names; additive HTTP SQL read port; 79 local checks passed; remote CI tracked on the delivery PR |
| C03 | PR #59, eeae52e (three CI workflows succeeded) | Persistent synthetic HTTPS installation and full fixture; 83 local checks passed; no cloud account/resource/publication |

| L03-PREP / B01 | PR #61, 503eb0e (four CI workflows succeeded), issue #60 | 71 sanitized real-C03 API examples; versioned handoff/schema; 90 local tests passed; no deployment or Lovable changes |

| C04-PREFLIGHT | Current branch recovery-mvp/c04-browser-preflight | Local HTTPS/CORS audit, OPTIONS logout correction, browser handoff and publication NO-GO checklist |

These are implementation states, not assertions of merge, deployment or production use.
Run `./recovery-mvp/tests/run-f03.sh` for regression and discovery integration tests.
See recovery-mvp/DISCOVERY.md for the discovery contract and limitations.

F04 contract and limitations: recovery-mvp/INTERVENTION.md. No production execution or value recovery is asserted.

F05 contract and limitations: recovery-mvp/RECOVERY.md. Observed recovery does not establish causal impact.

F06 integration contract: recovery-mvp/ORCHESTRATION.md. No frontend or deployment has been implemented.

L01 integration and local execution: recovery-mvp/api/README.md. Local test success is not production readiness or a remote CI result. No frontend or production deployment.

C01: recovery-mvp/infra/README.md and RESEARCH.md. Infrastructure prepared and locally tested only. Public DNS, host, actual Lovable origins and public CA certificate activation remain pending. No paid resources, publication or external HTTPS proof.

C02: recovery-mvp/api/README.md (C02) and openapi.json. Only client_id/display_name
from persisted clients, HTTP scope plus current session_user tenant membership. No
engine/RLS changes; clients remains unreadable directly by centerway_api. Install the
additive api/sql/001_client_directory.sql once before using the new endpoint. Per-client
scope remains HTTP-side as in L01. Pagination is bounded, not a cross-request snapshot.
No frontend change, publication, external connectivity or production readiness claimed.
Validation: ./recovery-mvp/infra/test.sh passed locally: 60 unchanged engine tests,
11 HTTP tests (seven L01 + four C02), eight verified-TLS tests (seven C01 + one C02),
79 total. GitHub Actions runs both suites independently on the delivery PR; consult
the checks on the exact commit for the remote result. All fixtures are synthetic.


C03: recovery-mvp/cloud-demo/README.md and RESEARCH.md. Conditional recommendation:
Oracle Always Free A1 ARM64, 1 OCPU/4 GB, 50 GB boot; current documented allowance is
2 OCPUs/12 GB total, not the former 4/24. Eligibility/capacity, real host, ARM execution,
DNS, mobile operation and external TLS remain unverified. US$0 is conditional on the
actual account/quotas; no paid resources, external accounts or servers were created.
Persistent PostgreSQL 17 and TLS volume, private SQLite/config/PKI, separate demo roles,
fixed image digests and migration hashes. Setup/fixture refuse automatic reseeding.
Full fixture uses authenticated API/orchestration; all evidence, outcomes and test
review records are explicitly synthetic; independent verification/causality are not
established. Only a preauthorized isolated reversible flag can execute (one attempt,
risk <=1, 24-hour policy). API/engines/C01/C02 files remain unchanged.
Validation: ./recovery-mvp/cloud-demo/test.sh passed locally (Python 3.12.14, x86_64):
60 engine + 11 HTTP + eight HTTPS + four persistent-demo tests = 83 checks. The final
persistent suite was also repeated after transport/state guards were added. Includes
full pipeline, authorized directory, role/tenant isolation, PG/API/gateway restart,
durable sessions/receipts, idempotency/audit and failures. Remote results are tracked
by the delivery PR's three independent GitHub Actions workflows on the exact commit.
Prepared only: future domain api.getcenterway.com; no DNS, email, Lovable or main
changes, public bind or public ACME requests. No real deployment/external HTTPS proof,
production readiness, VM restore or load benchmark. Internal certificates expire;
rotation and backups/restore require future operational work. Do not advance to L03.


L03-PREP / B01 (issue #60): LOVABLE_HANDOFF.md and recovery-mvp/integration/.
Base PR #59 eeae52e preserved byte-for-byte for SQL, engines/tests, production API,
C01/C02 and C03. New test-only collector reuses the real C03 Scenario and HTTPS stack.
71 canonical versioned cases cover login/session, client directory/pagination, staged
journeys, completed receipts with blocked/executed business results, persisted engine
error, F03 gaps/review, F05 inconclusive/complete recovery, identity/isolation,
idempotency/audit, HTTP 401/403/404/409/422/503 and an actual network refusal.
All input is synthetic. Only typed placeholders are exported for login passwords,
session tokens, generated UUIDs, dynamic clocks and input fingerprints; references,
versions, business windows/scalars/states/nulls and original declared content digests
are preserved. No raw HTTP, secrets, DSNs, PII or ephemeral identifiers in artifacts.
Reader's second-client access is an explicit temporary test grant for pagination,
never a new product permission; session invalidation is captured and documented.
Validation: ./recovery-mvp/integration/test.sh passed locally: 60 engine + 11 HTTP +
eight HTTPS + four persistent C03 + seven handoff tests = 90 total. The 71 examples
are cases inside the new suite, not 71 extra tests. A fresh live execution is compared
to the canonical export with strict contracts/typed reference bindings; malformed or
unknown data and secret leaks fail closed. The new independent GitHub Actions workflow
repeats the seven tests; the three previous workflows remain unchanged. Remote results
must be read on the delivery PR's exact commit. No goldens are updated automatically.
Prepared only for offline integration work. No Lovable-hosted transport/mapper proof,
external HTTPS, cloud account/resource, DNS/domain/email change, frontend login or real
intervention. Main unchanged. No paid infrastructure, service publication or automatic
advance to L03. C03 operational limitations remain; the handoff is not production readiness.


C04-PREFLIGHT: BROWSER_HANDOFF.md; recovery-mvp/browser/. Base PR #61 503eb0e.
L03-OFFLINE and 104 Lovable tests reported by the user, not independently executed;
not added to backend counts. Seven new tests use real C03/C01 loopback HTTPS and
browser headers, not a browser engine or hosted frontend. Audit found OPTIONS DELETE
/v1/session was refused because GET/DELETE have separate Flask rules. The sole API
correction resolves all methods for the same path, intersected with GET/POST/DELETE.
CI permits only that exact substitution; authentication, scopes, RLS and engines
remain unchanged. Proxy/TLS configurations and the 71 integration examples unchanged.
Local ./recovery-mvp/browser/test.sh passed: 90 regressions + seven C04 = 97 tests.
Includes 14 preflight subcases, origin spoof/lookalike rejection, four PG principals,
session/logout/expiry, client scope, operations/replay/conflict/error, audit/RLS and
PG/API failure. New independent CI workflow; remote proof on delivery PR exact SHA.
No actual origins supplied yet: reviewed origins.json is empty, activation NO-GO.
Offline origin comparator does not grant authority or edit configuration. Gateway 503
without API CORS headers may appear opaque to cross-origin browsers; documented.
No hosted browser, external TLS, DNS, cloud, paid infrastructure or public service.
Lovable and main untouched; public GO requires separate authorization and all pending
gates. No integration-live completion or automatic advance is asserted.

## T01 — adversarial fixture preparation (issue #69)

Base recovery-mvp/m68-live-frontend, 5086e33dc438fbc3e5d9f08014d2df21d3745a37.
See recovery-mvp/adversarial-t01/README.md for inspected contracts, fixture mapping,
private offline preparation, gated future activation and exact hosted UI links/limits.
New AtlasOps Cloud/Meridian Distribuição tenant/client, deterministic namespace IDs,
three private individual PostgreSQL accounts, signed synthetic contract/global window
plus eight explicit weekly revisions, eight outcomes (S7 partial), seven contextual
sources with real fixture-file digests, two deferred discovery inputs, one synthetic
flag/catalog and ZERO intervention policies. Usage/CSV/context are not coerced into
compatible outcome measurements. The 14/10 integration observation belongs to S7.
S9 is quarantined in future/s9.json and never loaded by the initial seed.

Operator-only two-phase provision/load: actual session_user writes F01 data; bootstrap
and version/data writes audited. Separate transactions permit real login identity and
resumable interruption; same private bundle replays without new rows, including under
concurrency. Collisions, role/scope/content drift or changed fixture fail closed. No
password reset, destructive reset, schema migration, broad permission or engine/API/UI
change. Config candidate is exact additive copy; offline activation comparator rejects
intervening configuration drift. Remote targets blocked unless operator deliberately
opts in and confirms exact tenant; those flags do not replace future authorization.
Existing A/B rows, evidence/audit and receipts verified unchanged in local snapshots.

Local validation: 11 new PostgreSQL17/TLS/API tests; existing 97 backend regressions,
11 managed and 189 frontend passed; frontend public opt-in test skipped (no credentials
or public calls), TypeScript passed. New independent CI repeats T01 and unchanged UI,
prior backend/managed workflows retain their guards. Remote CI results are recorded
on the delivery PR for the exact SHA, separately from these local results.

No Neon public database access/mutation, service publication, DNS, paid resources,
Lovable use/credits, merge or main changes. No T01 detection/discovery/investigation,
intervention, verification or recovery evaluation pre-executed. Initial work item is
detect. Current M68 UI permits authenticated consultation/refresh/logout and conditional
re-evaluation/intervention/undo for EXISTING investigations/executions/plans; it cannot
create contracts, measurements, detections, investigations, reviews or recovery plans.
Full manual F01–F06 solely through current UI is therefore unavailable; operator/API
steps require explicit later choices, never fabricated seeded conclusions. Public T01
activation/login and human acceptance remain pending separate authorization.

## T02 — manual journey controls (issue #71)

Base PR #70/ec407d4, branch recovery-mvp/t02-manual-journey. See
recovery-mvp/manual/README.md for real endpoint mapping, human T01 steps, deployment
prerequisites and limitations. Existing ten F06 commands reused; no SQL engine,
migration, T01 seed, old fixture or managed runtime changes. Minimal API extension:
GET manual-context, scoped/authenticated read-only repeatable-read F03 records,
F04 configuration/policies for session_user and last100 client audit (other principals'
policy events filtered), explicit truncation, no grants/inference/write/receipt.
Additive openapi-t02.json t02-v1 (original c02-v1/71-case capture unchanged); CI permits exact reviewed API/spec hashes, not arbitrary changes.

Client detail now exposes typed manual forms for F01 source/contract/evidence,
F02 selected revisions/cutoff, F03 opening/factors/evidence/review/evaluation,
F03.1 explicit company discovery, F04 request/undo, F05 windows/evaluation, F06 GET
refresh/receipts/audit. Existing visual identity preserved. Immutable memory drafts,
explicit scope confirmation, identical-key user resend after lost response, no
automatic POST retries or invented defaults/results/verification. Session/tenant
boundaries and late-response guards preserved. SHA-256 optional local file hashing
is not upload or independent verification. No self-authorization interface.

Actual application Chromium suite uses local HTTPS, C01 API and real PostgreSQL17,
clicks only for writes, separate synthetic T02 data (never operates T01), desktop and
390x844 mobile/touch. Tests include full pipeline with separate synthetic reviewer,
uncertain and unauthorized interventions blocked, recovery inconclusive, actual
committed response lost/replayed once, reader/reviewer permissions, refresh/login
and expiry. T01 API tests seed only the initial local fixture and assert no detection,
investigation, intervention or recovery executed. Existing regression suites retained.
Local/CI evidence is recorded on the delivery PR for the final SHA; it is not hosted
acceptance. No public Neon/Render access/mutations, Lovable use/credits/publication,
new accounts/resources on public services, main change or merge.

T01 activation and publishing backend/UI require separate authorization. Snapshot in
this repo is not proof of the actual Lovable GitHub/publication channel. Current live
M68 frontend does not have these controls. Context documents remain outside the API,
CSV meaning is not inferred, T01 has zero policies and S9 remains future-only. The
full manual UI can request legitimate steps and show blocks/inconclusive results;
it does not grant missing permissions or guarantee a successful intervention/recovery.

T02 local validation confirmed: 97 previous backend +11 managed +11 T01, six new
API tests,210 frontend tests (189 previous +21 new; one public opt-in skipped),
TypeScript/build and five actual-app Chromium tests passed. Local Chromium154,
HTTPS/PG17 and 390x844 mobile/touch; CI installs pinned Playwright1.62 Chromium.
Positive synthetic execution/undo is demonstrated only in disposable T02 with an
explicit test-admin bounded policy; T01 is never operated or granted a policy.
Original c02-v1 OpenAPI and 71-case canonical capture remain unchanged: new read
contract is separately versioned api/openapi-t02.json. No golden regeneration.

T02 audit error receipts are sanitized like journey responses; SQL messages remain only
in the immutable database history, not in the HTTP context. Verified by a real rejected
F06 input, with no T01 engine execution.

## T03-G2 — encrypted export and isolated restore preparation (issue #76)

Base PR #75/435c2d4. See recovery-mvp/gate1/README.md. Additive PG17 verified-TLS
stream export to age; encrypted snapshot baseline and role manifest; all database
sessions included, runtime secrets excluded with separate custody required. Restore
accepts no target DSN: fresh local networkless PG17 Docker sandbox, restricted
NOLOGIN roles, data/schema/RLS/ACL/identity comparisons and unconditional cleanup.
Existing engines, backups, API, frontend and T01 remain unchanged. Synthetic-only
CI; sensitive manual workflow has a literal disabled export job and fails closed.
No independent reviewer exists; TCP exemption does not authorize credential use.
Remote TCP success was reported by the user; no real export/restore/custody is
claimed. Destination, private-key custody and sensitive executor controls pending.
No Neon/Render/Lovable/main changes or paid services; T03 Gate1 remains blocked.
Local G2 validation: 14 synthetic tests passed, actual PG17 TLS export/age and
networkless restores, security failures and concurrent snapshot; actionlint1.7.7
passed. CI results tracked on the delivery PR, separately from local proof.

## T03-G3 — private custody handoff (issue #78)

Base PR #77/fb925f9. Holder reports tested Android age identity and encrypted key
copy/private backup folder in Drive; no actual Neon backup claimed. See
recovery-mvp/gate1/PRIVATE_RUNBOOK.md. Additive offline public-recipient fingerprint
and ciphertext return verifier; no key/DSN/database access. Existing G2 export,
restore and literal workflow lock unchanged. Temporary limited role requires later
provider privilege validation/authorization; no RLS changes or admin fallback assumed.
Private Docker-capable executor remains necessary; normal Termux is not proof of it.
Drive folder metadata only: separate backup/key folders, backup shared=false; no key
contents, uploads, Neon role changes, real exports, service/main changes or cost.

## T03-G5 — final Gate1 proposal (not executed)

See recovery-mvp/gate1/GATE1_FINAL.md. Residual LO writes are a proposed accepted
risk only in a disposable child, without modifying cloud_admin/PUBLIC. Provisioning
BYPASSRLS on Neon remains unproven; fail closed, never export as cw_owner fallback.
Minimal transport addition authenticates age on Android then passes bounded payload
through private authenticated SSH to the existing isolated restore; no identity key
sent to Codespaces. Two new transport tests and one synthetic PG17 integration passed.
Pre-export metadata must preserve original role/ACL baseline separately; pg_dump does
not include global credentials. One future Gate1 authorization required. No actual
Neon resources, credentials, backup, real transfer, deploy or cost in G5.

## T03-G6 — operational preparation delegation

Base PR #80/900cc4c. See recovery-mvp/gate1/DELEGATION.md. Single Android entry
prepares a private reviewed-code package in an existing Available Codespace,
verifies PG17/age/local Docker, synthetic SSH probe and receipt; only public age
recipient sent. Resume reuses G5 restore and cleans staging. New read-only pre-grant
baseline captures role attributes/memberships/data hashes into age ciphertext.
Seven new guard tests and one PG17 baseline integration passed locally. Real
workspace/Drive synthetic roundtrip byte equality and deletion404 proven.
Agent Codespaces API403/invalid CLI identity block remote preparation/SSH proof;
no real backup, new Neon resources/credentials, source/main/service changes or cost.

## T03-G7 — canonical Codespace selection and SSH diagnostics

Base PR #81/e41ae24. See recovery-mvp/gate1/SSH_DIAGNOSTICS.md. Fix unique Available
selection with other stopped entries, canonical-name resolution and read-only GET
identity check before SSH. Diagnostic exposes fixed status/phase/version without
credentials/connection fields; wrapper no longer changes authentication implicitly.
Local real diagnostic still blocked at list403; Android404 root cause remains
unproven without canonical name/path/version evidence. Official gh2.46.0/2.103.3
source confirms direct name lookup and connection flags. No Codespace started,
Neon operation, age identity access, source/main/service change or real backup.

## MVP FIRST — functional validation priority

Infrastructure expansion suspended for isolated synthetic MVP validation; Gate1 is
not a prerequisite of that test. See MVP_FIRST.md. Existing C03/API/PG17/TLS complete
journey executed:4 tests passed. Actual frontend Chromium154.0.8037.57 suite:5 passed,
including new positive recovery continuation in the existing form-only journey.
Migrations/engines/API/frontend unchanged. Synthetic admin policy is explicit and
bounded; review fixtures are not human/independent proof. Recovery reaches minimum,
causal attribution remains not_established. Mobile390x844 emulated. No T01 operations,
production/cloud/credentials/main changes or paid services. Next product action:
human acceptance of the same local journey with a concrete fictional business case.
