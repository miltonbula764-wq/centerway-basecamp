import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, PackagePlus } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { friendlyError } from "@/lib/errors";
import {
  c03AttemptLabel,
  c03RoleLabel,
  c03StatusLabel,
  translateC03Code,
  translateC03Reason,
  type C03AttemptStatus,
  type C03IndicatorStatus,
  type C03RefRole,
} from "@/lib/c03";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, formatDate, Loading, Mono, Panel, StatusPill } from "./ui-bits";

const PAGE_SIZE = 50;

type Bundle = {
  id: string;
  run_id: string;
  algorithm_version: string;
  c02_algorithm_version: string;
  c02_input_hash: string;
  data_cutoff: string;
  content_hash: string;
  revision_of: string | null;
  summary: { indicators?: number; complete?: number; insufficient?: number; context_facts?: number; stored_refs?: number; ref_budget?: number };
  created_at: string;
};

type Indicator = {
  id: string;
  indicator_key: string;
  status: C03IndicatorStatus;
  reasons: string[];
  ref_count: number;
  stored_ref_count: number;
  ref_budget: number;
  snapshot: { c02_status?: string; classification?: string; baseline_value?: number | null; below_target?: boolean | null };
};

type Ref = {
  id: number;
  ordinal: number;
  role: C03RefRole;
  window_label: string | null;
  window_start: string | null;
  window_end: string | null;
  observation_id: string;
  superseded_by: string | null;
  corrects_observation_id: string | null;
  indicator_key: string;
  observed_at: string;
  ingested_at: string;
  value_numeric: number | null;
  value_text: string | null;
  unit: string;
  source: string;
  payload_hash: string;
};

type Attempt = {
  id: string;
  status: C03AttemptStatus;
  code: string | null;
  bundle_id: string | null;
  created_at: string;
};

type BuildResult =
  | { status: "built"; bundle_id: string }
  | { status: "reused"; bundle_id: string }
  | { status: "rejected" | "failed"; code?: string };

const statusTone = (s: C03IndicatorStatus) =>
  s === "complete" ? "success" : s === "insufficient" ? "muted" : "neutral";
const attemptTone = (s: C03AttemptStatus) =>
  s === "built" ? "success" : s === "reused" ? "neutral" : s === "rejected" ? "primary" : "muted";

/** C03 evidence panel for the C02 run currently selected in the deterioration panel. */
export function EvidencePanel({ subjectId, runId }: { subjectId: string; runId: string | null }) {
  const { tenant, canWrite } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  // Guards against a late RPC response applying to a run/tenant the user has already left.
  const requestSeq = useRef(0);
  const [buildNote, setBuildNote] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    setBuildNote(null);
  }, [tenantId, subjectId, runId]);

  const bundles = useQuery({
    queryKey: tk(tenantId, "c03_bundles", subjectId),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c03_bundles")
        .select("id, run_id, algorithm_version, c02_algorithm_version, c02_input_hash, data_cutoff, content_hash, revision_of, summary, created_at")
        .eq("tenant_id", tenantId)
        .eq("subject_id", subjectId)
        .order("created_at", { ascending: false })
        .limit(50);
      if (error) throw error;
      return (data ?? []) as Bundle[];
    },
  });

  const bundle = bundles.data?.find((b) => b.run_id === runId) ?? null;

  const attempts = useQuery({
    queryKey: tk(tenantId, "c03_attempts", runId),
    enabled: !!runId,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c03_attempts")
        .select("id, status, code, bundle_id, created_at")
        .eq("tenant_id", tenantId)
        .eq("requested_run_id", runId!)
        .order("created_at", { ascending: false })
        .limit(20);
      if (error) throw error;
      return (data ?? []) as Attempt[];
    },
  });

  const build = useMutation({
    mutationFn: async () => {
      if (!runId) throw new Error("no_run");
      assertActiveTenant(tenantId);
      const capturedRun = runId;
      const seq = ++requestSeq.current;
      const { data, error } = await supabase.rpc("build_evidence_bundle", {
        _tenant_id: tenantId,
        _run_id: capturedRun,
      });
      if (error) throw error;
      return { result: data as BuildResult, capturedRun, seq };
    },
    onSuccess: ({ result, capturedRun, seq }) => {
      // Always refresh attempts, including rejected/failed results returned as JSON without error.
      qc.invalidateQueries({ queryKey: tk(tenantId, "c03_attempts") });
      qc.invalidateQueries({ queryKey: tk(tenantId, "c03_bundles") });
      if (seq !== requestSeq.current || capturedRun !== runId) return; // user moved on; no toast on the new context
      if (result.status === "built") {
        setBuildNote(null);
        toast.success("Pacote de evidência montado.");
      } else if (result.status === "reused") {
        setBuildNote(null);
        toast.info("Já existia um pacote para esta análise; foi reutilizado.");
      } else {
        setBuildNote({
          kind: "error",
          text: `${c03AttemptLabel[result.status]}: ${translateC03Code(result.code ?? null)}`,
        });
      }
    },
    onError: (e) => {
      qc.invalidateQueries({ queryKey: tk(tenantId, "c03_attempts") });
      setBuildNote({ kind: "error", text: friendlyError(e) });
    },
  });

  return (
    <Panel
      title="Pacote de evidência (C03)"
      className="lg:col-span-2"
      actions={
        canWrite && (
          <Button size="sm" variant="secondary" onClick={() => build.mutate()} disabled={build.isPending || !runId}>
            {build.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />} Montar pacote
          </Button>
        )
      }
    >
      <p className="mb-4 text-xs text-muted-foreground">
        Montagem determinística no servidor, apenas a pedido: revalida cada referência da análise selecionada contra as
        observações importadas até à sua data de corte. <strong>“Evidência íntegra” significa pacote completo e verificado — não
        prova recuperação, valor, causa nem abre um caso.</strong>
      </p>
      {!runId && <p className="text-sm text-muted-foreground">Selecione uma análise C02 para ver ou montar o pacote.</p>}
      {buildNote && (
        <div className="mb-4">
          {buildNote.kind === "error" ? <ErrorState message={buildNote.text} /> : <p className="text-sm text-muted-foreground">{buildNote.text}</p>}
        </div>
      )}
      {runId && (
        <BundleView
          key={`${tenantId}:${runId}`}
          tenantId={tenantId}
          runId={runId}
          bundles={bundles}
          bundle={bundle}
          attempts={attempts.data ?? []}
          attemptsLoading={attempts.isLoading}
          attemptsError={attempts.isError}
          onRetryAttempts={() => attempts.refetch()}
        />
      )}
    </Panel>
  );
}

