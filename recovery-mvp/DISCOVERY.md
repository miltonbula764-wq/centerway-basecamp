# F03.1 — structured discovery

Apply migration 005 after 001–004 in the isolated MVP database. Existing migrations
are unchanged. Run `./recovery-mvp/tests/run-f03.sh` for the complete regression suite.

An authorized integration supplies structured evidence already available to it using
`register_discovery_input(tenant, client, input_id, contract_id, contract_revision,
factor_json, evidence_array)`. The factor uses the F03 business fields. Evidence uses
the F03 evidence fields except factor_id/factor_revision, supplied by routing. Original
source IDs/revisions, references, hashes and collected_at are mandatory under F03
validation. No evidence or hypothesis text is generated from outcome numbers.

`register_discovery_rule(tenant, rule_id, category, purpose, assertion)` installs an
immutable rule edition: exact category equality plus an explicit boolean proposition
match. Rules contain no SQL or code. New configuration/data uses a new UUID; there
is no silent mutation, automatic replacement or retirement in this version.

`discover_impediments(tenant, cutoff)` processes all clients authorized within that
company. It matches available F02 detections with a deterioration/worsening signal,
exact contract revision, and structured non-usage evidence satisfying the rule.
No manual investigation creation is needed. It creates an F03 investigation, factor
and all observations in the matching bundle, including contrary observations.
An immutable origin links rule edition, input, detection, investigation and factor.
All three tables have RLS, composite scoped references, append-only audit and no direct
application write grants. A tenant lock prevents duplicate routing under concurrency.

The F03 report is returned alongside each origin. No verification is invented or
copied: initial reports remain inconclusive pending real reviews through F03. A later
batch reuses the same investigation and evaluates actual registered reviews, allowing
F03 to distinguish supported impediments from unconfirmed hypotheses. F03 retains
its independence/causality limitations and always returns execution_authorized=false.

The discovery cutoff selects rules, inputs and detections. F03 reports use a separate
current evaluation time (returned explicitly as report.as_of), because newly created
investigations cannot exist at an older cutoff. Repetition reuses routing identities;
it creates a new immutable evaluation at its new report cutoff. This is not a replay
of the original report: use read_investigation_context to retrieve that snapshot.

Limitations: explicit structured ingestion is required; this is not crawling or
semantic interpretation of documents. Rules support equality/boolean propositions,
not arbitrary expressions or causal inference. Full F03 domain validation happens
atomically when routing: malformed matching input aborts the batch without partial
investigations; correct it by registering a new input. No per-item failure queue,
pagination, scheduler, cross-company superuser batch, retirement or performance SLA.
Multiple matching rule editions may intentionally produce separate investigations.
No independent verification, paid AI, frontend, intervention or F04 is implemented.

Each bundle is one explicit factor instance; separate bundles are not semantically
reconciled. Producers must include contradictory observations of that instance in
its evidence array. Tests cover routing, real subsequent reviews, identity reuse,
multi-client processing, authorization and unmatched rules, alongside F01–F03 regressions.
