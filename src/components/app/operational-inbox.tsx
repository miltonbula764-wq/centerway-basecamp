import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import {
  inboxQuery,
  myWorkQuery,
  noticeLabels,
  responsibilityError,
  type Notice,
} from "@/lib/responsibilities";
import { queueActions, queueCategories, queueReasonText } from "@/lib/followup";
import { Button } from "@/components/ui/button";
import { ErrorState, Panel, formatDate } from "./ui-bits";

export function NotificationBadge({ onNavigate }: { onNavigate?: (() => void) | undefined }) {
  const { tenant, user } = useTenant();
  const q = useQuery(inboxQuery(tenant.id, user.id, false, null, 1));
  return (
    <Link
      to="/app/acompanhamento"
      hash="notificacoes"
      onClick={onNavigate}
      className="block px-3 py-2 text-sm underline"
    >
      Notificações{q.isSuccess ? ` (${q.data.unread_count} não lidas)` : ""}
    </Link>
  );
}
export function OperationalInbox() {
  const { tenant, user } = useTenant();
  return <Inbox key={`${tenant.id}:${tenant.role}:${user.id}`} />;
}
function Inbox() {
  const { tenant, user, canWrite } = useTenant();
  const qc = useQueryClient();
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const [unread, setUnread] = useState(false);
  const [pages, setPages] = useState<(Notice | null)[]>([null]);
  const q = useQuery(inboxQuery(tenant.id, user.id, unread, pages.at(-1)!));
  const action = useMutation({
    mutationFn: async (id: string | null) => {
      assertActiveTenant(tenant.id);
      const result = id
        ? await supabase.rpc("mark_notification_read", {
            _tenant_id: tenant.id,
            _notification_id: id,
          })
        : await supabase.rpc("prepare_operational_notifications", { _tenant_id: tenant.id });
      if (result.error) throw result.error;
      assertActiveTenant(tenant.id);
      if (live.current) await qc.invalidateQueries({ queryKey: tk(tenant.id, "notifications") });
    },
  });
  return (
    <section id="notificacoes" aria-label="Caixa de notificações" className="mb-8">
      <Panel title="Notificações internas">
        <p className="text-sm mb-3">
          Acontecimentos persistidos dirigidos à sua conta nesta empresa. Uma notificação não
          concede autorização nem comprova valor. Sem envio de emails.
        </p>
        <div className="flex flex-wrap gap-3 mb-3">
          <label>
            <input
              type="checkbox"
              checked={unread}
              onChange={(e) => {
                setUnread(e.target.checked);
                setPages([null]);
              }}
            />{" "}
            Apenas não lidas
          </label>
          <Button variant="secondary" disabled={q.isFetching} onClick={() => q.refetch()}>
            Atualizar notificações
          </Button>
          {canWrite && (
            <Button
              variant="secondary"
              disabled={action.isPending}
              onClick={() => action.mutate(null)}
            >
              Processar notificações pendentes
            </Button>
          )}
        </div>
        {q.isPending && <p>A carregar notificações…</p>}
        {q.error && (
          <ErrorState
            message={`Caixa indisponível (requer migração 0022). ${responsibilityError(q.error)}`}
            onRetry={() => q.refetch()}
          />
        )}
        {action.error && <ErrorState message={responsibilityError(action.error)} />}
        {action.isSuccess && <p aria-live="polite">Operação de notificações concluída.</p>}
        {q.data && (
          <>
            <p className="mb-3 text-sm">
              {q.data.unread_count} notificações não lidas · Página {pages.length}
            </p>
            {!q.data.items.length && <p>Sem notificações nesta página.</p>}
            {q.data.items.map((n) => (
              <article
                key={n.id}
                data-testid="notification"
                className="rounded border p-3 mb-3 space-y-2 text-sm"
              >
                <h3 className="font-semibold">
                  {noticeLabels[n.kind] || n.kind} · {n.is_read ? "Lida" : "Não lida"}
                </h3>
                <p>
                  {formatDate(n.created_at)} ·{" "}
                  {n.case_id ? `Caso ${n.case_id}` : "Revisão operacional"}
                </p>
                <details>
                  <summary>Fundamento da notificação</summary>
                  <pre className="whitespace-pre-wrap break-all text-xs max-h-60 overflow-auto">
                    {JSON.stringify(n.payload, null, 2)}
                  </pre>
                </details>
                <div className="flex flex-wrap gap-3">
                  {n.subject_id && (
                    <Link
                      to="/app/clientes/$subjectId"
                      params={{ subjectId: n.subject_id }}
                      className="underline"
                    >
                      Cliente da notificação
                    </Link>
                  )}
                  {n.case_id && n.subject_id ? (
                    <Link
                      to="/app/casos"
                      search={{
                        tenant: tenant.id,
                        subject: n.subject_id,
                        case: n.case_id,
                        kind: "operational",
                      }}
                      className="underline"
                    >
                      Caso da notificação
                    </Link>
                  ) : (
                    <a href="#revisoes-programadas" className="underline">
                      Revisões e tentativas
                    </a>
                  )}
                  {!n.is_read && (
                    <Button
                      variant="secondary"
                      disabled={action.isPending}
                      onClick={() => action.mutate(n.id)}
                    >
                      Marcar como lida
                    </Button>
                  )}
                </div>
              </article>
            ))}
            <div className="flex gap-3 my-3">
              <Button
                variant="secondary"
                disabled={pages.length === 1 || q.isFetching}
                onClick={() => setPages((p) => p.slice(0, -1))}
              >
                Notificações mais recentes
              </Button>
              <Button
                variant="secondary"
                disabled={!q.data.has_more || q.isFetching}
                onClick={() => setPages((p) => [...p, q.data!.items.at(-1)!])}
              >
                Notificações anteriores
              </Button>
            </div>
            {!!q.data.processing?.length && (
              <details>
                <summary>Processamento pendente ou com falha (administração)</summary>
                {q.data.processing.map((j) => (
                  <p key={j.id} className="text-xs break-all">
                    {j.id} · {j.status} · {j.attempts} tentativas ·{" "}
                    {j.error_code || "Sem erro registado"} · Próxima tentativa técnica:{" "}
                    {formatDate(j.next_try_at)}
                  </p>
                ))}
              </details>
            )}
          </>
        )}
      </Panel>
    </section>
  );
}
export function MyOperationalWork() {
  const { tenant, user } = useTenant();
  return <MyWork key={`${tenant.id}:${tenant.role}:${user.id}`} />;
}
function MyWork() {
  const { tenant, user } = useTenant();
  const [pages, setPages] = useState([""]);
  const q = useQuery(myWorkQuery(tenant.id, user.id, pages.at(-1)!));
  return (
    <section id="minhas-pendencias" aria-label="As minhas pendências" className="mb-8">
      <Panel title="As minhas pendências">
        <p className="text-sm mb-3">
          Casos com atribuição atual válida à sua conta. Estados e orientação calculados pelo Core,
          sem ações automáticas.
        </p>
        <Button variant="secondary" disabled={q.isFetching} onClick={() => q.refetch()}>
          Atualizar minhas pendências
        </Button>
        {q.isPending && <p>A carregar casos atribuídos…</p>}
        {q.error && (
          <ErrorState message={responsibilityError(q.error)} onRetry={() => q.refetch()} />
        )}
        {q.data && (
          <>
            {!q.data.items.length && <p className="my-3">Sem casos atualmente atribuídos a si.</p>}
            {q.data.items.map((i) => (
              <article
                key={i.case_id}
                data-testid="my-work"
                className="rounded border p-3 my-3 space-y-2 text-sm"
              >
                <h3 className="font-semibold">
                  {i.display_name || i.external_ref} · {i.indicator_key}
                </h3>
                <p>
                  {queueCategories[i.category]} · {i.state} · Caso {i.case_id} v{i.case_version}
                </p>
                <ul className="list-disc pl-5">
                  {i.reasons.map((r, n) => (
                    <li key={n}>{queueReasonText(r)}</li>
                  ))}
                </ul>
                <p>
                  Próxima orientação: {queueActions[i.next_action] || i.next_action}.{" "}
                  {i.can_prepare
                    ? "O seu papel permite preparar esta revisão."
                    : "Consulte as permissões do registo antes de agir."}
                </p>
                <p>
                  {i.review_at
                    ? `Data documentada: ${formatDate(i.review_at)}`
                    : "Data de revisão não documentada."}
                </p>
                <Link
                  className="underline"
                  to="/app/casos"
                  search={{
                    tenant: tenant.id,
                    subject: i.subject_id,
                    case: i.case_id!,
                    kind: "operational",
                  }}
                >
                  Abrir caso atribuído
                </Link>
              </article>
            ))}
            <div className="flex gap-3 my-3">
              <Button
                variant="secondary"
                disabled={pages.length === 1 || q.isFetching}
                onClick={() => setPages((p) => p.slice(0, -1))}
              >
                Meus casos anteriores
              </Button>
              <Button
                variant="secondary"
                disabled={!q.data.has_more || q.isFetching}
                onClick={() => setPages((p) => [...p, q.data!.next_cursor!])}
              >
                Meus casos seguintes
              </Button>
            </div>
          </>
        )}
      </Panel>
    </section>
  );
}
