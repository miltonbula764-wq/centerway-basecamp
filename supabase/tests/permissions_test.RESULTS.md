# Database tests – last run

- Date: 2026-10-14 (UTC). Roles `anon` / `authenticated` with JWT claims; never service_role for assertions.
- Migrations at run time: 0000–0008 (0004–0008 = C02 + C01 correction hardening).
- `permissions_test.sql`: **67 pass / 0 fail**.
- `ingestion_test.sql`: **35 pass / 0 fail** (re-run after the correction hardening; I27 still accepted).
- `c02_test.sql`: **47 pass / 0 fail** — outcome drop, usage-only, stable below target, missing week / small denominator,
  no data ≠ zero, baseline zero, lower-is-better, UTC boundaries, multiple sources, corrections (incompatible date/source,
  fork, version mismatch, no double count), idempotent rerun, revision with new data, anon/viewer/tenant B refused,
  client insert/update refused, owner update blocked by trigger, audit actor, version copy, direction contradiction blocks approval.
- All runs are rolled back. Afterwards: 0 fixture tenants/users, 0 runs.
- Semantics: see `c02_semantics.md`.

## Not covered
- Real concurrency (two simultaneous sessions) was **not executed**. Analysis takes the tenant row `FOR SHARE`, the approved
  profile `FOR SHARE`, a per-subject advisory lock, and relies on the `(tenant_id, subject_id, input_hash)` unique index.
- Ambiguous correction forks can no longer be created (unique index); the C02 fork handling is therefore untested on real data.
