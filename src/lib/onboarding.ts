import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "./tenant";
export type SetupSubject = {
  id: string;
  tenant_id: string;
  external_ref: string;
  display_name: string | null;
};
export type SetupIndicator = {
  tenant_id: string;
  subject_id: string | null;
  indicator_key: string;
  name: string;
  unit: string;
  configuration: null | {
    id: string;
    version: number;
    profile_id: string;
    pending_fields: string[];
    compatibility: string | null;
  };
  profile_changed: boolean;
  has_observations: boolean;
  new_observations: boolean;
  run: null | {
    id: string;
    as_of: string;
    data_cutoff: string;
    status: string | null;
    reasons: string[] | null;
  };
  bundle: null | { id: string; status: string | null; reasons: string[] | null };
  evaluation: null | {
    id: string;
    bundle_id: string;
    configuration_state: string;
    evidence: string;
    result: string;
    core_disposition: string;
    reasons: string[] | null;
  };
};
export type OperationalSetup = {
  tenant_id: string;
  role: string;
  server_now: string;
  approved_profile: null | { id: string; version: number; promise: string };
  draft_profile: null | { id: string; version: number; issues: string[] };
  subjects: SetupSubject[];
  has_more_subjects: boolean;
  subject: SetupSubject | null;
  indicators: SetupIndicator[];
  has_more_indicators: boolean;
};
export const onboardingQuery = (
  tenant: string,
  role: string,
  subject: string | undefined,
  afterSubject: string,
  afterIndicator: string,
) =>
  queryOptions({
    queryKey: tk(tenant, "onboarding", role, subject, afterSubject, afterIndicator),
    staleTime: 0,
    refetchInterval: 30000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("operational_onboarding", {
          _tenant_id: tenant,
          ...(subject ? { _subject_id: subject } : {}),
          ...(afterSubject ? { _after_subject: afterSubject } : {}),
          _after_indicator: afterIndicator,
          _limit: 25,
        })
        .abortSignal(signal);
      if (error) throw error;
      const p = data as unknown as OperationalSetup;
      if (
        !p ||
        p.tenant_id !== tenant ||
        p.role !== role ||
        (subject && p.subject?.id !== subject) ||
        (p.subject?.tenant_id && p.subject.tenant_id !== tenant) ||
        p.subjects.some((s) => s.tenant_id !== tenant) ||
        p.indicators.some((i) => i.tenant_id !== tenant || i.subject_id !== (p.subject?.id ?? null))
      )
        throw Error("Resposta de configuração não corresponde à empresa, papel ou cliente atual.");
      return p;
    },
  });
// Presentation of persisted facts only. Sufficiency/value remain exclusively C02/C03/C04 decisions.
export function indicatorSetup(i: SetupIndicator) {
  const evaluated = !!i.evaluation;
  const stale =
    i.new_observations ||
    i.profile_changed ||
    !!(i.evaluation && (!i.bundle || i.evaluation.bundle_id !== i.bundle.id));
  const valid =
    evaluated &&
    !stale &&
    i.evaluation!.evidence === "sufficient" &&
    i.evaluation!.configuration_state === "compatible";
  const stage: keyof typeof setupActions =
    !i.configuration || i.profile_changed
      ? "goal"
      : !i.has_observations
        ? "measurements"
        : !i.run || i.new_observations
          ? "analysis"
          : !i.bundle
            ? "evidence"
            : !evaluated || stale
              ? "evaluation"
              : "review";
  return { stage, valid, stale, evaluated };
}
export const setupActions = {
  goal: "Documentar ou rever objetivo C04",
  measurements: "Fornecer medições C01",
  analysis: "Executar ou rever análise C02",
  evidence: "Construir ou consultar pacote C03",
  evaluation: "Executar avaliação C04",
  review: "Rever resultado e pendências C04",
};
