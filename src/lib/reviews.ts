import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "./tenant";
import { queueReasonText, type QueueItem } from "./followup";
export const reviewStates = {
  pending: "Revisão pendente",
  available: "Revisão disponível",
  waiting: "Janela ou prazo em curso",
  current: "Sem nova revisão identificada",
  closed: "Caso encerrado",
  retired: "Referência substituída",
};
const reasons: Record<string, string> = {
  new_measurements_not_analysed: "Existem medições ainda não abrangidas pela análise C02.",
  documented_measurement_cadence_elapsed:
    "A cadência documentada decorreu desde a última medição; verificar atualização dos dados.",
  measurement_anchor_missing: "Falta uma medição de referência para calcular a próxima data.",
  measurement_cadence_missing: "Cadência não documentada. Não foi presumido um prazo.",
  documented_objective_deadline_reached:
    "O prazo documentado do objetivo chegou; preparar revisão humana.",
  new_evidence_required: "É necessária nova evidência; não há autorização automática para avançar.",
  observation_window_elapsed_not_proof:
    "A janela terminou; isso não comprova suficiência das medições.",
  source_no_longer_current:
    "Esta referência deixou de integrar a projeção atual; histórico preservado.",
};
export const reviewReason = (key: string) => reasons[key] || queueReasonText(key);
export type ReviewAttempt = {
  id: string;
  tenant_id: string;
  status: "completed" | "failed";
  finished_at: string;
  processed: number;
  error_code: string | null;
  actor_kind: "human" | "scheduler";
};
export type ReviewEntry = {
  id: string;
  tenant_id: string;
  entry_key: string;
  subject_id: string;
  indicator_key: string;
  revision: number;
  checked_at: string;
  source: Omit<QueueItem, "kind"> & { kind: QueueItem["kind"] | "measurement" };
  facts: {
    status: keyof typeof reviewStates;
    review_at?: string;
    next_measurement_at?: string;
    reasons: string[];
  };
  needs_refresh: boolean;
};
export type ReviewPage = {
  tenant_id: string;
  server_now: string;
  items: ReviewEntry[];
  has_more: boolean;
  next_cursor: string | null;
  scan: {
    next_poll_at: string;
    last_attempt_at: string | null;
    last_success_at: string | null;
    last_cycle_at: string | null;
    last_error: string | null;
    phase: string;
  } | null;
  attempts: ReviewAttempt[];
};
export const reviewsQuery = (tenant: string, status: string, indicator: string, after: string) =>
  queryOptions({
    queryKey: tk(tenant, "scheduled-reviews", status, indicator, after),
    staleTime: 0,
    refetchInterval: 60000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("scheduled_reviews", {
          _tenant_id: tenant,
          _status: status,
          _indicator: indicator,
          _after: after,
          _limit: 25,
        })
        .abortSignal(signal);
      if (error) throw error;
      const page = data as unknown as ReviewPage;
      if (
        page.tenant_id !== tenant ||
        page.items.some((x) => x.tenant_id !== tenant || x.source.tenant_id !== tenant) ||
        page.attempts.some((x) => x.tenant_id !== tenant)
      )
        throw new Error("Identidade da empresa não corresponde à consulta.");
      return page;
    },
  });
