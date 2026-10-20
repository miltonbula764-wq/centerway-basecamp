import { queryOptions } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { tk } from "./tenant";
import type { Json } from "@/integrations/supabase/types";
import type { QueueItem } from "./followup";
export type Assignment = {
  id: string;
  tenant_id: string;
  case_id: string;
  revision: number;
  assignee_id: string | null;
  reason: string;
  reference: string;
  created_by: string;
  created_at: string;
};
export type Responsibility = {
  tenant_id: string;
  case_id: string;
  current: Assignment | null;
  valid: boolean;
  items: Assignment[];
  has_more: boolean;
};
export type Notice = {
  id: string;
  tenant_id: string;
  recipient_id: string;
  kind: string;
  source_kind: string;
  source_id: string;
  subject_id: string | null;
  case_id: string | null;
  created_at: string;
  is_read: boolean;
  payload: Json;
};
export type Inbox = {
  tenant_id: string;
  user_id: string;
  unread_count: number;
  items: Notice[];
  has_more: boolean;
  processing: {
    id: string;
    status: string;
    attempts: number;
    error_code: string | null;
    next_try_at: string;
  }[];
};
export const noticeLabels: Record<string, string> = {
  case_assigned: "Caso atribuído",
  responsibility_changed: "Responsabilidade alterada",
  review_available: "Revisão disponível",
  authorization_needed: "Autorização necessária",
  observation_ended: "Janela de observação terminada",
  evidence_review: "Novas medições exigem revisão",
  operational_failure: "Falha de processamento operacional",
};
export function responsibilityError(error: unknown) {
  const m = (error as { message?: string })?.message || "";
  return (
    (
      {
        admin_required: "A gestão de responsáveis exige um administrador atual.",
        authorized_tenant_member_required:
          "O responsável deve ser administrador ou operador atual desta empresa.",
        assignment_version_conflict: "A atribuição mudou. Atualize antes de repetir.",
        assignment_unchanged:
          "Esta pessoa já é o responsável válido; não foi criada outra atribuição.",
        notification_unavailable: "Notificação indisponível para a sua sessão e permissões.",
      } as Record<string, string>
    )[m] ||
    m ||
    "Não foi possível concluir a operação."
  );
}
export const responsibilityQuery = (tenant: string, caseId: string, before: number | null) =>
  queryOptions({
    queryKey: tk(tenant, "responsibility", caseId, before),
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("case_responsibility", {
          _tenant_id: tenant,
          _case_id: caseId,
          ...(before !== null ? { _before: before } : {}),
          _limit: 25,
        })
        .abortSignal(signal);
      if (error) throw error;
      const p = data as unknown as Responsibility;
      if (
        p.tenant_id !== tenant ||
        p.case_id !== caseId ||
        [...p.items, ...(p.current ? [p.current] : [])].some(
          (x) => x.tenant_id !== tenant || x.case_id !== caseId,
        )
      )
        throw Error("Identidade da consulta de responsabilidades inválida.");
      return p;
    },
  });
export const inboxQuery = (
  tenant: string,
  user: string,
  unread = false,
  cursor: Notice | null = null,
  limit = 25,
  role = "unknown",
) =>
  queryOptions({
    queryKey: tk(tenant, "notifications", user, unread, cursor?.id, limit, role),
    staleTime: 0,
    refetchInterval: 30000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("notification_inbox", {
          _tenant_id: tenant,
          _unread_only: unread,
          ...(cursor ? { _before: cursor.created_at, _before_id: cursor.id } : {}),
          _limit: limit,
        })
        .abortSignal(signal);
      if (error) throw error;
      const p = data as unknown as Inbox;
      if (
        p.tenant_id !== tenant ||
        p.user_id !== user ||
        p.items.some((x) => x.tenant_id !== tenant || x.recipient_id !== user)
      )
        throw Error("Identidade da caixa de notificações inválida.");
      return p;
    },
  });
export const myWorkQuery = (tenant: string, user: string, after: string, role = "unknown") =>
  queryOptions({
    queryKey: tk(tenant, "my-work", user, after, role),
    staleTime: 0,
    refetchInterval: 30000,
    queryFn: async ({ signal }) => {
      const { data, error } = await supabase
        .rpc("my_operational_work", {
          _tenant_id: tenant,
          ...(after ? { _after: after } : {}),
          _limit: 25,
        })
        .abortSignal(signal);
      if (error) throw error;
      const p = data as unknown as {
        tenant_id: string;
        user_id: string;
        items: QueueItem[];
        has_more: boolean;
        next_cursor: string | null;
      };
      if (
        p.tenant_id !== tenant ||
        p.user_id !== user ||
        p.items.some((x) => !x || x.tenant_id !== tenant || x.kind !== "operational")
      )
        throw Error("Identidade da fila pessoal inválida.");
      return p;
    },
  });
