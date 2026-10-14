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
