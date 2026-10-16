import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { friendlyError } from "@/lib/errors";
import { algorithmLimitations, analysisErrorPt, c02StatusLabel, generalLimitations, translateReason, type C02Status } from "@/lib/c02";
import { classLabel, operatorLabel, kindLabel, type IndicatorClass } from "@/lib/profile";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, formatDate, Loading, Mono, Panel, StatusPill } from "./ui-bits";

type Win = {
  label?: string; start: string; end: string; n: number; value: number | null; denominator: number | null;
  coverage_pct: number | null; expected_slots: number; covered_slots: number; sufficient: boolean;
  metric?: number; meets_rule?: boolean; excluded?: Record<string, number>; late_observations?: number;
  source?: string | null; denominator_source?: string | null; denominator_coverage_pct?: number | null;
  corrections?: { observation_id: string; supersedes: string[] }[];
};
type Details = {
  windows: Win[]; reference: Win | null; baseline_window: Win | null;
  parameters: { deterioration_kind?: string; deterioration_operator?: string; deterioration_value?: number; deterioration_consecutive_windows?: number; observation_window_days?: number; unit?: string; target_value?: number | null };
};

const tone = (s: C02Status) =>
  s === "deterioration_candidate" ? "primary" : s === "no_deterioration" ? "success" : s === "persistent_condition" ? "neutral" : "muted";

const utc = (iso: string) => new Date(iso).toISOString().slice(0, 16).replace("T", " ") + "Z";
const num = (v: unknown) => (v === null || v === undefined ? "—" : String(Number(v)));

export function DeteriorationPanel({ subjectId, profileId, onRunChange }: { subjectId: string; profileId: string | undefined; onRunChange?: (runId: string | null) => void }) {
  const { tenant, canWrite } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);

  const runs = useQuery({
    queryKey: tk(tenantId, "c02_runs", subjectId),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c02_runs")
        .select("id, profile_version, algorithm_version, as_of, data_cutoff, observation_count, revision_of, summary, created_at")
        .eq("tenant_id", tenantId).eq("subject_id", subjectId)
        .order("created_at", { ascending: false }).limit(50);
      if (error) throw error;
      return data ?? [];
    },
  });
  const runId = selected ?? runs.data?.[0]?.id ?? null;
  useEffect(() => {
    onRunChange?.(runId);
  }, [runId, onRunChange]);
  const results = useQuery({
    queryKey: tk(tenantId, "c02_results", runId),
    enabled: !!runId,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("c02_results")
        .select("id, indicator_key, classification, status, below_target, baseline_value, reasons, observation_ids, details")
        .eq("tenant_id", tenantId).eq("run_id", runId!).order("indicator_key");
      if (error) throw error;
      return data ?? [];
    },
  });

  const run = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenantId);
      if (!profileId) throw new Error("no_profile");
      const { data, error } = await supabase.rpc("run_deterioration_analysis", {
        _tenant_id: tenantId, _subject_id: subjectId, _expected_profile_id: profileId,
      });
      if (error) throw error;
      return data as { run_id: string; reused: boolean };
    },
    onSuccess: (d) => {
      setSelected(d.run_id);
      qc.invalidateQueries({ queryKey: tk(tenantId, "c02_runs") });
      qc.invalidateQueries({ queryKey: tk(tenantId, "count") });
      toast.success(d.reused ? "Sem dados novos: foi reutilizada a análise existente." : "Análise concluída.");
    },
  });
  const runErr = run.error as { message?: string } | null;

  const current = runs.data?.find((r) => r.id === runId);
  const summary = current?.summary as { outcome_candidates?: number; usage_candidates?: number; insufficient?: number } | undefined;

  return (
    <Panel
      title="Deteção de deterioração (C02)"
      className="lg:col-span-2"
      actions={canWrite && (
        <Button size="sm" onClick={() => run.mutate()} disabled={run.isPending || !profileId}>
          {run.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Analisar agora
        </Button>
      )}
    >
      <p className="mb-4 text-xs text-muted-foreground">
        Cálculo determinístico no servidor: as janelas terminam à meia-noite UTC de hoje e só entram dados importados até ao momento da análise. Os resultados são <strong>sinais candidatos</strong>: não
        abrem casos, não indicam causa e um sinal só de uso nunca significa perda de valor.
      </p>
      {!profileId && <p className="text-sm text-muted-foreground">É preciso um perfil de valor aprovado para analisar.</p>}
      {run.isError && (
        <div className="mb-4"><ErrorState message={analysisErrorPt[runErr?.message ?? ""] ?? friendlyError(run.error)} /></div>
      )}
      {runs.isLoading ? <Loading /> : runs.isError ? (
        <ErrorState message="Não foi possível carregar as análises." onRetry={() => runs.refetch()} />
      ) : runs.data!.length === 0 ? (
        <Empty title="Sem análises">{canWrite ? "Use “Analisar agora” para calcular." : "Ainda ninguém analisou este cliente."}</Empty>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label htmlFor="c02run" className="text-muted-foreground">Análise</label>
            <select id="c02run" value={runId ?? ""} onChange={(e) => setSelected(e.target.value)}
              className="h-8 w-full max-w-full rounded-md border border-input bg-background px-2 text-xs sm:w-auto">
              {runs.data!.map((r, i) => (
                <option key={r.id} value={r.id}>
                  {formatDate(r.created_at)} · janelas até {utc(r.as_of)} · perfil v{r.profile_version}{i === 0 ? " (mais recente)" : ""}{r.revision_of ? " · revisão" : ""}
                </option>
              ))}
            </select>
          </div>
          {current && (
            <div className="flex flex-wrap gap-2 text-xs">
              <StatusPill tone="primary">{summary?.outcome_candidates ?? 0} candidatos em resultado</StatusPill>
              <StatusPill tone="neutral">{summary?.usage_candidates ?? 0} sinais de uso</StatusPill>
              <StatusPill tone="muted">{summary?.insufficient ?? 0} insuficientes</StatusPill>
              <span className="text-muted-foreground">
                {current.observation_count} observações consideradas · algoritmo <Mono>{current.algorithm_version}</Mono> · dados importados até {formatDate(current.data_cutoff)}
              </span>
            </div>
          )}
          {current && (
            <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">Limites conhecidos ({current.algorithm_version})</p>
              <ul className="mt-1 list-disc pl-5">
                {[...(algorithmLimitations[current.algorithm_version] ?? []), ...generalLimitations].map((l) => <li key={l}>{l}</li>)}
              </ul>
              {algorithmLimitations[current.algorithm_version] && (
                <p className="mt-1">Análise histórica mantida como foi calculada. Uma nova análise usa a versão atual.</p>
              )}
            </div>
          )}
          {results.isLoading ? <Loading /> : results.isError ? (
            <ErrorState message="Não foi possível carregar os resultados." onRetry={() => results.refetch()} />
          ) : (
            <ul className="space-y-3">
              {(results.data ?? []).map((r) => (
                <ResultItem key={r.id} r={r as never} />
              ))}
            </ul>
          )}
        </div>
      )}
    </Panel>
  );
}

