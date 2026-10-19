import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type { Json } from "@/integrations/supabase/types";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { profilesQuery } from "@/lib/queries";
import { caseStateLabel, eventDetails, journeyError, journeySteps, resultLabel, type CaseEvent, type JourneyCase } from "@/lib/journey-types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, ErrorState, formatDate, Loading, Mono, NativeSelect, PageHeader, Panel, StatusPill } from "./ui-bits";
import { OperationalCases } from "./operational-cases";
import { C04ValueState } from "./c04-value-state";
import { CaseStartGuide } from "./case-start-guide";

export function CaseWorkspace() {
  const { tenant } = useTenant();
  return <Workspace key={tenant.id} />;
}
function useJourneyAction() {
  const { tenant } = useTenant();
  const qc = useQueryClient();
  const alive = useRef(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const mutation = useMutation({
    mutationFn: async (fn: () => Promise<unknown>) => { assertActiveTenant(tenant.id); return fn(); },
    onSuccess: async () => {
      if (!alive.current) return;
      await qc.invalidateQueries({ queryKey: tk(tenant.id, "journey") });
      if (alive.current) setError(null);
    },
    onError: e => { if (alive.current) setError(journeyError(e)); },
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, isAlive: () => alive.current };
}
function Workspace() {
  const { tenant, isAdmin, canWrite } = useTenant();
  const [subjectId, setSubjectId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [focusStep, setFocusStep] = useState("C04");
  const subjects = useQuery({ queryKey: tk(tenant.id, "journey", "subjects"), queryFn: async () => {
    const { data, error } = await supabase.from("subjects").select("id,display_name,external_ref").eq("tenant_id", tenant.id).order("created_at").limit(100);
    if (error) throw error; return data;
  } });
  const cases = useQuery({ queryKey: tk(tenant.id, "journey", "cases", subjectId), queryFn: async () => {
    let query = supabase.from("cw_cases").select("*").eq("tenant_id", tenant.id).order("created_at", { ascending: false }).limit(100);
    if (subjectId) query = query.eq("subject_id", subjectId);
    const { data, error } = await query.returns<JourneyCase[]>(); if (error) throw error; return data;
  } });
  const operationalCount = useQuery({ queryKey: tk(tenant.id, "operational-count"), queryFn: async () => {
    const { count, error } = await supabase.from("cw_operational_cases").select("id", { count: "exact", head: true }).eq("tenant_id", tenant.id); if (error) throw error; return count ?? 0;
  } });
  const selected = cases.data?.find(c => c.id === caseId);
  return <>
    <PageHeader title="Casos · percurso CENTERWAY" description="Core: evidência → investigação → intervenção autorizada → resultado → decisão." />
    {subjects.isSuccess && cases.isSuccess && operationalCount.isSuccess && !operationalCount.data && !cases.data?.length && <CaseStartGuide subjectId={subjectId} noSubjects={!subjects.data?.length} />}
    <div id="case-client" className="mb-5 scroll-mt-20">
      <Field title="Cliente acompanhado"><NativeSelect className="h-11 min-w-0" value={subjectId} disabled={subjects.isLoading || subjects.isError || !subjects.data?.length} onChange={e => { setSubjectId(e.target.value); setCaseId(""); }}>
        <option value="">{subjects.isLoading ? "A carregar clientes…" : subjects.isError ? "Clientes indisponíveis" : !subjects.data?.length ? "Ainda não há clientes" : "Todos os clientes (até 100)"}</option>{subjects.data?.map(s => <option key={s.id} value={s.id}>{s.display_name || s.external_ref}</option>)}
      </NativeSelect></Field>
      {subjects.isError && <ErrorState message="Não foi possível consultar os clientes." onRetry={() => subjects.refetch()} />}
      {subjects.isSuccess && !!subjects.data?.length && <p className="mt-2 text-xs text-muted-foreground">Escolha um cliente para consultar os seus objetivos e casos.</p>}
    </div>
    {subjectId && <div id="C04-configurable" className="mb-6 scroll-mt-20"><C04ValueState subjectId={subjectId} /></div>}
    {subjectId && <div className="mb-6"><OperationalCases subjectId={subjectId} /></div>}
    <details className="mb-5 border-y border-border py-3">
      <summary className="cursor-pointer text-sm font-medium">Percurso C01–C10 <span className="ml-2 text-xs font-normal text-muted-foreground">Recolha → decisão</span></summary>
    <nav aria-label="Etapas do percurso" className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
      {journeySteps.map(([code, title, description]) => <a key={code} onClick={() => setFocusStep(code)} href={Number(code.slice(1)) < 4 ? (subjectId ? `/app/clientes/${subjectId}` : "/app/clientes") : code === "C04" ? (subjectId ? "#C04-configurable" : "#case-client") : "#case-dossier"} className="min-w-0 rounded-md border border-border p-3 text-sm hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="block font-mono text-xs text-primary">{code}</span><strong className="mt-1 block font-medium">{title}</strong><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
      </a>)}
    </nav></details>
    <details className="mb-6 rounded-md border border-border">
      <summary className="cursor-pointer p-4 text-sm font-medium">Exemplo legado · FlowReports · apenas demonstração <span className="ml-2 text-xs font-normal text-muted-foreground">flowreports-demo-v1 · dados sintéticos · não é regra geral da aplicação</span></summary>
      <div className="border-t border-border p-4">
    <aside aria-label="Limites da política do piloto" className="mb-6 border-l-2 border-primary/40 pl-4 text-sm">
      <p className="font-medium">Regras exclusivas · <span className="break-all font-mono text-xs text-primary">flowreports-demo-v1</span></p>
      <p className="mt-2 leading-relaxed text-muted-foreground">FlowReports / Loja Aurora: 10 → 4 h/semana, perfil compatível com report_hours e confirmação documental manual. O percurso de casos C05–C10 e o C04 do piloto aplicam apenas este cenário sintético, não regras universais de valor.</p>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">Sem conectores externos; a execução é um registo humano autorizado. A observação exige 14 dias e duas semanas completas.</p>
      <a href="/mvp-preview.html" className="mt-2 inline-block text-xs text-muted-foreground underline underline-offset-4">Referência ilustrativa · não executa operações</a>
    </aside>
    <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)] [&>*]:min-w-0">
      <div className="space-y-6">
        {subjectId ? <ObjectivePanel key={subjectId} subjectId={subjectId} canWrite={canWrite} isAdmin={isAdmin} onCase={setCaseId} /> :
          <Panel title="C04 · Objetivos do exemplo"><p className="text-sm text-muted-foreground">Selecione um cliente para registar o objetivo sintético deste exemplo, avaliar evidências e abrir um caso de demonstração.</p></Panel>}
        <Panel title="Casos persistidos" actions={<Button size="sm" variant="secondary" onClick={() => cases.refetch()}>Atualizar</Button>}>
          {cases.isLoading ? <Loading /> : cases.isError ? <ErrorState message={journeyError(cases.error)} onRetry={() => cases.refetch()} /> :
            !cases.data?.length ? <Empty title="Sem casos">Um caso exige C04 suficiente e objetivo não atingido. C02 candidato não abre casos.</Empty> :
              <div className="space-y-2">{cases.data.map(c => <button key={c.id} onClick={() => setCaseId(c.id)} aria-pressed={c.id === caseId}
                className={`w-full rounded-md border p-3 text-left text-sm ${c.id === caseId ? "border-primary bg-primary/5" : "border-border"}`}>
                <strong>{subjects.data?.find(s => s.id === c.subject_id)?.display_name || "Cliente"}</strong>
                <p className="my-2"><StatusPill tone={c.state === "closed_resolved" ? "success" : "neutral"}>{caseStateLabel[c.state]}</StatusPill></p>
                <Mono>{c.id.slice(0, 8)} · v{c.version}</Mono><span className="ml-3 text-xs text-muted-foreground">{formatDate(c.created_at)}</span>
              </button>)}</div>}
        </Panel>
      </div>
      <div id="case-dossier">{selected ? <CaseDetail key={selected.id} current={selected} focusStep={focusStep} /> : <Panel title="Core · acompanhamento"><Empty title="Selecione um caso">O histórico, as autorizações, a janela e os resultados aparecem aqui.</Empty></Panel>}</div>
    </div>
  </>;
}
function ObjectivePanel({ subjectId, canWrite, isAdmin, onCase }: { subjectId: string; canWrite: boolean; isAdmin: boolean; onCase: (id: string) => void }) {
  const { tenant } = useTenant();
  const action = useJourneyAction();
  const [objectiveId, setObjectiveId] = useState("");
  const [bundleId, setBundleId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const profiles = useQuery(profilesQuery(tenant.id));
  const approved = profiles.data?.find(p => p.status === "approved");
  const objectives = useQuery({ queryKey: tk(tenant.id, "journey", "objectives", subjectId), queryFn: async () => {
    const { data, error } = await supabase.from("cw_objectives").select("*").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const bundles = useQuery({ queryKey: tk(tenant.id, "journey", "bundles", subjectId), queryFn: async () => {
    const { data, error } = await supabase.from("c03_bundles").select("id,run_id,created_at").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const assessments = useQuery({ queryKey: tk(tenant.id, "journey", "assessments", subjectId), queryFn: async () => {
    const { data, error } = await supabase.from("cw_assessments").select("*").eq("tenant_id", tenant.id).eq("subject_id", subjectId).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const objective = objectives.data?.find(o => o.id === objectiveId);
  function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!approved) return;
    const fields = new FormData(e.currentTarget);
    action.run(async () => {
      const { error } = await supabase.rpc("create_demo_objective", { _tenant_id: tenant.id, _subject_id: subjectId, _profile_id: approved.id,
        _deadline: String(fields.get("deadline")), _source: String(fields.get("source")),
        _capacity_ref: String(fields.get("capacity")), _commitment_ref: String(fields.get("commitment")), _customer_ref: String(fields.get("customer")) });
      if (error) throw error;
    });
  }
  return <Panel title="C04 · Objetivo e avaliação"><div id="C04" className="space-y-4 text-sm">
    <p><Link to="/app/clientes/$subjectId" params={{ subjectId }} className="underline">C01–C03: consultar cliente, análises e pacotes</Link></p>
    {action.error && <ErrorState message={action.error} />}
    {[objectives, bundles, assessments].some(q => q.isError) && <ErrorState message={journeyError(objectives.error || bundles.error || assessments.error)} onRetry={() => { void objectives.refetch(); void bundles.refetch(); void assessments.refetch(); }} />}
    {objectives.isLoading && <Loading />}
    {isAdmin && <Button size="sm" variant="secondary" onClick={() => setShowForm(!showForm)}>Registar objetivo sintético</Button>}
    {showForm && isAdmin && <form onSubmit={create} className="space-y-3 rounded-md border border-border p-3">
      <p>Perfil aprovado: {approved ? `v${approved.version}` : "nenhum"}. Política: report_hours, 10 → 4 h/semana, duas semanas completas.</p>
      <Field title="Prazo confirmado ISO 8601 com fuso"><Input name="deadline" required placeholder="2026-09-01T00:00:00Z" pattern=".*(Z|[+-][0-9]{2}:[0-9]{2})$" /></Field>
      <Field title="Fonte das medições"><Input name="source" required maxLength={200} placeholder="synthetic-flowreports" /></Field>
      <Field title="Referência da capacidade do plano"><Input name="capacity" required maxLength={1000} /></Field>
      <Field title="Referência do compromisso da SaaS"><Input name="commitment" required maxLength={1000} /></Field>
      <Field title="Referência da confirmação do cliente"><Input name="customer" required maxLength={1000} /></Field>
      <label className="flex gap-2 text-xs"><input type="checkbox" required /> Confirmo documentos sintéticos distintos e compatíveis e dados fictícios.</label>
      <Button type="submit" disabled={action.pending || !approved}>Guardar objetivo confirmado</Button>
    </form>}
    <Field title="Objetivo histórico"><NativeSelect value={objectiveId} onChange={e => setObjectiveId(e.target.value)}>
      <option value="">Selecionar objetivo</option>{objectives.data?.map(o => <option key={o.id} value={o.id}>10 → 4 h/semana · prazo {formatDate(o.deadline)}</option>)}
    </NativeSelect></Field>
    {objective && <div className="space-y-1 text-xs text-muted-foreground"><p>Fonte: {objective.measurement_source}</p><p>Capacidade: {objective.capacity_ref}</p><p>Compromisso: {objective.commitment_ref}</p><p>Cliente: {objective.customer_confirmation_ref}</p><p>Política: {objective.policy_version}</p></div>}
    <Field title="Pacote C03 para avaliação"><NativeSelect value={bundleId} onChange={e => setBundleId(e.target.value)}>
      <option value="">Selecionar pacote persistido</option>{bundles.data?.map(b => <option key={b.id} value={b.id}>{formatDate(b.created_at)} · {b.id.slice(0, 8)}</option>)}
    </NativeSelect></Field>
    {canWrite && <Button disabled={!objectiveId || !bundleId || action.pending} onClick={() => action.run(async () => {
      const { error } = await supabase.rpc("assess_demo_objective", { _tenant_id: tenant.id, _objective_id: objectiveId, _bundle_id: bundleId }); if (error) throw error;
    })}>Avaliar objetivo no servidor</Button>}
    <div className="space-y-3">{assessments.data?.map(a => <div key={a.id} className="rounded-md border border-border p-3">
      <StatusPill tone={a.result === "achieved" ? "success" : "neutral"}>{resultLabel[a.result] ?? a.result}</StatusPill>
      <p className="my-2 text-xs text-muted-foreground">Evidência: {resultLabel[a.evidence]} · {formatDate(a.created_at)}</p>
      <p className="text-xs">Avaliação {a.id.slice(0, 8)} · objetivo {a.objective_id.slice(0, 8)} · pacote {a.bundle_id.slice(0, 8)}</p>
      <Details value={a.details} />
      {canWrite && a.result === "not_achieved" && a.evidence === "sufficient" && <Button size="sm" className="mt-2" disabled={action.pending} onClick={() => action.run(async () => {
        const { data, error } = await supabase.rpc("open_demo_case", { _tenant_id: tenant.id, _assessment_id: a.id }); if (error) throw error;
        if (action.isAlive()) onCase(data);
      })}>Abrir / consultar caso elegível</Button>}
    </div>)}</div>
    <p className="text-xs text-muted-foreground">Sem interpretação automática de documentos ou conclusão global. Configuração incompatível produz bloqueio ou insuficiência.</p>
  </div></Panel>;
}
function CaseDetail({ current, focusStep }: { current: JourneyCase; focusStep: string }) {
  const { tenant, canWrite, isAdmin } = useTenant();
  const action = useJourneyAction();
  const [tab, setTab] = useState("percurso");
  useEffect(() => {
    const tabs: Record<string, string> = { C05: "investigate", C06: "plan", C07: "record_execution", C08: "record_execution", C09: "observe", C10: "decide" };
    if (tabs[focusStep]) setTab(tabs[focusStep]!);
  }, [focusStep]);
  const [proof, setProof] = useState("");
  const [receipt, setReceipt] = useState("");
  const [bundleId, setBundleId] = useState("");
  const retry = useRef<{ signature: string; operation: string } | null>(null);
  const events = useQuery({ queryKey: tk(tenant.id, "journey", "events", current.id), queryFn: async () => {
    const { data, error } = await supabase.from("cw_case_events").select("*").eq("tenant_id", tenant.id).eq("case_id", current.id).order("sequence").limit(300).returns<CaseEvent[]>();
    if (error) throw error; return data;
  } });
  const observations = useQuery({ queryKey: tk(tenant.id, "journey", "integration", current.subject_id), queryFn: async () => {
    const { data, error } = await supabase.from("observations").select("id,value_text,observed_at,source").eq("tenant_id", tenant.id).eq("subject_id", current.subject_id).eq("indicator_key", "integration_status").order("observed_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const bundles = useQuery({ queryKey: tk(tenant.id, "journey", "bundles", current.subject_id), queryFn: async () => {
    const { data, error } = await supabase.from("c03_bundles").select("id,run_id,created_at").eq("tenant_id", tenant.id).eq("subject_id", current.subject_id).order("created_at", { ascending: false }).limit(100);
    if (error) throw error; return data;
  } });
  const last = (name: string) => events.data?.filter(e => e.command === name).at(-1);
  const execution = eventDetails(last("record_execution"));
  function command(name: string, payload: Json = {}) {
    const signature = JSON.stringify([current.id, current.version, name, payload]);
    if (retry.current?.signature !== signature) retry.current = { signature, operation: crypto.randomUUID() };
    const operation = retry.current.operation;
    action.run(async () => {
      const { error } = await supabase.rpc("command_demo_case", { _tenant_id: tenant.id, _case_id: current.id,
        _expected_version: current.version, _operation_id: operation, _command: name, _payload: payload });
      if (error) throw error;
    });
  }
  const allow = canWrite && !action.pending && !events.isError && !events.isLoading;
  return <div className="space-y-4"><Panel title="Core · caso e próximas ações"><div className="space-y-3 text-sm">
    <StatusPill tone={current.state === "closed_resolved" ? "success" : "primary"}>{caseStateLabel[current.state]}</StatusPill>
    <p><Mono>{current.id}</Mono> · versão {current.version}</p>
    <p className="text-xs text-muted-foreground">{current.policy_version} · dados sintéticos. Cada transição regista ator, política, referências e hora.</p>
    {action.error && <ErrorState message={action.error} />}
    {events.data?.some(e => eventDetails(e)["fixture"] === "synthetic_retrospective_history") && <p className="rounded border border-primary/40 bg-primary/5 p-3 text-xs">
      Histórico fictício carregado retrospectivamente para visualizar resultados. Não demonstra aprovação/execução histórica nem uma espera real de 14 dias. C09/C10 foram calculados sobre as medições sintéticas persistidas.
    </p>}
    {!canWrite && <p>Modo de consulta. O papel leitor não pode alterar o caso.</p>}
    {canWrite && ["investigation", "needs_information"].includes(current.state) && <div id="C05" className="space-y-3">
      <Field title="C05 · Prova da integração desativada"><NativeSelect value={proof} onChange={e => setProof(e.target.value)}>
        <option value="">Sem prova / solicitar informação</option>{observations.data?.map(o => <option key={o.id} value={o.id}>{o.value_text} · {formatDate(o.observed_at)} · {o.source}</option>)}
      </NativeSelect></Field>
      {observations.isError && <ErrorState message="Falha na leitura das provas C01." onRetry={() => observations.refetch()} />}
      <Button disabled={!allow} onClick={() => command("investigate", { observation_id: proof || null })}>Investigar condição conhecida</Button>
      <p className="text-xs text-muted-foreground">Importe integration_status=disabled pelo C01. Uma hipótese sem prova mantém o caso à espera de informação.</p>
    </div>}
    {canWrite && current.state === "impediment_found" && <Button id="C06" disabled={!allow} onClick={() => command("plan")}>C06 · Preparar intervenção manual</Button>}
    {current.state === "awaiting_approval" && <div id="C07" className="space-y-2"><p>Verificar e reativar manualmente a integração, guardar recibo e medir duas semanas. Aprovação válida por 24 horas.</p>
      {isAdmin ? <Button disabled={!allow} onClick={() => command("approve")}>Aprovar este plano como administrador</Button> : <p>Aguarda aprovação de um administrador.</p>}
    </div>}
    {canWrite && current.state === "approved" && <div className="space-y-3"><p>A reativação é feita por uma pessoa no sistema de origem.</p>
      <Field title="Recibo da execução humana"><Input value={receipt} onChange={e => setReceipt(e.target.value)} maxLength={2000} placeholder="Referência da tarefa e verificação efetuada" /></Field>
      <Button disabled={!allow || !receipt.trim()} onClick={() => command("record_execution", { receipt })}>C07 · Registar execução humana autorizada</Button>
    </div>}
    {typeof execution["wait_until"] === "string" && <div id="C08" className="rounded-md border border-border p-3"><strong>C08 · Janela de observação</strong>
      <p>Execução registada: {formatDate(String(execution["executed_at"]))}</p><p>Observar a partir de: {formatDate(String(execution["wait_until"]))}</p>
      <p className="mt-1 text-xs text-muted-foreground">14 dias, duas janelas semanais completas. O relógio do servidor decide. Sem avanço artificial do tempo nesta interface.</p>
    </div>}
    {canWrite && ["waiting_observation", "observed", "remain_open"].includes(current.state) && <div id="C09" className="space-y-3">
      <Field title="C09 · Novo pacote de medições pós-execução"><NativeSelect value={bundleId} onChange={e => setBundleId(e.target.value)}>
        <option value="">Selecionar pacote C03</option>{bundles.data?.map(b => <option value={b.id} key={b.id}>{formatDate(b.created_at)} · {b.id.slice(0, 8)}</option>)}
      </NativeSelect></Field>
      {bundles.isError && <ErrorState message="Falha na leitura dos pacotes." onRetry={() => bundles.refetch()} />}
      <Button variant="secondary" disabled={!allow || !bundleId} onClick={() => command("observe", { bundle_id: bundleId })}>Verificar janela e comparar resultados</Button>
    </div>}
    {canWrite && current.state === "observed" && <Button id="C10" disabled={!allow} onClick={() => command("decide")}>C10 · Avaliar encerramento ou continuidade</Button>}
    {current.state === "remain_open" && <p>O caso continua aberto. Novas medições e uma nova comparação podem demonstrar os critérios em falta.</p>}
    {current.state === "closed_resolved" && <p>Critérios do cenário satisfeitos. Melhoria após intervenção não prova causalidade.</p>}
  </div></Panel>
  <Panel title="Dossier do caso"><nav aria-label="Secções do caso" className="mb-4 flex flex-wrap gap-2">
    {[["percurso", "Histórico"], ["investigate", "C05 · Investigação"], ["plan", "C06 · Plano"], ["record_execution", "C07/C08 · Intervenção"], ["observe", "C09 · Resultados"], ["decide", "C10 · Decisão"]].map(([id, title]) =>
      <Button key={id} size="sm" variant={tab === id ? "default" : "secondary"} onClick={() => setTab(id!)}>{title}</Button>)}
  </nav>
  {events.isLoading ? <Loading /> : events.isError ? <ErrorState message={journeyError(events.error)} onRetry={() => events.refetch()} /> : tab === "percurso" ?
    <ol className="space-y-3">{events.data?.map(e => <li key={e.id} className="border-l-2 border-primary/40 pl-4 text-sm"><strong>{e.sequence}. {caseStateLabel[e.to_state]}</strong>
      <p className="mt-1 text-xs text-muted-foreground">{formatDate(e.created_at)} · {e.command} · ator {e.created_by.slice(0, 8)}</p><Details value={e.details} />
    </li>)}</ol> : last(tab) ? <EventView event={last(tab)!} /> : <Empty title="Esta etapa ainda não tem registo">Apenas resultados persistidos. Complete as pré-condições para chegar a esta etapa.</Empty>}
    <p className="mt-4 text-xs text-muted-foreground">Até 300 eventos por caso. Sem fecho administrativo, reabertura, renovação de aprovação ou scheduler automático neste piloto.</p>
  </Panel></div>;
}
function EventView({ event }: { event: CaseEvent }) {
  const d = eventDetails(event);
  return <div className="space-y-3 text-sm"><StatusPill tone="neutral">{caseStateLabel[event.to_state]}</StatusPill><p>{formatDate(event.created_at)} · ator <Mono>{event.created_by}</Mono></p>
    {typeof d["finding"] === "string" && <p>{d["finding"]}</p>}{typeof d["instructions"] === "string" && <p>{d["instructions"]}</p>}{typeof d["reason"] === "string" && <p>{d["reason"]}</p>}
    {d["component"] === "C09" && <><div className="grid grid-cols-3 gap-3"><Metric label="Antes" value={d["before_value"]} /><Metric label="Depois" value={d["value"]} /><Metric label="Meta" value={d["target"]} /></div>
      <p>{resultLabel[String(d["change"])] || String(d["change"])} · objetivo: {d["goal_achieved"] === true ? "atingido" : "não demonstrado"} · integração: {d["integration_verified"] === true ? "verificada" : "não demonstrada"}</p></>}
    <Details value={event.details} open />
  </div>;
}
function Metric({ label, value }: { label: string; value: Json | undefined }) {
  return <div className="rounded-md border border-border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono text-xl">{typeof value === "number" ? value : "—"}<span className="ml-1 text-xs">h/sem</span></p></div>;
}
function Field({ title, children }: { title: string; children: ReactNode }) { return <label className="block space-y-1.5 text-sm"><span>{title}</span>{children}</label>; }
function Details({ value, open = false }: { value: Json; open?: boolean }) {
  return <details className="mt-3 text-xs" open={open}><summary className="cursor-pointer text-muted-foreground">Critérios e referências persistidos</summary><pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-muted/30 p-3">{JSON.stringify(value, null, 2)}</pre></details>;
}
