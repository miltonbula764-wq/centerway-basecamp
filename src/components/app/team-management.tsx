import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, roleLabel, tk, useTenant, type Role } from "@/lib/tenant";
import { invitationLink, teamError, teamInvitesQuery, teamMembersQuery } from "@/lib/team";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, ErrorState, Loading, Mono, NativeSelect, Panel, formatDate } from "./ui-bits";
export function TeamManagement() {
  const { tenant } = useTenant();
  return <Team key={`${tenant.id}:${tenant.role}`} />;
}
function Team() {
  const { tenant, user, isAdmin } = useTenant();
  const qc = useQueryClient();
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const [memberPages, setMemberPages] = useState([""]);
  const [invitePages, setInvitePages] = useState([""]);
  const members = useQuery(teamMembersQuery(tenant.id, tenant.role, memberPages.at(-1)!));
  const invites = useQuery({
    ...teamInvitesQuery(tenant.id, invitePages.at(-1)!),
    enabled: isAdmin,
  });
  const [message, setMessage] = useState("");
  const [link, setLink] = useState<{ id: string; url: string } | null>(null);
  const [remove, setRemove] = useState<{ id: string; label: string } | null>(null);
  const operation = useRef<{ signature: string; id: string } | null>(null);
  const action = useMutation({
    mutationFn: async (fn: () => Promise<void>) => {
      assertActiveTenant(tenant.id);
      await fn();
    },
    onSuccess: async () => {
      if (!live.current) return;
      await Promise.all([
        qc.invalidateQueries({ queryKey: tk(tenant.id, "team") }),
        qc.invalidateQueries({ queryKey: tk(tenant.id, "audit") }),
        qc.invalidateQueries({ queryKey: ["memberships"] }),
      ]);
    },
  });
  function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const email = String(f.get("email")).trim();
    const role = String(f.get("role")) as Role;
    const date = new Date(String(f.get("expires")));
    if (!Number.isFinite(+date)) return;
    const signature = JSON.stringify([email, role, date.toISOString()]);
    if (operation.current?.signature !== signature)
      operation.current = { signature, id: crypto.randomUUID() };
    const operationId = operation.current.id;
    setMessage("");
    setLink(null);
    action.mutate(async () => {
      const { data, error } = await supabase.rpc("create_tenant_invitation", {
        _tenant_id: tenant.id,
        _email: email,
        _role: role,
        _expires_at: date.toISOString(),
        _operation_id: operationId,
      });
      if (error) throw error;
      if (!live.current) return;
      operation.current = null;
      const created = data as { id: string; token: string | null; status: string };
      if (created.token) {
        setLink({ id: created.id, url: invitationLink(created.token) });
        setMessage(
          "Convite criado. Não foi enviado email; copie e partilhe a ligação com a pessoa indicada.",
        );
      } else
        setMessage(
          "Este pedido já foi registado. A ligação não é recuperável: revogue este convite e crie outro se não guardou a ligação.",
        );
    });
  }
  function changeRole(id: string, role: Role) {
    setMessage("");
    action.mutate(async () => {
      const { error } = await supabase.rpc("set_member_role", {
        _tenant_id: tenant.id,
        _user_id: id,
        _role: role,
      });
      if (error) throw error;
      if (live.current) setMessage("Papel atualizado no servidor.");
    });
  }
  function removeMember() {
    if (!remove) return;
    const id = remove.id;
    setMessage("");
    action.mutate(async () => {
      const { error } = await supabase.rpc("remove_tenant_member", {
        _tenant_id: tenant.id,
        _user_id: id,
      });
      if (error) throw error;
      if (live.current) {
        setRemove(null);
        setMessage(
          "Acesso removido. Convites pendentes anteriores para este email também foram revogados.",
        );
      }
    });
  }
  function revoke(id: string) {
    setMessage("");
    action.mutate(async () => {
      const { error } = await supabase.rpc("revoke_tenant_invitation", {
        _tenant_id: tenant.id,
        _invitation_id: id,
      });
      if (error) throw error;
      if (live.current) {
        if (link?.id === id) setLink(null);
        setMessage("Convite revogado.");
      }
    });
  }
  return (
    <div className="space-y-5 lg:col-span-2">
      {action.error && <ErrorState message={teamError(action.error)} />}
      {message && (
        <p role="status" className="rounded border p-3 text-sm">
          {message}
        </p>
      )}
      <Panel title="Membros">
        <div className="space-y-3 text-sm">
          <p>
            Os papéis são impostos no PostgreSQL. Apenas administradores consultam os emails e gerem
            acessos.
          </p>
          {members.isPending ? (
            <Loading />
          ) : members.isError ? (
            <ErrorState
              message="Não foi possível carregar a equipa. Requer a migração 0016."
              onRetry={() => members.refetch()}
            />
          ) : (
            <ul className="divide-y">
              {members.data.slice(0, 50).map((m) => (
                <li
                  key={m.id}
                  className="flex flex-wrap items-center gap-3 py-3"
                  data-testid="team-member"
                >
                  <span className="min-w-0 break-all">
                    {m.email || m.user_id}
                    {m.user_id === user.id ? " · Você" : ""}
                  </span>
                  {isAdmin ? (
                    <label className="ml-auto">
                      Papel
                      <NativeSelect
                        aria-label={`Papel de ${m.email || m.user_id}`}
                        value={m.role}
                        disabled={action.isPending}
                        onChange={(e) => changeRole(m.user_id, e.target.value as Role)}
                      >
                        {Object.entries(roleLabel).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </NativeSelect>
                    </label>
                  ) : (
                    <span className="ml-auto">{roleLabel[m.role]}</span>
                  )}
                  {isAdmin && (
                    <Button
                      variant="secondary"
                      disabled={action.isPending}
                      onClick={() => setRemove({ id: m.user_id, label: m.email || m.user_id })}
                    >
                      Remover membro
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {remove && (
            <div
              role="group"
              aria-label="Confirmar remoção"
              className="space-y-3 rounded border p-3"
            >
              <p>
                Remover o acesso de <strong>{remove.label}</strong> a {tenant.name}? As decisões e o
                histórico permanecem. O último administrador não pode ser removido.
              </p>
              <Button disabled={action.isPending} onClick={removeMember}>
                Confirmar remoção
              </Button>
              <Button
                variant="secondary"
                disabled={action.isPending}
                onClick={() => setRemove(null)}
              >
                Cancelar
              </Button>
            </div>
          )}
          <Pages
            pages={memberPages}
            setPages={setMemberPages}
            next={members.data?.[49]?.id}
            more={(members.data?.length || 0) > 50}
            busy={members.isFetching}
          />
        </div>
      </Panel>
      {isAdmin && (
        <Panel title="Convites da equipa">
          <div className="space-y-4 text-sm">
            <p>
              Sem envio automático de email. O administrador copia e partilha a ligação. A aceitação
              exige a conta com o email indicado já verificado.
            </p>
            <form onSubmit={create} className="space-y-3" aria-label="Convidar colaborador">
              <label className="block">
                Email autorizado
                <Input
                  aria-label="Email autorizado"
                  name="email"
                  type="email"
                  maxLength={254}
                  required
                />
              </label>
              <label className="block">
                Papel proposto
                <NativeSelect aria-label="Papel proposto" name="role" defaultValue="operator">
                  {Object.entries(roleLabel).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </NativeSelect>
              </label>
              <label className="block">
                Válido até (hora local, máximo 30 dias)
                <Input aria-label="Válido até" name="expires" type="datetime-local" required />
              </label>
              <Button type="submit" disabled={action.isPending}>
                Criar convite
              </Button>
            </form>
            {link && (
              <div className="space-y-2 rounded border p-3">
                <p>
                  Ligação privada, apresentada apenas agora. Guarde-a antes de sair desta página.
                </p>
                <Input aria-label="Ligação de convite" readOnly value={link.url} />
                <Button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(link.url);
                      if (live.current)
                        setMessage("Ligação copiada. Partilhe-a apenas com o destinatário.");
                    } catch {
                      if (live.current)
                        setMessage(
                          "Não foi possível copiar automaticamente. Selecione e copie a ligação apresentada.",
                        );
                    }
                  }}
                >
                  Copiar ligação
                </Button>
              </div>
            )}
            {invites.isPending ? (
              <Loading />
            ) : invites.isError ? (
              <ErrorState
                message="Não foi possível carregar os convites."
                onRetry={() => invites.refetch()}
              />
            ) : !invites.data.length ? (
              <Empty title="Sem convites" />
            ) : (
              <ul className="divide-y">
                {invites.data.slice(0, 50).map((v) => (
                  <li
                    key={v.id}
                    data-testid="team-invite"
                    className="flex flex-wrap items-center gap-3 py-3"
                  >
                    <span className="break-all">{v.email}</span>
                    <span>{roleLabel[v.role]}</span>
                    <span>
                      {{
                        pending: "Pendente",
                        expired: "Expirado",
                        revoked: "Revogado",
                        accepted: "Aceite",
                      }[v.status] || v.status}
                    </span>
                    <span className="text-xs">Até {formatDate(v.expires_at)}</span>
                    <Mono>{v.id.slice(0, 8)}</Mono>
                    {v.status === "pending" && (
                      <Button
                        variant="secondary"
                        disabled={action.isPending}
                        onClick={() => revoke(v.id)}
                      >
                        Revogar convite
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <Pages
              pages={invitePages}
              setPages={setInvitePages}
              next={invites.data?.[49]?.id}
              more={(invites.data?.length || 0) > 50}
              busy={invites.isFetching}
            />
            <Button
              variant="secondary"
              disabled={action.isPending}
              onClick={() => {
                void invites.refetch();
                void members.refetch();
              }}
            >
              Atualizar equipa
            </Button>
          </div>
        </Panel>
      )}
    </div>
  );
}
function Pages({
  pages,
  setPages,
  next,
  more,
  busy,
}: {
  pages: string[];
  setPages: (p: string[]) => void;
  next: string | undefined;
  more: boolean;
  busy: boolean;
}) {
  return (
    <div className="flex gap-2">
      <Button
        variant="secondary"
        disabled={pages.length === 1 || busy}
        onClick={() => setPages(pages.slice(0, -1))}
      >
        Anterior
      </Button>
      <Button
        variant="secondary"
        disabled={!more || busy}
        onClick={() => setPages([...pages, next!])}
      >
        Seguinte
      </Button>
    </div>
  );
}
