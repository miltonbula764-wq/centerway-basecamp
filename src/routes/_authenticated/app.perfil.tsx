import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, CheckCircle2, CopyPlus, Loader2, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { indicatorsQuery, issuesQuery, profilesQuery } from "@/lib/queries";
import { friendlyError } from "@/lib/errors";
import { baselineLabel, classLabel, directionLabel, operatorLabel, statusLabel, translateIssue } from "@/lib/profile";
import type { Database } from "@/integrations/supabase/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Empty, ErrorState, FieldHint, formatDate, Loading, Mono, PageHeader, Panel, StatusPill } from "@/components/app/ui-bits";
import { IndicatorDialog } from "@/components/app/indicator-dialog";
import { cn } from "@/lib/utils";

type Profile = Database["public"]["Tables"]["tenant_value_profiles"]["Row"];
type Indicator = Database["public"]["Tables"]["profile_indicators"]["Row"];

export const Route = createFileRoute("/_authenticated/app/perfil")({
  validateSearch: (s: Record<string, unknown>): { v?: number } => ({
    v: Number(s.v) >= 1 ? Math.floor(Number(s.v)) : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Perfil de valor — CENTERWAY" },
      { name: "description", content: "Promessa, indicadores e versões do perfil de valor da empresa." },
      { property: "og:title", content: "Perfil de valor — CENTERWAY" },
      { property: "og:description", content: "Promessa, indicadores e versões do perfil de valor da empresa." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Perfil,
});

function Perfil() {
  const { tenant, canWrite } = useTenant();
  const { v } = Route.useSearch();
  const navigate = useNavigate({ from: "/app/perfil" });
  const profiles = useQuery(profilesQuery(tenant.id));

  if (profiles.isLoading) return <Loading />;
  if (profiles.isError) return <ErrorState message="Não foi possível carregar o perfil de valor." onRetry={() => profiles.refetch()} />;
  const list = profiles.data!;
  if (list.length === 0) return <CreateFirstDraft canWrite={canWrite} />;

  const draft = list.find((p) => p.status === "draft");
  const approved = list.find((p) => p.status === "approved");
  const current = list.find((p) => p.version === v) ?? draft ?? approved ?? list[0];

  return (
    <>
      <PageHeader
        title="Perfil de valor"
        description="Define a promessa de valor da empresa e como medi-la. Todos os clientes herdam a versão aprovada."
      />
      <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
        <nav aria-label="Versões" className="flex gap-2 overflow-x-auto lg:flex-col">
          {list.map((p) => (
            <button
              key={p.id}
              onClick={() => navigate({ search: { v: p.version } })}
              className={cn(
                "flex shrink-0 items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm",
                p.id === current.id ? "border-primary/60 bg-primary/5" : "border-border hover:bg-accent/40",
              )}
            >
              <span className="font-mono">v{p.version}</span>
              <StatusPill tone={p.status === "approved" ? "success" : p.status === "draft" ? "primary" : "muted"}>{statusLabel[p.status]}</StatusPill>
            </button>
          ))}
        </nav>
        <ProfileView key={current.id} profile={current} hasDraft={!!draft} draftVersion={draft?.version} onOpenVersion={(ver) => navigate({ search: { v: ver } })} />
      </div>
    </>
  );
}

function CreateFirstDraft({ canWrite }: { canWrite: boolean }) {
  const { tenant } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const [promise, setPromise] = useState("");
  const [outcome, setOutcome] = useState("");
  const create = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenantId);
      const { error } = await supabase.rpc("create_value_profile_draft", {
        _tenant_id: tenantId,
        _promise: promise.trim(),
        _expected_outcome: outcome.trim() || undefined,
      });
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tk(tenantId, "profiles") });
      toast.success("Rascunho criado.");
    },
  });

  return (
    <>
      <PageHeader title="Perfil de valor" description="Ainda não existe perfil de valor nesta empresa." />
      {!canWrite ? (
        <Empty title="Sem perfil de valor">Um administrador ou operador pode criar o primeiro rascunho.</Empty>
      ) : (
        <Panel title="Criar rascunho">
          <form onSubmit={(e) => { e.preventDefault(); if (promise.trim()) create.mutate(); }} className="space-y-4">
            <PromiseFields promise={promise} setPromise={setPromise} outcome={outcome} setOutcome={setOutcome} />
            {create.isError && <ErrorState message={friendlyError(create.error)} />}
            <Button type="submit" disabled={create.isPending || !promise.trim()}>
              {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Criar rascunho
            </Button>
          </form>
        </Panel>
      )}
    </>
  );
}

