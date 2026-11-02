// Pure mapping F06 journey → UI view models. No business re-interpretation:
// statuses are passed through; text is only formatted for display.
import type { ClientJourney, WorkItem, WorkItemNext } from "@/domain/f06";
import { L01Error } from "./transport";
import type {
  ContractVM,
  CustomerVM,
  DecisionVM,
  DemoOnlyMeta,
  InvestigationVM,
  OverviewKpis,
  ReceiptVM,
  RecoveryVM,
  TimelineEventVM,
  WorkItemVM,
} from "@/domain/types";

export const nextLabel: Record<WorkItemNext, string> = {
  append_value: "Falta contrato explícito ou fonte",
  detect: "Fornecer revisões, corte e política de períodos",
  supply_context_or_open_investigation: "Deteção sem investigação ligada",
  investigate: "Avaliar fatores e evidências registados",
  supply_evidence_or_verification: "Recolher evidência ou verificação",
  review_investigation_conclusion: "Rever conclusão (sem candidato acionável)",
  review_intervention_authorization: "Rever suporte; a F04 decide a autorização",
  review_execution_blocker: "Rever razão de bloqueio F04",
  plan_recovery: "Definir janelas comparáveis F05",
  evaluate_recovery: "Avaliar evidência anterior/posterior",
  supply_outcome_evidence_and_reevaluate: "Falta suporte suficiente para a F05",
  review_observed_recovery: "Rever conclusão F05 e os seus limites",
};

export const shortId = (id: string) => id.slice(0, 8);

/** Engine list items are objects; render the most descriptive field. */
export function describeItem(o: unknown): string {
  if (typeof o === "string") return o;
  if (!o || typeof o !== "object") return String(o);
  const r = o as Record<string, unknown>;
  const main = r["statement"] ?? r["predicate"] ?? r["purpose"] ?? r["category"] ?? r["reason"];
  if (typeof main === "string") {
    const extra = main !== r["reason"] && typeof r["reason"] === "string" ? ` (${r["reason"]})` : "";
    return main + extra;
  }
  return JSON.stringify(o);
}

const asList = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const fmtDate = (iso: string) => iso.slice(0, 10);

export function businessStatusOf(result: unknown): string | null {
  if (!result || typeof result !== "object") return null;
  const r = result as Record<string, unknown>;
  // F03/F05 run rows nest the semantic report under `.result`.
  const inner = r["result"];
  if (inner && typeof inner === "object" && !Array.isArray(inner)) {
    const n = inner as Record<string, unknown>;
    const iv = n["status"] ?? n["state"];
    if (typeof iv === "string") return iv;
  }
  const v = r["status"] ?? r["state"] ?? r["code"];
  return typeof v === "string" ? v : null;
}

const JOURNEY_ARRAYS = [
  "contracts", "sources", "evidence_history", "detections", "investigations", "decisions",
  "executions", "recovery_plans", "operations", "work_items",
] as const;

/**
 * Validate a `{data, demo}` journey envelope before mapping. Any mismatch is a
 * contract error (never an inferred success or an empty journey).
 */
export function validateJourneyEnvelope(body: unknown, expected?: { tenant: string; client: string }): ClientJourney {
  const fail = (code: string): never => { throw new L01Error("contract", 200, code); };
  if (!body || typeof body !== "object" || typeof (body as Record<string, unknown>)["demo"] !== "boolean") fail("journey_envelope_invalid");
  const d = (body as Record<string, unknown>)["data"] as Record<string, unknown> | undefined;
  if (!d || typeof d !== "object") return fail("journey_envelope_invalid");
  if (d["contract_version"] !== "f06-v1") fail("journey_version_unsupported");
  if (d["causal_attribution"] !== "not_established") fail("journey_causal_attribution_unexpected");
  if (d["authorization_basis"] !== "engine_checks_required_at_execution") fail("journey_authorization_basis_unexpected");
  for (const k of JOURNEY_ARRAYS) if (!Array.isArray(d[k])) fail(`journey_missing_${k}`);
  if (expected && (d["tenant_id"] !== expected.tenant || d["client_id"] !== expected.client)) fail("journey_scope_mismatch");
  return d as unknown as ClientJourney;
}

