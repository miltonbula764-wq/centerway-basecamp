# L03-PREP fixtures (test-only)

- Source: github.com/miltonbula764-wq/centerway-basecamp, PR #61, branch
  `recovery-mvp/l03-prep-integration-fixtures`, head `503eb0ea176f0e33ee1f06534a21488de3b60535`.
- Files copied unchanged from `recovery-mvp/integration/fixtures/v1/`: capture.json,
  CASE_MATRIX.md, bundle.schema.json.
- capture.json sha256 `6a8b1896db1976b5e34bf63d705f2371d7c4a9979a5ff5bbb26b8d33dc2d8eae`;
  fixture_version `l03-prep-v1`; base_commit `eeae52ef…`; openapi c02-v1 sha256 `83196d58…`.
- Captured over LOCAL HTTPS (C03). Synthetic and sanitized: passwords/tokens are typed
  placeholders. `demo:false` does not mean real data. Not a hosted API.
- Read only by `src/test/l03-fixtures.test.ts`; never imported by the app bundle.

