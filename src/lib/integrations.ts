import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "./tenant";
// Administrative metadata uses the existing admin cache boundary: demotion evicts it too.
export const integrationKey = (tenant: string) => tk(tenant, "team", "admin", "integrations");
export const credentialsQuery = (tenant: string, page: number) =>
  queryOptions({
    queryKey: [...integrationKey(tenant), "credentials", page],
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .from("ingestion_credentials")
        .select(
          "id,tenant_id,name,source,expires_at,revoked_at,rotated_from,created_at,last_used_at,last_status",
        )
        .eq("tenant_id", tenant)
        .order("id")
        .range(page * 25, page * 25 + 25)
        .abortSignal(signal);
      if (error) throw error;
      if (data.some((r) => r.tenant_id !== tenant)) throw Error("tenant_mismatch");
      return data;
    },
  });
export const ingestionEventsQuery = (tenant: string, page: number) =>
  queryOptions({
    queryKey: [...integrationKey(tenant), "events", page],
    staleTime: 0,
    refetchInterval: 30_000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .from("ingestion_api_events")
        .select("*")
        .eq("tenant_id", tenant)
        .order("created_at", { ascending: false })
        .order("id", { ascending: false })
        .range(page * 25, page * 25 + 25)
        .abortSignal(signal);
      if (error) throw error;
      if (data.some((r) => r.tenant_id !== tenant)) throw Error("tenant_mismatch");
      const ids = [...new Set(data.flatMap((r) => (r.batch_id ? [r.batch_id] : [])))];
      if (!ids.length) return data.map((r) => ({ ...r, errors: [] }));
      const batches = await supabase
        .from("ingestion_batches")
        .select("id,tenant_id,errors")
        .eq("tenant_id", tenant)
        .in("id", ids)
        .abortSignal(signal);
      if (batches.error) throw batches.error;
      if (batches.data.some((r) => r.tenant_id !== tenant)) throw Error("tenant_mismatch");
      return data.map((r) => ({
        ...r,
        errors: batches.data.find((b) => b.id === r.batch_id)?.errors ?? [],
      }));
    },
  });
export function ingestionError(error: unknown) {
  const message = (error as { message?: string })?.message;
  if (message === "credential_expiry_required")
    return "Escolha uma validade futura de até 365 dias.";
  if (message === "admin_required") return "Esta operação exige um administrador atual da empresa.";
  return "Não foi possível concluir. Atualize e confirme os campos e as permissões. A migração 0018 é necessária.";
}
