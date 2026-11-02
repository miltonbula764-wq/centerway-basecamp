// UI view models derived from the F06 journey (see src/data/journey-mapper.ts).
// Raw transport/projection types live in ./l01.ts and ./f06.ts.
import type { Direction, InterventionDecision, InvestigationStatus, RecoveryStatus, ValueState, WorkItem, WorkItemNext } from "./f06";
import type { OperationName } from "./l01";

export type { Direction, InvestigationStatus, RecoveryStatus, ValueState, WorkItemNext };
export type DecisionStatus = InterventionDecision["status"];
export type Priority = "alta" | "media" | "baixa";
export type Stage = WorkItem["stage"];

/** Fields with NO HTTP source in L01 (GAP-02). Always rendered with a demo label. */
export interface DemoOnlyMeta {
  company: string;
  segment: string;
  plan: string;
  owner: string;
  priority: Priority;
}

export interface WorkItemVM {
  stage: Stage;
  next: WorkItemNext;
  label: string;
  refId: string | null;
  asOf: string | null;
  /** Engine-provided blockers/needed rendered as text. */
  notes: string[];
}

export interface TimelineEventVM {
  at: string;
  label: string;
  refId: string;
  kind: "contract" | "detection" | "investigation" | "decision" | "execution" | "undo" | "recovery";
}

export interface SourceVM {
  id: string;
  revision: number;
  name: string;
  method: string;
  locator: string;
  recordedAt: string;
}

export interface ContractVM {
  id: string;
  customerId: string;
  revision: number;
  objective: string;
  indicator: string;
  unit: string;
  baseline: number;
  minimum: number;
  target: number;
  direction: Direction;
  method: string;
  period: string;
  baselinePeriod: string;
  sourceName: string;
  revisions: { revision: number; at: string; actor: string; reason: string }[];
  detections: { id: string; state: ValueState; asOf: string; revision: number }[];
}

export interface InvestigationReportVM {
  reportId: string;
  asOf: string;
  status: InvestigationStatus;
  facts: string[];
  hypotheses: string[];
  contradictions: string[];
  missing: string[];
  candidates: string[];
}

export interface InvestigationVM {
  id: string;
  customerId: string;
  contractId: string;
  contractRevision: number;
  detectionId: string;
  detectionState: ValueState | null;
  question: string;
  openedAt: string;
  actor: string;
  /** Latest persisted run only (the projection does not carry history). */
  report: InvestigationReportVM | null;
  decisionIds: string[];
}

export interface DecisionVM {
  id: string;
  customerId: string;
  investigationId: string;
  status: DecisionStatus;
  reason: string;
  actor: string;
  at: string;
  executions: { id: string; at: string; isUndo: boolean }[];
  reversed: boolean;
}

export interface RecoveryVM {
  id: string;
  customerId: string;
  decisionId: string;
  contractId: string;
  indicator: string;
  unit: string;
  direction: Direction | null;
  windows: string;
  evaluated: boolean;
  status: RecoveryStatus | null;
  reason: string | null;
  executionSucceeded: boolean | null;
  improvementObserved: boolean | null;
  minimumMet: boolean | null;
  before: number | null;
  after: number | null;
  minimum: number | null;
  asOf: string | null;
}

export interface ReceiptVM {
  requestId: string;
  customerId: string;
  operation: OperationName;
  /** Transport/porta level. */
  transportStatus: "completed" | "error";
  /** Business result as reported by the engine (may be blocked/failed/inconclusive). */
  businessStatus: string | null;
  actor: string;
  at: string;
}

export interface CustomerVM {
  id: string;
  tenantId: string;
  demo: DemoOnlyMeta | null;
  displayName: string;
  contracts: ContractVM[];
  sources: SourceVM[];
  investigations: InvestigationVM[];
  decisions: DecisionVM[];
  recoveries: RecoveryVM[];
  receipts: ReceiptVM[];
  workItems: WorkItemVM[];
  timeline: TimelineEventVM[];
  /** Passed through from F06; the UI never upgrades these. */
  causalAttribution: "not_established";
  authorizationBasis: "engine_checks_required_at_execution";
}

/** Counts over synthetic projections — illustrative, not production metrics. */
export interface OverviewKpis {
  clients: number;
  contracts: number;
  openWorkItems: number;
  inconclusiveInvestigations: number;
  executedDecisions: number;
  blockedDecisions: number;
  evaluatedRecoveries: number;
}

export interface ActivityVM extends ReceiptVM {
  customerName: string;
}

