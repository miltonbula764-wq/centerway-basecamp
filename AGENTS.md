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
- Approved/superseded Value Profiles and their indicators are immutable; changes create a new version — why: evidence must reference a stable definition.
- Observations are append-only; corrections are new rows with `corrects_observation_id`; idempotency hash is computed server-side — why: auditability and safe replays.
- `audit_log` is written only by DB triggers with `auth.uid()` as actor and is immutable — why: the client cannot forge history.
- Permission tests run as real `authenticated`/`anon` roles with JWT claims inside a transaction that is always rolled back — why: service_role bypasses RLS and would prove nothing.
