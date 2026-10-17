import type { Json } from "@/integrations/supabase/types";
export type Objective = {
  id: string; tenant_id: string; subject_id: string; profile_id: string; policy_version: string;
  deadline: string; measurement_source: string; capacity_ref: string; commitment_ref: string;
  customer_confirmation_ref: string; created_by: string; created_at: string;
};
export type Assessment = {
  id: string; tenant_id: string; subject_id: string; objective_id: string; bundle_id: string;
  policy_version: string; result: string; evidence: string; details: Json; created_by: string; created_at: string;
};
export type CaseState = "investigation" | "needs_information" | "impediment_found" | "awaiting_approval" |
  "approved" | "waiting_observation" | "observed" | "remain_open" | "closed_resolved";
export type JourneyCase = {
  id: string; tenant_id: string; subject_id: string; assessment_id: string; policy_version: string;
  state: CaseState; version: number; created_by: string; created_at: string;
};
export type CaseEvent = {
  id: string; tenant_id: string; subject_id: string; case_id: string; sequence: number;
  operation_id: string; command: string; request_hash: string; from_state: string | null; to_state: CaseState;
  details: Json; policy_version: string; created_by: string; created_at: string;
};
export type ReadOnlyTable<T> = { Row: T; Insert: never; Update: never; Relationships: [] };
export const caseStateLabel: Record<CaseState, string> = {
  investigation: "Em investigação", needs_information: "Aguarda evidência", impediment_found: "Impedimento confirmado",
  awaiting_approval: "Aguarda aprovação", approved: "Intervenção aprovada", waiting_observation: "Janela de observação",
  observed: "Resultado observado", remain_open: "Caso continua aberto", closed_resolved: "Encerrado com critérios satisfeitos",
};
export const resultLabel: Record<string, string> = {
  achieved: "Objetivo atingido", not_achieved: "Objetivo não atingido", pending_deadline: "Prazo ainda não vencido",
  inconclusive: "Evidência insuficiente", sufficient: "Suficiente", insufficient: "Insuficiente",
  improved: "Melhorou", unchanged: "Sem alteração", worsened: "Piorou", confirmed_blocker: "Impedimento confirmado",
};
export const journeySteps = [
  ["C01", "Recolha", "Observações imutáveis via CSV"], ["C02", "Sinais", "Análise temporal c02-v2"],
  ["C03", "Evidências", "Pacote histórico verificável"], ["C04", "Objetivo", "Critérios e prazo explícitos"],
  ["C05", "Investigação", "Condição e prova temporal"], ["C06", "Plano", "Intervenção manual verificável"],
  ["C07", "Execução", "Aprovação e recibo humano"], ["C08", "Observação", "Janela no servidor"],
  ["C09", "Resultado", "Comparação antes / depois"], ["C10", "Decisão", "Encerrar ou manter aberto"],
] as const;
export function eventDetails(event: CaseEvent | undefined): Record<string, Json | undefined> {
  const v = event?.details; return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
export function journeyError(error: unknown): string {
  const e = error as { code?: string; message?: string };
  if (["42P01", "PGRST205", "PGRST202"].includes(e?.code ?? ""))
    return "O percurso MVP ainda não está instalado nesta base. Use uma base descartável com a migração 0012. O backend hospedado não foi alterado.";
  const errors: Record<string, string> = {
    admin_required: "Esta operação exige um administrador.", write_role_required: "É necessário ser administrador ou operador desta empresa.",
    demo_profile_incompatible: "O perfil não corresponde à política sintética report_hours. Consulte o contrato da demonstração.",
    approved_profile_and_deadline_required: "É necessário um perfil aprovado e um prazo válido.",
    historical_profile_mismatch: "A evidência pertence a outra versão do perfil.",
    assessment_not_eligible: "Só uma avaliação suficiente com objetivo não atingido permite abrir um caso.",
    stale_case_version: "O caso mudou. Atualize o histórico antes de repetir.", idempotency_conflict: "A chave da operação já foi usada com outro conteúdo.",
    transition_not_allowed: "Esta ação não é permitida no estado atual.",
    approval_expired: "A aprovação expirou. Este piloto ainda não permite renovar o plano; a execução ficou bloqueada.",
    human_receipt_required: "Registe a referência da execução humana (até 2000 caracteres).",
    observation_window_not_due: "A janela de 14 dias ainda não terminou. O servidor mantém o caso em observação.",
    bundle_not_found: "O pacote não existe para este cliente e empresa.", case_not_found: "Caso não encontrado nesta empresa.",
  };
  return errors[e?.message ?? ""] ?? "Não foi possível concluir a operação. Atualize os dados e tente novamente; nenhuma conclusão foi presumida.";
}
