import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk, type Role } from "./tenant";
export function teamError(error: unknown): string {
  const message = (error as { message?: string })?.message || "";
  if (message.includes("last admin"))
    return "Não é possível remover ou despromover o último administrador da empresa.";
  const known: Record<string, string> = {
    admin_required: "Esta ação exige um administrador atual da empresa.",
    "not authorized": "Já não tem autorização para esta operação.",
    invitation_unavailable:
      "Convite indisponível: inválido, expirado, revogado, utilizado ou destinado a outro email.",
    verified_email_required:
      "Confirme primeiro o email da sua conta. Volte a abrir a ligação depois da confirmação.",
    invitation_expiry_required: "Escolha uma validade futura de até 30 dias.",
    invalid_invitation: "Verifique o email, o papel e a validade do convite.",
    idempotency_conflict: "O pedido foi alterado. Atualize antes de voltar a submeter.",
    invitation_already_accepted_remove_member:
      "O convite já foi aceite. Para retirar acesso, remova o membro.",
    "membership not found": "O membro já não existe nesta empresa. Atualize a lista.",
  };
  return (
    known[message] ||
    "Não foi possível concluir. Atualize os dados e confirme as suas permissões antes de repetir."
  );
}
export const teamMembersQuery = (tenantId: string, role: Role, after: string) =>
  queryOptions({
    queryKey: tk(tenantId, "team", role, "members", after),
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("list_team_members", {
          _tenant_id: tenantId,
          ...(after ? { _after: after } : {}),
          _limit: 51,
        })
        .abortSignal(signal);
      if (error) throw error;
      if (data.some((m) => m.tenant_id !== tenantId)) throw Error("tenant_mismatch");
      return data;
    },
  });
export const teamInvitesQuery = (tenantId: string, after: string) =>
  queryOptions({
    queryKey: tk(tenantId, "team", "admin", "invitations", after),
    staleTime: 0,
    refetchInterval: 30000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("list_tenant_invitations", {
          _tenant_id: tenantId,
          ...(after ? { _after: after } : {}),
          _limit: 51,
        })
        .abortSignal(signal);
      if (error) throw error;
      if (data.some((m) => m.tenant_id !== tenantId)) throw Error("tenant_mismatch");
      return data;
    },
  });
export function invitationLink(token: string): string {
  return `${window.location.origin}/convite#token=${token}`;
}
