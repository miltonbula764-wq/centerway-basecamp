# CENTERWAY V2

The user authorized the independent rebuild in Mission 01 and multi-client support in Mission 02. This directory is a new
Python/SQLite sandbox and does not use the historical application's components,
Supabase schema, RPCs, providers, or build tools. Root rules specific to those
historical components do not describe this runtime. Never publish the public-credential lab or merge to main. A private preview requires explicit authorization, dedicated synthetic data, private accounts and verified HTTPS infrastructure.

- Run `python -m unittest discover -s tests -v` from v2.
- Permissions, evidence, decisions and effects are server owned; the browser passes IDs for cycle operations. Customer registration and observation batches are validated server-side.
- Keep tenant predicates in all scoped database operations. Never reuse browser role claims.
- Sandbox effects, execution uniqueness and audit history commit atomically.
- Identify simulated decisions and simulated usage explicitly; never label them real AI or production recovery.

- Every cycle operation must require explicit tenant and customer IDs, and match the case to both.
- Preserve snapshots on new cycles; ingestion is atomic, idempotent and append-only.
- Only one nonterminal cycle per customer; historical cycles cannot acquire new verification results.

- Private preview changes belong in transport/authentication, never in C01–C06 decision logic.
- Never serve a preview-marked database through the lab HTTP entrypoint. No insecure TLS fallback.
- Provision credentials outside the checkout with restrictive permissions; never commit or log them.

- Keep contracts/openapi.json and API_CONTRACT.md consistent with HTTP behavior; validate real responses.
- External CORS is opt-in, private HTTPS only, exact origins; preserve Strict cookies and cross-site rejection.

- Private service startup must open an existing V2 database without seed/DDL/migration.
- Infra files are templates only; no service activation, DNS changes, paid resources or real-data migration without authorization.
- Run CADDY_BIN=/path/to/verified/caddy python -m unittest discover -s tests -v for proxy verification.

- Production is a separate permanent private authentication foundation: no demo seed, lease bypass, simulated business data or action success. All unprepared business operations must fail closed at HTTP and storage layers.
- Keep production and demo markers, credentials, cookies and data isolated. Local account changes revoke affected sessions; never add a public administration endpoint or bypass the guards.

- Integration configurations are versioned declarations, not evidence or execution grants. Keep tenant-scoped reads/writes, current memberships, append-only provenance and optimistic version checks. Do not connect the new repository to C01–C06 or activate production operations in Mission 06.
- Optional integration tables require explicit local setup; never install/migrate them during HTTP startup. Synthetic configuration fixtures are forbidden in production.

- Mission 07 authorizes authenticated evidence ingestion/query only in separate inactive tables. Never write to sandbox observations/cases or activate production C01–C06 from evidence intake. Pin tenant/customer/configuration/source/time and preserve immutable identities/provenance.
- Evidence availability/quality is structural, not truth, coverage, deterioration or recovery. Preserve conflicting claims; never resolve them or mix configuration versions by inference. Optional evidence setup stays local and explicit, never on HTTP startup.

- Mission 08 adaptive C02 is isolated and inactive: explicit thresholds, goals, source fields, units, windows and full aligned coverage only. Missing/conflicting data never imply deterioration; operational evidence alone never proves value loss.
- Preserve criteria/run versions, original evidence and reproducible snapshots. Bump the detection algorithm for semantic changes; never silently reinterpret past results. Do not connect adaptive results to Core, sandbox C02, actions or production activation.

- Mission 09 structured C03 is isolated/inactive and pins SaaS/customer/C02 result and original evidence. Recorded facts, operator hypotheses, observed noncompliance and missing information must stay distinct; never promote a hypothesis/correlation to a confirmed cause.
- Supported impediments require an explicit declared requirement plus non-disputed evidence. Preserve source/version/hash links and immutable reproducible revisions. Do not connect C03 to AI, C04, interventions, Core/sandbox changes or production activation.

- Mission 10 only proposes inactive C04 recommendations. AI never authorizes/executes; independently validate references, snapshots, current Core permissions, catalogue and conditions. Revalidate after inference without holding the SQLite transaction across a provider call.
- No credentials/configuration means unavailable, never simulator fallback. Fixtures are test-only, clearly labelled and refused in production. Protect provider secrets, require explicit data/tenant authorization and verified HTTPS; no automatic retries for pending/interrupted requests. Preserve prior engines and all Core/production execution blocks.

- Mission 11 adds only isolated controlled C05. C04 never grants authority: require explicit human confirmation of the exact intent hash and a current session of the Core operator, then revalidate actor/approver, versions, evidence, catalogue and a new fenced current snapshot before dispatch. Never reuse historical condition truth as current permission.
- Only explicitly injected test adapters on synthetic non-production contracts are accepted; no default/runtime connector. Production/external operations remain blocked. Reserve once before I/O; pending/uncertain/failure never retries automatically. Preserve immutable approvals/attempts/receipts even if access expires during I/O. Test effects never establish operational/value recovery or implement C06.

- Mission 12 adds isolated inactive C06 only: pin C05 intent/approval/attempt/receipt/audit and original configuration; use explicitly declared verification targets with versioned complete before/after windows. Execution, operation and value remain independent. Post proof must strictly follow dispatch and the receipt when present, including entire metric periods. Never infer recovery from missing baseline, old evidence, a receipt or an already-met target; never arbitrate conflicting evidence.
- Preserve append-only plans/runs and deterministic historical replay, including pending C05 snapshots after a later receipt. C06 cannot call adapters, repeat interventions, resolve final uncertainty, close cases, authorize Core transitions or activate production. All demonstrations are synthetic-only, with real recovery flags false/null; no new HTTP endpoint or startup DDL.

- Mission 13 coordinates existing M06–M12 engines through bounded local polling and immutable per-customer case checkpoints; do not rebuild stages or fabricate C03 declarations, recommendations, approvals or C06 plans. Preserve deterministic C04/C05 IDs across crashes and fence any concurrent C05 reservation before changing lineage. After dispatch, only verification/review states are allowed for that attempt.
- No configured AI means awaiting_ai; no connector means awaiting_execution. Fixtures/test dispatch are trusted test injection only, never runtime defaults/CLI flags. Human approval remains M11/session bound; no automatic retry of pending inference or uncertain C05. Production registration/processing stays blocked. GET /api/orchestration/cases is authenticated scoped read-only API 1.3; no worker invocation, startup DDL, model context, credentials or write endpoint.

- Mission 14 permits multiple immutable historical orchestration cases, at most one active per SaaS/customer. Lifecycle close/open is an explicit operator/session decision pinned to a reviewed snapshot, never automatic C06 recovery. New cycles require the latest closed predecessor and genuinely new post-closure evidence; never copy C02–C06 decisions or C05 grants.
- Pending/uncertain C05 anywhere in the customer (including unowned legacy attempts) blocks closure/new cycles. Human uncertainty review stays unresolved and grants nothing. Storage fences prevent old C03/C04 lineage, C05 intents/grants/reservations and C06 additions after closure. Use only explicit offline M13 upgrade on copies; no startup migration/repair or old-row rehash. Preserve all original records/hashes. Production lifecycle mutations remain blocked.
