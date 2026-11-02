// Synthetic F06 journeys. Every value is fictitious and labelled demo.
import type {
  ClientJourney,
  ContractVersion,
  DetectionRun,
  Direction,
  InterventionDecision,
  InterventionExecution,
  InvestigationResult,
  JourneyInvestigation,
  JourneyRecoveryPlan,
  RecoveryResult,
  RecoveryStatus,
  SourceVersion,
  ValueState,
} from "@/domain/f06";
import type { OperationName, OperationReceipt, SessionInfo } from "@/domain/l01";
import { deriveWorkItems } from "./derive-work-items";

export const DEMO_TENANT = "a0000000-0000-4000-8000-00000000000a";
const u = (prefix: string, n: number) => `${prefix}${String(n).padStart(6, "0")}-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const clientId = (n: number) => u("c1", n);

const actorOp = "demo_operator";
const actorRev = "demo_reviewer";

function source(n: number, name: string, method: string, at: string): SourceVersion {
  return { id: u("50", n), revision: 1, name, locator: `synthetic://source/${n}`, method, actor: actorOp, recorded_at: at, reason: "Fonte sintética de demonstração" };
}

function contract(
  client: number, n: number, revision: number, at: string,
  p: { objective: string; indicator: string; unit: string; direction: Direction; baseline: number; minimum: number; target: number; method: string; src: number; reason: string },
): ContractVersion {
  return {
    tenant_id: DEMO_TENANT, client_id: clientId(client), id: u("c0", n), revision,
    objective: p.objective, expected_outcome: p.objective, indicator: p.indicator, unit: p.unit,
    measurement_method: p.method, direction: p.direction, baseline: p.baseline, minimum_acceptable: p.minimum, target: p.target,
    baseline_start: "2026-01-01T00:00:00Z", baseline_end: "2026-03-31T23:59:59Z",
    period_start: "2026-04-01T00:00:00Z", period_end: "2026-12-31T23:59:59Z",
    source_id: u("50", p.src), source_revision: 1, baseline_reference: "Relatório sintético de baseline",
    actor: actorOp, recorded_at: at, reason: p.reason,
  };
}

function detection(n: number, contractN: number, rev: number, state: ValueState, at: string): DetectionRun {
  return { id: u("d0", n), contract_id: u("c0", contractN), contract_revision: rev, algorithm: "f02-v1", as_of: at, required_periods: 2, revision: 1, state, input_snapshot: null, result: null, actor: actorOp, recorded_at: at };
}

const item = (o: Record<string, unknown>) => o;

function investigation(n: number, detN: number, contractN: number, question: string, at: string, result: Partial<InvestigationResult> & { status: InvestigationResult["status"] } | null): JourneyInvestigation {
  return {
    id: u("10", n), detection_id: u("d0", detN), contract_id: u("c0", contractN), contract_revision: 1, question, actor: actorOp, recorded_at: at,
    report_id: result ? u("e0", n) : null, as_of: result ? at : null, evidence_snapshot: null,
    result: result
      ? {
          observed_facts: [], hypotheses: [], contradictions: [], missing_information: [], intervention_candidates: [],
          execution_authorized: false, independent_verification: "not_established", causal_inference: "not_performed",
          ...result,
        }
      : null,
  };
}

function decision(n: number, invN: number, status: InterventionDecision["status"], reason: string, at: string): InterventionDecision {
  return { id: u("de", n), investigation_id: u("10", invN), report_id: u("e0", invN), factor_id: u("fa", n), policy_id: status === "executed" ? u("90", n) : null, status, reason, actor: actorRev, recorded_at: at };
}

function execution(n: number, decN: number, at: string, undoOf: string | null = null): InterventionExecution {
  return { id: u("ee", n), decision_id: u("de", decN), resource_id: u("5f", decN), before_value: undoOf !== null, after_value: undoOf === null, undo_of: undoOf, actor: actorRev, recorded_at: at };
}

