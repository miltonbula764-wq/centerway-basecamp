import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type { Database } from "@/integrations/supabase/types";
import { tk } from "./tenant";
export type Cycle = {
  id: string;
  tenant_id: string;
  case_id: string;
  number: number;
  start_sequence: number;
  reason: string;
  reference: string;
  previous_decision_id: string | null;
  created_by: string;
  created_at: string;
};
export type CycleEvent = Database["public"]["Tables"]["cw_operational_events"]["Row"];
export type CycleHistory = {
  tenant_id: string;
  case_id: string;
  subject_id: string;
  case_version: number;
  current: Cycle;
  selected: Cycle;
  cycles: Cycle[];
  events: CycleEvent[];
  heads: Record<string, CycleEvent>;
  has_more_cycles: boolean;
  has_more_events: boolean;
};
export const cycleHistoryQuery = (
  tenant: string,
  subject: string,
  caseId: string,
  version: number,
  cycleId: string | null,
  before: number | null,
  after: number,
) =>
  queryOptions({
    queryKey: tk(
      tenant,
      "operational",
      subject,
      "cycle-history",
      caseId,
      version,
      cycleId,
      before,
      after,
    ),
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("operational_cycle_history", {
          _tenant_id: tenant,
          _case_id: caseId,
          ...(cycleId ? { _cycle_id: cycleId } : {}),
          ...(before !== null ? { _before_cycle: before } : {}),
          _after_event: after,
          _limit: 25,
        })
        .abortSignal(signal);
      if (error) throw error;
      const h = data as unknown as CycleHistory;
      const valid = (x: { tenant_id: string; case_id: string }) =>
        x.tenant_id === tenant && x.case_id === caseId;
      if (
        h.tenant_id !== tenant ||
        h.case_id !== caseId ||
        h.subject_id !== subject ||
        !valid(h.current) ||
        !valid(h.selected) ||
        h.cycles.some((x) => !valid(x)) ||
        [...h.events, ...Object.values(h.heads)].some((x) => !valid(x) || x.subject_id !== subject)
      )
        throw Error("Identidade do histórico não corresponde ao caso e à empresa.");
      return h;
    },
  });
