# Mission 68 — public acceptance evidence

This report distinguishes actual remote HTTP/controller results from hosted UI acceptance.

## Deployed releases
- Render service srv-dbisih6c6qcc739irri0, Free, existing resources preserved.
- Branch recovery-mvp/m68-live-frontend, actual deployed application commit 851f4b7ddf7ac554dd93638782392b0e70a1523e.
- Deployment dep-dbj0ba8u01pc73e4p2d0 confirmed live.
- API https://centerway-synthetic-m67.onrender.com.
- Lovable application commit e4248eefe24fc9a76d9738bc3d1625df613ed45d.
- Lovable publication 5bbedf85-1524-49f7-b715-d25644ede08d; public UI https://value-recovery-radar.lovable.app/app.
- Hosted UI inspected: synthetic/public API banner and real login form; no mock customer list shown without authentication. Full authenticated UI acceptance remains pending.
- CORS: exact public and preview Lovable origins, no wildcard. Both public preflights return 204 with the matching allow-origin. An untrusted origin returns 403 without allow-origin.
- No credentials or tokens are included here. No paid resources, permission changes, migrations or real data.

## Passed remote checks
Previous public HTTP acceptance passed 25 checks: three synthetic logins (alice, bob, reader), matching browser-origin headers, session reads, authorized directories and journeys, cross-company denial, logout and revoked-token denial.

A new opt-in acceptance scenario exercises the ACTUAL frontend HttpTransport + LiveRuntime + SessionController and journey mapper against the public Render HTTPS API. It passed independently of fixtures/mocks:
1. Real alice login and authorized directory.
2. F01 contracts, F02 detections, F03 investigations, F04 decisions, F05 recovery plans and F06 receipts mapped into the UI view models.
3. Synthetic directory name from API and no invented demo metadata.
4. Causal attribution remains not_established.
5. Access to another company rejected with 403.
6. Simulated client network loss surfaces network error and clears displayed cache.
7. Explicit refresh after restoring network reloads the same persisted customer.
8. Logout clears session/customer state.
9. Reader permissions prevent preparing an intervention; no operations POST is sent.
10. Injected local clock expiration clears state. This does not prove browser timed expiration or remotely changed server TTL.

The new test has NO fake journey response and sends no intervention. The offline segment deliberately simulates only client network loss; all successful responses are actual remote API responses. It is HEADLESS acceptance, not desktop/mobile browser proof.

## Reproduce without committing secrets
Set CW_SYNTHETIC_CREDENTIALS_FILE to the private operator credential file path, never to credential values. Run from recovery-mvp/lovable-ui:
```sh
NODE_USE_ENV_PROXY=1 bun run test src/test/public-runtime.acceptance.test.ts --maxWorkers=1
```
The optional test skips without the credential-file environment variable. The existing default suite passes 189 checks; local TypeScript passes. Credentials are read only at runtime, never logged or returned. Sanitized request evidence records method/path/status only, without bodies, bearer or passwords.

## Acceptance still blocked
The cloud browser is not authenticated to CENTERWAY. Its secure sign-in request expired without a confirmed submission. Existing private credentials work through the real transport, but cannot be entered through model-visible browser tools. The operator must complete the secure login in this conversation's cloud browser.

After that login, verify the full hosted F01–F06 navigation, API traffic/log evidence, explicit policy-gated synthetic operations, logout, desktop/mobile layout and errors. Preserve policy denials; do not renew policies or create extra authorization merely to make a test pass. Do not declare completion, pilot readiness or causal recovery based on HTTP/controller tests.

The Lovable source has no active mock fallback; authenticated UI behavior has not yet been independently established. No new Lovable build messages were sent during this follow-up; reported total remains 3.1 credits, final balance not queried.
