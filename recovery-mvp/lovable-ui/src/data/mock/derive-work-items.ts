// Mirror of the work_items CTE in sql/008 — used ONLY to give synthetic
// journeys the same guidance the server would compute. Not a decision engine.
import type { ClientJourney, WorkItem } from "@/domain/f06";

export function deriveWorkItems(j: Omit<ClientJourney, "work_items">): WorkItem[] {
  const items: WorkItem[] = [];
  if (j.contracts.length === 0) items.push({ stage: "contract", next: "append_value", needed: "explicit_value_contract_and_source" });
  for (const id of new Set(j.contracts.map((c) => c.id))) {
    if (!j.detections.some((d) => d.contract_id === id))
      items.push({ stage: "detection", contract_id: id, next: "detect", needed: "explicit_revisions_cutoff_and_period_policy" });
  }
  for (const d of j.detections) {
    if (!j.investigations.some((i) => i.detection_id === d.id))
      items.push({ stage: "investigation", detection_id: d.id, next: "supply_context_or_open_investigation", needed: "explicit_factors_and_contextual_evidence" });
  }
  for (const i of j.investigations) {
    if (j.decisions.some((d) => d.investigation_id === i.id && d.status === "executed")) continue;
    const r = i.result;
    const next =
      i.report_id === null
        ? "investigate"
        : r?.status === "inconclusivo"
          ? "supply_evidence_or_verification"
          : r?.status === "impedimento_demonstrado" && r.intervention_candidates.length > 0
            ? "review_intervention_authorization"
            : "review_investigation_conclusion";
    items.push({ stage: "investigation", investigation_id: i.id, next, blockers: r?.contradictions ?? null, needed: r?.missing_information ?? null, report_id: i.report_id, as_of: i.as_of });
  }
  for (const d of j.decisions) {
    if (j.recovery_plans.some((p) => p.decision_id === d.id)) continue;
    items.push({ stage: "intervention", decision_id: d.id, next: d.status === "executed" ? "plan_recovery" : "review_execution_blocker", blocker: d.reason });
  }
  for (const p of j.recovery_plans) {
    const next = p.report_id === null ? "evaluate_recovery" : p.result?.status === "resultado_inconclusivo" ? "supply_outcome_evidence_and_reevaluate" : "review_observed_recovery";
    items.push({ stage: "recovery", plan_id: p.id, next, result: p.result, as_of: p.as_of });
  }
  return items;
}

