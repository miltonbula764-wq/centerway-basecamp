import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { reviewsQuery, reviewStates, reviewReason, type ReviewAttempt } from "@/lib/reviews";
import { queueActions } from "@/lib/followup";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, ErrorState, Loading, NativeSelect, formatDate } from "./ui-bits";
export function ScheduledReviews() {
  const { tenant, canWrite } = useTenant();
  return <Reviews key={`${tenant.id}:${canWrite}`} />;
}
function Reviews() {
  const { tenant, canWrite } = useTenant();
  const cache = useQueryClient();
  const [filters, setFilters] = useState({ status: "", indicator: "" });
  const [cursors, setCursors] = useState([""]);
  const [operation, setOperation] = useState<string | null>(null);
  const query = useQuery(
    reviewsQuery(tenant.id, filters.status, filters.indicator, cursors.at(-1)!),
  );
  const prepare = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenant.id);
      const id = operation || crypto.randomUUID();
      setOperation(id);
      const { data, error } = await supabase.rpc("prepare_scheduled_reviews", {
        _tenant_id: tenant.id,
        _operation_id: id,
      });
      if (error) throw error;
      assertActiveTenant(tenant.id);
      const attempt = data as unknown as ReviewAttempt;
      if (attempt.tenant_id !== tenant.id) throw new Error("Resposta de outra empresa rejeitada.");
      setOperation(null);
      await cache.invalidateQueries({ queryKey: tk(tenant.id, "scheduled-reviews") });
      if (attempt.status === "failed")
        throw new Error(
          `Preparação falhou (${attempt.error_code}). A tentativa está registada; pode tentar novamente.`,
        );
      return attempt;
    },
  });
  return (
    <section aria-label="Revisões programadas" className="mb-8">
      <Panel title="Monitorização e revisões programadas">
        <p className="mb-3 text-sm">
          Preparação de revisão humana, sem executar avaliações ou intervenções. Estados registados
          na última verificação; consulte o registo operacional antes de agir. A consulta não
          processa a fila.
        </p>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setFilters({
              status: String(f.get("review-status")),
              indicator: String(f.get("review-indicator")),
            });
            setCursors([""]);
          }}
        >
          <label>
            Estado da revisão
            <NativeSelect name="review-status" aria-label="Estado da revisão">
              <option value="">Todas as revisões</option>
              {Object.entries(reviewStates).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label>
            Indicador da revisão
            <Input name="review-indicator" maxLength={200} />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button type="submit">Filtrar revisões</Button>
            <Button
              type="button"
              variant="secondary"
              disabled={query.isFetching}
              onClick={() => query.refetch()}
            >
              Atualizar revisões
            </Button>
          </div>
        </form>
        {canWrite && (
          <Button
            className="my-3"
            variant="secondary"
            disabled={prepare.isPending}
            onClick={() => prepare.mutate()}
          >
            {prepare.isPending ? "A preparar…" : "Preparar próximo lote de revisões"}
          </Button>
        )}
        <p className="text-xs my-2">
          Cada preparação verifica até 50 referências. Não executa C02/C03/C04. O processamento
          periódico depende da instalação separada do agendador.
        </p>
        {prepare.isError && <p role="alert">{prepare.error.message}</p>}
        {prepare.isSuccess && (
          <p role="status">Lote preparado: {prepare.data.processed} referências verificadas.</p>
        )}
        {query.isError && (
          <ErrorState
            message={`Não foi possível consultar as revisões (requer migração 0020). ${query.error.message}`}
            onRetry={() => query.refetch()}
          />
        )}
        {query.isPending && <Loading />}
        {query.data && (
          <>
            <p className="my-3 text-xs">
              Relógio do servidor: {formatDate(query.data.server_now)} · Última tentativa:{" "}
              {query.data.scan?.last_attempt_at
                ? formatDate(query.data.scan.last_attempt_at)
                : "Ainda não executada"}{" "}
              · Último ciclo completo:{" "}
              {query.data.scan?.last_cycle_at
                ? formatDate(query.data.scan.last_cycle_at)
                : "Ainda não concluído"}
            </p>
            {query.data.scan?.last_error && (
              <p role="alert">
                Falha de processamento: {query.data.scan.last_error}. Os resultados anteriores foram
                preservados. A próxima tentativa pode recuperar o processamento.
              </p>
            )}
            <p className="text-xs mb-3">
              Próxima consulta técnica elegível:{" "}
              {query.data.scan ? formatDate(query.data.scan.next_poll_at) : "Não registada"}. Não é
              um prazo comercial nem garantia de execução.
            </p>
            {!query.data.items.length && <p>Sem revisões preparadas para estes filtros.</p>}
            <div className="space-y-3">
              {query.data.items.map((item) => (
                <article
                  key={item.id}
                  data-testid="scheduled-review"
                  className="rounded border p-3 text-sm space-y-2"
                >
                  <h3 className="font-semibold">
                    {item.source.display_name || item.source.external_ref} · {item.indicator_key}
                  </h3>
                  <p>
                    {reviewStates[item.facts.status]} · {item.source.state} · Revisão de
                    monitorização v{item.revision}
                  </p>
                  <p className="text-xs">
                    Verificado: {formatDate(item.checked_at)}
                    {item.source.case_id &&
                      ` · Caso ${item.source.case_id} v${item.source.case_version}`}
                    {item.source.configuration_version &&
                      ` · Configuração v${item.source.configuration_version}`}
                  </p>
                  {item.needs_refresh && (
                    <p className="font-semibold">
                      Existem alterações ou uma data entretanto atingida. Reprocessar antes de
                      utilizar esta orientação.
                    </p>
                  )}
                  <ul className="list-disc pl-5">
                    {item.facts.reasons.map((r, i) => (
                      <li key={`${r}:${i}`}>{reviewReason(r)}</li>
                    ))}
                  </ul>
                  <p>
                    Data documentada da revisão:{" "}
                    {item.facts.review_at ? formatDate(item.facts.review_at) : "Não definida"}
                  </p>
                  {item.facts.next_measurement_at && (
                    <p>
                      Próxima medição segundo a cadência documentada:{" "}
                      {formatDate(item.facts.next_measurement_at)}
                    </p>
                  )}
                  <p>
                    Orientação na última verificação:{" "}
                    {queueActions[item.source.next_action] || "Consultar o registo"}. As operações
                    existentes validam novamente a autorização.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Link
                      className="underline"
                      to="/app/clientes/$subjectId"
                      params={{ subjectId: item.subject_id }}
                    >
                      Consultar cliente
                    </Link>
                    {item.source.kind !== "measurement" && (
                      <Link
                        className="underline"
                        to="/app/casos"
                        search={{
                          tenant: tenant.id,
                          subject: item.subject_id,
                          case: item.source.case_id || undefined,
                          kind: item.source.kind,
                          configuration: !item.source.case_id
                            ? item.source.configuration_id || undefined
                            : undefined,
                          evaluation: !item.source.case_id
                            ? item.source.evaluation_id || undefined
                            : undefined,
                        }}
                      >
                        Consultar registo operacional
                      </Link>
                    )}
                  </div>
                </article>
              ))}
            </div>
            <div className="flex gap-3 my-3">
              <Button
                variant="secondary"
                disabled={cursors.length === 1 || query.isFetching}
                onClick={() => setCursors((c) => c.slice(0, -1))}
              >
                Revisões anteriores
              </Button>
              <Button
                variant="secondary"
                disabled={!query.data.has_more || query.isFetching}
                onClick={() => setCursors((c) => [...c, query.data!.next_cursor!])}
              >
                Revisões seguintes
              </Button>
            </div>
            <details>
              <summary>Últimas tentativas de processamento</summary>
              <ul>
                {query.data.attempts.map((a) => (
                  <li key={a.id}>
                    {formatDate(a.finished_at)} ·{" "}
                    {a.actor_kind === "scheduler" ? "Agendador" : "Utilizador autorizado"} ·{" "}
                    {a.status === "completed" ? "Concluída" : `Falha ${a.error_code}`} ·{" "}
                    {a.processed} referências
                  </li>
                ))}
              </ul>
            </details>
          </>
        )}
      </Panel>
    </section>
  );
}