function plan(n: number, decN: number, contractN: number, at: string, r: { status: RecoveryStatus; reason: string; exec: boolean; improve: boolean | null; min: boolean | null; before: number | null; after: number | null; baseline: number; minimum: number } | null): JourneyRecoveryPlan {
  const result: RecoveryResult | null = r && {
    status: r.status, reason: r.reason, execution_succeeded: r.exec, improvement_observed: r.improve, minimum_met: r.min, baseline_met: null,
    delta: r.before !== null && r.after !== null ? Math.round((r.after - r.before) * 100) / 100 : null,
    before: r.before === null ? null : { observed_value: r.before }, after: r.after === null ? null : { observed_value: r.after },
    baseline: r.baseline, minimum_acceptable: r.minimum,
    causal_attribution: "not_established", independent_verification: "not_established", evidence_basis: "producer_declared_outcomes",
  };
  return { id: u("70", n), decision_id: u("de", decN), contract_id: u("c0", contractN), pre_revision: 1, post_revision: 2, reason: "Janelas comparáveis sintéticas", actor: actorOp, recorded_at: at, report_id: r ? u("7e", n) : null, as_of: r ? at : null, result, evidence_snapshot: null };
}

let rid = 0;
function receipt(client: number, operation: OperationName, at: string, result: unknown, status: "completed" | "error" = "completed"): OperationReceipt {
  rid += 1;
  return { tenant_id: DEMO_TENANT, client_id: clientId(client), request_id: u("ab", rid), operation, arguments: null, status, result, actor: operation === "intervene" || operation === "undo" ? actorRev : actorOp, recorded_at: at };
}

function journey(client: number, p: Partial<Omit<ClientJourney, "work_items" | "contract_version" | "tenant_id" | "client_id" | "authorization_basis" | "causal_attribution">>): ClientJourney {
  const base = {
    contract_version: "f06-v1" as const, tenant_id: DEMO_TENANT, client_id: clientId(client),
    authorization_basis: "engine_checks_required_at_execution" as const, causal_attribution: "not_established" as const,
    contracts: [], sources: [], evidence_history: [], detections: [], investigations: [], decisions: [], executions: [], recovery_plans: [], operations: [],
    ...p,
  };
  return { ...base, work_items: deriveWorkItems(base) };
}

/* 1 — Lumetra: two contracts in parallel (one investigation inconclusive, one detection without investigation). */
const j1 = journey(1, {
  sources: [source(1, "Registos de produto (sintético)", "Exportação de eventos", "2026-05-10T09:00:00Z")],
  contracts: [
    contract(1, 1, 1, "2026-05-12T10:00:00Z", { objective: "Reduzir tempo de fecho mensal", indicator: "Dias até fecho contabilístico", unit: "dias", direction: "lower", baseline: 9, minimum: 7, target: 4, method: "Mediana mensal", src: 1, reason: "Versão inicial" }),
    contract(1, 1, 2, "2026-06-03T10:00:00Z", { objective: "Reduzir tempo de fecho mensal", indicator: "Dias até fecho contabilístico", unit: "dias", direction: "lower", baseline: 9, minimum: 7, target: 5, method: "Mediana mensal", src: 1, reason: "Meta ajustada de 4 para 5 dias" }),
    contract(1, 2, 1, "2026-06-10T10:00:00Z", { objective: "Aumentar adoção da reconciliação", indicator: "Utilizadores ativos semanais", unit: "%", direction: "higher", baseline: 40, minimum: 50, target: 65, method: "Média semanal", src: 1, reason: "Versão inicial" }),
  ],
  detections: [
    detection(1, 1, 2, "deterioracao_demonstrada", "2026-08-20T12:00:00Z"),
    detection(2, 2, 1, "deterioracao_demonstrada", "2026-09-15T12:00:00Z"),
  ],
  investigations: [
    investigation(1, 1, 1, "Porque aumentou o tempo de fecho mensal?", "2026-09-10T12:00:00Z", {
      status: "inconclusivo",
      observed_facts: [item({ predicate: "Mediana subiu de 6,8 para 8,4 dias entre julho e agosto", value: true })],
      hypotheses: [item({ statement: "Saída de um utilizador-chave reduziu o uso do módulo" }), item({ statement: "Alteração de processo interno do cliente" })],
      missing_information: [item({ purpose: "Confirmação do cliente sobre mudanças de equipa", reason: "evidence_missing" })],
    }),
  ],
  operations: [
    receipt(1, "append_value", "2026-05-12T10:00:00Z", { kind: "contract", revision: 1 }),
    receipt(1, "detect", "2026-08-20T12:00:00Z", { state: "deterioracao_demonstrada" }),
    receipt(1, "investigate", "2026-09-10T12:00:00Z", { status: "inconclusivo" }),
    receipt(1, "detect", "2026-09-15T12:00:00Z", { state: "deterioracao_demonstrada" }),
  ],
});

