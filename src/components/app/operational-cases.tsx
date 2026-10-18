import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type { Database, Json } from "@/integrations/supabase/types";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { resultLabel } from "@/lib/journey-types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, ErrorState, Loading, NativeSelect, Panel, formatDate } from "./ui-bits";

type Case = Database["public"]["Tables"]["cw_operational_cases"]["Row"];
type Event = Database["public"]["Tables"]["cw_operational_events"]["Row"];
const states: Record<string, string> = { investigation: "C05 · Em investigação", needs_information: "C05 · Informação insuficiente", hypothesis: "C05 · Hipótese", impediment_confirmed: "C05 · Impedimento confirmado", awaiting_approval: "C06 · Plano aguarda autorização", approved: "C07 · Autorização registada", waiting_observation: "C08 · Em observação", observed: "C09 · Resultado registado", remain_open: "C10 · Caso permanece aberto", closed_resolved: "C10 · Encerrado com critérios satisfeitos" };
const errors: Record<string, string> = {
  case_version_conflict: "O caso mudou. Atualize e reveja o histórico antes de repetir.", idempotency_conflict: "Esta operação já foi registada com outros dados.",
  evaluation_requires_information: "A avaliação ainda tem informação pendente. Não pode originar uma intervenção.",
  evaluation_already_has_case: "Esta avaliação já tem um caso. Selecione-o na lista.", configuration_revision_requires_review: "Existe uma nova configuração deste indicador. O contrato histórico foi preservado; reveja a nova avaliação antes de decidir outro caso.",
  observation_window_not_elapsed: "A janela configurada ainda não terminou segundo o relógio do servidor.", new_subject_bundle_required: "Selecione um novo pacote C03 deste cliente, diferente da evidência inicial.",
  valid_authorization_required: "A execução exige autorização válida para o plano atual. Renove a autorização se necessário.", approver_no_longer_authorized: "O responsável pela autorização já não é administrador. É necessária nova autorização.",
  confirmed_requires_observation: "Um impedimento confirmado exige pelo menos uma observação persistida.", invalid_or_superseded_evidence_reference: "A referência não pertence a este cliente/empresa, está corrigida ou não é válida.", investigation_evidence_changed: "Uma prova da investigação foi corrigida. Reveja a investigação antes de intervir.",
};
const object = (value: Json): Record<string, Json | undefined> => value as Record<string, Json | undefined>;
function useAction(subjectId: string) {
  const { tenant } = useTenant(); const qc = useQueryClient(); const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  return useMutation({ mutationFn: async (fn: () => Promise<void>) => { assertActiveTenant(tenant.id); await fn(); }, onSuccess: async () => {
    if (!alive.current) return;
    await Promise.all([qc.invalidateQueries({ queryKey: tk(tenant.id, "operational", subjectId) }), qc.invalidateQueries({ queryKey: tk(tenant.id, "c04", subjectId) }), qc.invalidateQueries({ queryKey: tk(tenant.id, "operational-count") })]);
  } });
}
export function OperationalCases({ subjectId }: { subjectId: string }) {
  const { tenant } = useTenant(); return <Workspace key={`${tenant.id}:${subjectId}`} subjectId={subjectId} />;
}
function Workspace({ subjectId }: { subjectId: string }) {
  const { tenant, isAdmin } = useTenant(); const action = useAction(subjectId); const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const [evaluationId, setEvaluationId] = useState(""); const [caseId, setCaseId] = useState(""); const operation = useRef<{ signature: string; id: string } | null>(null);
  const evaluations = useQuery({ queryKey: tk(tenant.id, "c04", subjectId, "evaluations"), queryFn: async () => {
    const { data, error } = await supabase.from("c04_evaluations").select("*").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100); if (error) throw error; return data;
  } });
  const cases = useQuery({ queryKey: tk(tenant.id, "operational", subjectId, "cases"), queryFn: async () => {
    const { data, error } = await supabase.from("cw_operational_cases").select("*").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100); if (error) throw error; return data;
  } });
  const selected = cases.data?.find(c => c.id === caseId); const evaluation = evaluations.data?.find(a => a.id === evaluationId);
  const eligible = evaluation?.evidence === "sufficient" && evaluation.configuration_state === "compatible" && ["achieved", "not_achieved"].includes(evaluation.result);
  function open(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const definition: Record<string, Json> = { eligible: true, configuration_pinned: true };
    for (const k of ["eligibility_reason", "eligibility_ref", "opening_criteria", "closure_criteria", "closure_ref"]) definition[k] = String(f.get(k));
    const signature = JSON.stringify([evaluationId, definition]); if (operation.current?.signature !== signature) operation.current = { signature, id: crypto.randomUUID() };
    const id = operation.current.id;
    action.mutate(async () => { const { data, error } = await supabase.rpc("open_operational_case", { _tenant_id: tenant.id, _evaluation_id: evaluationId, _operation_id: id, _definition: definition }); if (error) throw error; if (alive.current) setCaseId(data); });
  }
  return <div id="operational-core" className="space-y-5 scroll-mt-20"><Panel title="Core · Percurso operacional configurável"><div className="space-y-4 text-sm">
    <p>Um caso acompanha um indicador. O Core recebe avaliações C04 persistidas, incluindo pendências; nenhum sinal C02 ou resultado abre uma intervenção automaticamente.</p>
    {(cases.error || evaluations.error) && <ErrorState message={(cases.error || evaluations.error)!.message + " · O percurso requer a migração 0014."} onRetry={() => { void cases.refetch(); void evaluations.refetch(); }} />}
    {action.error && <ErrorState message={errors[action.error.message] || action.error.message} />}
    <Field title="Entrada C04"><NativeSelect aria-label="Entrada C04" value={evaluationId} onChange={e => setEvaluationId(e.target.value)}><option value="">Selecionar avaliação individual</option>{evaluations.data?.map(a => <option key={a.id} value={a.id}>{String(object(a.details)["indicator_key"])} · {resultLabel[a.result]} · {a.configuration_state} · {a.id.slice(0, 8)}</option>)}</NativeSelect></Field>
    {evaluation && !eligible && <p role="status">Pendência C04: {evaluation.configuration_state} / {resultLabel[evaluation.result]} / {evaluation.evidence}. Registe ou esclareça os factos no C04; esta entrada não autoriza intervenção.</p>}
    {evaluation && eligible && isAdmin && <form onSubmit={open} className="space-y-3 rounded border border-border p-3">
      <p>Decisão humana de elegibilidade. Defina os critérios deste caso; o sistema não presume uma política comercial universal.</p>
      <Text name="opening_criteria" title="Critérios específicos de abertura" /><Text name="eligibility_reason" title="Fundamento da elegibilidade" /><Text name="eligibility_ref" title="Referência da decisão de abertura (HTTPS ou URN)" />
      <Text name="closure_criteria" title="Critérios específicos de encerramento" /><Text name="closure_ref" title="Referência dos critérios de encerramento (HTTPS ou URN)" />
      <label className="flex gap-2"><input type="checkbox" required /> Confirmo a elegibilidade e a utilização da configuração histórica: objetivo demonstrado, prova pós-execução, ausência de pendências materiais e revisão humana para encerrar. Revisões C04 posteriores exigem novo caso nesta versão.</label>
      <Button disabled={action.isPending || cases.isError} type="submit">Abrir caso com decisão documentada</Button>
    </form>}
    {cases.isLoading ? <Loading /> : !cases.data?.length ? <Empty title="Sem casos operacionais">Uma avaliação elegível e decisão documentada de administrador são necessárias.</Empty> : <Field title="Caso operacional"><NativeSelect aria-label="Caso operacional" value={caseId} onChange={e => setCaseId(e.target.value)}><option value="">Selecionar caso</option>{cases.data.map(c => <option key={c.id} value={c.id}>{states[c.state]} · {c.id.slice(0, 8)} · v{c.version}</option>)}</NativeSelect></Field>}
    <Button variant="secondary" onClick={() => cases.refetch()}>Atualizar casos operacionais</Button>
  </div></Panel>{selected && <Dossier key={selected.id} current={selected} />}</div>;
}
function Dossier({ current }: { current: Case }) {
  const { tenant, isAdmin, canWrite } = useTenant(); const action = useAction(current.subject_id); const retry = useRef<{ signature: string; operation: string } | null>(null);
  const [observationsSelected, setObservationsSelected] = useState<string[]>([]);
  const events = useQuery({ queryKey: tk(tenant.id, "operational", current.subject_id, "events", current.id), queryFn: async () => {
    const { data, error } = await supabase.from("cw_operational_events").select("*").eq("tenant_id", tenant.id).eq("case_id", current.id).order("sequence").limit(500); if (error) throw error; return data;
  } });
  const observations = useQuery({ queryKey: tk(tenant.id, "operational", current.subject_id, "observations"), queryFn: async () => {
    const { data, error } = await supabase.from("observations").select("id,indicator_key,value_numeric,value_text,unit,source,observed_at").eq("tenant_id", tenant.id).eq("subject_id", current.subject_id).order("observed_at", { ascending: false }).limit(100); if (error) throw error; return data;
  } });
  const bundles = useQuery({ queryKey: tk(tenant.id, "operational", current.subject_id, "bundles"), queryFn: async () => {
    const { data, error } = await supabase.from("c03_bundles").select("id,created_at").eq("tenant_id", tenant.id).eq("subject_id", current.subject_id).order("created_at", { ascending: false }).limit(100); if (error) throw error; return data;
  } });
  const execution = events.data?.find(e => e.command === "record_execution");
  const comparison = events.data?.filter(e => e.command === "observe").at(-1);
  const decision = events.data?.filter(e => e.command === "decide").at(-1);
  const authorization = events.data?.filter(e => e.command === "approve").at(-1);
  const plan = events.data?.filter(e => e.command === "plan").at(-1);
  function command(name: string, payload: Record<string, Json>) {
    const signature = JSON.stringify([current.id, current.version, name, payload]);
    if (retry.current?.signature !== signature) retry.current = { signature, operation: crypto.randomUUID() };
    const operation = retry.current.operation;
    action.mutate(async () => { const { error } = await supabase.rpc("command_operational_case", { _tenant_id: tenant.id, _case_id: current.id, _expected_version: current.version, _operation_id: operation, _command: name, _payload: payload }); if (error) throw error; });
  }
  function submit(name: string, extra: Record<string, Json> = {}) { return (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, Json>;
    if (name === "plan") data["observation_seconds"] = Number(data["observation_seconds"]);
    if (name === "decide") for (const key of ["close_requested", "criteria_met", "material_contradiction"]) data[key] = data[key] === "true";
    command(name, { ...data, ...extra });
  }; }
  return <Panel title="Dossier operacional C05–C10"><div className="space-y-5 text-sm">
    <strong role="status">{states[current.state]} · v{current.version}</strong>
    <p>Contrato por indicador · individual-review-v1. Um ciclo de intervenção por caso; sem conectores e sem causalidade automática.</p>
    <dl>{Object.entries(object(current.opening_definition)).filter(([k]) => !["eligible", "configuration_pinned"].includes(k)).map(([k, v]) => <div key={k} className="mb-2"><dt className="font-medium">{{ eligibility_reason: "Fundamento", eligibility_ref: "Referência da abertura", opening_criteria: "Critérios de abertura", closure_criteria: "Critérios de encerramento", closure_ref: "Referência do encerramento" }[k] || k}</dt><dd className="break-words text-muted-foreground">{String(v)}</dd></div>)}</dl>
    {action.error && <ErrorState message={errors[action.error.message] || action.error.message} />}
    {(events.error || observations.error || bundles.error) && <ErrorState message={(events.error || observations.error || bundles.error)!.message} onRetry={() => { void events.refetch(); void observations.refetch(); void bundles.refetch(); }} />}
    {canWrite && events.isSuccess && !execution && current.state !== "closed_resolved" && <Stage title="C05 · Investigar" onSubmit={submit("investigate", { observation_ids: observationsSelected })} pending={action.isPending} button="Registar investigação">
      <Field title="Conclusão da investigação"><NativeSelect aria-label="Conclusão da investigação" name="status" required><option value="insufficient">Informação insuficiente</option><option value="hypothesis">Hipótese</option><option value="confirmed">Impedimento confirmado por revisão humana</option></NativeSelect></Field>
      <Text name="finding" title="Constatação e limites da investigação" /><Text name="reference" title="Referência da investigação (HTTPS ou URN)" />
      <fieldset><legend>Provas C01 deste cliente (até 100; confirmação exige pelo menos uma)</legend><div className="max-h-48 space-y-2 overflow-auto rounded border p-2">{observations.data?.map(o => <label key={o.id} className="flex gap-2 text-xs"><input type="checkbox" value={o.id} checked={observationsSelected.includes(o.id)} onChange={e => setObservationsSelected(ids => e.target.checked ? [...ids, o.id] : ids.filter(id => id !== o.id))} />{o.indicator_key}: {o.value_numeric ?? o.value_text} {o.unit} · {o.source} · {formatDate(o.observed_at)} · {o.id.slice(0, 8)}</label>)}</div></fieldset>
      <p className="text-xs text-muted-foreground">O servidor verifica empresa, cliente e referências corrigidas. Documentos externos são referências declaradas; o conteúdo não é consultado nem certificado.</p>
    </Stage>}
    {canWrite && ["impediment_confirmed", "awaiting_approval", "approved"].includes(current.state) && <Stage title="C06 · Preparar ou rever plano" onSubmit={submit("plan")} pending={action.isPending} button="Guardar plano para autorização">
      <Text name="action" title="Intervenção humana concreta" /><Text name="rationale" title="Justificação da intervenção" /><Text name="success_conditions" title="Condições de sucesso verificáveis" /><Text name="limitations" title="Limitações conhecidas" /><Text name="reversal" title="Passos de reversão ou justificação da sua ausência" /><Text name="reference" title="Referência do plano (HTTPS ou URN)" />
      <Text name="observation_seconds" title="Janela de observação em segundos (1–31536000)" number />
      <p className="text-xs">A janela é uma escolha explícita deste plano. Deve ser compatível com as janelas do indicador. Rever o plano invalida a autorização anterior.</p>
    </Stage>}
    {plan && <div className="rounded border p-3"><strong>Último plano registado · verificar estado e autorização</strong><p>{String(object(plan.details)["action"])}</p><p>Sucesso: {String(object(plan.details)["success_conditions"])}</p><p>Observação: {String(object(plan.details)["observation_seconds"])} segundos</p></div>}
    {isAdmin && ["awaiting_approval", "approved"].includes(current.state) && <Stage title="C07 · Autorizar plano atual" onSubmit={submit("approve")} pending={action.isPending} button="Autorizar plano atual">
      <Text name="valid_until" title="Autorização válida até (ISO com fuso)" /><Text name="reason" title="Fundamento da autorização" /><Text name="reference" title="Referência da autorização (HTTPS ou URN)" />
    </Stage>}
    {authorization && <p>Validade da última autorização: {formatDate(String(object(authorization.details)["valid_until"]))}. A execução revalida o papel do autorizador e o plano no servidor.</p>}
    {canWrite && current.state === "approved" && <Stage title="C07 · Registar execução humana" onSubmit={submit("record_execution")} pending={action.isPending} button="Registar execução autorizada">
      <Text name="receipt" title="Recibo descritivo da execução humana" /><Text name="reference" title="Referência da execução (HTTPS ou URN)" /><p>O recibo regista uma execução declarada. Não prova recuperação de valor.</p>
    </Stage>}
    {execution && <div className="rounded border p-3"><strong>C08 · Janela validada pelo servidor</strong><p>Execução: {formatDate(String(object(execution.details)["executed_at"]))}</p><p>Observar depois de: {formatDate(String(object(execution.details)["wait_until"]))}</p>{object(execution.details)["fixture"] && <p>Histórico sintético retrospectivo: não comprova autorização ou execução passadas.</p>}</div>}
    {canWrite && ["waiting_observation", "observed", "remain_open"].includes(current.state) && <Stage title="C09 · Comparar nova evidência" onSubmit={submit("observe")} pending={action.isPending || bundles.isError} button="Comparar com objetivo histórico">
      <Field title="Novo pacote C03"><NativeSelect aria-label="Novo pacote C03" name="bundle_id" required><option value="">Selecionar novo pacote deste cliente</option>{bundles.data?.map(b => <option key={b.id} value={b.id}>{formatDate(b.created_at)} · {b.id.slice(0, 8)}</option>)}</NativeSelect></Field><p>A janela deve ter terminado no servidor. Medições anteriores à execução não demonstram o resultado pós-intervenção.</p>
    </Stage>}
    {comparison && <Comparison event={comparison} />}
    {isAdmin && current.state === "observed" && <Stage title="C10 · Decisão humana documentada" onSubmit={submit("decide")} pending={action.isPending} button="Registar decisão de continuidade ou fecho">
      <Choice name="close_requested" title="Decisão solicitada" yes="Solicitar encerramento" no="Manter aberto" /><Choice name="criteria_met" title="Critérios específicos satisfeitos?" yes="Sim, revistos com prova" no="Não ou pendentes" /><Choice name="material_contradiction" title="Existe contradição material?" yes="Sim" no="Não, revisto por administrador" />
      <Text name="reason" title="Fundamento da decisão" /><Text name="reference" title="Referência da revisão final (HTTPS ou URN)" /><p>O servidor mantém aberto se faltar evidência suficiente, objetivo demonstrado, configuração histórica aplicável ou revisão dos critérios.</p>
    </Stage>}
    {decision && <div className="rounded border p-3"><strong>Decisão persistida: {states[decision.to_state]}</strong><p>{String(object(decision.details)["reason"])}</p><p>Pendências: {((object(decision.details)["reasons"] || []) as Json[]).join("; ") || "Nenhuma identificada nesta revisão"}</p></div>}
    <details><summary className="cursor-pointer">Histórico imutável e referências</summary>{events.data?.map(e => <article key={e.id} className="mt-3 rounded border p-3"><strong>#{e.sequence} · {e.command} → {states[e.to_state]}</strong><p className="text-xs">{formatDate(e.created_at)} · ator {e.created_by}</p><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(e.details, null, 2)}</pre></article>)}</details>
  </div></Panel>;
}
function Comparison({ event }: { event: Event }) {
  const d = object(event.details); const after = object(d["after"] as Json); const before = object(d["before"] as Json);
  return <div className="space-y-2 rounded border p-3"><strong>C09 · {resultLabel[String(d["result"])]}</strong><p>Evidência pós-execução: {d["sufficient"] ? "suficiente" : "insuficiente"}. Causalidade não estabelecida.</p>{[["Antes", before], ["Depois", after]].map(([title, data]) => <div key={String(title)}><strong>{String(title)}</strong>{((data as Record<string, Json>)["windows"] as Json[] || []).map((w, i) => <p key={i}>{String(object(w)["value"] ?? "sem valor")} · {formatDate(String(object(w)["start"]))} → {formatDate(String(object(w)["end"]))}</p>)}</div>)}{!!(d["reasons"] as Json[])?.length && <p>Pendências: {(d["reasons"] as Json[]).join("; ")}</p>}</div>;
}
function Field({ title, children }: { title: string; children: ReactNode }) { return <label className="block space-y-1">{title}{children}</label>; }
function Text({ name, title, number = false }: { name: string; title: string; number?: boolean }) { return <Field title={title}><Input aria-label={title} name={name} required maxLength={4000} type={number ? "number" : "text"} min={number ? 1 : undefined} max={number ? 31536000 : undefined} step={number ? 1 : undefined} /></Field>; }
function Choice({ name, title, yes, no }: { name: string; title: string; yes: string; no: string }) { return <Field title={title}><NativeSelect aria-label={title} name={name} required defaultValue=""><option value="">Selecionar explicitamente</option><option value="false">{no}</option><option value="true">{yes}</option></NativeSelect></Field>; }
function Stage({ title, children, onSubmit, pending, button }: { title: string; children: ReactNode; onSubmit: (e: FormEvent<HTMLFormElement>) => void; pending: boolean; button: string }) { return <form aria-label={title} onSubmit={onSubmit} className="space-y-3 rounded border border-border p-3"><h3 className="font-medium">{title}</h3>{children}<Button type="submit" disabled={pending}>{button}</Button></form>; }
