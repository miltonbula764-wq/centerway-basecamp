import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type { Json } from "@/integrations/supabase/types";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { indicatorsQuery, profilesQuery } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, Loading, NativeSelect, Panel, formatDate } from "./ui-bits";

type Definition = Record<string, string | number | null>;
const fields = [
  ["promise", "Promessa documentada da SaaS"], ["promise_ref", "Referência da promessa"],
  ["plan_capability", "Capacidade permitida pelo plano contratado"], ["plan_ref", "Referência do plano"],
  ["customer_goal", "Objetivo específico do cliente"], ["customer_ref", "Referência da confirmação do objetivo"],
  ["compatibility_ref", "Referência da revisão documental humana"], ["unit", "Unidade (igual ao perfil)"],
  ["source", "Fonte exata das medições"], ["target", "Meta numérica"],
  ["window_count", "Quantidade de janelas C02 atuais a exigir (1–100)"],
  ["observation_start", "Início admissível da observação (ISO com fuso)"], ["deadline", "Prazo do objetivo (ISO com fuso)"],
] as const;
const fieldLabels: Record<string, string> = { ...Object.fromEntries(fields), compatibility: "Revisão documental humana", aggregation: "Agregação", comparator: "Comparador" };
const errors: Record<string, string> = {
  configuration_version_conflict: "Esta configuração já tem uma revisão mais recente. Atualize a página e selecione a última versão antes de criar outra.",
  idempotency_conflict: "Este identificador de operação já foi usado com outros dados. Abra novamente o formulário.",
  approved_outcome_required: "Selecione um indicador de resultado de um perfil aprovado ou histórico.",
  timestamp_with_timezone_required: "As datas exigem formato ISO 8601 com fuso, por exemplo 2026-10-18T00:00:00Z.",
  invalid_goal_period: "O início da observação tem de ser anterior ao prazo.",
  write_role_required: "A avaliação exige permissão de administrador ou operador.",
  admin_required: "A configuração exige permissão de administrador.",
};
const labels: Record<string, string> = {
  achieved: "Objetivo atingido", not_achieved: "Objetivo não atingido", pending_deadline: "Prazo ainda não atingido", inconclusive: "Avaliação inconclusiva",
  compatible: "Compatível · revisão humana", contradiction: "Contradição de configuração", missing_documentation: "Documentação pendente", not_checkable: "Compatibilidade não verificável",
  sufficient: "Suficiente para estas regras", insufficient: "Insuficiente", needs_information: "Informação pendente", configuration_review: "Revisão de configuração necessária", assessment_available: "Avaliação disponível para revisão",
};
export function C04ValueState({ subjectId }: { subjectId: string }) {
  const { tenant } = useTenant();
  return <ValueState key={`${tenant.id}:${subjectId}`} subjectId={subjectId} />;
}
function ValueState({ subjectId }: { subjectId: string }) {
  const { tenant, isAdmin, canWrite } = useTenant();
  const qc = useQueryClient();
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const [configurationId, setConfigurationId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [indicatorKey, setIndicatorKey] = useState("");
  const [bundleId, setBundleId] = useState("");
  const [edit, setEdit] = useState(false);
  const retry = useRef<{ signature: string; operation: string } | null>(null);
  const profiles = useQuery(profilesQuery(tenant.id));
  const configurations = useQuery({ queryKey: tk(tenant.id, "c04", subjectId, "configurations"), queryFn: async () => {
    const { data, error } = await supabase.from("c04_configurations").select("*").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const evaluations = useQuery({ queryKey: tk(tenant.id, "c04", subjectId, "evaluations"), queryFn: async () => {
    const { data, error } = await supabase.from("c04_evaluations").select("*").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const bundles = useQuery({ queryKey: tk(tenant.id, "c04", subjectId, "bundles"), queryFn: async () => {
    const { data, error } = await supabase.from("c03_bundles").select("id,created_at").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const selected = configurations.data?.find(c => c.id === configurationId);
  const activeProfile = selected?.profile_id || profileId;
  const indicators = useQuery({ ...indicatorsQuery(tenant.id, activeProfile), enabled: !!activeProfile });
  const definition = (selected?.definition || {}) as Definition;
  const action = useMutation({ mutationFn: async (fn: () => Promise<void>) => { assertActiveTenant(tenant.id); await fn(); }, onSuccess: async () => {
    if (!alive.current) return;
    await qc.invalidateQueries({ queryKey: tk(tenant.id, "c04", subjectId) });
    await qc.invalidateQueries({ queryKey: tk(tenant.id, "followup") });
  } });
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const d: Definition = {};
    for (const key of [...fields.map(([k]) => k), "compatibility", "aggregation", "comparator"]) {
      const value = String(fd.get(key) ?? "").trim();
      d[key] = value === "" ? null : ["target", "window_count"].includes(key) ? Number(value) : value;
    }
    const payload = { _tenant_id: tenant.id, _subject_id: subjectId, _profile_id: activeProfile, _indicator_key: selected?.["indicator_key"] || indicatorKey, _previous_id: (selected?.id ?? null) as string, _definition: d as Json };
    const signature = JSON.stringify(payload);
    if (retry.current?.signature !== signature) retry.current = { signature, operation: crypto.randomUUID() };
    const operation = retry.current.operation;
    action.mutate(async () => {
      const { data, error } = await supabase.rpc("save_c04_configuration", { ...payload, _operation_id: operation });
      if (error) throw error;
      if (alive.current) { setConfigurationId(data); setEdit(false); }
    });
  }
  const readError = configurations.error || evaluations.error || bundles.error || profiles.error || indicators.error;
  return <Panel title="C04 · Value State configurável"><div className="space-y-4 text-sm">
    <p>Regras explícitas por cliente e indicador de resultado. Promessa, plano, objetivo e medições são registos distintos. Campos desconhecidos ficam pendentes; nenhum contacto é enviado.</p>
    {readError && <ErrorState message={`C04 indisponível: ${readError.message}. A migração 0013 é necessária para este bloco.`} onRetry={() => { void configurations.refetch(); void evaluations.refetch(); void bundles.refetch(); void profiles.refetch(); void indicators.refetch(); }} />}
    {action.error && <ErrorState message={errors[action.error.message] || action.error.message} />}
    {configurations.isLoading && <Loading />}
    <label className="block">Configuração histórica (até 100)<NativeSelect aria-label="Configuração histórica (até 100)" value={configurationId} onChange={e => { setConfigurationId(e.target.value); setEdit(false); action.reset(); }}>
      <option value="">Nova configuração</option>{configurations.data?.map(c => <option key={c.id} value={c.id}>{c.indicator_key} · v{c.version} · {formatDate(c.created_at)}</option>)}
    </NativeSelect></label>
    {isAdmin && <Button variant="secondary" disabled={!!readError} onClick={() => setEdit(!edit)}>{selected ? "Criar revisão desta configuração" : "Registar informação conhecida"}</Button>}
    {selected && selected.pending_fields.length > 0 && <div role="status" className="rounded border border-border p-3"><strong>Informação pendente nesta versão</strong><ul className="mt-2 list-disc pl-5">{selected.pending_fields.map(k => <li key={k}>{fieldLabels[k] || k}</li>)}</ul><p className="mt-2 text-xs text-muted-foreground">Registe apenas informação documentada. Nenhum pedido é enviado ao cliente.</p></div>}
    {selected && <details><summary className="cursor-pointer">Consultar definição v{selected.version}</summary><dl className="mt-2 space-y-2 text-xs">{Object.entries(definition).map(([key, value]) => <div key={key}><dt className="font-medium">{fieldLabels[key] || key}</dt><dd className="break-words text-muted-foreground">{value === null ? "Pendente" : String(value)}</dd></div>)}</dl></details>}
    {edit && isAdmin && <form key={configurationId} onSubmit={save} className="space-y-3 rounded border border-border p-3">
      <p className="text-xs text-muted-foreground">Guardar cria uma versão imutável. Não copie compromissos ou confirmações que não possui. Uma revisão exige a última versão deste indicador.</p>
      <label className="block">Perfil histórico<NativeSelect aria-label="Perfil histórico" required value={activeProfile} disabled={!!selected} onChange={e => { setProfileId(e.target.value); setIndicatorKey(""); }}><option value="">Selecionar perfil aprovado</option>{profiles.data?.filter(p => p.status !== "draft").map(p => <option key={p.id} value={p.id}>Perfil v{p.version} · {p.status}</option>)}</NativeSelect></label>
      <label className="block">Indicador outcome<NativeSelect aria-label="Indicador outcome" required value={selected?.["indicator_key"] || indicatorKey} disabled={!!selected || !activeProfile} onChange={e => setIndicatorKey(e.target.value)}><option value="">Selecionar indicador</option>{indicators.data?.filter(i => i.classification === "outcome").map(i => <option key={i.id} value={i.key}>{i.name} · {i.key} · {i.unit} · {i.aggregation}</option>)}</NativeSelect></label>
      {fields.map(([key, label]) => <label key={key} className="block">{label}<Input aria-label={label} name={key} defaultValue={definition[key] ?? ""} maxLength={4000} type={["target", "window_count"].includes(key) ? "number" : "text"} step={key === "target" ? "any" : key === "window_count" ? "1" : undefined} min={key === "window_count" ? 1 : undefined} max={key === "window_count" ? 100 : undefined} /></label>)}
      {([ ["compatibility", "Revisão documental humana", [["compatible", "Compatível"], ["contradiction", "Contradição documentada"], ["not_checkable", "Não verificável"]]], ["aggregation", "Agregação (igual ao perfil C02)", [["mean", "Média"], ["sum", "Soma"], ["last", "Último valor"]]], ["comparator", "Comparação de cada janela com a meta", [["lt", "Menor que"], ["lte", "Menor ou igual"], ["gt", "Maior que"], ["gte", "Maior ou igual"], ["eq", "Igual"]]] ] as const).map(([key, label, options]) => <label key={key} className="block">{label}<NativeSelect aria-label={label} name={key} defaultValue={definition[key] ?? ""}><option value="">Pendente</option>{options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</NativeSelect></label>)}
      <p className="text-xs text-muted-foreground">São exigidas todas as janelas current_1…N do pacote C03, suficientes segundo o perfil, na fonte e período indicados. Não há média entre metas nem inferência de causalidade.</p>
      <Button disabled={action.isPending || !activeProfile || !(selected?.["indicator_key"] || indicatorKey)} type="submit">Guardar nova versão</Button>
    </form>}
    <label className="block">Pacote C03 persistido<NativeSelect aria-label="Pacote C03 persistido" value={bundleId} onChange={e => setBundleId(e.target.value)}><option value="">Selecionar pacote</option>{bundles.data?.map(b => <option key={b.id} value={b.id}>{formatDate(b.created_at)} · {b.id.slice(0, 8)}</option>)}</NativeSelect></label>
    {canWrite && <Button disabled={!selected || !bundleId || action.isPending || !!readError} onClick={() => action.mutate(async () => {
      const { error } = await supabase.rpc("evaluate_c04_configuration", { _tenant_id: tenant.id, _configuration_id: configurationId, _bundle_id: bundleId }); if (error) throw error;
    })}>Avaliar indicador no servidor</Button>}
    {evaluations.data?.filter(e => !configurationId || e.configuration_id === configurationId).map(e => <article key={e.id} className="space-y-2 rounded border border-border p-3">
      <strong>{labels[e.result]} · {String((e.details as Record<string, Json>)?.["indicator_key"] ?? "")}</strong>
      <p>Configuração: {labels[e.configuration_state]}<br />Evidência: {labels[e.evidence]}<br />Core: {labels[e.core_disposition]}</p>
      <ObservedResult details={e.details} />
      <p className="text-xs text-muted-foreground">{formatDate(e.created_at)} · c04-numeric-v1 · promessa cumprida: não determinada</p>
      <details><summary className="cursor-pointer">Medições, pendências e proveniência</summary><pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(e.details, null, 2)}</pre></details>
    </article>)}
    <p className="text-xs text-muted-foreground">O Core recebe avaliações e pendências persistidas no percurso operacional abaixo. A abertura exige elegibilidade e decisão humana documentadas, sem política comercial universal. O piloto FlowReports permanece separado.</p>
  </div></Panel>;
}

function ObservedResult({ details }: { details: Json }) {
  const d = details as { definition: Definition; windows: Array<{ label: string; value: number | null; start: string; end: string }>; missing_documentation: string[]; reasons: string[] };
  return <div className="space-y-2 text-xs">
    <p>Meta documentada: {d.definition["comparator"] ?? "comparador pendente"} {d.definition["target"] ?? "meta pendente"} {d.definition["unit"] ?? ""} · fonte: {d.definition["source"] ?? "pendente"}</p>
    {d.windows.map(w => <p key={w.label}>Resultado observado: {w.value ?? "indisponível"} {d.definition["unit"] ?? ""} · {formatDate(w.start)} → {formatDate(w.end)}</p>)}
    {!!d.missing_documentation.length && <p>Documentação pendente: {d.missing_documentation.map(k => fieldLabels[k] || k).join("; ")}</p>}
    {!!d.reasons.length && <p>Não é possível concluir o objetivo com estas regras e evidências. Consulte os motivos e a proveniência abaixo.</p>}
  </div>;
}