function BundleView({
  tenantId,
  runId,
  bundles,
  bundle,
  attempts,
  attemptsLoading,
  attemptsError,
  onRetryAttempts,
}: {
  tenantId: string;
  runId: string;
  bundles: ReturnType<typeof useQuery<Bundle[]>>;
  bundle: Bundle | null;
  attempts: Attempt[];
  attemptsLoading: boolean;
  attemptsError: boolean;
  onRetryAttempts: () => void;
}) {
  const indicators = useQuery({
    queryKey: tk(tenantId, "c03_indicators", bundle?.id),
    enabled: !!bundle,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c03_indicators")
        .select("id, indicator_key, status, reasons, ref_count, stored_ref_count, ref_budget, snapshot")
        .eq("tenant_id", tenantId)
        .eq("bundle_id", bundle!.id)
        .order("indicator_key");
      if (error) throw error;
      return (data ?? []) as Indicator[];
    },
  });

  return (
    <div className="space-y-4">
      {bundles.isLoading ? (
        <Loading />
      ) : bundles.isError ? (
        <ErrorState message="Não foi possível carregar os pacotes." onRetry={() => bundles.refetch()} />
      ) : !bundle ? (
        <Empty title="Sem pacote para esta análise">
          A análise selecionada ainda não tem pacote de evidência. A montagem é explícita e nunca automática.
        </Empty>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2 text-xs">
            <StatusPill tone="success">{bundle.summary?.complete ?? 0} íntegros</StatusPill>
            <StatusPill tone="muted">{bundle.summary?.insufficient ?? 0} insuficientes</StatusPill>
            <StatusPill tone="neutral">{bundle.summary?.context_facts ?? 0} contexto</StatusPill>
            <span className="text-muted-foreground">
              {bundle.summary?.stored_refs ?? 0} referências guardadas · algoritmo <Mono>{bundle.algorithm_version}</Mono> sobre{" "}
              <Mono>{bundle.c02_algorithm_version}</Mono> · dados até {formatDate(bundle.data_cutoff)}
              {bundle.revision_of ? " · revisão de pacote anterior" : ""}
            </span>
          </div>
          <dl className="grid grid-cols-1 gap-y-1 text-xs text-muted-foreground sm:grid-cols-[180px_1fr]">
            <dt>Hash do conteúdo</dt>
            <dd><Mono className="break-all">{bundle.content_hash}</Mono></dd>
            <dt>Hash dos dados da análise</dt>
            <dd><Mono className="break-all">{bundle.c02_input_hash}</Mono></dd>
          </dl>
          {indicators.isLoading ? (
            <Loading />
          ) : indicators.isError ? (
            <ErrorState message="Não foi possível carregar os indicadores do pacote." onRetry={() => indicators.refetch()} />
          ) : (
            <ul className="space-y-3">
              {(indicators.data ?? []).map((i) => (
                <IndicatorItem key={i.id} tenantId={tenantId} bundleId={bundle.id} indicator={i} />
              ))}
            </ul>
          )}
        </div>
      )}
      <div>
        <h3 className="mb-2 text-xs font-medium text-muted-foreground">Tentativas de montagem nesta análise</h3>
        {attemptsLoading ? (
          <Loading />
        ) : attemptsError ? (
          <ErrorState message="Não foi possível carregar as tentativas." onRetry={onRetryAttempts} />
        ) : attempts.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nenhuma tentativa registada.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {attempts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2">
                <StatusPill tone={attemptTone(a.status)}>{c03AttemptLabel[a.status]}</StatusPill>
                <span className="text-muted-foreground">{formatDate(a.created_at)}</span>
                {a.code && <span className="text-muted-foreground">{translateC03Code(a.code)}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function IndicatorItem({ tenantId, bundleId, indicator }: { tenantId: string; bundleId: string; indicator: Indicator }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(indicator.stored_ref_count / PAGE_SIZE));

  const refs = useQuery({
    queryKey: tk(tenantId, "c03_refs", indicator.id, page),
    enabled: open && indicator.stored_ref_count > 0,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c03_refs")
        .select("id, ordinal, role, window_label, window_start, window_end, observation_id, superseded_by, corrects_observation_id, indicator_key, observed_at, ingested_at, value_numeric, value_text, unit, source, payload_hash")
        .eq("tenant_id", tenantId)
        .eq("bundle_id", bundleId)
        .eq("indicator_id", indicator.id)
        .order("ordinal", { ascending: true })
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1);
      if (error) throw error;
      return (data ?? []) as Ref[];
    },
  });

  const budgetExceeded = indicator.stored_ref_count === 0 && indicator.ref_count > 0;

  return (
    <li className="rounded-md border border-border p-3">
      <button
        type="button"
        className="flex w-full flex-wrap items-center gap-2 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
        <Mono className="text-foreground">{indicator.indicator_key}</Mono>
        <StatusPill tone={statusTone(indicator.status)}>{c03StatusLabel[indicator.status]}</StatusPill>
        <span className="text-xs text-muted-foreground">
          {budgetExceeded
            ? `${indicator.ref_count} referências exigidas · 0 guardadas (limite ${indicator.ref_budget})`
            : `${indicator.stored_ref_count} referências guardadas`}
        </span>
      </button>
      {indicator.reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-9 text-xs text-muted-foreground">
          {indicator.reasons.map((r) => (
            <li key={r}>{translateC03Reason(r)}</li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-3 pl-9">
          {budgetExceeded ? (
            <p className="text-xs text-muted-foreground">
              O limite de referências foi excedido; nenhuma foi guardada para não apresentar um pacote parcial como completo.
            </p>
          ) : indicator.stored_ref_count === 0 ? (
            <p className="text-xs text-muted-foreground">Sem referências guardadas para este indicador.</p>
          ) : refs.isLoading ? (
            <Loading />
          ) : refs.isError ? (
            <ErrorState message="Não foi possível carregar as referências." onRetry={() => refs.refetch()} />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-left text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-3 font-normal">#</th>
                      <th className="py-1 pr-3 font-normal">Papel</th>
                      <th className="py-1 pr-3 font-normal">Valor</th>
                      <th className="py-1 pr-3 font-normal">Fonte</th>
                      <th className="py-1 pr-3 font-normal">Janela</th>
                      <th className="py-1 pr-3 font-normal">Observado</th>
                      <th className="py-1 font-normal">Hash</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border font-mono tabular-nums">
                    {(refs.data ?? []).map((r) => (
                      <tr key={r.id}>
                        <td className="py-1 pr-3">{r.ordinal}</td>
                        <td className="py-1 pr-3 font-sans">
                          {c03RoleLabel[r.role] ?? r.role}
                          {r.corrects_observation_id && <span className="text-muted-foreground"> · corrige outra</span>}
                        </td>
                        <td className="py-1 pr-3">
                          {r.value_numeric ?? r.value_text ?? "—"} <span className="text-muted-foreground">{r.unit}</span>
                        </td>
                        <td className="py-1 pr-3 font-sans">{r.source}</td>
                        <td className="py-1 pr-3 whitespace-nowrap text-muted-foreground">
                          {r.window_label ?? "—"}
                        </td>
                        <td className="py-1 pr-3 whitespace-nowrap">{formatDate(r.observed_at)}</td>
                        <td className="py-1 text-muted-foreground" title={r.payload_hash}>
                          {r.payload_hash.slice(0, 12)}…
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  Página {page + 1} de {totalPages} · {indicator.stored_ref_count} referências no total
                </span>
                <span className="flex gap-2">
                  <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                    Anterior
                  </Button>
                  <Button size="sm" variant="ghost" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)}>
                    Seguinte
                  </Button>
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </li>
  );
}