/* 2 — Norvia: executed (synthetic) decision, partial recovery. */
const j2 = journey(2, {
  sources: [source(2, "API de entregas (sintético)", "Integração simulada", "2026-03-01T09:00:00Z")],
  contracts: [
    contract(2, 3, 1, "2026-03-04T10:00:00Z", { objective: "Aumentar entregas no prazo", indicator: "Entregas no prazo", unit: "%", direction: "higher", baseline: 91, minimum: 90, target: 95, method: "Média móvel 30 dias", src: 2, reason: "Versão inicial" }),
    contract(2, 3, 2, "2026-09-01T10:00:00Z", { objective: "Aumentar entregas no prazo", indicator: "Entregas no prazo", unit: "%", direction: "higher", baseline: 91, minimum: 90, target: 95, method: "Média móvel 30 dias", src: 2, reason: "Janela posterior registada" }),
  ],
  detections: [detection(3, 3, 1, "deterioracao_demonstrada", "2026-06-15T12:00:00Z")],
  investigations: [
    investigation(2, 3, 3, "Porque caíram as entregas no prazo?", "2026-07-05T12:00:00Z", {
      status: "impedimento_demonstrado",
      observed_facts: [item({ predicate: "Queda concentrada em duas rotas novas", value: true })],
      hypotheses: [item({ statement: "Janelas de entrega incompletas nas rotas novas" })],
      intervention_candidates: [item({ category: "Configuração", potentially_actionable: true })],
    }),
  ],
  decisions: [decision(1, 2, "executed", "policy_checks_passed_synthetic", "2026-07-10T12:00:00Z")],
  executions: [execution(1, 1, "2026-07-10T12:01:00Z")],
  recovery_plans: [plan(1, 1, 3, "2026-10-15T12:00:00Z", { status: "recuperacao_parcial", reason: "improvement_below_contractual_minimum", exec: true, improve: true, min: false, before: 86, after: 89, baseline: 91, minimum: 90 })],
  operations: [
    receipt(2, "detect", "2026-06-15T12:00:00Z", { state: "deterioracao_demonstrada" }),
    receipt(2, "investigate", "2026-07-05T12:00:00Z", { status: "impedimento_demonstrado" }),
    receipt(2, "intervene", "2026-07-10T12:00:00Z", { status: "executed", synthetic: true }),
    receipt(2, "evaluate_recovery", "2026-10-15T12:00:00Z", { status: "recuperacao_parcial" }),
  ],
});