function PromiseFields(p: { promise: string; setPromise: (s: string) => void; outcome: string; setOutcome: (s: string) => void }) {
  return (
    <>
      <div>
        <Label htmlFor="promise">Promessa de valor</Label>
        <Textarea id="promise" value={p.promise} onChange={(e) => p.setPromise(e.target.value)} maxLength={4000} rows={3} className="mt-1.5" required />
        <FieldHint>O que o cliente espera obter ao usar o produto, em linguagem do cliente.</FieldHint>
      </div>
      <div>
        <Label htmlFor="outcome">Resultado esperado (opcional)</Label>
        <Textarea id="outcome" value={p.outcome} onChange={(e) => p.setOutcome(e.target.value)} maxLength={4000} rows={2} className="mt-1.5" />
        <FieldHint>O resultado observável que demonstra que a promessa se cumpre.</FieldHint>
      </div>
    </>
  );
}

function ProfileView({ profile, hasDraft, draftVersion, onOpenVersion }: { profile: Profile; hasDraft: boolean; draftVersion?: number; onOpenVersion: (v: number) => void }) {
  const { tenant, canWrite, isAdmin } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const isDraft = profile.status === "draft";
  const editable = isDraft && canWrite;
  const indicators = useQuery(indicatorsQuery(tenantId, profile.id));
  const issues = useQuery({ ...issuesQuery(tenantId, profile.id), enabled: isDraft });
  const [dialog, setDialog] = useState<{ open: boolean; indicator?: Indicator }>({ open: false });
  const [toDelete, setToDelete] = useState<Indicator | null>(null);
  const [confirmApprove, setConfirmApprove] = useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: tk(tenantId, "profiles") });
    qc.invalidateQueries({ queryKey: tk(tenantId, "indicators") });
    qc.invalidateQueries({ queryKey: tk(tenantId, "issues") });
  };

  const del = useMutation({
    mutationFn: async (id: string) => {
      assertActiveTenant(tenantId);
      const { error } = await supabase.from("profile_indicators").delete().eq("id", id).eq("tenant_id", tenantId);
      if (error) throw error;
    },
    onSuccess: () => { invalidate(); setToDelete(null); toast.success("Indicador removido."); },
    onError: (e) => toast.error(friendlyError(e)),
  });

  const approve = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenantId);
      const { error } = await supabase.rpc("approve_value_profile", { _profile_id: profile.id });
      if (error) throw error;
    },
    onSuccess: () => { invalidate(); setConfirmApprove(false); toast.success(`Versão ${profile.version} aprovada.`); },
    onError: (e) => { setConfirmApprove(false); invalidate(); toast.error(friendlyError(e)); },
  });

  const newVersion = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenantId);
      const { error } = await supabase.rpc("create_value_profile_version", { _from_profile_id: profile.id });
      if (error) throw error;
      const { data } = await supabase.from("tenant_value_profiles").select("version").eq("tenant_id", tenantId).eq("status", "draft").order("version", { ascending: false }).limit(1).maybeSingle();
      return data?.version;
    },
    onSuccess: (ver) => { invalidate(); toast.success("Nova versão em rascunho criada."); if (ver) onOpenVersion(ver); },
    onError: (e) => toast.error(friendlyError(e)),
  });

  const issueList = issues.data ?? [];
  const approvable = isDraft && issues.isSuccess && issueList.length === 0;

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-lg">v{profile.version}</h2>
        <StatusPill tone={profile.status === "approved" ? "success" : isDraft ? "primary" : "muted"}>{statusLabel[profile.status]}</StatusPill>
        {profile.approved_at && <span className="text-xs text-muted-foreground">aprovado em {formatDate(profile.approved_at)}</span>}
        <div className="ml-auto flex flex-wrap gap-2">
          {!isDraft && canWrite && (
            <Button
              variant="secondary"
              disabled={hasDraft || newVersion.isPending}
              onClick={() => newVersion.mutate()}
              title={hasDraft ? `Já existe um rascunho (v${draftVersion}).` : undefined}
            >
              {newVersion.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CopyPlus className="h-4 w-4" />}
              Criar nova versão
            </Button>
          )}
          {isDraft && isAdmin && (
            <Button disabled={!approvable || approve.isPending} onClick={() => setConfirmApprove(true)}>
              <ShieldCheck className="h-4 w-4" /> Aprovar
            </Button>
          )}
        </div>
      </div>
      {!isDraft && hasDraft && canWrite && (
        <p className="text-xs text-muted-foreground">
          Já existe um rascunho (v{draftVersion}).{" "}
          <button className="underline" onClick={() => onOpenVersion(draftVersion!)}>Abrir rascunho</button>
        </p>
      )}
      {!isDraft && (
        <p className="text-xs text-muted-foreground">Esta versão é imutável. Para alterar, crie uma nova versão.</p>
      )}

      {isDraft && (
        <Panel title="Requisitos de aprovação">
          {issues.isLoading ? (
            <Loading label="A validar…" />
          ) : issues.isError ? (
            <ErrorState message={friendlyError(issues.error)} onRetry={() => issues.refetch()} />
          ) : issueList.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-success">
              <CheckCircle2 className="h-4 w-4" /> Cumpre os requisitos. {isAdmin ? "Pode aprovar." : "Um administrador pode aprovar."}
            </p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {issueList.map((i) => (
                <li key={i} className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                  <span>{translateIssue(i)}</span>
                </li>
              ))}
            </ul>
          )}
          <FieldHint>Validado pelo servidor. Indicadores de uso e contexto não precisam de regras.</FieldHint>
        </Panel>
      )}

      {editable ? <DraftPromiseForm profile={profile} /> : (
        <Panel title="Promessa">
          <p className="whitespace-pre-wrap text-sm">{profile.promise}</p>
          {profile.expected_outcome && (
            <>
              <p className="mt-4 text-xs text-muted-foreground">Resultado esperado</p>
              <p className="mt-1 whitespace-pre-wrap text-sm">{profile.expected_outcome}</p>
            </>
          )}
        </Panel>
      )}

      <Panel
        title="Indicadores"
        actions={editable && (
          <Button size="sm" variant="secondary" onClick={() => setDialog({ open: true })}>
            <Plus className="h-4 w-4" /> Adicionar
          </Button>
        )}
      >
        {indicators.isLoading ? (
          <Loading />
        ) : indicators.isError ? (
          <ErrorState message="Não foi possível carregar os indicadores." onRetry={() => indicators.refetch()} />
        ) : indicators.data!.length === 0 ? (
          <Empty title="Sem indicadores">É necessário pelo menos um indicador de resultado para aprovar.</Empty>
        ) : (
          <ul className="divide-y divide-border">
            {indicators.data!.map((i) => (
              <li key={i.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill tone={i.classification === "outcome" ? "primary" : "muted"}>{classLabel[i.classification]}</StatusPill>
                  <span className="text-sm font-medium">{i.name}</span>
                  <Mono className="text-muted-foreground">{i.key}</Mono>
                  {editable && (
                    <div className="ml-auto flex gap-1">
                      <Button size="icon" variant="ghost" aria-label="Editar indicador" onClick={() => setDialog({ open: true, indicator: i })}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" aria-label="Remover indicador" onClick={() => setToDelete(i)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
                <IndicatorSummary i={i} />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {editable && <IndicatorDialog open={dialog.open} onOpenChange={(o) => setDialog({ open: o })} profileId={profile.id} indicator={dialog.indicator} />}

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover indicador?</AlertDialogTitle>
            <AlertDialogDescription>“{toDelete?.name}” será removido deste rascunho. Versões aprovadas não são afetadas.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); if (toDelete) del.mutate(toDelete.id); }} disabled={del.isPending}>
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmApprove} onOpenChange={setConfirmApprove}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Aprovar versão {profile.version}?</AlertDialogTitle>
            <AlertDialogDescription>
              Depois de aprovada, esta versão fica imutável e passa a ser herdada por todos os clientes. A versão aprovada anterior, se existir, fica substituída.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); approve.mutate(); }} disabled={approve.isPending}>
              {approve.isPending && <Loader2 className="h-4 w-4 animate-spin" />} Aprovar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function DraftPromiseForm({ profile }: { profile: Profile }) {
  const { tenant } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const [promise, setPromise] = useState(profile.promise);
  const [outcome, setOutcome] = useState(profile.expected_outcome ?? "");
  useEffect(() => { setPromise(profile.promise); setOutcome(profile.expected_outcome ?? ""); }, [profile.promise, profile.expected_outcome]);
  const dirty = promise !== profile.promise || outcome !== (profile.expected_outcome ?? "");

  const save = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenantId);
      const { error } = await supabase
        .from("tenant_value_profiles")
        .update({ promise: promise.trim(), expected_outcome: outcome.trim() || null })
        .eq("id", profile.id)
        .eq("tenant_id", tenantId)
        .eq("status", "draft");
      if (error) throw error;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: tk(tenantId, "profiles") }); toast.success("Rascunho guardado."); },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (promise.trim()) save.mutate();
  }

  return (
    <Panel title="Promessa">
      <form onSubmit={submit} className="space-y-4">
        <PromiseFields promise={promise} setPromise={setPromise} outcome={outcome} setOutcome={setOutcome} />
        {save.isError && <ErrorState message={friendlyError(save.error)} />}
        <Button type="submit" variant="secondary" disabled={!dirty || !promise.trim() || save.isPending}>
          {save.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar alterações
        </Button>
      </form>
    </Panel>
  );
}

