import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, useTenant } from "@/lib/tenant";
import {
  credentialsQuery,
  ingestionEventsQuery,
  ingestionError,
  integrationKey,
} from "@/lib/integrations";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel, Loading, ErrorState, formatDate } from "./ui-bits";
export function IntegrationManagement() {
  const { tenant } = useTenant();
  return <Integrations key={`${tenant.id}:${tenant.role}`} />;
}
function Integrations() {
  const { tenant, isAdmin } = useTenant();
  const qc = useQueryClient();
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const [page, setPage] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const credentials = useQuery({ ...credentialsQuery(tenant.id, page), enabled: isAdmin });
  const events = useQuery({ ...ingestionEventsQuery(tenant.id, historyPage), enabled: isAdmin });
  const [secret, setSecret] = useState<{ id: string; value: string } | null>(null);
  const [message, setMessage] = useState("");
  const operation = useRef<{ signature: string; id: string } | null>(null);
  const action = useMutation({
    mutationFn: async (fn: () => Promise<void>) => {
      assertActiveTenant(tenant.id);
      await fn();
    },
    onSuccess: async () => {
      if (live.current) await qc.invalidateQueries({ queryKey: integrationKey(tenant.id) });
    },
  });
  function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const name = String(f.get("name"));
    const source = String(f.get("source"));
    const expires = new Date(String(f.get("expires")));
    if (!Number.isFinite(+expires)) return;
    const rotate = String(f.get("rotate") || "");
    const signature = JSON.stringify([name, source, expires.toISOString(), rotate]);
    if (operation.current?.signature !== signature)
      operation.current = { signature, id: crypto.randomUUID() };
    const id = operation.current.id;
    setSecret(null);
    setMessage("");
    action.mutate(async () => {
      const { data, error } = await supabase.rpc("create_ingestion_credential", {
        _tenant_id: tenant.id,
        _name: name,
        _source: source,
        _expires_at: expires.toISOString(),
        _operation_id: id,
        ...(rotate ? { _rotate_from: rotate } : {}),
      });
      if (error) throw error;
      if (!live.current) return;
      operation.current = null;
      const result = data as { id: string; secret: string | null };
      if (result.secret) setSecret({ id: result.id, value: result.secret });
      setMessage(
        result.secret
          ? "Credencial criada. Guarde o segredo agora; não será apresentado novamente."
          : "Pedido já registado. O segredo não é recuperável: revogue e crie outra credencial se necessário.",
      );
    });
  }
  function revoke(id: string) {
    action.mutate(async () => {
      const { error } = await supabase.rpc("revoke_ingestion_credential", {
        _tenant_id: tenant.id,
        _credential_id: id,
      });
      if (error) throw error;
      if (live.current) {
        if (secret?.id === id) setSecret(null);
        setMessage("Credencial revogada no servidor.");
      }
    });
  }
  return (
    <Panel title="Integrações · API C01" className="lg:col-span-2">
      {!isAdmin ? (
        <p>A gestão de credenciais exige um administrador.</p>
      ) : (
        <div className="space-y-4 text-sm">
          <p>
            Ingestão limitada ao C01, sem abertura automática de casos. O endpoint exige instalação
            posterior da Edge Function; criar uma chave não publica o serviço.
          </p>
          {action.error && <ErrorState message={ingestionError(action.error)} />}
          {message && <p role="status">{message}</p>}
          {secret && (
            <div className="space-y-2 rounded border p-3">
              <label htmlFor="ingestion-secret">Segredo apresentado uma única vez</label>
              <Input id="ingestion-secret" value={secret.value} readOnly autoComplete="off" />
              <Button
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(secret.value);
                    if (live.current)
                      setMessage("Credencial copiada. Guarde-a num gestor de segredos.");
                  } catch {
                    if (live.current) setMessage("Selecione e copie o segredo manualmente.");
                  }
                }}
              >
                Copiar credencial
              </Button>
              <Button type="button" variant="outline" onClick={() => setSecret(null)}>
                Ocultar segredo
              </Button>
            </div>
          )}
          <form
            aria-label="Criar credencial de ingestão"
            onSubmit={create}
            className="grid gap-3 sm:grid-cols-2"
          >
            <label>
              Nome da integração
              <Input name="name" required maxLength={200} />
            </label>
            <label>
              Fonte exata autorizada
              <Input name="source" required maxLength={200} />
            </label>
            <label>
              Validade (hora local, até 365 dias)
              <Input name="expires" type="datetime-local" required />
            </label>
            <label>
              Rotação opcional · ID da credencial atual
              <Input name="rotate" placeholder="Deixe vazio para uma nova integração" />
            </label>
            <p className="sm:col-span-2">
              Na rotação, a fonte deve ser a mesma e a chave anterior é revogada imediatamente, na
              mesma transação.
            </p>
            <Button disabled={action.isPending} type="submit">
              Criar credencial
            </Button>
          </form>
          <h3 className="font-semibold">Credenciais</h3>
          {credentials.isPending ? (
            <Loading />
          ) : credentials.isError ? (
            <ErrorState
              message={ingestionError(credentials.error)}
              onRetry={() => credentials.refetch()}
            />
          ) : (
            <>
              <ul className="divide-y">
                {credentials.data.slice(0, 25).map((c) => (
                  <li key={c.id} className="space-y-1 py-3 break-all">
                    <strong>{c.name}</strong> · {c.source}
                    <p>ID: {c.id}</p>
                    <p>
                      Validade: {formatDate(c.expires_at)} ·{" "}
                      {c.revoked_at
                        ? "Revogada"
                        : "Não revogada (a validade é verificada pelo servidor)"}
                    </p>
                    <p>
                      Última utilização:{" "}
                      {c.last_used_at ? formatDate(c.last_used_at) : "Sem utilização"} · HTTP{" "}
                      {c.last_status ?? "—"}
                    </p>
                    {!c.revoked_at && (
                      <Button
                        variant="outline"
                        disabled={action.isPending}
                        onClick={() => revoke(c.id)}
                      >
                        Revogar {c.name}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
              {!credentials.data.length && <p>Sem credenciais.</p>}
              <Button variant="outline" disabled={!page} onClick={() => setPage(page - 1)}>
                Credenciais anteriores
              </Button>{" "}
              <Button
                variant="outline"
                disabled={credentials.data.length <= 25}
                onClick={() => setPage(page + 1)}
              >
                Mais credenciais
              </Button>
            </>
          )}
          <h3 className="font-semibold">Histórico HTTP (sem segredos)</h3>
          {events.isPending ? (
            <Loading />
          ) : events.isError ? (
            <ErrorState message={ingestionError(events.error)} onRetry={() => events.refetch()} />
          ) : (
            <>
              <ul className="divide-y">
                {events.data.slice(0, 25).map((e) => (
                  <li key={e.id} className="py-2 break-all">
                    {formatDate(e.created_at)} · HTTP {e.http_status} · {e.code}
                    <p>
                      Credencial: {e.credential_id} · Lote: {e.batch_id ?? "Não criado"} · Pedido:{" "}
                      {e.operation_id ?? "—"}
                    </p>
                    {Array.isArray(e.errors) && e.errors.length > 0 && (
                      <pre className="whitespace-pre-wrap">{JSON.stringify(e.errors, null, 2)}</pre>
                    )}
                  </li>
                ))}
              </ul>
              {!events.data.length && <p>Sem pedidos registados para credenciais reconhecidas.</p>}
              <Button
                variant="outline"
                disabled={!historyPage}
                onClick={() => setHistoryPage(historyPage - 1)}
              >
                Histórico anterior
              </Button>{" "}
              <Button
                variant="outline"
                disabled={events.data.length <= 25}
                onClick={() => setHistoryPage(historyPage + 1)}
              >
                Mais histórico
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            onClick={() => qc.invalidateQueries({ queryKey: integrationKey(tenant.id) })}
          >
            Atualizar integrações
          </Button>
          <details>
            <summary>Como utilizar a API</summary>
            <p>
              Após instalar a função Supabase <code>ingest-v1</code>, envie POST para{" "}
              <code>/functions/v1/ingest-v1/observations</code> no domínio do seu projeto Supabase,
              com Authorization: Bearer SEGREDO e Idempotency-Key: UUID.
            </p>
            <p>
              JSON: profile_id aprovado, source igual à credencial, coverage (start/end ISO 8601 com
              fuso e declared: true), rows (subject_external_ref, indicator_key, observed_at,
              value_numeric ou value_text, unit, idempotency_key; corrects_observation_id opcional).
              Até 1000 linhas, 2 MB e 30 pedidos/minuto/chave.
            </p>
            <p>
              Os lotes e erros detalhados permanecem na página{" "}
              <Link to="/app/dados" className="underline">
                Dados
              </Link>
              . A documentação completa está em docs/ingestion-api.md no repositório.
            </p>
          </details>
        </div>
      )}
    </Panel>
  );
}
