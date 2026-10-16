import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, PackagePlus } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { friendlyError } from "@/lib/errors";
import { c02StatusLabel, translateReason, type C02Status } from "@/lib/c02";
import { classLabel, type IndicatorClass } from "@/lib/profile";
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
  summary: Record<string, unknown> | null;
  created_at: string;
};

type Snapshot = {
  c02_status?: string;
  c02_reasons?: string[];
  classification?: string;
  baseline_value?: number | string | null;
  below_target?: boolean | null;
};

type Indicator = {
  id: string;
  indicator_key: string;
  status: C03IndicatorStatus;
  reasons: string[];
  ref_count: number;
  stored_ref_count: number;
  ref_budget: number;
  snapshot: Snapshot | null;
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

/** Identity captured when the user clicks; travels with the request and its result. */
type BuildVars = { tenantId: string; subjectId: string; runId: string; gen: number };

const statusTone = (s: C03IndicatorStatus) =>
  s === "complete" ? "success" : s === "insufficient" ? "muted" : "neutral";
const attemptTone = (s: C03AttemptStatus) =>
  s === "built" ? "success" : s === "reused" ? "neutral" : s === "rejected" ? "primary" : "muted";

/** UTC minute precision, explicit "Z". */
const utc = (iso: string | null | undefined) =>
  iso ? new Date(iso).toISOString().slice(0, 16).replace("T", " ") + "Z" : "—";
/** Missing counts are unknown, never zero. */
const count = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? String(v) : "?");
const isActive = (tenantId: string) => {
  try {
    assertActiveTenant(tenantId);
    return true;
  } catch {
    return false;
  }
};

