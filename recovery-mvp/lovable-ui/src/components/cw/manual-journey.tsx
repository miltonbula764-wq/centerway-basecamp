import { useState } from "react";
import { useRouter } from "@tanstack/react-router";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useLiveSession } from "./live-session";
import { L01Error } from "@/data/transport";
import {
  ACTIONS,
  ARGUMENTS,
  dataFields,
  parseFields,
  validateRequest,
  type Field,
} from "@/data/manual-contract";
import type { ClientJourney, ManualContext } from "@/domain/f06";
import type { OperationName, OperationReceipt, OperationRequest } from "@/domain/l01";
import type { LiveRuntime } from "@/data/live-runtime";
type OperationDraft = Awaited<ReturnType<LiveRuntime["prepare"]>>;
const control = "min-h-11 w-full min-w-0 rounded-md border bg-surface px-3 py-2 text-sm";
const button = "min-h-11 rounded-md border px-3 py-2 text-sm disabled:opacity-40";
const print = (value: unknown) => JSON.stringify(value, null, 2);
const objects = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.filter((x) => x && typeof x === "object") : [];
type Row = Record<string, unknown>;
type Option = { value: string; label: string };
function Raw({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="min-w-0 rounded border p-2">
      <summary className="cursor-pointer text-sm">{title}</summary>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
        {print(value)}
      </pre>
    </details>
  );
}
export function ManualJourney({ client }: { client: string }) {
  const { state } = useLiveSession();
  return (
    <ManualEditor
      key={`${state.auth.session?.principal}|${state.auth.tenant}|${client}`}
      client={client}
    />
  );
}
function ManualEditor({ client }: { client: string }) {
  const { runtime, state } = useLiveSession();
  const router = useRouter();
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ journey: ClientJourney; context: ManualContext } | null>(
    null,
  );
  const [op, setOp] = useState<OperationName>("detect"),
    [kind, setKind] = useState("source");
  const [args, setArgs] = useState<Record<string, string>>({}),
    [data, setData] = useState<Record<string, string>>({}),
    [revisions, setRevisions] = useState<number[]>([]);
  const [draft, setDraft] = useState<OperationDraft | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [uncertain, setUncertain] = useState(false),
    [receipt, setReceipt] = useState<OperationReceipt | null>(null);
  const j = loaded?.journey,
    c = loaded?.context;
  const allowed =
    state.auth.status === "authenticated" &&
    runtime.controller.canAttempt(op) &&
    (op !== "discover_company" || state.auth.companyTenants.includes(state.auth.tenant!));
  const bound =
    draft &&
    draft.principal === state.auth.session?.principal &&
    draft.tenant === state.auth.tenant &&
    draft.client === runtime.controller.state.client &&
    draft.client === client;
  const frozen = !!draft || !!receipt || busy;
  const update = (key: string, value: string) => setArgs((old) => ({ ...old, [key]: value }));
  const datum = (key: string, value: string) => setData((old) => ({ ...old, [key]: value }));
  async function read() {
    setBusy(true);
    setError(null);
    try {
      setLoaded(await runtime.loadManual(client));
    } catch (e) {
      setLoaded(null);
      setError(
        e instanceof L01Error
          ? `${e.code} (${e.status ?? "rede"})`
          : "Não foi possível consultar o contexto autorizado",
      );
    } finally {
      setBusy(false);
    }
  }
  function reset(operation: OperationName = op, nextKind = kind) {
    setOp(operation);
    setKind(nextKind);
    setArgs({ id: crypto.randomUUID(), expected_revision: "0" });
    setData({});
    setRevisions([]);
    setDraft(null);
    setReceipt(null);
    setConfirmed(false);
    setUncertain(false);
    setError(null);
  }
  function select(label: string, value: string, items: Option[], change: (value: string) => void) {
    return (
      <label className="flex min-w-0 flex-col gap-1 text-sm">
        {label}
        <select
          aria-label={label}
          className={control}
          value={value}
          onChange={(e) => change(e.target.value)}
          disabled={frozen}
        >
          <option value="">Selecionar…</option>
          {items.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function existing(): Row[] {
    return (
      ((op === "append_value"
        ? kind === "source"
          ? j?.sources
          : kind === "contract"
            ? j?.contracts
            : j?.evidence_history
        : kind === "factor"
          ? c?.factors
          : kind === "evidence"
            ? c?.evidence
            : c?.verifications
      )?.filter(
        (r) =>
          op === "append_value" ||
          ("investigation_id" in r && r["investigation_id"] === args["investigation_id"]),
      ) as unknown as Row[]) ?? []
    );
  }
  function refs(type: Field["type"]): Row[] {
    return type === "source"
      ? ((j?.sources as unknown as Row[]) ?? [])
      : (type === "factor" ? (c?.factors ?? []) : (c?.evidence ?? [])).filter(
          (r) => r["investigation_id"] === args["investigation_id"],
        );
  }
  const refOptions = (list: Row[]): Option[] =>
    list.map((r) => ({
      value: `${r["id"]}|${r["revision"]}`,
      label: `${r["name"] ?? r["id"]} · r${r["revision"]}`,
    }));
  function fieldView(
    field: Field,
    values: Record<string, string>,
    change: (key: string, value: string) => void,
  ) {
    const raw = values[field.key] ?? "";
    if (["source", "factor", "evidence"].includes(field.type ?? ""))
      return (
        <div key={field.key}>
          {select(field.label, raw, refOptions(refs(field.type)), (v) => change(field.key, v))}
        </div>
      );
    if (field.choices || field.type === "boolean")
      return (
        <div key={field.key}>
          {select(
            field.label,
            raw,
            (field.choices ?? ["true", "false", ...(field.nullable ? ["null"] : [])]).map((v) => ({
              value: v,
              label: v,
            })),
            (v) => change(field.key, v),
          )}
        </div>
      );
    return (
      <div key={field.key} className="min-w-0">
        <label className="flex flex-col gap-1 text-sm">
          {field.label}
          <input
            aria-label={field.label}
            className={control}
            value={raw}
            disabled={frozen}
            type={field.type === "number" ? "number" : "text"}
            step="any"
            maxLength={2000}
            placeholder={field.type === "instant" ? "AAAA-MM-DDTHH:mm:ssZ" : undefined}
            onChange={(e) => change(field.key, e.target.value)}
          />
        </label>
        {field.type === "instant" && (
          <button
            type="button"
            className="min-h-9 text-xs underline"
            disabled={frozen}
            onClick={() => change(field.key, new Date().toISOString())}
          >
            Usar instante atual — {field.label}
          </button>
        )}
        {field.type === "hash" && (
          <label className="mt-1 block text-xs">
            Calcular SHA-256 de ficheiro local (não enviado)
            <input
              type="file"
              className="block max-w-full text-xs"
              disabled={frozen}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                if (file.size > 1048576) {
                  setError("Documento local limitado a 1 MiB");
                  return;
                }
                const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
                change(
                  field.key,
                  Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, "0")).join(""),
                );
              }}
            />
          </label>
        )}
      </div>
    );
  }
  const inv = j?.investigations.find((i) => i.id === args["investigation_id"]);
  const detection = j?.detections.find((d) => d.id === args["detection_id"]);
  const contractId =
    op === "detect"
      ? args["contract_id"]
      : j?.investigations.find(
          (i) => i.id === j.decisions.find((d) => d.id === args["decision_id"])?.investigation_id,
        )?.contract_id;
  const contracts = j?.contracts.filter((v) => v.id === contractId) ?? [];
  function argumentOptions(key: string): Option[] | null {
    if (key === "kind") return [];
    if (key === "contract_id")
      return [...new Set(j?.contracts.map((v) => v.id))].map((id) => ({ value: id, label: id }));
    if (key === "detection_id")
      return j?.detections.map((d) => ({ value: d.id, label: `${d.id} · ${d.state}` })) ?? [];
    if (key === "contract_revision")
      return objects((detection?.result as Row)?.["periods"]).map((p) => ({
        value: String(p["contract_revision"]),
        label: `r${p["contract_revision"]} · ${p["state"]}`,
      }));
    if (key === "investigation_id")
      return (
        j?.investigations.map((i) => ({
          value: i.id,
          label: `${i.id} · contrato r${i.contract_revision} · ${i.result?.status ?? "sem relatório"}`,
        })) ?? []
      );
    if (key === "report_id")
      return inv?.report_id
        ? [{ value: inv.report_id, label: `${inv.report_id} · ${inv.result?.status}` }]
        : [];
    if (key === "decision_id")
      return (
        j?.decisions.map((d) => ({
          value: d.id,
          label: `${d.id} · ${d.status} · ${d.recorded_at}`,
        })) ?? []
      );
    if (key === "execution_id")
      return (
        j?.executions
          .filter((e) => !e.undo_of)
          .map((e) => ({ value: e.id, label: `${e.id} · ${e.actor}` })) ?? []
      );
    if (key === "plan_id")
      return (
        j?.recovery_plans.map((p) => ({
          value: p["id"],
          label: `${p["id"]} · r${p["pre_revision"]} → r${p["post_revision"]}`,
        })) ?? []
      );
    if (key === "pre_revision" || key === "post_revision")
      return contracts.map((v) => ({
        value: String(v.revision),
        label: `r${v.revision} · ${v.period_start} → ${v.period_end}`,
      }));
    return null;
  }
  function argumentChange(key: string, value: string) {
    setArgs((old) => ({
      ...old,
      [key]: value,
      ...(key === "detection_id"
        ? { contract_revision: "" }
        : key === "investigation_id"
          ? { report_id: "" }
          : key === "decision_id"
            ? { pre_revision: "", post_revision: "" }
            : {}),
    }));
    if (key === "contract_id") setRevisions([]);
    if (key === "investigation_id") setData({});
  }
  function copyRecord(value: string) {
    const [id, rev] = value.split("|");
    const record = existing().find((r) => r["id"] === id && String(r["revision"]) === rev);
    if (!record) return;
    const values: Record<string, string> = {};
    for (const field of dataFields(op, kind))
      values[field.key] = ["source", "factor", "evidence"].includes(field.type ?? "")
        ? `${record[field.key]}|${record[field.key.replace(/_id$/, "_revision")]}`
        : record[field.key] == null
          ? ""
          : String(record[field.key]);
    setData(values);
    setArgs((old) => ({
      ...old,
      id: String(record["id"]),
      expected_revision: String(
        Math.max(
          ...existing()
            .filter((r) => r["id"] === record["id"])
            .map((r) => Number(r["revision"])),
        ),
      ),
    }));
  }
  async function preview() {
    setError(null);
    setBusy(true);
    try {
      const parsed = parseFields(ARGUMENTS[op], { ...args, kind });
      if (op === "append_value" || op === "append_investigation")
        parsed["data"] = parseFields(dataFields(op, kind), data);
      if (op === "detect") {
        parsed["revisions"] = [...revisions].sort((a, b) => a - b);
        if (
          contracts
            .filter((c) => revisions.includes(c.revision))
            .some((c) => Date.parse(c.period_end) > Date.parse(String(parsed["as_of"])))
        )
          throw new Error("A janela selecionada ainda não terminou no corte indicado");
      }
      const request = validateRequest({
        request_id: crypto.randomUUID(),
        operation: op,
        arguments: parsed,
      } as unknown as OperationRequest);
      setDraft(await runtime.prepare(client, request));
      setConfirmed(false);
    } catch (e) {
      setError(
        e instanceof L01Error
          ? `${e.code} (${e.status ?? "rede"})`
          : e instanceof Error
            ? e.message
            : "Pedido inválido",
      );
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    if (!draft || !bound || !confirmed || busy || !allowed) return;
    setBusy(true);
    setError(null);
    setUncertain(false);
    try {
      setReceipt(await runtime.submit(draft.request.request_id));
      setDraft(null);
    } catch (e) {
      if (e instanceof L01Error) {
        setError(`${e.code} (${e.status ?? "rede"})`);
        setUncertain(e.kind === "network" || e.status === 503);
        if (e.receipt) {
          setReceipt(e.receipt);
          setDraft(null);
        }
      } else {
        setError("Resposta desconhecida; consulte os recibos antes de novo pedido");
        setUncertain(true);
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className={button}
        onClick={() => {
          setOpen(true);
          void read();
        }}
      >
        Operar jornada F01–F06
      </button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (busy) return;
          setOpen(value);
          if (!value && receipt)
            void runtime
              .refresh()
              .then(() => router.invalidate())
              .catch(() => {});
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl">
          <DialogTitle>Operação manual do cliente</DialogTitle>
          <DialogDescription>
            Dados sintéticos. Empresa e cliente vêm da sessão autorizada. Nenhum passo é executado
            automaticamente; utilização não é valor de negócio e recuperação observada não prova
            causalidade.
          </DialogDescription>
          <p className="break-all text-xs">
            Empresa {state.auth.tenant} · Cliente {client} · {state.auth.session?.principal}
          </p>
          <button className={button} disabled={busy || !!draft} onClick={() => void read()}>
            Atualizar jornada por GET
          </button>
          {busy && <p role="status">A aguardar resposta…</p>}
          {error && (
            <p role="alert" className="break-words text-sm text-destructive">
              {error}
            </p>
          )}
          {loaded && (
            <>
              {select("Ação manual", op, ACTIONS, (v) =>
                reset(v as OperationName, v === "append_investigation" ? "factor" : "source"),
              )}
              {!allowed && (
                <p role="note">
                  Sem permissão para esta ação na sessão. O servidor revalida sempre.
                </p>
              )}
              {op === "discover_company" && (
                <p role="note">
                  A descoberta abrange a empresa INTEIRA, não apenas este cliente. Exige escopo de
                  empresa. Não cria verificações humanas.
                </p>
              )}
              {(op === "append_value" || op === "append_investigation") && (
                <>
                  {select(
                    "Tipo de registo",
                    kind,
                    (op === "append_value"
                      ? ["source", "contract", "evidence"]
                      : ["factor", "evidence", "verification"]
                    ).map((v) => ({ value: v, label: v })),
                    (v) => {
                      setKind(v);
                      setData({});
                      setArgs((old) => ({
                        ...old,
                        id: crypto.randomUUID(),
                        expected_revision: "0",
                      }));
                    },
                  )}
                  {select(
                    "Copiar registo para nova revisão",
                    "",
                    refOptions(existing()),
                    copyRecord,
                  )}
                  <p className="text-xs">
                    Correções acrescentam versões. verified é declaração do produtor, não prova
                    independente. Revisão exige identidade distinta do autor da evidência.
                  </p>
                </>
              )}
              <div className="grid min-w-0 gap-3 sm:grid-cols-2">
                {ARGUMENTS[op]
                  .filter((f) => f.key !== "kind")
                  .map((field) => {
                    const opts = argumentOptions(field.key);
                    return opts ? (
                      <div key={field.key}>
                        {select(field.label, args[field.key] ?? "", opts, (v) =>
                          argumentChange(field.key, v),
                        )}
                      </div>
                    ) : (
                      fieldView(field, args, update)
                    );
                  })}
              </div>
              {op === "detect" && (
                <>
                  <fieldset className="min-w-0 rounded border p-2">
                    <legend>Revisões para deteção (seleção explícita)</legend>
                    {contracts.map((v) => {
                      const ev = j!.evidence_history.filter(
                        (e) => e.contract_id === v.id && e.contract_revision === v.revision,
                      );
                      return (
                        <label
                          key={v.revision}
                          className="flex min-h-11 items-start gap-2 break-all text-xs"
                        >
                          <input
                            type="checkbox"
                            aria-label={`Selecionar revisão ${v.revision}`}
                            disabled={frozen}
                            checked={revisions.includes(v.revision)}
                            onChange={(e) =>
                              setRevisions((old) =>
                                e.target.checked
                                  ? [...old, v.revision]
                                  : old.filter((r) => r !== v.revision),
                              )
                            }
                          />
                          <span>
                            r{v.revision} · {v.period_start} → {v.period_end} ·{" "}
                            {ev.length
                              ? ev
                                  .map((e) => `${e.quality}: ${e.observed_value} ${e.unit}`)
                                  .join("; ")
                              : "sem evidência"}
                          </span>
                        </label>
                      );
                    })}
                  </fieldset>
                  <p className="text-xs">
                    Dados parciais/contraditórios permanecem selecionáveis e identificados. A
                    interface não os corrige; o motor decide suficiência e estado.
                  </p>
                </>
              )}
              {op === "append_value" &&
                kind === "evidence" &&
                select(
                  "Usar medição de contrato/versão",
                  "",
                  (j?.contracts ?? []).map((v) => ({
                    value: `${v.id}|${v.revision}`,
                    label: `${v.id} · r${v.revision} · ${v.period_start} → ${v.period_end}`,
                  })),
                  (v) => {
                    const [id, rev] = v.split("|");
                    const contract = j!.contracts.find(
                      (c) => c.id === id && String(c.revision) === rev,
                    );
                    if (contract)
                      setData((old) => ({
                        ...old,
                        contract_id: contract.id,
                        contract_revision: String(contract.revision),
                        source_id: `${contract.source_id}|${contract.source_revision}`,
                        unit: contract.unit,
                        measurement_method: contract.measurement_method,
                        period_start: contract.period_start,
                        period_end: contract.period_end,
                      }));
                  },
                )}
              {(op === "append_value" || op === "append_investigation") && (
                <div className="grid min-w-0 gap-3 sm:grid-cols-2">
                  {dataFields(op, kind).map((field) => fieldView(field, data, datum))}
                </div>
              )}
              {op === "intervene" && (
                <>
                  <p role="note">
                    Apenas flag sintética reversível. Permissão HTTP não concede política.
                    Incerteza, falta de autorização ou relatório desatualizado bloqueiam o motor;
                    nenhum efeito externo é permitido.
                  </p>
                  <Raw
                    title="Catálogo, recursos e autorizações deste principal"
                    value={{
                      catalog: c!.catalog,
                      policies: c!.policies,
                      revocations: c!.revocations,
                      resources: c!.resources,
                    }}
                  />
                </>
              )}
              {op === "plan_recovery" && (
                <p className="text-xs">
                  Crie revisões F01 explícitas se necessário. O servidor exige janelas comparáveis
                  antes/depois da decisão/execução. Decisão bloqueada não prova execução nem
                  recuperação.
                </p>
              )}
              {!draft && !receipt && (
                <button
                  className={button}
                  disabled={!allowed || busy}
                  onClick={() => void preview()}
                >
                  Pré-visualizar pedido
                </button>
              )}
              {draft && (
                <>
                  <Raw
                    title="Preview imutável do pedido"
                    value={{
                      principal: draft.principal,
                      tenant: draft.tenant,
                      client: draft.client,
                      ...draft.request,
                    }}
                  />
                  <p className="break-all font-mono text-xs">Pedido {draft.request.request_id}</p>
                  <label className="flex min-h-11 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(e) => setConfirmed(e.target.checked)}
                      disabled={busy}
                    />
                    Confirmo este pedido sintético e o âmbito apresentado.
                  </label>
                  <button
                    className={button}
                    disabled={!confirmed || !bound || !allowed || busy || (!!error && !uncertain)}
                    onClick={() => void submit()}
                  >
                    {uncertain ? "Reenviar exatamente o mesmo pedido" : "Confirmar envio manual"}
                  </button>
                  {uncertain && (
                    <p role="note">
                      Resposta incerta. Sem retry automático. Reenvio conserva UUID/conteúdo; não
                      crie outro pedido para repetir a ação. Consulte recibos.
                    </p>
                  )}
                  {!uncertain && (
                    <button
                      className={button}
                      disabled={busy}
                      onClick={() => {
                        setDraft(null);
                        setConfirmed(false);
                        setError(null);
                      }}
                    >
                      Editar antes de novo envio
                    </button>
                  )}
                </>
              )}
              {receipt && (
                <div role="status">
                  <p>
                    Recibo {receipt.status}. Resultado de negócio separado; execução não é
                    recuperação e causalidade não está estabelecida.
                  </p>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
                    {print(receipt)}
                  </pre>
                </div>
              )}
              {receipt && (
                <button
                  className={button}
                  disabled={busy}
                  onClick={() => {
                    reset();
                    void read();
                  }}
                >
                  Novo pedido após consultar recibo
                </button>
              )}
              <Raw
                title="Contrato, revisões, fontes e evidências F01 (API)"
                value={{
                  contracts: j!.contracts,
                  sources: j!.sources,
                  evidence: j!.evidence_history,
                }}
              />
              <Raw
                title="Factos, hipóteses, contradições e lacunas calculados pela F03"
                value={j!.investigations}
              />
              <Raw
                title="Registos F03 introduzidos por operadores (não conclusões)"
                value={{
                  factors: c!.factors,
                  evidence: c!.evidence,
                  verifications: c!.verifications,
                }}
              />
              <Raw
                title="Estados, próximas etapas e recibos F06"
                value={{
                  work_items: j!.work_items,
                  detections: j!.detections,
                  decisions: j!.decisions,
                  recoveries: j!.recovery_plans,
                  operations: j!.operations,
                }}
              />
              <Raw title="Auditoria do cliente (últimos 100 eventos)" value={c!.audit} />
              {Object.values(c!.truncated).some(Boolean) && (
                <p role="note">
                  Há histórico adicional não apresentado. Limite: 100 registos por coleção; não se
                  presume ausência de dados.
                </p>
              )}
              <p className="text-xs">
                Localizadores não são anexos obtidos/verificados. Os documentos CSV/P1/média T01
                ficam fora da API; não há interpretação semântica. Um hash não é revisão
                humana/independente.
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
