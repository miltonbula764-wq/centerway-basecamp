import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type { TenantInfo } from "./tenant";

export const membershipsQuery = (userId: string) =>
  queryOptions({
    queryKey: ["memberships", userId],
    staleTime: 0,
    refetchInterval: 30000,
    refetchOnWindowFocus: "always",
    queryFn: async ({ signal }): Promise<TenantInfo[]> => {
      const { data, error } = await supabase
        .from("memberships")
        .select("role, tenants(id, name, subject_unit_type)")
        .eq("user_id", userId)
        .order("created_at").abortSignal(signal);
      if (error) throw error;
      return (data ?? [])
        .filter((m) => m.tenants)
        .map((m) => ({
          id: m.tenants!.id,
          name: m.tenants!.name,
          subject_unit_type: m.tenants!.subject_unit_type,
          role: m.role,
        }));
    },
  });
