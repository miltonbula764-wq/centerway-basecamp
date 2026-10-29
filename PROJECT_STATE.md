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
| C01 | PR #57, 3b9d3a2 (both CI workflows succeeded) | HTTPS configurations and local synthetic TLS tests; no publication/external verification |
| C02 | PR #58, 9d8c124 (both CI workflows succeeded) | Authenticated, bounded client directory with persisted names; additive HTTP SQL read port; 79 local checks passed; remote CI tracked on the delivery PR |

| C03 | Current branch recovery-mvp/c03-persistent-cloud-demo | Persistent synthetic HTTPS installation and full fixture; 83 local checks passed; no cloud account/resource/publication |

These are implementation states, not assertions of merge, deployment or production use.
Run `./recovery-mvp/tests/run-f03.sh` for regression and discovery integration tests.
See recovery-mvp/DISCOVERY.md for the discovery contract and limitations.

F04 contract and limitations: recovery-mvp/INTERVENTION.md. No production execution or value recovery is asserted.

F05 contract and limitations: recovery-mvp/RECOVERY.md. Observed recovery does not establish causal impact.

F06 integration contract: recovery-mvp/ORCHESTRATION.md. No frontend or deployment has been implemented.

L01 integration and local execution: recovery-mvp/api/README.md. Local test success is not production readiness or a remote CI result. No frontend or production deployment.

C01: recovery-mvp/infra/README.md and RESEARCH.md. Infrastructure prepared and locally tested only. Public DNS, host, actual Lovable origins and public CA certificate activation remain pending. No paid resources, publication or external HTTPS proof.

C02: recovery-mvp/api/README.md (C02) and openapi.json. Only client_id/display_name
from persisted clients, HTTP scope plus current session_user tenant membership. No
engine/RLS changes; clients remains unreadable directly by centerway_api. Install the
additive api/sql/001_client_directory.sql once before using the new endpoint. Per-client
scope remains HTTP-side as in L01. Pagination is bounded, not a cross-request snapshot.
No frontend change, publication, external connectivity or production readiness claimed.
Validation: ./recovery-mvp/infra/test.sh passed locally: 60 unchanged engine tests,
11 HTTP tests (seven L01 + four C02), eight verified-TLS tests (seven C01 + one C02),
79 total. GitHub Actions runs both suites independently on the delivery PR; consult
the checks on the exact commit for the remote result. All fixtures are synthetic.


C03: recovery-mvp/cloud-demo/README.md and RESEARCH.md. Conditional recommendation:
Oracle Always Free A1 ARM64, 1 OCPU/4 GB, 50 GB boot; current documented allowance is
2 OCPUs/12 GB total, not the former 4/24. Eligibility/capacity, real host, ARM execution,
DNS, mobile operation and external TLS remain unverified. US$0 is conditional on the
actual account/quotas; no paid resources, external accounts or servers were created.
Persistent PostgreSQL 17 and TLS volume, private SQLite/config/PKI, separate demo roles,
fixed image digests and migration hashes. Setup/fixture refuse automatic reseeding.
Full fixture uses authenticated API/orchestration; all evidence, outcomes and test
review records are explicitly synthetic; independent verification/causality are not
established. Only a preauthorized isolated reversible flag can execute (one attempt,
risk <=1, 24-hour policy). API/engines/C01/C02 files remain unchanged.
Validation: ./recovery-mvp/cloud-demo/test.sh passed locally (Python 3.12.14, x86_64):
60 engine + 11 HTTP + eight HTTPS + four persistent-demo tests = 83 checks. The final
persistent suite was also repeated after transport/state guards were added. Includes
full pipeline, authorized directory, role/tenant isolation, PG/API/gateway restart,
durable sessions/receipts, idempotency/audit and failures. Remote results are tracked
by the delivery PR's three independent GitHub Actions workflows on the exact commit.
Prepared only: future domain api.getcenterway.com; no DNS, email, Lovable or main
changes, public bind or public ACME requests. No real deployment/external HTTPS proof,
production readiness, VM restore or load benchmark. Internal certificates expire;
rotation and backups/restore require future operational work. Do not advance to L03.