function ResultItem({ r }: {
  r: { indicator_key: string; classification: IndicatorClass; status: C02Status; below_target: boolean | null;
       baseline_value: number | null; reasons: string[]; observation_ids: string[]; details: Details };
}) {
  const p = r.details.parameters ?? {};
  const wins = [...(r.details.windows ?? [])].reverse();
  const all = [r.details.baseline_window, r.details.reference, ...wins].filter(Boolean) as Win[];
  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Mono className="text-foreground">{r.indicator_key}</Mono>
        <StatusPill tone="muted">{classLabel[r.classification]}</StatusPill>
        <StatusPill tone={tone(r.status)}>{c02StatusLabel[r.status]}</StatusPill>
        {r.status === "deterioration_candidate" && r.classification === "usage" && (
          <span className="text-xs text-muted-foreground">Sinal de uso — sozinho não prova perda de valor.</span>
        )}
        {r.below_target && <StatusPill tone="neutral">Abaixo do alvo (gap)</StatusPill>}
      </div>
      {p.deterioration_kind ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Regra: {kindLabel[p.deterioration_kind as keyof typeof kindLabel]} {operatorLabel[p.deterioration_operator as keyof typeof operatorLabel]} {num(p.deterioration_value)} em {num(p.deterioration_consecutive_windows)} janelas de {num(p.observation_window_days)} dias, e a janela de referência anterior não pode cumprir a regra.
          {" "}Baseline: {num(r.baseline_value)} {String(p.unit ?? "")}{p.target_value != null ? ` · alvo ${num(p.target_value)}` : ""}.
        </p>
      ) : null}
      {r.reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-muted-foreground">
          {r.reasons.map((x) => <li key={x}>{translateReason(x)}</li>)}
        </ul>
      )}
      {all.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-normal">Janela [início, fim) UTC</th>
                <th className="py-1 pr-3 font-normal">Valor</th>
                <th className="py-1 pr-3 font-normal">Métrica</th>
                <th className="py-1 pr-3 font-normal">Cobertura</th>
                <th className="py-1 pr-3 font-normal">Fonte</th>
                <th className="py-1 pr-3 font-normal">Denominador</th>
                <th className="py-1 font-normal">Obs.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono tabular-nums">
              {all.map((w) => (
                <tr key={w.label}>
                  <td className="py-1 pr-3 whitespace-nowrap">
                    <span className="mr-2 font-sans text-muted-foreground">{w.label === "baseline" ? "baseline" : w.label === "reference" ? "referência" : `atual ${w.label?.slice(8)}`}</span>
                    {utc(w.start)} → {utc(w.end)}
                  </td>
                  <td className="py-1 pr-3">{w.value == null ? "—" : Number(w.value).toFixed(2)}</td>
                  <td className="py-1 pr-3">{w.metric == null ? "—" : `${Number(w.metric).toFixed(2)}${w.meets_rule ? " ✓" : ""}`}</td>
                  <td className="py-1 pr-3">{w.covered_slots}/{w.expected_slots} ({num(w.coverage_pct)}%)</td>
                  <td className="py-1 pr-3 font-sans">{w.source ?? "—"}</td>
                  <td className="py-1 pr-3">
                    {num(w.denominator)}
                    {w.denominator_coverage_pct != null ? ` · cob. ${num(w.denominator_coverage_pct)}%` : ""}
                    {w.denominator_source && w.denominator_source !== w.source ? ` · ${w.denominator_source}` : ""}
                  </td>
                  <td className="py-1">{w.n}{w.corrections?.length ? ` (${w.corrections.length} corr.)` : ""}{w.excluded && Object.keys(w.excluded).length ? ` (+${Object.values(w.excluded).reduce((a, b) => a + b, 0)} excl.)` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] text-muted-foreground">{r.observation_ids.length} observações referenciadas como evidência. ✓ = cumpre a regra.</p>
        </div>
      )}
    </li>
  );
}
