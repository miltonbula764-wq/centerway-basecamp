# C03 Evidence Builder tests – last run 2026-10-15 (UTC)

- Migration 0010 (`c03-v1`) applied. Executed via SQL as real `anon`/`authenticated` roles with JWT claims; whole block rolled back
  (0 fixture rows remain). Elevated privileges used only to back-date fixture ingestion, move one fixture run's cut-off,
  forge corrupted C02 runs, inject a fault trigger and call the private budget helper.
- Run 1: 37 pass / 3 fail — all 3 were test bugs (attempt counter also counted tenant B's run_not_found attempt; G02 fixture).
- Run 2: **39 pass / 1 fail**. G02 (ref ingested after cut-off) WAS rejected with no bundle and a persisted attempt, but with code
  `correction_chain_invalid` instead of `ref_after_cutoff`, because the forged fixture also broke the correction chain of another
  window. The fixture was corrected afterwards (keeps the original ids + adds the late id) and **has not been re-run**.
- Covered: positive bundle (baseline fixed, paired denominator, correction with superseded original, values/hash/source copied
  equal to observations), context_facts with explicit "not collected", inherited insufficiency, summary counts, replay reuse with
  no new refs, late correction excluded from old bundle, new C02 revision → new bundle linked by revision_of, old bundle intact,
  forged id / incoherent value / incoherent denominator / wrong input hash / fake chain rejected, legacy c02-v1 never complete,
  budget overflow → insufficient with counts and 0 stored refs, injected fault → whole bundle undone + attempt persisted,
  anon/viewer/tenant-B refused, private helpers not callable, direct insert/update/delete refused, owner update blocked.
- Not covered: real concurrency (two sessions) not executed — relies on advisory lock + unique (tenant, run, algorithm);
  a genuine cross-tenant observation id was not fixtured (lookup is tenant-filtered, tested with a random id).
- C01/C02 code unchanged; their suites were not re-run. Note: this remix's migration journal table was empty; the 10 existing
  migrations were registered as applied (hashes of the committed files) so only 0010 ran.
