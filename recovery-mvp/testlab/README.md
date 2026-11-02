# CENTERWAY TestLab 20 — offline measurement fixture

One SaaS **SYNTHETIC FlowPilot SaaS**, 20 distinct customer IDs. Four each: excellent, good, median, deteriorating, inconclusive. Outcome values, disputed data, missing data, and usage-only data deliberately vary by cycle. One deteriorating customer later improves, but the test oracle never asserts causality.

This is the **safe offline fixture generator**, not yet a live API integration. It neither logs into the public service nor writes to Neon. Events are deterministic by client and cycle. For real ingestion the 20 clients must first exist in an authorized isolated synthetic tenant, with contracts, source revisions and scoped identities. The actual ingestion adapter must use `append_value` and verify operation receipts. Do **not** send `expected_case_for_test_oracle_only` to the CENTERWAY engine.

No new infrastructure, credentials, dependencies or paid services.

```sh
python recovery-mvp/testlab/testlab20.py --catalog
python recovery-mvp/testlab/testlab20.py --cycles 3
python recovery-mvp/testlab/testlab20.py --cycles 12 --interval 120 --realtime
```

User-initiated intervention, investigation and recovery verification remain manual. Synthetic evidence and compressed time never establish real-world causality.
