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
