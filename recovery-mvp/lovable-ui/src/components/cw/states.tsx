import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, CloudOff, Inbox, KeyRound, Loader2, Lock, RefreshCw, SearchX, ServerCrash } from "lucide-react";
import { L01Error } from "@/data/transport";

export type UiErrorKind = "401" | "403" | "404" | "409" | "422" | "503" | "network" | "unknown";

export function errorKindOf(e: unknown): UiErrorKind {
  if (e instanceof L01Error) {
    if (e.kind === "network") return "network";
    const k = String(e.status);
    if (["401", "403", "404", "409", "422", "503"].includes(k)) return k as UiErrorKind;
  }
  return "unknown";
}

const copy: Record<UiErrorKind, { icon: typeof Lock; title: string; body: string }> = {
  "401": { icon: KeyRound, title: "Sessão expirada ou inválida", body: "Inicie sessão novamente. Rascunhos em curso são mantidos apenas em memória nesta página." },
  "403": { icon: Lock, title: "Sem permissão para esta operação ou cliente", body: "O servidor recusou o pedido (scope, operação ou origem). A interface não concede permissões." },
  "404": { icon: SearchX, title: "Cliente inexistente ou não visível", body: "Não é possível distinguir entre inexistente e sem visibilidade." },
  "409": { icon: AlertTriangle, title: "Conflito", body: "O request_id foi reutilizado com outro conteúdo/principal, ou a revisão mudou. Recarregue o percurso; uma nova tentativa exige um novo pedido explícito." },
  "422": { icon: AlertTriangle, title: "Pedido rejeitado pelo motor ou validação", body: "Resultado mostrado sem reinterpretação. Corrija os dados e use um novo request_id." },
  "503": { icon: ServerCrash, title: "Serviço indisponível", body: "Base indisponível, timeout ou configuração rejeitada. Se um comando estava em curso, repita explicitamente o MESMO pedido para conhecer o resultado." },
  network: { icon: CloudOff, title: "Sem ligação", body: "A resposta pode ter-se perdido após o registo. Nunca há repetição automática de intervenção ou reversão." },
  unknown: { icon: AlertTriangle, title: "Erro inesperado", body: "Sem detalhes sensíveis disponíveis." },
};

export function ErrorState({ kind, code, action }: { kind: UiErrorKind; code?: string | undefined; action?: ReactNode }) {
  const c = copy[kind];
  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-center px-4 py-12 text-center">
      <c.icon className="mb-3 size-5 text-muted-foreground" />
      <h3 className="font-medium">{c.title}</h3>
      <p className="mt-1 text-muted-foreground">{c.body}</p>
      <div className="mt-2 font-mono text-[11px] text-subtle-foreground">{kind === "network" ? "network" : `HTTP ${kind}`}{code ? ` · ${code}` : ""}</div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorStateFrom({ error, action }: { error: unknown; action?: ReactNode }) {
  return <ErrorState kind={errorKindOf(error)} code={error instanceof L01Error ? error.code : undefined} action={action} />;
}

export function LoadingState({ label = "A carregar percurso…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  );
}

export function NoDataState({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center py-12 text-center text-muted-foreground">
      <Inbox className="mb-2 size-5" />
      {children}
    </div>
  );
}

/** Explicit resend affordance (design only — disabled in L02.2). */
export function ResendSameRequest({ requestId }: { requestId: string }) {
  return (
    <button disabled title="Disponível após integração segura" className="inline-flex h-8 cursor-not-allowed items-center gap-1.5 rounded-md border px-2.5 text-[12px] text-subtle-foreground">
      <RefreshCw className="size-3" /> Repetir o mesmo pedido · {requestId.slice(0, 8)}
    </button>
  );
}

export function BackToOverview() {
  return <Link to="/app" className="text-[13px] text-primary">Voltar à Visão Geral</Link>;
}

