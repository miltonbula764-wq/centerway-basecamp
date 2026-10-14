# Permission tests – last run

- Date: 2026-10-14 (UTC)
- Script: `supabase/tests/permissions_test.sql` (roles `anon` / `authenticated` with JWT claims; never service_role)
- Result: **61 pass / 0 fail**. Negative tests check the exact SQLSTATE and, where relevant, the constraint name.
- Fixtures: the whole run is rolled back. Checked afterwards: 0 rows in every app table, 0 fixture users.
- Migrations applied at run time: `0000_centerway_foundation`, `0001_tenant_value_profiles`.

## Not covered
- Real concurrency (two simultaneous sessions) was **not executed**: the SQL runner gives a single session.
  Serialization relies on locks: tenant row `FOR UPDATE` → profile row `FOR UPDATE` (approval / new version / draft)
  and profile row `FOR SHARE` in the indicator trigger. Only the sequential behaviour is tested here.
- T48 approves v3 copied from v1; "usage indicators need no rules at approval" is not exercised by an approval yet.
