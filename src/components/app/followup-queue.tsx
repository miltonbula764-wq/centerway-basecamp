import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useTenant } from "@/lib/tenant";
import { followupQuery, queueActions, queueCategories, queueReasonText } from "@/lib/followup";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, ErrorState, Loading, NativeSelect, PageHeader, Panel, formatDate } from "./ui-bits";
export function FollowupQueue() {
  const { tenant } = useTenant();
  return <Queue key={tenant.id} />;
}
function Queue() {
  const { tenant } = useTenant();
  const [filters, setFilters] = useState({ client: "", indicator: "", category: "" });
  const [cursors, setCursors] = useState<string[]>([""]);
  const query = useQuery(
    followupQuery(tenant.id, { ...filters, after: cursors[cursors.length - 1]! }),
  );
  function filter(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setFilters({
      client: String(f.get("client")),
      indicator: String(f.get("indicator")),
      category: String(f.get("category")),
    });
    setCursors([""]);
  }
  return (
    <>
      <PageHeader
        title="Central de acompanhamento"
        description={`${tenant.name} · Estados persistidos, pendências e orientação para o próximo trabalho humano.`}
      />
      <form
        onSubmit={filter}
        className="mb-5 grid gap-3 sm:grid-cols-2"
        aria-label="Filtros de acompanhamento"
      >
        <label>
          Cliente
          <Input name="client" maxLength={200} placeholder="Nome ou referência" />
        </label>
        <label>
          Indicador
          <Input name="indicator" maxLength={200} placeholder="Chave do indicador" />
        </label>
        <label>
          Estado
          <NativeSelect name="category" aria-label="Estado">
            <option value="">Todos os estados</option>
            {Object.entries(queueCategories).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </label>
        <div className="flex items-end gap-2">
          <Button type="submit">Filtrar fila</Button>
          <Button
            type="button"
            variant="secondary"
            disabled={query.isFetching}
            onClick={() => query.refetch()}
          >
            Atualizar fila
          </Button>
        </div>
      </form>
      <p className="mb-4 text-sm text-muted-foreground">
        Leitura sem alterações aos casos. A orientação exige revisão humana; cada operação volta a
        validar permissões e evidências no servidor. Sem prioridade comercial calculada.
      </p>
      {query.isError && (
        <ErrorState
          message={`Não foi possível consultar a central. Requer a migração 0015. ${query.error.message}`}
          onRetry={() => query.refetch()}
        />
      )}
      {query.isPending ? (
        <Loading />
      ) : (
        !query.isError &&
        query.data && (
          <>
            <p role="status" className="mb-3 text-xs text-muted-foreground">
              Relógio do servidor: {formatDate(query.data.server_now)} · Página {cursors.length} ·{" "}
              {query.isFetching ? "A atualizar…" : "Atualização automática a cada minuto"}
            </p>
            {!query.data.items.length ? (
              <Empty title="Sem entradas para estes filtros">
                A fila acompanha indicadores de resultado do perfil aprovado, configurações C04 e
                casos existentes. Clientes sem perfil/indicador definido devem ser preparados em
                Clientes e Perfil de valor.
              </Empty>
            ) : (
              <div className="space-y-4">
                {query.data.items.map((item) => (
                  <article
                    key={item.entry_key}
                    data-testid="queue-entry"
                    data-entry-key={item.entry_key}
                  >
                    <Panel
                      title={`${item.display_name || item.external_ref} · ${item.indicator_key}`}
                    >
                      <div className="space-y-3 break-words text-sm">
                        <p className="font-semibold">{queueCategories[item.category]}</p>
                        <p>
                          {item.tenant_name} · {item.external_ref} · Estado persistido: {item.state}
                        </p>
                        <p className="text-xs">
                          {item.contract}
                          {item.configuration_version !== null &&
                            ` · Configuração v${item.configuration_version}`}
                          {item.case_id && ` · Caso ${item.case_id} · v${item.case_version}`}
                          {item.evaluation_id && ` · Avaliação ${item.evaluation_id}`}
                        </p>
                        {item.stale && (
                          <p role="status" className="rounded border p-2">
                            Informação desatualizada: configuração ou evidências posteriores exigem
                            revisão. O resultado histórico mantém-se.
                          </p>
                        )}
                        <ul className="list-disc pl-5">
                          {item.reasons.map((reason, i) => (
                            <li key={`${reason}:${i}`}>{queueReasonText(reason)}</li>
                          ))}
                        </ul>
                        <p>
                          <strong>Próxima orientação: </strong>
                          {queueActions[item.next_action] || item.next_action}
                        </p>
                        <p className="text-xs">
                          {item.required_role === "read"
                            ? "Consulta de leitura."
                            : item.can_prepare
                              ? "O seu papel permite preparar esta revisão; a validação final pertence à operação existente."
                              : `Esta revisão exige ${item.required_role === "admin" ? "administrador" : "administrador ou operador"}. Pode consultar o registo.`}
                        </p>
                        <p>
                          {item.review_at
                            ? `${item.review_kind === "objective_deadline" ? "Prazo documentado do objetivo" : "Fim da janela C08"}: ${formatDate(item.review_at)} · ${item.review_due ? "Data atingida no servidor; rever suficiência" : "Ainda em curso"}`
                            : "Data de revisão não documentada. Nenhum prazo foi presumido."}
                        </p>
                        <details>
                          <summary className="cursor-pointer">
                            Fundamento e referências persistidas
                          </summary>
                          <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">
                            {JSON.stringify(item.basis, null, 2)}
                          </pre>
                        </details>
                        <div className="flex flex-wrap gap-4">
                          <Link
                            className="underline"
                            to="/app/clientes/$subjectId"
                            params={{ subjectId: item.subject_id }}
                          >
                            Abrir cliente
                          </Link>
                          <Link
                            className="underline"
                            to="/app/casos"
                            search={{
                              tenant: tenant.id,
                              subject: item.subject_id,
                              case: item.case_id || undefined,
                              kind: item.kind,
                              configuration: !item.case_id
                                ? item.configuration_id || undefined
                                : undefined,
                              evaluation: !item.case_id
                                ? item.evaluation_id || undefined
                                : undefined,
                            }}
                          >
                            {item.case_id ? "Abrir caso" : "Abrir objetivo e avaliação"}
                          </Link>
                        </div>
                      </div>
                    </Panel>
                  </article>
                ))}
              </div>
            )}
            <div className="mt-5 flex items-center gap-3">
              <Button
                variant="secondary"
                disabled={cursors.length === 1 || query.isFetching}
                onClick={() => setCursors((c) => c.slice(0, -1))}
              >
                Página anterior
              </Button>
              <Button
                variant="secondary"
                disabled={!query.data.has_more || query.isFetching}
                onClick={() => setCursors((c) => [...c, query.data!.next_cursor!])}
              >
                Página seguinte
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Ordem estável por tipo e identidade; 25 entradas por página. A fila é atual: filtros e
              páginas podem mudar após novas operações.
            </p>
          </>
        )
      )}
    </>
  );
}