function workItemVM(w: WorkItem): WorkItemVM {
  const base = { stage: w.stage, next: w.next, label: nextLabel[w.next] };
  switch (w.stage) {
    case "contract":
      return { ...base, refId: null, asOf: null, notes: [] };
    case "detection":
      return { ...base, refId: w.contract_id, asOf: null, notes: [] };
    case "investigation":
      if ("detection_id" in w) return { ...base, refId: w.detection_id, asOf: null, notes: [] };
      return { ...base, refId: w.investigation_id, asOf: w.as_of, notes: [...asList(w.blockers), ...asList(w.needed)].map(describeItem) };
    case "intervention":
      return { ...base, refId: w.decision_id, asOf: null, notes: [w.blocker] };
    case "recovery":
      return { ...base, refId: w.plan_id, asOf: w.as_of, notes: [] };
  }
}

export function mapJourney(j: ClientJourney, demo: DemoOnlyMeta | null): CustomerVM {
  const customerId = j.client_id;
  const latestContract = new Map<string, (typeof j.contracts)[number]>();
  for (const c of j.contracts) {
    const prev = latestContract.get(c.id);
    if (!prev || c.revision > prev.revision) latestContract.set(c.id, c);
  }
  const sourceName = (id: string) => j.sources.find((s) => s.id === id)?.name ?? shortId(id);

  const contracts: ContractVM[] = [...latestContract.values()].map((c) => ({
    id: c.id, customerId, revision: c.revision, objective: c.objective, indicator: c.indicator, unit: c.unit,
    baseline: c.baseline, minimum: c.minimum_acceptable, target: c.target, direction: c.direction, method: c.measurement_method,
    period: `${fmtDate(c.period_start)} → ${fmtDate(c.period_end)}`, baselinePeriod: `${fmtDate(c.baseline_start)} → ${fmtDate(c.baseline_end)}`,
    sourceName: `${sourceName(c.source_id)} · r${c.source_revision}`,
    revisions: j.contracts.filter((x) => x.id === c.id).sort((a, b) => a.revision - b.revision).map((x) => ({ revision: x.revision, at: x.recorded_at, actor: x.actor, reason: x.reason })),
    detections: j.detections.filter((d) => d.contract_id === c.id).map((d) => ({ id: d.id, state: d.state, asOf: d.as_of, revision: d.contract_revision })),
  }));

  const investigations: InvestigationVM[] = j.investigations.map((i) => ({
    id: i.id, customerId, contractId: i.contract_id, contractRevision: i.contract_revision, detectionId: i.detection_id,
    detectionState: j.detections.find((d) => d.id === i.detection_id)?.state ?? null,
    question: i.question, openedAt: i.recorded_at, actor: i.actor,
    report: i.result && i.report_id && i.as_of
      ? {
          reportId: i.report_id, asOf: i.as_of, status: i.result.status,
          facts: asList(i.result.observed_facts).map(describeItem),
          hypotheses: asList(i.result.hypotheses).map(describeItem),
          contradictions: asList(i.result.contradictions).map(describeItem),
          missing: asList(i.result.missing_information).map(describeItem),
          candidates: asList(i.result.intervention_candidates).map(describeItem),
        }
      : null,
    decisionIds: j.decisions.filter((d) => d.investigation_id === i.id).map((d) => d.id),
  }));

  const decisions: DecisionVM[] = j.decisions.map((d) => {
    const execs = j.executions.filter((e) => e.decision_id === d.id);
    return {
      id: d.id, customerId, investigationId: d.investigation_id, status: d.status, reason: d.reason, actor: d.actor, at: d.recorded_at,
      executions: execs.map((e) => ({ id: e.id, at: e.recorded_at, isUndo: e.undo_of !== null })),
      reversed: execs.some((e) => e.undo_of !== null),
    };
  });

  const recoveries: RecoveryVM[] = j.recovery_plans.map((p) => {
    const c = latestContract.get(p.contract_id);
    const r = p.result;
    return {
      id: p.id, customerId, decisionId: p.decision_id, contractId: p.contract_id,
      indicator: c?.indicator ?? shortId(p.contract_id), unit: c?.unit ?? "", direction: c?.direction ?? null,
      windows: `r${p.pre_revision} → r${p.post_revision}`, evaluated: r !== null,
      status: r?.status ?? null, reason: r?.reason ?? null,
      executionSucceeded: r?.execution_succeeded ?? null, improvementObserved: r?.improvement_observed ?? null, minimumMet: r?.minimum_met ?? null,
      before: r?.before?.observed_value ?? null, after: r?.after?.observed_value ?? null,
      minimum: r?.minimum_acceptable ?? c?.minimum_acceptable ?? null, asOf: p.as_of,
    };
  });

  const receipts: ReceiptVM[] = j.operations.map((o) => ({
    requestId: o.request_id, customerId, operation: o.operation, transportStatus: o.status,
    businessStatus: businessStatusOf(o.result), actor: o.actor, at: o.recorded_at,
  }));

  const timeline: TimelineEventVM[] = [
    ...j.contracts.map((c) => ({ at: c.recorded_at, kind: "contract" as const, refId: c.id, label: `Contrato ${shortId(c.id)} · revisão ${c.revision}` })),
    ...j.detections.map((d) => ({ at: d.recorded_at, kind: "detection" as const, refId: d.id, label: `Deteção F02 · ${d.state}` })),
    ...j.investigations.map((i) => ({ at: i.recorded_at, kind: "investigation" as const, refId: i.id, label: `Investigação aberta · ${i.question}` })),
    ...j.decisions.map((d) => ({ at: d.recorded_at, kind: "decision" as const, refId: d.id, label: `Decisão F04 · ${d.status}` })),
    ...j.executions.map((e) => ({ at: e.recorded_at, kind: e.undo_of ? ("undo" as const) : ("execution" as const), refId: e.id, label: e.undo_of ? "Reversão sintética (undo)" : "Execução sintética" })),
    ...j.recovery_plans.map((p) => ({ at: p.as_of ?? p.recorded_at, kind: "recovery" as const, refId: p.id, label: p.result ? `Avaliação F05 · ${p.result.status}` : "Plano de recuperação criado" })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return {
    id: customerId, tenantId: j.tenant_id, demo, displayName: demo?.company ?? `Cliente ${shortId(customerId)}`,
    contracts, sources: j.sources.map((s) => ({ id: s.id, revision: s.revision, name: s.name, method: s.method, locator: s.locator, recordedAt: s.recorded_at })),
    investigations, decisions, recoveries, receipts, workItems: j.work_items.map(workItemVM), timeline,
    causalAttribution: j.causal_attribution, authorizationBasis: j.authorization_basis,
  };
}

export function computeKpis(cs: CustomerVM[]): OverviewKpis {
  const all = <T,>(f: (c: CustomerVM) => T[]) => cs.flatMap(f);
  return {
    clients: cs.length,
    contracts: all((c) => c.contracts).length,
    openWorkItems: all((c) => c.workItems).length,
    inconclusiveInvestigations: all((c) => c.investigations).filter((i) => i.report?.status === "inconclusivo").length,
    executedDecisions: all((c) => c.decisions).filter((d) => d.status === "executed").length,
    blockedDecisions: all((c) => c.decisions).filter((d) => d.status === "blocked").length,
    evaluatedRecoveries: all((c) => c.recoveries).filter((r) => r.evaluated).length,
  };
}

