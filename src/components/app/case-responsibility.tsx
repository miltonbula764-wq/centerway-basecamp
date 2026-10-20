import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { responsibilityQuery, responsibilityError } from "@/lib/responsibilities";
import { teamMembersQuery } from "@/lib/team";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, NativeSelect, formatDate } from "./ui-bits";
export function CaseResponsibility({ caseId }: { caseId: string }) {
  const { tenant } = useTenant();
  return <Responsibility key={`${tenant.id}:${tenant.role}:${caseId}`} caseId={caseId} />;
}
function Responsibility({ caseId }: { caseId: string }) {
  const { tenant, isAdmin } = useTenant();
  const qc = useQueryClient();
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const [pages, setPages] = useState<(number | null)[]>([null]);
  const [memberPages, setMemberPages] = useState([""]);
  const operation = useRef<{ signature: string; id: string } | null>(null);
  const q = useQuery(responsibilityQuery(tenant.id, caseId, pages.at(-1)!));
  const members = useQuery({
    ...teamMembersQuery(tenant.id, tenant.role, memberPages.at(-1)!),
    enabled: isAdmin,
  });
  const action = useMutation({
    mutationFn: async (payload: { assignee: string; reason: string; reference: string }) => {
      assertActiveTenant(tenant.id);
      const revision = q.data?.current?.revision || 0;
      const signature = JSON.stringify([caseId, revision, payload]);
      if (operation.current?.signature !== signature)
        operation.current = { signature, id: crypto.randomUUID() };
      const { error } = await supabase.rpc("assign_operational_case", {
        _tenant_id: tenant.id,
        _case_id: caseId,
        _assignee_id: payload.assignee === "__remove" ? null : payload.assignee,
        _reason: payload.reason,
        _reference: payload.reference,
        _expected_revision: revision,
        _operation_id: operation.current.id,
      });
      if (error) throw error;
      assertActiveTenant(tenant.id);
      if (!live.current) return;
      operation.current = null;
      await Promise.all([
        qc.invalidateQueries({ queryKey: tk(tenant.id, "responsibility", caseId) }),
        qc.invalidateQueries({ queryKey: tk(tenant.id, "my-work") }),
        qc.invalidateQueries({ queryKey: tk(tenant.id, "notifications") }),
      ]);
    },
  });
  return (
    <section aria-label="Responsável do caso" className="space-y-3 rounded border p-3">
      <h3 className="font-semibold">Responsável do caso</h3>
      {q.isPending && <p>A carregar atribuição…</p>}
      {q.error && <ErrorState message={responsibilityError(q.error)} onRetry={() => q.refetch()} />}
      {q.data && (
        <>
          <p>
            {q.data.current?.assignee_id
              ? `Responsável: ${q.data.current.assignee_id}`
              : "Sem responsável atribuído"}
          </p>
          {q.data.current?.assignee_id && !q.data.valid && (
            <p role="alert">
              Atribuição pendente de revisão: o membro foi removido ou já não tem um papel
              operacional. Nenhuma permissão foi concedida pela atribuição.
            </p>
          )}
        </>
      )}
      <Button variant="secondary" onClick={() => q.refetch()} disabled={q.isFetching}>
        Atualizar responsável
      </Button>
      {isAdmin && q.isSuccess && (
        <form
          aria-label="Gerir responsável"
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            action.mutate({
              assignee: String(f.get("assignee")),
              reason: String(f.get("reason")),
              reference: String(f.get("reference")),
            });
          }}
        >
          <label>
            Responsável proposto
            <NativeSelect
              name="assignee"
              aria-label="Responsável proposto"
              required
              defaultValue=""
            >
              <option value="" disabled>
                Selecionar explicitamente
              </option>
              <option value="__remove">Remover atribuição</option>
              {members.data
                ?.slice(0, 50)
                .filter((m) => m.role !== "viewer")
                .map((m) => (
                  <option key={m.id} value={m.user_id}>
                    {m.email || m.user_id} · {m.role}
                  </option>
                ))}
            </NativeSelect>
          </label>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={memberPages.length === 1 || members.isFetching}
              onClick={() => setMemberPages((p) => p.slice(0, -1))}
            >
              Membros anteriores
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={!members.data || members.data.length <= 50 || members.isFetching}
              onClick={() => setMemberPages((p) => [...p, members.data![49]!.id])}
            >
              Mais membros
            </Button>
          </div>
          {members.error && <p role="alert">{responsibilityError(members.error)}</p>}
          <label>
            Fundamento da atribuição ou remoção
            <Input name="reason" required maxLength={4000} />
          </label>
          <label>
            Referência da atribuição (HTTPS ou URN)
            <Input name="reference" required maxLength={4000} />
          </label>
          <Button type="submit" disabled={action.isPending || q.isFetching || members.isPending}>
            Guardar responsabilidade documentada
          </Button>
          <p className="text-xs">
            A responsabilidade não concede permissões nem autoriza intervenções.
          </p>
        </form>
      )}
      {action.error && <ErrorState message={responsibilityError(action.error)} />}
      {action.isSuccess && <p aria-live="polite">Responsabilidade registada.</p>}
      {q.data && (
        <details>
          <summary>Histórico de responsabilidades</summary>
          {q.data.items.map((a) => (
            <article key={a.id} className="border rounded p-2 mt-2">
              <p>
                v{a.revision} · {a.assignee_id || "Sem responsável"} · {formatDate(a.created_at)}
              </p>
              <p>{a.reason}</p>
              <p className="break-all">
                {a.reference} · Autor: {a.created_by}
              </p>
            </article>
          ))}
          <div className="flex gap-2 mt-2">
            <Button
              variant="secondary"
              disabled={pages.length === 1 || q.isFetching}
              onClick={() => setPages((p) => p.slice(0, -1))}
            >
              Atribuições mais recentes
            </Button>
            <Button
              variant="secondary"
              disabled={!q.data.has_more || q.isFetching}
              onClick={() => setPages((p) => [...p, q.data!.items.at(-1)!.revision])}
            >
              Atribuições anteriores
            </Button>
          </div>
        </details>
      )}
    </section>
  );
}
