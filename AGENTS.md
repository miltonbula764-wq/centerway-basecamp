<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

# CENTERWAY – engineering rules

- Case guidance only presents existing queries/links, never seeds/actions — why: do not duplicate journey logic.
- CaseWorkspace orders deep-link blocks, keeping C04 mounted and original identity guards — why: presentation must not change case contracts.

- Tenant isolation is enforced in PostgreSQL (RLS + composite `(tenant_id, id)` FKs + immutable `tenant_id` triggers); never trust a tenant_id sent by the browser — why: authorization must hold even if the client is hostile.
- Membership changes, onboarding and Value Profile approval go only through SECURITY DEFINER RPCs (`create_tenant`, `add_tenant_member`, `set_member_role`, `remove_tenant_member`, `approve_value_profile`, `create_value_profile_version`) — why: clients have no direct write grants on these state transitions.
- The Value Profile belongs to the tenant (`tenant_value_profiles` + `profile_indicators`); all subjects inherit the single approved version. The old per-subject `value_profiles`/`indicators` tables are deprecated and must not be used — why: the plan defines one profile per tenant.
- Approved/superseded profiles and their indicators are immutable; changes create a new version. Approval validates the outcome-indicator contract server-side (`value_profile_approval_issues`) — why: evidence must reference a stable, explicit definition.
- Lock order for profile changes: tenant row FOR UPDATE → profile row (FOR UPDATE in RPCs, FOR SHARE in the indicator trigger) — why: approval and edits/copies must not interleave.
- Observations are append-only; corrections are new rows with `corrects_observation_id`; idempotency hash is computed server-side — why: auditability and safe replays.
- `audit_log` is written only by DB triggers with `auth.uid()` as actor and is immutable — why: the client cannot forge history.
- Permission tests run as real `authenticated`/`anon` roles with JWT claims inside a transaction that is always rolled back — why: service_role bypasses RLS and would prove nothing.
- UI reads/writes go through the browser client under RLS; every tenant-scoped query key starts with `["t", tenantId]` and is removed on tenant switch/logout, and mutations call `assertActiveTenant` with the tenant captured at form open — why: stale data or writes must never cross tenants.
- Only the selected tenant id is kept in localStorage, always revalidated against `memberships` — why: permissions live in the database, not the browser.
- Tenant/session UI regression tests exercise the real app layout, context and mutations with controlled requests; report them separately from hosted credential-login tests — why: deterministic race coverage must not be mistaken for real authentication or database permission proof.
- Observations and ingestion batches are written only by `import_observations` (clients have no INSERT/UPDATE grants); it revalidates role, approved profile id, limits and every row, and commits a batch atomically or records a failed batch with per-line error codes — why: preview in the browser is advisory and must never be the authority.
- Ingestion error codes are shared between the RPC and `src/lib/ingest.ts`; add a code in both places — why: the preview must mirror the server's messages.
- C02 deterioration analysis runs only in `run_deterioration_analysis` (SECURITY DEFINER, current algorithm `c02-v2`); any semantic change bumps the algorithm version and old runs are never recomputed; clients only pass ids and read immutable `c02_runs`/`c02_results` — why: results and evidence refs must never come from the browser.
- C03 evidence bundles are built only by `build_evidence_bundle(tenant, run)` (`c03-v1`), from the stored C02 snapshot plus observations ingested by the run's cut-off, re-validating every ref and calculation; one bundle per (tenant, run, algorithm), integrity failures roll back the bundle in a subtransaction and are recorded in append-only `c03_attempts` — why: evidence must be reproducible and never trust the caller or later data.
- C02 never defaults missing configuration: absent aggregation/cadence/denominator/rule yields `insufficient_config`; unsupported methods are reported, not approximated; a paired denominator needs its own cadence/coverage and the same source as the numerator, and sources must match across all windows — why: no invented thresholds or silent reinterpretation.
- A C02 run is identified by a hash of (algorithm, profile, subject, as_of, all observation ids+payload hashes); same inputs reuse the run, new inputs create a run with `revision_of` — why: reproducible, append-only history.
- Observations from another profile version are used only when the indicator's measurement fingerprint (`_c02_fingerprint`) is identical; corrections must match source, observed_at and fingerprint and may not fork — why: incompatible meanings must never be mixed.
- C02 signals are candidates only; no table or code may turn them into actionable cases until the case block exists — why: usage-only or unvalidated signals must not trigger interventions.

## Independent recovery MVP (F01–F03.1)

These rules apply to `recovery-mvp/`; the V2 rules above describe the legacy project.
Confirmed implementation: F01 #49, F02 #50, F03 #51. F03.1 adds configurable discovery
and automatic F03 routing. See PROJECT_STATE.md and recovery-mvp/DISCOVERY.md.
Use real PostgreSQL login roles in disposable integration tests. Identity is
`session_user`; audit is transactional and append-only. Preserve prior migrations.
Discovery creates hypotheses and observations only: never synthesize reviewer records,
independent verification, causal conclusions or intervention authorization.
Do not implement F04 without a new explicit mission. Do not modify main.