/* 3 — Quintal: contradictions open + an earlier case reversed (undo) → inconclusive. */
const j3 = journey(3, {
  sources: [source(3, "Agenda clínica (sintético)", "Integração simulada", "2026-02-01T09:00:00Z"), source(4, "Relatório manual (sintético)", "Ficheiro declarado", "2026-02-01T09:00:00Z")],
  contracts: [
    contract(3, 4, 1, "2026-02-10T10:00:00Z", { objective: "Reduzir faltas a consultas", indicator: "Taxa de faltas", unit: "%", direction: "lower", baseline: 12, minimum: 10, target: 7, method: "Rácio semanal", src: 3, reason: "Versão inicial" }),
  ],
  detections: [detection(4, 4, 1, "deterioracao_demonstrada", "2026-04-02T12:00:00Z"), detection(5, 4, 1, "resultado_inconclusivo", "2026-08-05T12:00:00Z")],
  investigations: [
    investigation(3, 4, 4, "Lembretes desativados explicam a subida?", "2026-04-10T12:00:00Z", {
      status: "impedimento_demonstrado",
      observed_facts: [item({ predicate: "Lembretes desativados numa clínica desde março", value: true })],
      intervention_candidates: [item({ category: "Configuração", potentially_actionable: true })],
    }),
    investigation(4, 5, 4, "Porque divergem as fontes sobre a taxa de faltas?", "2026-08-20T12:00:00Z", {
      status: "inconclusivo",
      observed_facts: [item({ predicate: "Agenda clínica indica 11,5% em julho", value: true })],
      hypotheses: [item({ statement: "Definições diferentes de 'falta' entre fontes" })],
      contradictions: [item({ purpose: "Relatório manual indica 8% para o mesmo período" })],
      missing_information: [item({ purpose: "Definição comum de 'falta'", reason: "evidence_missing" }), item({ purpose: "Dados por clínica", reason: "evidence_missing" })],
    }),
  ],
  decisions: [decision(2, 3, "executed", "policy_checks_passed_synthetic", "2026-04-15T12:00:00Z")],
  executions: [execution(2, 2, "2026-04-15T12:01:00Z"), execution(3, 2, "2026-05-02T09:00:00Z", u("ee", 2))],
  recovery_plans: [plan(2, 2, 4, "2026-07-01T12:00:00Z", { status: "resultado_inconclusivo", reason: "intervention_reversed_before_window_end", exec: true, improve: null, min: null, before: null, after: null, baseline: 12, minimum: 10 })],
  operations: [
    receipt(3, "intervene", "2026-04-15T12:00:00Z", { status: "executed", synthetic: true }),
    receipt(3, "undo", "2026-05-02T09:00:00Z", { undone: true, synthetic: true }),
    receipt(3, "evaluate_recovery", "2026-07-01T12:00:00Z", { status: "resultado_inconclusivo" }),
    receipt(3, "investigate", "2026-08-20T12:00:00Z", { status: "inconclusivo" }),
  ],
});

/* 4 — Brisa: no contract yet. */
const j4 = journey(4, {
  operations: [receipt(4, "append_value", "2026-09-14T10:00:00Z", { sqlstate: "23514", code: "engine_rejected" }, "error")],
});

/* 5 — Ferro: complete recovery (synthetic). */
const j5 = journey(5, {
  sources: [source(5, "Telemetria de equipamentos (sintético)", "Exportação de eventos", "2026-01-05T09:00:00Z")],
  contracts: [
    contract(5, 5, 1, "2026-01-08T10:00:00Z", { objective: "Reduzir paragens não planeadas", indicator: "Horas de paragem por mês", unit: "h", direction: "lower", baseline: 40, minimum: 30, target: 20, method: "Soma mensal", src: 5, reason: "Versão inicial" }),
  ],
  detections: [detection(6, 5, 1, "deterioracao_demonstrada", "2026-03-18T12:00:00Z")],
  investigations: [
    investigation(5, 6, 5, "Porque aumentaram as paragens?", "2026-04-05T12:00:00Z", {
      status: "impedimento_demonstrado",
      observed_facts: [item({ predicate: "Operadores novos sem formação registada", value: true })],
      intervention_candidates: [item({ category: "Formação", potentially_actionable: true })],
    }),
  ],
  decisions: [decision(3, 5, "executed", "policy_checks_passed_synthetic", "2026-04-15T12:00:00Z")],
  executions: [execution(4, 3, "2026-04-15T12:01:00Z")],
  recovery_plans: [plan(3, 3, 5, "2026-07-01T12:00:00Z", { status: "recuperacao_completa", reason: "contractual_minimum_restored", exec: true, improve: true, min: true, before: 40, after: 22, baseline: 40, minimum: 30 })],
  operations: [receipt(5, "evaluate_recovery", "2026-07-01T12:00:00Z", { status: "recuperacao_completa" })],
});

