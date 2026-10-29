# Confirmed CENTERWAY MVP state

Independent implementation is in recovery-mvp/. Legacy application remains separate.

| Mission | Implemented base | Scope |
|---|---|---|
| F01 | PR #49, 2a06c47 | Versioned value contracts, provenance, isolation and audit |
| F02 | PR #50, 45f7555 | Deterministic deterioration detection and frozen snapshots |
| F03 | PR #51, 9d0a28e | Structured investigation and recorded verification |
| F03.1 | PR #52, 074630f | Rule discovery and batch routing to F03 |
| F04 | PR #53, 9f964c2 | Authorized decisions, isolated reversible synthetic execution |
| F05 | PR #54, 1523a18 | Versioned before/after verification of contractual value |
| F06 | PR #55, c4d9756 | Idempotent operations and client journey projection |
| L01 | PR #56, d32c6e8 (CI run 40902550601 succeeded) | Authenticated HTTP transport, per-user PostgreSQL identity, local synthetic demo and independent CI |
| L02.2 | Interface prepared, reported by user; not inspected in C01 | External Lovable project remains untouched |
| C01 | Current branch recovery-mvp/c01-https-infrastructure | HTTPS configurations and local synthetic TLS tests; no publication/external verification |

These are implementation states, not assertions of merge, deployment or production use.
Run `./recovery-mvp/tests/run-f03.sh` for regression and discovery integration tests.
See recovery-mvp/DISCOVERY.md for the discovery contract and limitations.

F04 contract and limitations: recovery-mvp/INTERVENTION.md. No production execution or value recovery is asserted.

F05 contract and limitations: recovery-mvp/RECOVERY.md. Observed recovery does not establish causal impact.

F06 integration contract: recovery-mvp/ORCHESTRATION.md. No frontend or deployment has been implemented.

L01 integration and local execution: recovery-mvp/api/README.md. Local test success is not production readiness or a remote CI result. No frontend or production deployment.

C01: recovery-mvp/infra/README.md and RESEARCH.md. Infrastructure prepared and locally tested only. Public DNS, host, actual Lovable origins and public CA certificate activation remain pending. No paid resources, publication or external HTTPS proof.
