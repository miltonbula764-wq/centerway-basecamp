# Database tests – last run

- Date: 2026-10-14 (UTC). Roles `anon` / `authenticated` with JWT claims; never service_role for assertions.
- Migrations at run time: 0000, 0001, 0002, 0003_csv_ingestion_c01.
- `permissions_test.sql`: **67 pass / 0 fail** (adds T16b–d direct writes denied, T62–T63 zero-outcome regression of 0002, T64 outcome must be numeric).
  Trigger-level checks (T14–T16, T52–T55) now run on the privileged fixture path because clients no longer have INSERT on observations/batches.
- `ingestion_test.sql`: **35 pass / 0 fail** (viewer/anon/cross-tenant refused, approved profile required, stale profile blocked,
  limits, valid commit, replay no-op, conflicts incl. same file and write-time, atomic rollback, per-line codes, corrections, audit).
- Both runs are rolled back. Afterwards: 0 tenants/subjects/batches/observations, 0 fixture users.

## Not covered
- Real concurrency (two simultaneous sessions) was **not executed**. Imports take the tenant row `FOR UPDATE` (serialized with
  each other and with approval/versioning) and rely on the `(tenant_id, idempotency_key)` unique index as the final guard.
