import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "./tenant";
import type { Json } from "@/integrations/supabase/types";
export const queueCategories = {
  information_pending: "Informação pendente",
  contradiction: "Contradição identificada",
  assessment_review: "Avaliação disponível para revisão",
  investigation_planning: "Investigação ou planeamento pendente",
  authorization_execution: "Autorização ou execução pendente",
  waiting_observation: "A aguardar observação",
  results_review: "Pronto para revisão de resultados",
  result_open: "Resultado inconclusivo ou caso ainda aberto",
  closed: "Caso encerrado",
} as const;
export const queueActions: Record<string, string> = {
  document_goal: "Documentar o objetivo individual no C04",
  review_configuration: "Rever a documentação e a configuração C04",
  evaluate: "Preparar uma avaliação C04 com evidências",
  review_eligibility: "Rever a avaliação e documentar uma decisão de elegibilidade",
  collect_evidence: "Recolher medições ou referências e preparar nova evidência C03",
  investigate: "Investigar ou rever o impedimento com referências verificáveis",
  plan: "Preparar o plano e as condições de sucesso",
  authorize: "Autorizar ou renovar a autorização do plano atual",
  record_execution: "Registar a execução humana autorizada",
  wait: "Aguardar a janela documentada e recolher medições",
  compare: "Rever nova evidência com o objetivo histórico",
  decide: "Rever os critérios e documentar a decisão C10",
  consult_history: "Consultar o encerramento e o histórico",
  review_historical_contract: "Rever a nova configuração; o contrato deste caso continua fixado",
  consult_pilot: "Consultar as regras e o dossier específico do piloto FlowReports",
};
export const queueReasons: Record<string, string> = {
  configuration_missing: "Objetivo individual ainda não configurado.",
  evaluation_missing: "Não existe avaliação desta configuração.",
  configuration_revision_requires_review:
    "Existe uma versão C04 posterior. A preparação, execução e o fecho deste contrato histórico ficam bloqueados.",
  investigation_evidence_changed: "Uma referência da investigação foi corrigida; exige revisão.",
  valid_authorization_required:
    "A autorização não é válida para execução: verificar validade, plano e papel atual do aprovador.",
  window_end_does_not_prove_measurement_sufficiency:
    "O fim da janela permite revisão, mas não comprova medições suficientes.",
  objective_not_demonstrated: "O objetivo histórico ainda não foi demonstrado.",
  specific_closure_criteria_pending: "Falta demonstrar os critérios específicos de encerramento.",
  material_contradiction: "Existe contradição material documentada.",
  new_relevant_evidence_requires_comparison:
    "Há evidência relevante ainda não coberta pela comparação.",
  post_execution_observation_insufficient:
    "As medições não cobrem a janela necessária após a execução.",
  c04_evidence_or_configuration_pending: "C04 com evidência ou configuração pendente.",
  required_windows_unavailable: "Faltam janelas de medição exigidas.",
  indicator_evidence_insufficient: "Evidência insuficiente para este indicador.",
  measurement_rules_not_satisfied: "As regras documentadas de medição não foram satisfeitas.",
  specific_pilot_contract: "Cenário específico flowreports-demo-v1; consultar as regras do piloto.",
};
export type QueueItem = {
  entry_key: string;
  kind: "c04" | "operational" | "legacy";
  tenant_id: string;
  tenant_name: string;
  subject_id: string;
  display_name: string | null;
  external_ref: string;
  indicator_key: string;
  configuration_id: string | null;
  configuration_version: number | null;
  evaluation_id: string | null;
  case_id: string | null;
  case_version: number | null;
  state: string;
  category: keyof typeof queueCategories;
  next_action: string;
  reasons: string[];
  basis: Json;
  review_at: string | null;
  review_kind: string;
  review_due: boolean;
  updated_at: string | null;
  stale: boolean;
  contract: string;
  can_prepare: boolean;
  required_role: string;
};
export type QueuePage = {
  tenant_id: string;
  server_now: string;
  items: QueueItem[];
  has_more: boolean;
  next_cursor: string | null;
};
export type QueueFilter = { client: string; indicator: string; category: string; after: string };
export const followupQuery = (tenantId: string, filter: QueueFilter) =>
  queryOptions({
    queryKey: tk(tenantId, "followup", filter),
    staleTime: 0,
    refetchInterval: 60000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("core_followup_queue", {
          _tenant_id: tenantId,
          _client: filter.client,
          _indicator: filter.indicator,
          _category: filter.category,
          _after: filter.after,
          _limit: 25,
        })
        .abortSignal(signal);
      if (error) throw error;
      const page = data as unknown as QueuePage;
      if (page.tenant_id !== tenantId || page.items.some((item) => item.tenant_id !== tenantId))
        throw new Error("Identidade da empresa não corresponde à consulta.");
      return page;
    },
  });
