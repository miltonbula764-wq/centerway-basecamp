# Mission 68 — live synthetic frontend integration

Status: implementation prepared; hosted acceptance pending. This document does
not establish a successful public browser login or production readiness.

The existing Lovable project is the frontend source of truth. Its pre-change
commit is 149ee23a60618b577e9535ce8c121d34813741a2. A reproducible source snapshot
is preserved under recovery-mvp/lovable-ui, separate from the legacy root UI.
No design rebuild, paid resource, main merge or real data is authorized.

## Integration

Browser-only /app routes use existing HttpTransport and SessionController over
https://centerway-synthetic-m67.onrender.com. All displayed journeys and directory
names come from authenticated API reads; no live mock/fixture fallback. Unknown
metadata remains absent. Tokens stay in memory, TTL expires locally, logout
clears the cache immediately and revokes the token. Reload requires login; the
underlying API records persist independently of the browser session.

Investigation evaluation, policy-gated synthetic intervention, synthetic undo
and recovery re-evaluation require an explicit frozen draft and confirmation.
No write is triggered by navigation or work-item suggestions. Uncertain replies
have no automatic retry: an explicit resend retains the original request ID.
Server permission/policy denials are preserved. Creating new contract/observation
forms remains outside this integration; existing records are readable.

## Render browser origin configuration

CENTERWAY_BROWSER_ORIGINS is an optional JSON array of exact HTTPS origins. It
replaces the origins field independently of the secret-bearing managed config.
Existing configuration is unchanged if absent. Invalid/empty/wildcard/path
origins reject startup. It changes no user, token TTL, DB role or permission.
Planned allowlist: the verified public Lovable origin and authenticated preview
origin only. Do not assume getcenterway.com is attached to this Lovable project.
Render currently deploys m67 branch with automatic deploy disabled. Publish this
code deliberately only after CI; never claim a saved env var is active before
a deployment and public preflight/auth checks establish it.

## Evidence

Local source: 189 Vitest tests passed, TypeScript passed, production build passed.
Added runtime isolation/logout/expiry/permission/uncertain retry tests and UI
confirmation tests. Updated old inactive-only assertions to enforce live imports
without mocks/fixtures/storage. Actual PostgreSQL/HTTPS regression and managed
allowlist tests run in CI, separately from public browser acceptance.

Hosted desktop/mobile login, F01–F06 navigation, network/session failures,
permission isolation, refresh and logs are still acceptance gates until recorded
with actual evidence. Synthetic results do not establish causal recovery or
validation with real SaaS clients.