function IndicatorSummary({ i }: { i: Indicator }) {
  const u = i.unit;
  const rule = (k: Indicator["deterioration_kind"], o: Indicator["deterioration_operator"], v: number | null, w: number | null) =>
    k && o && v !== null ? `${operatorLabel[o].split(" (")[1]?.replace(")", "") ?? o} ${v}${k === "relative_pct" ? "% do baseline" : ` ${u}`}${w ? ` · ${w} janela(s)` : ""}` : "—";
  const items: [string, string][] = [
    ["Unidade", u],
    ["Direção", directionLabel[i.direction]],
    ["Baseline", i.baseline_method ? `${baselineLabel[i.baseline_method]}${i.baseline_value !== null ? ` = ${i.baseline_value} ${u}` : ""}${i.baseline_min_period_days ? ` · mín. ${i.baseline_min_period_days} d` : ""}` : "—"],
    ["Janelas", i.observation_window_days || i.comparison_window_days ? `obs. ${i.observation_window_days ?? "—"} d · comp. ${i.comparison_window_days ?? "—"} d` : "—"],
    ["Suficiência", i.min_coverage_pct || i.min_denominator ? `cobertura ≥ ${i.min_coverage_pct ?? "—"}% · denom. ≥ ${i.min_denominator ?? "—"}` : "—"],
    ["Alvo", i.target_value !== null ? `${i.target_value} ${u}` : "—"],
    ["Deterioração", rule(i.deterioration_kind, i.deterioration_operator, i.deterioration_value, i.deterioration_consecutive_windows)],
    ["Recuperação", rule(i.recovery_kind, i.recovery_operator, i.recovery_value, i.recovery_consecutive_windows)],
  ];
  return (
    <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <dt className="w-24 shrink-0 text-muted-foreground">{k}</dt>
          <dd className="font-mono">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
