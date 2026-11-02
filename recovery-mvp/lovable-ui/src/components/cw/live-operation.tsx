import { useState } from "react";
import { useRouter } from "@tanstack/react-router";
import type { OperationRequest } from "@/domain/l01";
import type { OperationDraft } from "@/data/session-controller";
import { L01Error } from "@/data/transport";
import { useLiveSession } from "./live-session";
import { ErrorStateFrom } from "./states";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";

/** Explicit draft + confirmation. Server authorization always decides. No automatic POST retries. */
export function LiveOperation({ client, operation, arguments: args, label }: {
  client: string; operation: OperationRequest["operation"]; arguments: OperationRequest["arguments"]; label: string;
}) {
  const { runtime, state } = useLiveSession();
  const router = useRouter();
  const [draft, setDraft] = useState<OperationDraft | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<unknown>(null);
  const allowed = state.auth.status === "authenticated" && runtime.controller.canAttempt(operation);
  const currentScope = draft && draft.principal === state.auth.session?.principal && draft.tenant === state.auth.tenant && draft.client === runtime.controller.state.client;
  async function prepare() {
    setBusy(true); setError(null); setResult(null); setConfirmed(false); setOpen(true);
    try { setDraft(await runtime.prepare(client, { request_id: crypto.randomUUID(), operation, arguments: args } as OperationRequest)); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!draft || !confirmed || !currentScope || busy) return;
    setBusy(true); setError(null);
    try {
      const receipt = await runtime.submit(draft.request.request_id);
      setResult(receipt); setDraft(null);
    } catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  const uncertain = error instanceof L01Error && (error.kind === "network" || error.status === 503);
  return <>
    <button disabled={!allowed || busy} title={!allowed ? "Sem permissão na sessão" : undefined} onClick={() => { if (draft) setOpen(true); else void prepare(); }} className="inline-flex min-h-9 items-center rounded-md border px-3 text-[12px] hover:bg-surface-hover disabled:opacity-40 max-sm:min-h-11">{label}</button>
    <Dialog open={open} onOpenChange={(value) => { if (!busy) { setOpen(value); if (!value && result) void runtime.refresh().then(() => router.invalidate()).catch(() => {}); } }}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto">
        <DialogTitle>{label}</DialogTitle>
        <DialogDescription>Pedido à API da demonstração. Apenas dados sintéticos. A interface não concede autorização; o servidor revalida permissões, políticas e limites.</DialogDescription>
        {draft && <p className="break-all font-mono text-xs text-muted-foreground">Pedido {draft.request.request_id}</p>}
        {draft && <label className="flex gap-3 text-sm"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />Confirmo o envio deste pedido sintético.</label>}
        {error != null && <ErrorStateFrom error={error} />}
        {result != null && <div role="status"><p>Recibo recebido da API. Consulte o resultado de negócio; processamento não significa recuperação. Ao fechar, os dados serão atualizados.</p><pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(result, null, 2)}</pre></div>}
        {draft && (!error || uncertain) && <button disabled={busy || !confirmed || !currentScope} onClick={() => void submit()} className="min-h-11 rounded-md bg-primary px-4 text-primary-foreground disabled:opacity-40">{busy ? "A aguardar resposta…" : uncertain ? "Reenviar exatamente o mesmo pedido" : "Confirmar envio"}</button>}
        {uncertain && <p className="text-xs text-muted-foreground">A resposta pode ter-se perdido. Não há repetição automática. A nova tentativa conserva o mesmo identificador e conteúdo.</p>}
      </DialogContent>
    </Dialog>
  </>;
}
