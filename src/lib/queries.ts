import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "./tenant";

export const profilesQuery = (tenantId: string) =>
  queryOptions({
    queryKey: tk(tenantId, "profiles"),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("tenant_value_profiles")
        .select("*")
        .eq("tenant_id", tenantId)
        .order("version", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
  });

export const indicatorsQuery = (tenantId: string, profileId: string) =>
  queryOptions({
    queryKey: tk(tenantId, "indicators", profileId),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("profile_indicators")
        .select("*")
        .eq("tenant_id", tenantId)
        .eq("profile_id", profileId)
        .order("created_at");
      if (error) throw error;
      return data ?? [];
    },
  });

export const issuesQuery = (tenantId: string, profileId: string) =>
  queryOptions({
    queryKey: tk(tenantId, "issues", profileId),
    queryFn: async () => {
      const { data, error } = await supabase.rpc("value_profile_approval_issues", { _profile_id: profileId });
      if (error) throw error;
      return (data ?? []) as string[];
    },
  });

export const countQuery = (tenantId: string, table: "subjects" | "observations" | "ingestion_batches" | "memberships") =>
  queryOptions({
    queryKey: tk(tenantId, "count", table),
    queryFn: async () => {
      const { count, error } = await supabase.from(table).select("id", { count: "exact", head: true }).eq("tenant_id", tenantId);
      if (error) throw error;
      return count ?? 0;
    },
  });

/** Existing immutable C03 identity, not a new C04 conclusion or persisted state. */
export type ValueContextBundle = {
  id: string;
  run_id: string;
  c02_input_hash: string;
  c02_algorithm_version: string;
  data_cutoff: string;
};
type Run = {
  id: string; tenant_id: string; subject_id: string; profile_id: string; profile_version: number;
  input_hash: string; algorithm_version: string; data_cutoff: string;
};
type Profile = {
  id: string; tenant_id: string; version: number; status: string; approved_at: string | null;
  promise: string; expected_outcome: string | null;
};


/** Read-only provenance for future Core consumers; no value classification. */
export const historicalValueContextQuery = (tenantId: string, subjectId: string, bundle: ValueContextBundle) =>
  queryOptions({
    queryKey: tk(tenantId, "value_context", subjectId, bundle.run_id, bundle.id),
    queryFn: async () => {
      const runs = await supabase.from("c02_runs")
        .select("id, tenant_id, subject_id, profile_id, profile_version, input_hash, algorithm_version, data_cutoff")
        .eq("tenant_id", tenantId).eq("subject_id", subjectId).eq("id", bundle.run_id).limit(2);
      if (runs.error) throw runs.error;
      if (runs.data?.length !== 1) return null;
      const run = runs.data[0] as Run;
      if (run.id !== bundle.run_id || run.tenant_id !== tenantId || run.subject_id !== subjectId ||
          run.input_hash !== bundle.c02_input_hash || run.algorithm_version !== bundle.c02_algorithm_version ||
          !Number.isFinite(Date.parse(run.data_cutoff)) || Date.parse(run.data_cutoff) !== Date.parse(bundle.data_cutoff)) return null;
      const profiles = await supabase.from("tenant_value_profiles")
        .select("id, tenant_id, version, status, approved_at, promise, expected_outcome")
        .eq("tenant_id", tenantId).eq("id", run.profile_id).limit(2);
      if (profiles.error) throw profiles.error;
      if (profiles.data?.length !== 1) return null;
      const profile = profiles.data[0] as Profile;
      if (profile.id !== run.profile_id || profile.tenant_id !== tenantId || profile.version !== run.profile_version ||
          !["approved", "superseded"].includes(profile.status) || !profile.approved_at ||
          !Number.isFinite(Date.parse(profile.approved_at)) || !profile.promise?.trim()) return null;
      return { profile, run, bundle: { ...bundle } };
    },
  });
