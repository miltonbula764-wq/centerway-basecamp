// F06 client_journey projection (sql/008_operational_orchestration.sql, "f06-v1").
// Row columns follow the F01–F07 tables; anything not verified stays `unknown`.
import type { Instant, OperationReceipt, Uuid } from "./l01";

export type Direction = "higher" | "lower";
export type ValueState = "valor_demonstrado" | "deterioracao_demonstrada" | "valor_insuficiente" | "resultado_inconclusivo";

interface Audited {
  actor: string;
  recorded_at: Instant;
}

export interface ContractVersion extends Audited {
  tenant_id: Uuid;
  client_id: Uuid;
  id: Uuid;
  revision: number;
  objective: string;
  expected_outcome: string;
  indicator: string;
  unit: string;
  measurement_method: string;
  direction: Direction;
  baseline: number;
  minimum_acceptable: number;
  target: number;
  baseline_start: Instant;
  baseline_end: Instant;
  period_start: Instant;
  period_end: Instant;
  source_id: Uuid;
  source_revision: number;
  baseline_reference: string;
  reason: string;
}

export interface SourceVersion extends Audited {
  id: Uuid;
  revision: number;
  name: string;
  locator: string;
  method: string;
  reason: string;
}

export interface EvidenceVersion extends Audited {
  id: Uuid;
  revision: number;
  contract_id: Uuid;
  contract_revision: number;
  source_id: Uuid;
  source_revision: number;
  evidence_type: "outcome" | "usage";
  /** Declared by the producer; not an independent verification. */
  quality: "verified" | "partial" | "disputed";
  observed_value: number;
  unit: string;
  measurement_method: string;
  period_start: Instant;
  period_end: Instant;
  reference: string;
  content_sha256: string;
  reason: string;
}

export interface DetectionRun extends Audited {
  id: Uuid;
  contract_id: Uuid;
  contract_revision: number;
  algorithm: "f02-v1";
  as_of: Instant;
  required_periods: number;
  revision: number;
  state: ValueState;
  input_snapshot: unknown;
  result: unknown;
}

export type InvestigationStatus = "impedimento_demonstrado" | "nenhum_impedimento_demonstrado" | "inconclusivo";

/** F03 run_investigation result. List items are engine objects — kept loose. */
export interface InvestigationResult {
  status: InvestigationStatus;
  observed_facts: Record<string, unknown>[];
  hypotheses: Record<string, unknown>[];
  contradictions: Record<string, unknown>[];
  missing_information: Record<string, unknown>[];
  excluded_evidence?: unknown[];
  factor_conclusions?: unknown[];
  intervention_candidates: Record<string, unknown>[];
  execution_authorized: false;
  independent_verification: "not_established";
  causal_inference: "not_performed";
  [k: string]: unknown;
}

/** investigations row + latest persisted run (null fields when never run). */
export interface JourneyInvestigation extends Audited {
  id: Uuid;
  detection_id: Uuid;
  contract_id: Uuid;
  contract_revision: number;
  question: string;
  report_id: Uuid | null;
  as_of: Instant | null;
  result: InvestigationResult | null;
  evidence_snapshot: unknown;
}

export interface InterventionDecision extends Audited {
  id: Uuid;
  investigation_id: Uuid;
  report_id: Uuid;
  factor_id: Uuid | null;
  policy_id: Uuid | null;
  status: "blocked" | "executed" | "failed";
  reason: string;
}

export interface InterventionExecution extends Audited {
  id: Uuid;
  decision_id: Uuid;
  resource_id: Uuid;
  before_value: boolean;
  after_value: boolean;
  undo_of: Uuid | null;
}

export type RecoveryStatus = "recuperacao_completa" | "recuperacao_parcial" | "ausencia_de_recuperacao" | "resultado_inconclusivo";

/** F05 evaluate_recovery result. Three indicators are deliberately separate. */
export interface RecoveryResult {
  status: RecoveryStatus;
  reason: string;
  execution_succeeded: boolean;
  improvement_observed: boolean | null;
  minimum_met: boolean | null;
  baseline_met: boolean | null;
  delta: number | null;
  before: { observed_value?: number; state?: ValueState; [k: string]: unknown } | null;
  after: { observed_value?: number; state?: ValueState; [k: string]: unknown } | null;
  baseline: number | null;
  minimum_acceptable: number | null;
  causal_attribution: "not_established";
  independent_verification: "not_established";
  evidence_basis: string;
}

export interface JourneyRecoveryPlan extends Audited {
  id: Uuid;
  decision_id: Uuid;
  contract_id: Uuid;
  pre_revision: number;
  post_revision: number;
  reason: string;
  report_id: Uuid | null;
  as_of: Instant | null;
  result: RecoveryResult | null;
  evidence_snapshot: unknown;
}

export type WorkItemNext =
  | "append_value"
  | "detect"
  | "supply_context_or_open_investigation"
  | "investigate"
  | "supply_evidence_or_verification"
  | "review_investigation_conclusion"
  | "review_intervention_authorization"
  | "review_execution_blocker"
  | "plan_recovery"
  | "evaluate_recovery"
  | "supply_outcome_evidence_and_reevaluate"
  | "review_observed_recovery";

/** Integration guidance over persisted state. NOT permission, eligibility or causality. */
export type WorkItem =
  | { stage: "contract"; next: "append_value"; needed: string }
  | { stage: "detection"; contract_id: Uuid; next: "detect"; needed: string }
  | { stage: "investigation"; detection_id: Uuid; next: "supply_context_or_open_investigation"; needed: string }
  | {
      stage: "investigation";
      investigation_id: Uuid;
      next: Extract<WorkItemNext, "investigate" | "supply_evidence_or_verification" | "review_intervention_authorization" | "review_investigation_conclusion">;
      blockers: unknown;
      needed: unknown;
      report_id: Uuid | null;
      as_of: Instant | null;
    }
  | { stage: "intervention"; decision_id: Uuid; next: "plan_recovery" | "review_execution_blocker"; blocker: string }
  | {
      stage: "recovery";
      plan_id: Uuid;
      next: "evaluate_recovery" | "supply_outcome_evidence_and_reevaluate" | "review_observed_recovery";
      result: RecoveryResult | null;
      as_of: Instant | null;
    };

export interface ClientJourney {
  contract_version: "f06-v1";
  tenant_id: Uuid;
  client_id: Uuid;
  authorization_basis: "engine_checks_required_at_execution";
  causal_attribution: "not_established";
  contracts: ContractVersion[];
  sources: SourceVersion[];
  evidence_history: EvidenceVersion[];
  detections: DetectionRun[];
  investigations: JourneyInvestigation[];
  decisions: InterventionDecision[];
  executions: InterventionExecution[];
  recovery_plans: JourneyRecoveryPlan[];
  operations: OperationReceipt[];
  work_items: WorkItem[];
}

