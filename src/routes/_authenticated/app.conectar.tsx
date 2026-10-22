import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect, useRef } from "react";
import { connectedRequest } from "@/lib/connected";
import { assertActiveTenant, tk, unitLabel, useTenant } from "@/lib/tenant";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/_authenticated/app/conectar")({ component: ConnectedPage });
const labels: Record<string, string> = {
  not_connected: "Não conectado",
  authorization_pending: "Autorização pendente",
  connected: "Conectado",
  needs_mapping: "Precisa de mapeamento",
  insufficient_data: "Dados insuficientes",
  active: "Sincronização ativa",
  failed: "Falha",
  revoked: "Revogado",
};
function ConnectedPage() {
  const { tenant, user, isAdmin } = useTenant();
  return <ConnectedWizard key={tenant.id + user.id} tenant={tenant} isAdmin={isAdmin} />;
}
function ConnectedWizard({
  tenant,
  isAdmin,
}: {
  tenant: { id: string; subject_unit_type: "organization" | "person" };
  isAdmin: boolean;
}) {
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const qc = useQueryClient(),
    id = tenant.id;
  const [error, setError] = useState("");
  const [service, setService] = useState(""),
    [promise, setPromise] = useState(""),
    [sources, setSources] = useState("PostHog"),
    [consent, setConsent] = useState(false),
    [region, setRegion] = useState("eu");
  const [names, setNames] = useState<Record<string, string>>({}),
    [chosen, setChosen] = useState<Record<string, boolean>>({}),
    [metrics, setMetrics] = useState<Record<string, boolean>>({}),
    [start, setStart] = useState(""),
    [goal, setGoal] = useState<Record<string, string>>({}),
    [outcome, setOutcome] = useState<Record<string, boolean>>({});
  const state = useQuery({
    queryKey: tk(id, "connected"),
    enabled: isAdmin,
    queryFn: ({ signal }) => connectedRequest(id, "status", undefined, signal),
    retry: false,
  });
  const mutate = useMutation({
    mutationFn: async ({ action, body }: { action: string; body?: object }) => {
      setError("");
      assertActiveTenant(id);
      const value = await connectedRequest(id, action, body || {});
      assertActiveTenant(id);
      if (!alive.current) throw new Error("Sessão da ligação mudou.");
      if (action === "start") {
        const u = new URL(value.authorization);
        sessionStorage.setItem(
          "cw.posthog.pending",
          JSON.stringify({ tenant: id, state: u.searchParams.get("state") }),
        );
        window.location.assign(u.href);
      }
      return value;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: tk(id, "connected") }),
    onError: (e) => setError(e.message),
  });
  const act = (action: string, body?: object) =>
    mutate.mutate({ action, ...(body ? { body } : {}) });
  const s = state.data;
  const preview = s?.preview;
  const busy = mutate.isPending;
  const profile = useQuery({
    queryKey: tk(id, "connector-approved-profile"),
    enabled: isAdmin,
    queryFn: async () => {
      const { supabase } = await import("@/integrations/supabase/client");
      const { data, error } = await supabase
        .from("tenant_value_profiles")
        .select("id,version")
        .eq("tenant_id", id)
        .eq("status", "approved")
        .maybeSingle();
      if (error) throw error;
      if (!data) return null;
      const indicators = await supabase
        .from("profile_indicators")
        .select(
          "key,name,classification,direction,unit,value_type,aggregation,expected_cadence_days,target_value",
        )
        .eq("tenant_id", id)
        .eq("profile_id", data.id);
      if (indicators.error) throw indicators.error;
      return { ...data, indicators: indicators.data };
    },
  });
  const [existing, setExisting] = useState(false);
  const [mappedKeys, setMappedKeys] = useState<Record<string, string>>({});
  const [directions, setDirections] = useState<Record<string, string>>({});
  if (!isAdmin)
    return (
      <p>
        A ligação requer um administrador da empresa. Os percursos manuais continuam disponíveis.
      </p>
    );
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
      <h1 className="text-2xl font-semibold">Ligar os seus dados</h1>
      <p>
        Responda a cinco perguntas, autorize o PostHog e reveja os clientes e indicadores antes de
        sincronizar. Não são criadas avaliações ou intervenções automaticamente.
      </p>
      <p>
        <Link to="/app/perfil" className="underline">
          Perfil e regras manuais
        </Link>{" "}
        ·{" "}
        <Link to="/app/dados" className="underline">
          Dados e histórico
        </Link>
      </p>
      {state.isPending && <p role="status">A verificar a ligação…</p>}
      {(error || state.error) && (
        <p role="alert" className="rounded border border-destructive p-3 break-words">
          {error || state.error?.message}. Não foi confirmada uma ligação. Se faltar configuração do
          servidor, contacte a equipa responsável.
        </p>
      )}
      {s && (
        <p role="status">
          Estado: {labels[s.status] || s.status}
          {s.project_name ? " · " + s.project_name : ""}
        </p>
      )}
      {s?.last_error && <p role="alert">Última pendência: {s.last_error}</p>}
      {s && ["not_connected", "revoked"].includes(s.status) && (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            act("start", {
              service,
              promise,
              sources,
              consent,
              unit: tenant.subject_unit_type,
              region,
            });
          }}
        >
          <div>
            <Label htmlFor="service">1. Que serviço SaaS oferece?</Label>
            <Input
              id="service"
              required
              maxLength={500}
              value={service}
              onChange={(e) => setService(e.target.value)}
            />
          </div>
          <div>
            <Label>2. Quem são os seus clientes?</Label>
            <p>{unitLabel[tenant.subject_unit_type]} — tipo definido na criação da empresa.</p>
          </div>
          <div>
            <Label htmlFor="promise">3. Que resultado promete aos clientes?</Label>
            <Input
              id="promise"
              required
              maxLength={2000}
              value={promise}
              onChange={(e) => setPromise(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="sources">4. Que fontes de dados já utiliza?</Label>
            <Input
              id="sources"
              required
              maxLength={500}
              value={sources}
              onChange={(e) => setSources(e.target.value)}
            />
            <Label htmlFor="region">Região do seu PostHog</Label>
            <select
              className="block border p-2"
              id="region"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
            >
              <option value="eu">Europa</option>
              <option value="us">Estados Unidos</option>
            </select>
          </div>
          <div>
            <Label>
              <input
                type="checkbox"
                required
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />{" "}
              5. Autorizo a descoberta e recolha dos grupos e contagens que confirmar.
            </Label>
            <p className="text-sm">
              Permissões: leitura de um único projeto, grupos e consultas. Sem acesso de escrita no
              PostHog. Identificadores pessoais desnecessários são descartados. Os dados aceites
              ficam no histórico C01; pode interromper leituras futuras ao desligar. Esta ligação
              depende da sessão autorizada e expira com ela.
            </p>
          </div>
          {tenant.subject_unit_type === "person" && (
            <p>
              O primeiro conector suporta grupos B2B. Pessoas não serão convertidas em empresas.
              Para B2C, utilize o percurso manual.
            </p>
          )}
          <Button disabled={busy || tenant.subject_unit_type === "person"} type="submit">
            Autorizar no PostHog
          </Button>
        </form>
      )}
      {s && s.status !== "not_connected" && (s.status !== "revoked" || s.needs_reauthorization) && (
        <Button variant="outline" disabled={busy} onClick={() => act("disconnect")}>
          Desligar e retirar consentimento
        </Button>
      )}
      {preview?.group_types?.length > 0 && !s.profile_id && (
        <section className="space-y-3">
          <h2 className="text-xl">Que grupo representa um cliente?</h2>
          <p>Escolha explicitamente o grupo. Utilizadores individuais não são clientes B2B.</p>
          {preview.group_types.map((g: any) => (
            <Button
              className="mr-2 mb-2"
              key={g.index}
              disabled={busy}
              variant="outline"
              onClick={() => act("discover", { group_type_index: g.index })}
            >
              {g.name}
            </Button>
          ))}
        </section>
      )}
      {preview?.limitations?.map((p: string) => (
        <p key={p} className="text-sm">
          {p}
        </p>
      ))}
      {preview?.groups?.length > 0 && !s.profile_id && (
        <section className="space-y-4">
          <h2 className="text-xl">Confirme clientes e objetivos</h2>
          <p>
            A amostra pode ser incompleta{preview.truncated ? " e atingiu o limite" : ""}. Só os
            clientes selecionados serão criados. Referências estáveis são preservadas.
          </p>
          <div className="max-h-72 overflow-auto space-y-2">
            {preview.groups.map((g: any) => (
              <div key={g.ref} className="flex gap-2">
                <input
                  aria-label={"Selecionar " + g.name}
                  type="checkbox"
                  checked={!!chosen[g.ref]}
                  onChange={(e) => setChosen({ ...chosen, [g.ref]: e.target.checked })}
                />
                <Input
                  aria-label={"Nome de " + g.name}
                  value={names[g.ref] ?? g.name}
                  onChange={(e) => setNames({ ...names, [g.ref]: e.target.value })}
                />
              </div>
            ))}
          </div>
          <Label htmlFor="start">Início do histórico a importar (UTC, até 366 dias)</Label>
          <Input id="start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          {profile.data && (
            <Label className="block">
              <input
                type="checkbox"
                checked={existing}
                onChange={(e) => setExisting(e.target.checked)}
              />{" "}
              Mapear explicitamente para o perfil aprovado v{profile.data.version} (chaves e
              unidades devem coincidir)
            </Label>
          )}
          {preview.metrics.map((m: any) => (
            <div className="space-y-2 border rounded p-3" key={m.event}>
              <Label>
                <input
                  type="checkbox"
                  checked={!!metrics[m.event]}
                  onChange={(e) => setMetrics({ ...metrics, [m.event]: e.target.checked })}
                />{" "}
                {m.name}
              </Label>
              {existing && (
                <div>
                  <Label htmlFor={"mapping-" + m.key}>Indicador aprovado para {m.name}</Label>
                  <select
                    id={"mapping-" + m.key}
                    className="block w-full border p-2"
                    value={mappedKeys[m.event] || ""}
                    onChange={(e) => setMappedKeys({ ...mappedKeys, [m.event]: e.target.value })}
                  >
                    <option value="">Escolha explicitamente</option>
                    {profile.data?.indicators
                      .filter(
                        (i) =>
                          i.unit === "events" &&
                          i.value_type === "numeric" &&
                          i.aggregation === "sum" &&
                          i.expected_cadence_days === 1,
                      )
                      .map((i) => (
                        <option key={i.key} value={i.key}>
                          {i.name} · {i.key}
                        </option>
                      ))}
                  </select>
                  <p>
                    As metas, direção e regras do perfil aprovado prevalecem. Os campos abaixo só se
                    aplicam a novos rascunhos.
                  </p>
                </div>
              )}
              <p>
                Contagem diária UTC · events · soma. Apenas grupos com eventos observados; nenhuma
                ausência é preenchida com zero.
              </p>
              <Label htmlFor={"goal-" + m.key}>
                Meta numérica, se documentada pelo responsável
              </Label>
              <Input
                id={"goal-" + m.key}
                type="number"
                step="any"
                value={goal[m.event] || ""}
                onChange={(e) => setGoal({ ...goal, [m.event]: e.target.value })}
              />
              <Label>
                <input
                  type="checkbox"
                  checked={!!outcome[m.event]}
                  onChange={(e) => setOutcome({ ...outcome, [m.event]: e.target.checked })}
                />{" "}
                Confirmo que esta contagem representa um resultado para o cliente, fundamentado no
                contrato
              </Label>
              <Label htmlFor={"direction-" + m.key}>Direção confirmada pelo responsável</Label>
              <select
                id={"direction-" + m.key}
                className="block border p-2"
                value={directions[m.event] || ""}
                onChange={(e) => setDirections({ ...directions, [m.event]: e.target.value })}
              >
                <option value="">Escolha</option>
                <option value="higher_is_better">Maior é melhor</option>
                <option value="lower_is_better">Menor é melhor</option>
              </select>
              <p className="text-xs break-all">
                Chave: {m.key}. A direção e as regras temporais/comerciais serão revistas no perfil
                antes da aprovação.
              </p>
            </div>
          ))}
          <Button
            disabled={busy}
            onClick={() =>
              act("prepare", {
                selection: {
                  confirmed: true,
                  start,
                  groups: preview.groups
                    .filter((g: any) => chosen[g.ref])
                    .map((g: any) => ({ ref: g.ref, name: names[g.ref] ?? g.name })),
                  metrics: preview.metrics
                    .filter((m: any) => metrics[m.event])
                    .map((m: any) => ({
                      ...m,
                      key: existing ? mappedKeys[m.event] || "" : m.key,
                      classification: existing
                        ? profile.data?.indicators.find((i) => i.key === mappedKeys[m.event])
                            ?.classification
                        : outcome[m.event]
                          ? "outcome"
                          : "usage",
                      direction: existing
                        ? profile.data?.indicators.find((i) => i.key === mappedKeys[m.event])
                            ?.direction
                        : directions[m.event] || "",
                      target_value: goal[m.event] || null,
                    })),
                  ...(existing ? { existing_profile_id: profile.data?.id } : {}),
                },
              })
            }
          >
            Confirmar seleção e criar rascunho
          </Button>
          <p>
            Esta confirmação não ativa a sincronização. Não comprova documentos, objetivos ou a
            promessa global.
          </p>
        </section>
      )}
      {s?.profile_id && (
        <section className="space-y-3">
          <h2 className="text-xl">Rever contrato antes da recolha</h2>
          <p>
            Perfil: {s.profile_id}. Defina a direção e as regras em{" "}
            <Link to="/app/perfil" className="underline">
              Perfil de valor
            </Link>
            . A aprovação usa exatamente o contrato existente; configurações em falta bloqueiam a
            ativação.
          </p>
          <pre className="whitespace-pre-wrap break-words text-sm">
            {JSON.stringify(s.profile_issues, null, 2)}
          </pre>
          {s.status !== "active" && (
            <Button disabled={busy} onClick={() => act("activate")}>
              Aprovar perfil e ativar sincronização
            </Button>
          )}
        </section>
      )}
      {s?.status === "active" && (
        <section className="space-y-3">
          <p>
            Sincronização autorizada. O agendamento externo tem de ser instalado pela equipa; esta
            página não instala Cron. Credencial C01 técnica com validade de 30 dias; a sessão e o
            consentimento continuam a ser verificados a cada execução.
          </p>
          <Button disabled={busy} onClick={() => act("sync")}>
            Sincronizar um período agora
          </Button>
          <p>
            Último sucesso: {s.last_success_at || "Ainda não ocorreu"} · Pedidos pendentes:{" "}
            {s.pending_batches}
          </p>
          <p className="break-words">Watermarks: {JSON.stringify(s.watermarks)}</p>
        </section>
      )}
      {s?.recent_attempts?.length > 0 && (
        <section>
          <h2 className="text-xl">Atividade da ligação</h2>
          <ul>
            {s.recent_attempts.map((a: any) => (
              <li className="break-words" key={a.id}>
                {a.started_at} · {a.kind} · {a.status} {a.code || ""} {a.http_status || ""}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
