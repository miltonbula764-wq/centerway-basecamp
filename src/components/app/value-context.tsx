import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "@/lib/tenant";
import { ErrorState, Loading, Mono, StatusPill } from "./ui-bits";

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

/** Read through the run's historical profile FK, never through the currently approved profile. */
export function ValueContext({ tenantId, subjectId, bundle }: {
  tenantId: string; subjectId: string; bundle: ValueContextBundle;
}) {
  const context = useQuery({
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
      return profile;
    },
  });

  return (
    <section aria-label="Promessa na análise" className="rounded-md border border-border p-4 text-sm">
      <h3 className="mb-2 font-medium">Promessa na análise</h3>
      {context.isLoading ? <Loading /> : context.isError ? (
        <ErrorState message="Não foi possível consultar a promessa desta análise." onRetry={() => context.refetch()} />
      ) : !context.data ? (
        <p className="text-muted-foreground">Contexto histórico indisponível ou incompatível com este pacote.</p>
      ) : (
        <div className="space-y-2">
          <StatusPill tone="neutral">Perfil v{context.data.version} · aprovado para esta análise</StatusPill>
          <p className="whitespace-pre-wrap">{context.data.promise}</p>
          <dl className="grid gap-y-1 text-xs sm:grid-cols-[180px_1fr]">
            <dt className="text-muted-foreground">Resultado esperado</dt>
            <dd className="whitespace-pre-wrap">{context.data.expected_outcome?.trim() || "Não registado neste perfil."}</dd>
            <dt className="text-muted-foreground">Perfil histórico</dt>
            <dd><Mono className="break-all">{context.data.id}</Mono></dd>
          </dl>
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Conclusão de valor não disponível. O sinal C02 e a integridade do pacote, por si só, não demonstram valor realizado
        nem perda de valor. As evidências e os indicadores desta análise estão apresentados abaixo.
      </p>
    </section>
  );
}
