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
