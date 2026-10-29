# Confirmed CENTERWAY MVP state

Independent implementation is in recovery-mvp/. Legacy application remains separate.

| Mission | Implemented base | Scope |
|---|---|---|
| F01 | PR #49, 2a06c47 | Versioned value contracts, provenance, isolation and audit |
| F02 | PR #50, 45f7555 | Deterministic deterioration detection and frozen snapshots |
| F03 | PR #51, 9d0a28e | Structured investigation and recorded verification |
| F03.1 | PR #52, 074630f | Rule discovery and batch routing to F03 |
| F04 | Current branch recovery-mvp/f04-synthetic-interventions | Authorized decisions, isolated reversible synthetic execution |
| F05 | Not implemented | Requires a new mission |

These are implementation states, not assertions of merge, deployment or production use.
Run `./recovery-mvp/tests/run-f03.sh` for regression and discovery integration tests.
See recovery-mvp/DISCOVERY.md for the discovery contract and limitations.

F04 contract and limitations: recovery-mvp/INTERVENTION.md. No production execution or value recovery is asserted.