/* 6 — Atlas: absence of recovery + a blocked decision in parallel. */
const j6 = journey(6, {
  sources: [source(6, "Registos de produto (sintético)", "Exportação de eventos", "2026-04-01T09:00:00Z")],
  contracts: [
    contract(6, 6, 1, "2026-04-02T10:00:00Z", { objective: "Aumentar adoção do módulo de inventário", indicator: "Utilizadores ativos semanais", unit: "%", direction: "higher", baseline: 35, minimum: 45, target: 60, method: "Média semanal", src: 6, reason: "Versão inicial" }),
  ],
  detections: [detection(7, 6, 1, "valor_insuficiente", "2026-06-20T12:00:00Z")],
  investigations: [
    investigation(6, 7, 6, "Porque é baixa a adoção nas lojas?", "2026-06-28T12:00:00Z", {
      status: "impedimento_demonstrado",
      observed_facts: [item({ predicate: "Apenas 2 de 6 lojas usam o módulo", value: true })],
      hypotheses: [item({ statement: "Falta de formação nas lojas sem uso" })],
      intervention_candidates: [item({ category: "Formação", potentially_actionable: true }), item({ category: "Configuração", potentially_actionable: true })],
    }),
  ],
  decisions: [
    decision(4, 6, "executed", "policy_checks_passed_synthetic", "2026-07-12T12:00:00Z"),
    decision(5, 6, "blocked", "no_valid_policy_for_factor", "2026-07-12T12:05:00Z"),
  ],
  executions: [execution(5, 4, "2026-07-12T12:01:00Z")],
  recovery_plans: [plan(4, 4, 6, "2026-10-01T12:00:00Z", { status: "ausencia_de_recuperacao", reason: "no_observed_improvement", exec: true, improve: false, min: false, before: 36, after: 35, baseline: 35, minimum: 45 })],
  operations: [
    receipt(6, "intervene", "2026-07-12T12:00:00Z", { status: "executed", synthetic: true }),
    receipt(6, "intervene", "2026-07-12T12:05:00Z", { status: "blocked", reason: "no_valid_policy_for_factor" }),
    receipt(6, "evaluate_recovery", "2026-10-01T12:00:00Z", { status: "ausencia_de_recuperacao" }),
  ],
});

export const mockJourneys: ClientJourney[] = [j1, j2, j3, j4, j5, j6];

export const mockSession: SessionInfo = {
  username: "demo",
  principal: "demo_reader",
  clients: { [DEMO_TENANT]: mockJourneys.map((j) => j.client_id) },
  operations: [],
  company_tenants: [],
  demo: true,
};

/**
 * DEMO-ONLY metadata. There is NO HTTP source for these fields in L01
 * (see GAP-02); shown with an explicit "Demonstração" label.
 */
export interface DemoClientMeta {
  company: string;
  segment: string;
  plan: string;
  owner: string;
  priority: "alta" | "media" | "baixa";
}
export const demoClientMeta: Record<string, DemoClientMeta> = {
  [clientId(1)]: { company: "Lumetra Analytics", segment: "Fintech", plan: "Enterprise", owner: "Ana Ribeiro", priority: "alta" },
  [clientId(2)]: { company: "Norvia Logística", segment: "Logística", plan: "Growth", owner: "Rui Matos", priority: "media" },
  [clientId(3)]: { company: "Quintal Saúde", segment: "Saúde", plan: "Enterprise", owner: "Marta Sousa", priority: "alta" },
  [clientId(4)]: { company: "Brisa Educação", segment: "EdTech", plan: "Growth", owner: "Ana Ribeiro", priority: "media" },
  [clientId(5)]: { company: "Ferro & Vidro Industrial", segment: "Indústria", plan: "Enterprise", owner: "Rui Matos", priority: "baixa" },
  [clientId(6)]: { company: "Atlas Retalho", segment: "Retalho", plan: "Starter", owner: "Marta Sousa", priority: "media" },
};

