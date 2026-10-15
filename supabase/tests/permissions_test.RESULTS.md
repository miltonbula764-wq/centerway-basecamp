# Database tests – last run

- Date: 2026-10-15 (UTC). Roles `anon` / `authenticated` with JWT claims; never service_role for assertions.
- Migrations at run time: 0000–0009 (0009 = C02 `c02-v2`).
- `c02_test.sql`: **70 pass / 0 fail / 0 not run** (2026-10-15) — the 47 v1 checks, adapted to v2 (only change: the
  paired denominator fixture now declares its own weekly cadence and 100% coverage), plus 23 v2 checks:
  sources differing between windows (each valid alone) → insufficient; positive control same source; source/denominator
  coverage stored; synthetic stored `c02-v1` run byte-identical and linked by `revision_of`, not reused; replay reuses;
  different as_of → new run; denominator from another source; late correction → revision, corrected value, chain proof
  stored, earlier run unchanged; chain resolution honours the cut-off (before 48 / after 70); denominator without own
  coverage → insufficient_config; own coverage 1/7 < 50% → insufficient though sum ≥ minimum; daily denominator positive
  control; denominator of an incompatible version → explicit reason; v2 internals not callable by authenticated;
  anon/viewer/tenant B refused.
- The cut-off check (V15) back-dates `ingested_at` of that fixture subject's original rows by suspending only the
  `observations_append_only` trigger inside the rolled-back transaction (audit is an INSERT trigger, untouched). This briefly
  locks the observations table while the test runs.
- `permissions_test.sql` (67/0) and `ingestion_test.sql` (35/0) were last run 2026-10-14; C01 code was not changed by 0009,
  so they were not re-run.
- All runs are rolled back. Afterwards: 0 fixture tenants/users, 0 runs, append-only trigger enabled.
- Semantics: see `c02_semantics.md`.

## Not covered
- Real concurrency (two simultaneous sessions) was **not executed**. Analysis takes the tenant row `FOR SHARE`, the approved
  profile `FOR SHARE`, a per-subject advisory lock, and relies on the `(tenant_id, subject_id, input_hash)` unique index.
- Ambiguous correction forks can no longer be created (unique index); the C02 fork handling is therefore untested on real data.
