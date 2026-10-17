import { useQuery } from "@tanstack/react-query";
import { historicalValueContextQuery, type ValueContextBundle } from "@/lib/queries";
import { ErrorState, Loading, Mono, StatusPill } from "./ui-bits";

/** Read through the run's historical profile FK, never through the currently approved profile. */
export function ValueContext({ tenantId, subjectId, bundle }: {
  tenantId: string; subjectId: string; bundle: ValueContextBundle;
}) {
  const context = useQuery(historicalValueContextQuery(tenantId, subjectId, bundle));

  return (
    <section aria-label="Promessa na análise" className="rounded-md border border-border p-4 text-sm">
      <h3 className="mb-2 font-medium">Promessa na análise</h3>
      {context.isLoading ? <Loading /> : context.isError ? (
        <ErrorState message="Não foi possível consultar a promessa desta análise." onRetry={() => context.refetch()} />
      ) : !context.data ? (
        <p className="text-muted-foreground">Contexto histórico indisponível ou incompatível com este pacote.</p>
      ) : (
        <div className="space-y-2">
          <StatusPill tone="neutral">Perfil v{context.data.profile.version} · aprovado para esta análise</StatusPill>
          <p className="whitespace-pre-wrap">{context.data.profile.promise}</p>
          <dl className="grid gap-y-1 text-xs sm:grid-cols-[180px_1fr]">
            <dt className="text-muted-foreground">Resultado esperado</dt>
            <dd className="whitespace-pre-wrap">{context.data.profile.expected_outcome?.trim() || "Não registado neste perfil."}</dd>
            <dt className="text-muted-foreground">Perfil histórico</dt>
            <dd><Mono className="break-all">{context.data.profile.id}</Mono></dd>
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
