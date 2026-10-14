import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Download, FileUp } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant, TENANT_CHANGED, tk, useTenant } from "@/lib/tenant";
import { countQuery, indicatorsQuery, profilesQuery } from "@/lib/queries";
import { CSV_COLUMNS, CSV_MAX_BYTES, CSV_MAX_ROWS, csvToRows, decodeUtf8, toCsv, type CsvRow } from "@/lib/csv";
import { labelFor, previewErrors, TEMPLATE_ROWS, utcFromLocalInput, type IndicatorContract, type LineErrors } from "@/lib/ingest";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Empty, ErrorState, FieldError, FieldHint, formatDate, Loading, Mono, PageHeader, Panel, StatusPill } from "@/components/app/ui-bits";

export const Route = createFileRoute("/_authenticated/app/dados")({
  head: () => ({
    meta: [
      { title: "Dados — CENTERWAY" },
      { name: "description", content: "Importação CSV de observações e histórico de lotes." },
      { property: "og:title", content: "Dados — CENTERWAY" },
      { property: "og:description", content: "Importação CSV de observações e histórico de lotes." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Dados,
});

const batchStatus = { received: "Recebido", processing: "Em processamento", completed: "Concluído", failed: "Recusado" } as const;

function rpcMessage(e: unknown): string {
  const err = (e ?? {}) as { code?: string; message?: string };
  const m = err.message ?? "";
  if (m === TENANT_CHANGED) return m;
  if (m.includes("approved value profile changed")) return "O perfil de valor aprovado mudou desde a pré-visualização. Volte a carregar o ficheiro para validar com o perfil atual.";
  if (m.includes("no approved value profile")) return "A empresa não tem perfil de valor aprovado.";
  if (m.includes("coverage not declared")) return "Confirme a cobertura declarada.";
  if (m.includes("invalid coverage")) return "O fim da cobertura tem de ser posterior ao início.";
  if (m.includes("coverage starts in the future")) return "A cobertura não pode começar no futuro.";
  if (m.includes("too many rows")) return `Máximo ${CSV_MAX_ROWS} linhas.`;
  if (m.includes("payload too large")) return "Ficheiro demasiado grande.";
  if (m.includes("invalid source")) return "Indique a fonte (até 200 caracteres).";
  if (err.code === "42501") return "Não tem permissão para importar nesta empresa.";
  if (err.code === "28000" || err.code === "PGRST301") return "A sessão expirou. Inicie sessão novamente.";
  if (/fetch|network/i.test(m)) return "Sem ligação ao servidor. Nada foi gravado; tente novamente.";
  return "Não foi possível concluir a importação.";
}

type ImportResult = { batch_id: string; status: "completed" | "failed"; row_count: number; inserted: number; duplicates: number; rejected: number; errors: LineErrors[] };

function Dados() {
  const { tenant, canWrite } = useTenant();
  const obs = useQuery(countQuery(tenant.id, "observations"));
  const profiles = useQuery(profilesQuery(tenant.id));
  const approved = profiles.data?.find((p) => p.status === "approved");

  return (
    <>
      <PageHeader
        title="Dados"
        description="C01 · Recolha. Importe observações em CSV; ficam guardadas por cliente na base de dados. O CSV é só o transporte. As observações nunca são alteradas; correções são novos registos."
        actions={<TemplateButton />}
      />
      <div className="space-y-6">
        <ContractPanel />
        {canWrite ? (
          profiles.isLoading ? (
            <Panel title="Nova importação"><Loading /></Panel>
          ) : profiles.isError ? (
            <Panel title="Nova importação"><ErrorState message="Não foi possível carregar o perfil de valor." onRetry={() => profiles.refetch()} /></Panel>
          ) : !approved ? (
            <Panel title="Nova importação">
              <Empty title="Sem perfil de valor aprovado">
                A importação exige um perfil aprovado: as chaves e unidades vêm dele. <Link to="/app/perfil" className="underline underline-offset-2">Abrir perfil de valor</Link>
              </Empty>
            </Panel>
          ) : (
            <ImportPanel profileId={approved.id} profileVersion={approved.version} />
          )
        ) : (
          <Panel title="Nova importação">
            <p className="text-sm text-muted-foreground">O seu papel é Leitor: pode consultar o histórico, mas não importar.</p>
          </Panel>
        )}
        <BatchHistory totalObs={obs.data} />
      </div>
    </>
  );
}

function TemplateButton() {
  const download = () => {
    const blob = new Blob([toCsv(TEMPLATE_ROWS)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "centerway-modelo-SINTETICO.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Button variant="outline" size="sm" onClick={download}>
      <Download className="mr-1.5 h-4 w-4" /> Modelo CSV
    </Button>
  );
}

function ContractPanel() {
  const [open, setOpen] = useState(false);
  return (
    <Panel
      title="Contrato do ficheiro"
      actions={
        <button onClick={() => setOpen((o) => !o)} className="text-xs text-muted-foreground hover:text-foreground">
          {open ? "Esconder" : "Ver colunas"}
        </button>
      }
    >
      <p className="text-sm text-muted-foreground">
        CSV UTF-8 com cabeçalho, separado por vírgulas, até 1 MB e {CSV_MAX_ROWS} linhas. Um ficheiro inválido não grava nada: se uma linha falhar, o lote inteiro é recusado e os erros ficam registados. O modelo descarregável contém apenas um exemplo sintético — não é importado automaticamente.
      </p>
      {open && (
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
          {[
            ["subject_external_ref", "Referência externa exata de um cliente que já existe nesta empresa. Clientes não são criados nem fundidos pela importação."],
            ["indicator_key", "Chave de um indicador do perfil de valor aprovado."],
            ["observed_at", "Momento observado, ISO 8601 com fuso: 2026-01-08T00:00:00Z ou 2026-01-08T01:00:00+01:00. Guardado em UTC."],
            ["value_numeric", "Número com ponto decimal. Use esta coluna OU value_text, nunca as duas. Vazio não é zero."],
            ["value_text", "Texto, só para indicadores de uso/contexto definidos como texto."],
            ["unit", "Tem de ser igual à unidade do indicador."],
            ["idempotency_key", "Identificador único da observação. Reimportar a mesma chave com o mesmo conteúdo não duplica; com conteúdo diferente é conflito."],
            ["corrects_observation_id", "Opcional. Id de uma observação existente do mesmo cliente, indicador e unidade que esta linha corrige."],
          ].map(([k, v]) => (
            <div key={k} className="contents">
              <dt><Mono>{k}</Mono></dt>
              <dd className="text-muted-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </Panel>
  );
}

type Prepared = { fileName: string; rows: CsvRow[]; errors: LineErrors[]; tenantId: string; profileId: string };

function ImportPanel({ profileId, profileVersion }: { profileId: string; profileVersion: number }) {
  const { tenant } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const indicators = useQuery(indicatorsQuery(tenantId, profileId));
  const fileRef = useRef<HTMLInputElement>(null);

  const [source, setSource] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [declared, setDeclared] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const startD = utcFromLocalInput(start);
  const endD = utcFromLocalInput(end);
  const formErrors: Partial<Record<"source" | "start" | "end" | "declared", string>> = {};
  if (source.trim().length < 1 || source.trim().length > 200) formErrors.source = "Indique a fonte (até 200 caracteres).";
  if (!startD) formErrors.start = "Indique o início.";
  if (!endD) formErrors.end = "Indique o fim.";
  if (startD && endD && endD <= startD) formErrors.end = "O fim tem de ser posterior ao início.";
  if (startD && startD > new Date()) formErrors.start = "Não pode começar no futuro.";
  if (!declared) formErrors.declared = "Confirme a cobertura declarada.";
  const formOk = Object.keys(formErrors).length === 0;

  const reset = () => {
    setPrepared(null);
    setFileError(null);
    setResult(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const onFile = async (file: File | undefined) => {
    setPrepared(null);
    setResult(null);
    setFileError(null);
    if (!file) return;
    if (!/\.csv$/i.test(file.name)) return setFileError("Escolha um ficheiro .csv.");
    if (file.size > CSV_MAX_BYTES) return setFileError("O ficheiro tem mais de 1 MB.");
    if (file.size === 0) return setFileError("O ficheiro está vazio.");
    if (!startD || !endD || endD <= startD) return setFileError("Defina primeiro o intervalo de cobertura.");
    setChecking(true);
    try {
      const text = decodeUtf8(await file.arrayBuffer());
      if (text === null) return setFileError("O ficheiro não está em UTF-8 válido.");
      const table = csvToRows(text);
      if (!table.ok) return setFileError(table.error);
      const refs = [...new Set(table.rows.map((r) => r.subject_external_ref.trim()).filter(Boolean))];
      const known = new Set<string>();
      for (let i = 0; i < refs.length; i += 100) {
        const { data, error } = await supabase.from("subjects").select("external_ref").eq("tenant_id", tenantId).in("external_ref", refs.slice(i, i + 100));
        if (error) throw error;
        data?.forEach((s) => known.add(s.external_ref));
      }
      const map = new Map<string, IndicatorContract>();
      (indicators.data ?? []).forEach((i) => map.set(i.key, { key: i.key, unit: i.unit, value_type: i.value_type }));
      const errors = previewErrors(table.rows, { subjects: known, indicators: map, coverageStart: startD, coverageEnd: endD, now: new Date() });
      assertActiveTenant(tenantId);
      setPrepared({ fileName: file.name, rows: table.rows, errors, tenantId, profileId });
    } catch (e) {
      setFileError(rpcMessage(e));
    } finally {
      setChecking(false);
    }
  };

  const commit = useMutation({
    mutationFn: async (p: Prepared) => {
      assertActiveTenant(p.tenantId);
      const rows = p.rows.map((r) => {
        const o: Record<string, string | number> = { line: r.line };
        for (const c of CSV_COLUMNS) o[c] = r[c];
        return o;
      });
      const { data, error } = await supabase.rpc("import_observations", {
        _tenant_id: p.tenantId,
        _expected_profile_id: p.profileId,
        _source: source.trim(),
        _coverage_start: startD!.toISOString(),
        _coverage_end: endD!.toISOString(),
        _coverage_declared: declared,
        _file_name: p.fileName,
        _rows: rows,
      });
      if (error) throw error;
      return data as unknown as ImportResult;
    },
    onSuccess: (res) => {
      setResult(res);
      setPrepared(null);
      if (fileRef.current) fileRef.current.value = "";
      qc.invalidateQueries({ queryKey: ["t", tenantId] });
    },
  });

  const subjectsTouched = prepared ? new Set(prepared.rows.map((r) => r.subject_external_ref.trim())).size : 0;

  return (
    <Panel title={`Nova importação · perfil v${profileVersion}`}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <Label htmlFor="src">Fonte</Label>
          <Input id="src" value={source} onChange={(e) => setSource(e.target.value)} placeholder="ex.: exportação do sistema de faturação" className="mt-1.5" maxLength={200} />
          <FieldHint>De onde vêm estes dados. Fica registado em cada observação.</FieldHint>
          {source && <FieldError>{formErrors.source}</FieldError>}
        </div>
        <div>
          <Label htmlFor="cs">Cobertura — início (UTC)</Label>
          <Input id="cs" type="datetime-local" value={start} onChange={(e) => { setStart(e.target.value); reset(); }} className="mt-1.5" />
          {start && <FieldError>{formErrors.start}</FieldError>}
        </div>
        <div>
          <Label htmlFor="ce">Cobertura — fim (UTC, exclusivo)</Label>
          <Input id="ce" type="datetime-local" value={end} onChange={(e) => { setEnd(e.target.value); reset(); }} className="mt-1.5" />
          {end && <FieldError>{formErrors.end}</FieldError>}
        </div>
        <div className="md:col-span-2 flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3">
          <Checkbox id="decl" checked={declared} onCheckedChange={(v) => setDeclared(v === true)} className="mt-0.5" />
          <Label htmlFor="decl" className="text-sm font-normal leading-snug text-muted-foreground">
            Declaro que este ficheiro pretende cobrir o intervalo acima. Entendo que é uma declaração, não prova de que os dados estão completos, e que linhas ausentes não significam zero nem falta de atividade.
          </Label>
        </div>
        <div className="md:col-span-2">
          <Label htmlFor="file">Ficheiro CSV</Label>
          <Input id="file" ref={fileRef} type="file" accept=".csv,text/csv" disabled={checking || indicators.isLoading} onChange={(e) => onFile(e.target.files?.[0])} className="mt-1.5" />
          <FieldHint>UTF-8, até 1 MB e {CSV_MAX_ROWS} linhas. A validação aqui é uma pré-visualização; o servidor volta a validar tudo ao confirmar.</FieldHint>
          <FieldError>{fileError}</FieldError>
        </div>
      </div>

      {checking && <Loading label="A validar ficheiro…" />}

      {prepared && (
        <div className="mt-6 space-y-4 border-t border-border pt-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <FileUp className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{prepared.fileName}</span>
            <span className="text-muted-foreground">· {prepared.rows.length} linhas · {subjectsTouched} clientes</span>
            {prepared.errors.length === 0 ? (
              <StatusPill tone="success">Sem erros na pré-visualização</StatusPill>
            ) : (
              <StatusPill tone="neutral">{prepared.errors.length} linhas com erros</StatusPill>
            )}
          </div>
          {prepared.errors.length > 0 && <ErrorList errors={prepared.errors} />}
          <PreviewTable rows={prepared.rows} errors={prepared.errors} />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => commit.mutate(prepared)}
              disabled={!formOk || prepared.errors.length > 0 || commit.isPending}
            >
              {commit.isPending ? "A importar…" : `Confirmar importação de ${prepared.rows.length} linhas`}
            </Button>
            <Button variant="ghost" onClick={reset} disabled={commit.isPending}>Cancelar</Button>
            {!formOk && <span className="text-xs text-muted-foreground">{Object.values(formErrors)[0]}</span>}
            {prepared.errors.length > 0 && <span className="text-xs text-muted-foreground">Corrija o ficheiro: com erros nada é importado.</span>}
          </div>
          {commit.isError && <ErrorState message={rpcMessage(commit.error)} />}
        </div>
      )}

      {result && (
        <div className="mt-6 border-t border-border pt-4" role="status">
          {result.status === "completed" ? (
            <p className="text-sm">
              <StatusPill tone="success">Lote concluído</StatusPill>{" "}
              <span className="ml-1">{result.inserted} novas observações · {result.duplicates} repetidas sem alteração (já existiam) · 0 recusadas.</span>
            </p>
          ) : (
            <div className="space-y-2">
              <p className="text-sm"><StatusPill tone="neutral">Lote recusado</StatusPill> <span className="ml-1">Nenhuma observação foi gravada. {result.rejected} linhas com erros.</span></p>
              <ErrorList errors={result.errors} />
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function ErrorList({ errors }: { errors: LineErrors[] }) {
  const shown = errors.slice(0, 50);
  return (
    <div className="max-h-64 overflow-y-auto rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
      <ul className="space-y-1">
        {shown.map((e) => (
          <li key={e.line}>
            <Mono className="text-destructive">linha {e.line}</Mono>{" "}
            <span className="text-muted-foreground">{e.errors.map(labelFor).join(" ")}</span>
          </li>
        ))}
      </ul>
      {errors.length > shown.length && <p className="mt-2 text-xs text-muted-foreground">+ {errors.length - shown.length} linhas com erros.</p>}
    </div>
  );
}

function PreviewTable({ rows, errors }: { rows: CsvRow[]; errors: LineErrors[] }) {
  const bad = useMemo(() => new Set(errors.map((e) => e.line)), [errors]);
  const shown = rows.slice(0, 20);
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-xs">
        <thead className="bg-muted/40 text-left text-muted-foreground">
          <tr>
            {["Linha", "Cliente", "Indicador", "Observado", "Valor", "Unidade", "Chave"].map((h) => (
              <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {shown.map((r) => (
            <tr key={r.line} className={bad.has(r.line) ? "bg-destructive/5" : undefined}>
              <td className="px-3 py-1.5 font-mono">{r.line}</td>
              <td className="px-3 py-1.5">{r.subject_external_ref}</td>
              <td className="px-3 py-1.5 font-mono">{r.indicator_key}</td>
              <td className="whitespace-nowrap px-3 py-1.5 font-mono">{r.observed_at}</td>
              <td className="max-w-48 truncate px-3 py-1.5">{r.value_numeric || r.value_text || <span className="text-muted-foreground">vazio</span>}</td>
              <td className="px-3 py-1.5">{r.unit}</td>
              <td className="max-w-40 truncate px-3 py-1.5 font-mono">{r.idempotency_key}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > shown.length && <p className="px-3 py-2 text-xs text-muted-foreground">A mostrar 20 de {rows.length} linhas.</p>}
    </div>
  );
}

function BatchHistory({ totalObs }: { totalObs: number | undefined }) {
  const { tenant } = useTenant();
  const [open, setOpen] = useState<string | null>(null);
  const batches = useQuery({
    queryKey: tk(tenant.id, "batches"),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("ingestion_batches")
        .select("id, source, status, coverage_start, coverage_end, coverage_declared, file_name, row_count, inserted_count, duplicate_count, rejected_count, errors, profile_version, created_at, committed_at")
        .eq("tenant_id", tenant.id)
        .order("created_at", { ascending: false })
        .limit(50);
      if (error) throw error;
      return data ?? [];
    },
  });

  return (
    <Panel title={`Histórico de lotes${totalObs !== undefined ? ` · ${totalObs} observações guardadas` : ""}`}>
      {batches.isLoading ? (
        <Loading />
      ) : batches.isError ? (
        <ErrorState message="Não foi possível carregar os lotes." onRetry={() => batches.refetch()} />
      ) : batches.data!.length === 0 ? (
        <Empty title="Sem lotes">Ainda não foi importado nenhum ficheiro nesta empresa.</Empty>
      ) : (
        <ul className="divide-y divide-border text-sm">
          {batches.data!.map((b) => {
            const isOpen = open === b.id;
            const errs = (Array.isArray(b.errors) ? b.errors : []) as unknown as LineErrors[];
            return (
              <li key={b.id} className="py-2">
                <button className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 text-left" onClick={() => setOpen(isOpen ? null : b.id)} aria-expanded={isOpen}>
                  {isOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                  <span className="font-medium">{b.source}</span>
                  <StatusPill tone={b.status === "completed" ? "success" : b.status === "failed" ? "neutral" : "muted"}>{batchStatus[b.status]}</StatusPill>
                  <span className="text-xs text-muted-foreground">
                    {b.inserted_count} novas · {b.duplicate_count} repetidas · {b.rejected_count} com erro
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground">{formatDate(b.created_at)}</span>
                </button>
                {isOpen && (
                  <div className="mt-3 space-y-3 pl-6">
                    <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[max-content_1fr]">
                      <dt className="text-muted-foreground">Ficheiro</dt><dd>{b.file_name ?? "—"}</dd>
                      <dt className="text-muted-foreground">Linhas</dt><dd>{b.row_count}</dd>
                      <dt className="text-muted-foreground">Cobertura declarada (UTC)</dt>
                      <dd><Mono>{b.coverage_start ?? "—"}</Mono> → <Mono>{b.coverage_end ?? "—"}</Mono> {b.coverage_declared ? "· declarada, não prova de completude" : ""}</dd>
                      <dt className="text-muted-foreground">Perfil de valor</dt><dd>{b.profile_version ? `v${b.profile_version}` : "—"}</dd>
                      <dt className="text-muted-foreground">Gravado</dt><dd>{b.committed_at ? formatDate(b.committed_at) : "Nada gravado"}</dd>
                      <dt className="text-muted-foreground">Id do lote</dt><dd><Mono>{b.id}</Mono></dd>
                    </dl>
                    {errs.length > 0 && <ErrorList errors={errs} />}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