/** C03 evidence panel for the C02 run currently selected in the deterioration panel. */
export function EvidencePanel({ subjectId, runId }: { subjectId: string; runId: string | null }) {
  const { tenant, canWrite } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const [buildNote, setBuildNote] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  // Late-response guard: a generation that changes on every tenant/subject/run change and on unmount.
  const identity = `${tenantId}|${subjectId}|${runId ?? ""}`;
  const identityRef = useRef(identity);
  identityRef.current = identity;
  const genRef = useRef(0);
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    genRef.current += 1;
    setBuildNote(null);
    return () => {
      // Runs on identity change and on unmount: invalidates every in-flight request of the old context.
      genRef.current += 1;
      aliveRef.current = false;
    };
  }, [identity]);
  const isCurrent = (v: BuildVars) =>
    aliveRef.current && v.gen === genRef.current && identityRef.current === `${v.tenantId}|${v.subjectId}|${v.runId}`;

  const bundleQ = useQuery({
    queryKey: tk(tenantId, "c03_bundle", subjectId, runId),
    enabled: !!runId,
    queryFn: async () => {
      // Direct server lookup for the selected run (not a truncated list of the subject's bundles).
      const { data, error } = await supabase
        .from("c03_bundles")
        .select("id, run_id, algorithm_version, c02_algorithm_version, c02_input_hash, data_cutoff, content_hash, revision_of, summary, created_at")
        .eq("tenant_id", tenantId)
        .eq("subject_id", subjectId)
        .eq("run_id", runId!)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return (data ?? []) as Bundle[];
    },
  });

  const attempts = useQuery({
    queryKey: tk(tenantId, "c03_attempts", subjectId, runId),
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
    mutationFn: async (v: BuildVars) => {
      assertActiveTenant(v.tenantId); // pre-request guard
      const { data, error } = await supabase.rpc("build_evidence_bundle", { _tenant_id: v.tenantId, _run_id: v.runId });
      if (error) throw error;
      return data as BuildResult;
    },
    onSuccess: (result, v) => {
      // Always refresh with the captured tenant/run, including rejected/failed JSON results.
      qc.invalidateQueries({ queryKey: tk(v.tenantId, "c03_attempts", v.subjectId, v.runId) });
      qc.invalidateQueries({ queryKey: tk(v.tenantId, "c03_bundle", v.subjectId, v.runId) });
      if (!isCurrent(v) || !isActive(v.tenantId)) return; // user moved on: no toast/note in the new context
      if (result?.status === "built") {
        setBuildNote(null);
        toast.success("Pacote de evidência montado.");
      } else if (result?.status === "reused") {
        setBuildNote(null);
        toast.info("Já existia um pacote para esta análise; foi reutilizado.");
      } else {
        const st = result?.status === "rejected" || result?.status === "failed" ? result.status : null;
        setBuildNote({
          kind: "error",
          text: `${st ? c03AttemptLabel[st] : "Resposta não reconhecida"}: ${translateC03Code(st ? (result as { code?: string }).code : null)}`,
        });
      }
    },
    onError: (e, v) => {
      qc.invalidateQueries({ queryKey: tk(v.tenantId, "c03_attempts", v.subjectId, v.runId) });
      if (!isCurrent(v)) return;
      setBuildNote({ kind: "error", text: friendlyError(e) });
    },
  });

  // Pending state only belongs to the context that started it.
  const pendingHere =
    build.isPending && !!build.variables && `${build.variables.tenantId}|${build.variables.subjectId}|${build.variables.runId}` === identity;

  const bundles = bundleQ.data ?? [];
  const bundle = bundles[0] ?? null;

  return (
    <Panel
      title="Pacote de evidência (C03)"
      className="lg:col-span-2"
      actions={
        canWrite && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => runId && build.mutate({ tenantId, subjectId, runId, gen: genRef.current })}
            disabled={pendingHere || !runId}
          >
            {pendingHere ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />} Montar pacote
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
        <div key={identity} className="space-y-4">
          {bundleQ.isLoading ? (
            <Loading />
          ) : bundleQ.isError ? (
            <ErrorState message="Não foi possível carregar o pacote desta análise." onRetry={() => bundleQ.refetch()} />
          ) : !bundle ? (
            <Empty title="Sem pacote para esta análise">
              A análise selecionada ainda não tem pacote de evidência. A montagem é explícita e nunca automática.
            </Empty>
          ) : (
            <BundleView tenantId={tenantId} bundle={bundle} otherVersions={bundles.length - 1} />
          )}
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted-foreground">Tentativas de montagem nesta análise</h3>
            {attempts.isLoading ? (
              <Loading />
            ) : attempts.isError ? (
              <ErrorState message="Não foi possível carregar as tentativas." onRetry={() => attempts.refetch()} />
            ) : (attempts.data ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">Nenhuma tentativa registada.</p>
            ) : (
              <ul className="space-y-1 text-xs">
                {attempts.data!.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-2">
                    <StatusPill tone={attemptTone(a.status)}>{c03AttemptLabel[a.status] ?? a.status}</StatusPill>
                    <span className="text-muted-foreground">{formatDate(a.created_at)}</span>
                    {a.code && <span className="text-muted-foreground">{translateC03Code(a.code)}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}

function BundleView({ tenantId, bundle, otherVersions }: { tenantId: string; bundle: Bundle; otherVersions: number }) {
  const indicators = useQuery({
    queryKey: tk(tenantId, "c03_indicators", bundle.id),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c03_indicators")
        .select("id, indicator_key, status, reasons, ref_count, stored_ref_count, ref_budget, snapshot")
        .eq("tenant_id", tenantId)
        .eq("bundle_id", bundle.id)
        .order("indicator_key");
      if (error) throw error;
      return (data ?? []) as Indicator[];
    },
  });
  const s = bundle.summary ?? {};

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <StatusPill tone="success">{count(s.complete)} íntegros</StatusPill>
        <StatusPill tone="muted">{count(s.insufficient)} insuficientes</StatusPill>
        <StatusPill tone="neutral">{count(s.context_facts)} contexto</StatusPill>
        <span className="text-muted-foreground">
          {count(s.stored_refs)} referências guardadas · algoritmo <Mono>{bundle.algorithm_version}</Mono> sobre{" "}
          <Mono>{bundle.c02_algorithm_version}</Mono>
        </span>
      </div>
      <dl className="grid grid-cols-1 gap-y-1 text-xs text-muted-foreground sm:grid-cols-[200px_1fr]">
        <dt>Pacote</dt>
        <dd><Mono className="break-all">{bundle.id}</Mono></dd>
        <dt>Análise C02</dt>
        <dd><Mono className="break-all">{bundle.run_id}</Mono></dd>
        <dt>Corte dos dados (UTC)</dt>
        <dd><Mono>{utc(bundle.data_cutoff)}</Mono></dd>
        <dt>Montado em (UTC)</dt>
        <dd><Mono>{utc(bundle.created_at)}</Mono></dd>
        <dt>Revisão do pacote</dt>
        <dd>{bundle.revision_of ? <Mono className="break-all">{bundle.revision_of}</Mono> : "— (primeiro pacote deste cliente)"}</dd>
        <dt>Hash do conteúdo</dt>
        <dd><Mono className="break-all">{bundle.content_hash}</Mono></dd>
        <dt>Hash dos dados da análise</dt>
        <dd><Mono className="break-all">{bundle.c02_input_hash}</Mono></dd>
      </dl>
      {otherVersions > 0 && (
        <p className="text-xs text-muted-foreground">
          Existem mais {otherVersions} pacote(s) desta análise com outra versão de algoritmo; mostra-se o mais recente.
        </p>
      )}
      {indicators.isLoading ? (
        <Loading />
      ) : indicators.isError ? (
        <ErrorState message="Não foi possível carregar os indicadores do pacote." onRetry={() => indicators.refetch()} />
      ) : (indicators.data ?? []).length === 0 ? (
        <p className="text-xs text-muted-foreground">Pacote sem indicadores registados.</p>
      ) : (
        <ul className="space-y-3">
          {indicators.data!.map((i) => (
            <IndicatorItem key={i.id} tenantId={tenantId} bundle={bundle} indicator={i} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Historical C02 state as stored in the C03 snapshot; never reconstructed from the current profile. */
function SnapshotSummary({ indicatorKey, snapshot }: { indicatorKey: string; snapshot: Snapshot | null }) {
  const sn = snapshot ?? {};
  const has = (v: unknown) => v !== undefined && v !== null;
  return (
    <div data-testid={`c03-snapshot-${indicatorKey}`} className="mt-2 pl-6 text-xs text-muted-foreground">
      {!sn.c02_status ? (
        <p>Snapshot sem estado C02 registado.</p>
      ) : (
        <p>
          Na análise C02 (snapshot guardado): {c02StatusLabel[sn.c02_status as C02Status] ?? `estado ${sn.c02_status}`}
          {sn.classification ? ` · ${classLabel[sn.classification as IndicatorClass] ?? sn.classification}` : ""}
          {" · "}Baseline: {has(sn.baseline_value) ? String(sn.baseline_value) : "não registado"}
          {" · "}
          {sn.below_target === true ? "abaixo do alvo (gap) nesse momento" : sn.below_target === false ? "não abaixo do alvo" : "gap não registado"}
        </p>
      )}
      {(sn.c02_reasons ?? []).length > 0 && (
        <p>Motivos C02: {sn.c02_reasons!.map((r) => translateReason(r)).join("; ")}</p>
      )}
    </div>
  );
}

function IndicatorItem({ tenantId, bundle, indicator }: { tenantId: string; bundle: Bundle; indicator: Indicator }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<number | null>(null);
  const totalPages = Math.max(1, Math.ceil(indicator.stored_ref_count / PAGE_SIZE));

  const refs = useQuery({
    queryKey: tk(tenantId, "c03_refs", bundle.id, indicator.id, page),
    enabled: open && indicator.stored_ref_count > 0,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c03_refs")
        .select("id, ordinal, role, window_label, window_start, window_end, observation_id, superseded_by, corrects_observation_id, indicator_key, observed_at, ingested_at, value_numeric, value_text, unit, source, payload_hash")
        .eq("tenant_id", tenantId)
        .eq("bundle_id", bundle.id)
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
        <StatusPill tone={statusTone(indicator.status)}>{c03StatusLabel[indicator.status] ?? indicator.status}</StatusPill>
        <span className="text-xs text-muted-foreground">
          {budgetExceeded
            ? `${indicator.ref_count} referências exigidas · 0 guardadas (limite ${indicator.ref_budget})`
            : `${indicator.stored_ref_count} referências guardadas`}
        </span>
      </button>
      <SnapshotSummary indicatorKey={indicator.indicator_key} snapshot={indicator.snapshot} />
      {indicator.reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-9 text-xs text-muted-foreground">
          {indicator.reasons.map((r) => (
            <li key={r}>{translateC03Reason(r)}</li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-3 pl-0 sm:pl-6">
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
              <ul className="divide-y divide-border text-xs">
                {(refs.data ?? []).map((r) => (
                  <li key={r.id} className="py-1">
                    <button
                      type="button"
                      aria-label={`Detalhe da referência ${r.ordinal}`}
                      aria-expanded={detail === r.ordinal}
                      onClick={() => setDetail((d) => (d === r.ordinal ? null : r.ordinal))}
                      className="flex w-full flex-wrap items-center gap-x-3 gap-y-0.5 text-left"
                    >
                      <span className="w-10 font-mono tabular-nums text-muted-foreground">#{r.ordinal}</span>
                      <span>{c03RoleLabel[r.role] ?? r.role}</span>
                      <span className="font-mono tabular-nums">
                        {r.value_numeric ?? r.value_text ?? "—"} <span className="text-muted-foreground">{r.unit}</span>
                      </span>
                      <span className="text-muted-foreground">{r.source}</span>
                      <span className="text-muted-foreground">{r.window_label ?? "sem janela"}</span>
                      {r.corrects_observation_id && <span className="text-muted-foreground">· corrige outra</span>}
                    </button>
                    {detail === r.ordinal && <RefDetail r={r} cutoff={bundle.data_cutoff} />}
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  Página {page + 1} de {totalPages} · {indicator.stored_ref_count} referências no total
                </span>
                <span className="flex gap-2">
                  <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => { setDetail(null); setPage((p) => p - 1); }}>
                    Anterior
                  </Button>
                  <Button size="sm" variant="ghost" disabled={page + 1 >= totalPages} onClick={() => { setDetail(null); setPage((p) => p + 1); }}>
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

/** Full, tap-accessible reference detail. All values are rendered as plain text data. */
function RefDetail({ r, cutoff }: { r: Ref; cutoff: string }) {
  const window = r.window_start || r.window_end ? `[${utc(r.window_start)}, ${utc(r.window_end)})` : "—";
  return (
    <dl
      data-testid={`c03-ref-detail-${r.ordinal}`}
      className="mt-2 grid grid-cols-1 gap-y-1 rounded-md bg-muted/40 p-2 text-muted-foreground sm:grid-cols-[180px_1fr]"
    >
      <dt>Papel</dt>
      <dd>{c03RoleLabel[r.role] ?? r.role}</dd>
      <dt>Observação</dt>
      <dd><Mono className="break-all">{r.observation_id}</Mono></dd>
      <dt>Indicador</dt>
      <dd><Mono>{r.indicator_key}</Mono></dd>
      <dt>Valor</dt>
      <dd className="break-words">
        {r.value_numeric !== null ? <Mono>{String(r.value_numeric)}</Mono> : r.value_text !== null ? <span>{r.value_text}</span> : "—"}{" "}
        <span>{r.unit}</span>
      </dd>
      <dt>Fonte</dt>
      <dd className="break-words">{r.source}</dd>
      <dt>Janela {r.window_label ?? ""} [início, fim) UTC</dt>
      <dd><Mono>{window}</Mono></dd>
      <dt>Observado (UTC)</dt>
      <dd><Mono>{utc(r.observed_at)}</Mono></dd>
      <dt>Recebido (UTC)</dt>
      <dd><Mono>{utc(r.ingested_at)}</Mono></dd>
      <dt>Corte do pacote (UTC)</dt>
      <dd><Mono>{utc(cutoff)}</Mono></dd>
      <dt>Corrige a observação</dt>
      <dd>{r.corrects_observation_id ? <Mono className="break-all">{r.corrects_observation_id}</Mono> : "—"}</dd>
      <dt>Substituída por</dt>
      <dd>{r.superseded_by ? <Mono className="break-all">{r.superseded_by}</Mono> : "—"}</dd>
      <dt>Hash do conteúdo</dt>
      <dd><Mono className="break-all">{r.payload_hash}</Mono></dd>
    </dl>
  );
}
