/** RFC 4180-style CSV parser: quoted fields, escaped quotes (""), commas and newlines inside quotes, CRLF/LF, UTF-8 BOM. */

export const CSV_MAX_BYTES = 1_000_000; // 1 MB, also enforced server-side on the payload
export const CSV_MAX_ROWS = 1000; // data rows (header excluded), also enforced server-side

export const CSV_COLUMNS = [
  "subject_external_ref",
  "indicator_key",
  "observed_at",
  "value_numeric",
  "value_text",
  "unit",
  "idempotency_key",
  "corrects_observation_id",
] as const;
export type CsvColumn = (typeof CSV_COLUMNS)[number];
export const CSV_REQUIRED: CsvColumn[] = ["subject_external_ref", "indicator_key", "observed_at", "unit", "idempotency_key"];

export type CsvRecord = { line: number; fields: string[] };
export type ParseResult = { ok: true; records: CsvRecord[] } | { ok: false; error: string };

export function parseCsv(input: string): ParseResult {
  let text = input;
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const records: CsvRecord[] = [];
  let field = "";
  let fields: string[] = [];
  let inQuotes = false;
  let line = 1;
  let recordLine = 1;
  let fieldStarted = false;
  let afterQuote = false;

  const endField = () => {
    fields.push(field);
    field = "";
    fieldStarted = false;
    afterQuote = false;
  };
  const endRecord = () => {
    endField();
    if (!(fields.length === 1 && fields[0] === "")) records.push({ line: recordLine, fields });
    fields = [];
  };

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
          afterQuote = true;
        }
      } else {
        if (c === "\n") line++;
        field += c;
      }
      continue;
    }
    if (c === '"') {
      if (fieldStarted || afterQuote) return { ok: false, error: `Linha ${line}: aspas no meio de um campo. Use aspas à volta do campo inteiro.` };
      inQuotes = true;
      fieldStarted = true;
    } else if (c === ",") {
      endField();
    } else if (c === "\r" || c === "\n") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      endRecord();
      line++;
      recordLine = line;
    } else {
      if (afterQuote) return { ok: false, error: `Linha ${line}: texto depois de fechar aspas.` };
      field += c;
      fieldStarted = true;
    }
  }
  if (inQuotes) return { ok: false, error: `Linha ${recordLine}: aspas por fechar.` };
  if (fieldStarted || afterQuote || fields.length > 0) endRecord();
  return { ok: true, records };
}

export type CsvRow = { line: number } & Record<CsvColumn, string>;
export type TableResult = { ok: true; rows: CsvRow[] } | { ok: false; error: string };

/** Validates the header against the contract and maps records to rows. */
export function csvToRows(input: string): TableResult {
  const parsed = parseCsv(input);
  if (!parsed.ok) return parsed;
  const [header, ...data] = parsed.records;
  if (!header) return { ok: false, error: "O ficheiro está vazio." };
  const names = header.fields.map((h) => h.trim());
  const unknown = names.filter((n) => !(CSV_COLUMNS as readonly string[]).includes(n));
  if (unknown.length) return { ok: false, error: `Colunas desconhecidas: ${unknown.join(", ")}.` };
  const dup = names.filter((n, i) => names.indexOf(n) !== i);
  if (dup.length) return { ok: false, error: `Colunas repetidas: ${[...new Set(dup)].join(", ")}.` };
  const missing = CSV_REQUIRED.filter((c) => !names.includes(c));
  if (missing.length) return { ok: false, error: `Faltam colunas obrigatórias: ${missing.join(", ")}.` };
  if (!names.includes("value_numeric") && !names.includes("value_text"))
    return { ok: false, error: "É preciso a coluna value_numeric ou value_text." };
  if (data.length === 0) return { ok: false, error: "O ficheiro não tem linhas de dados." };
  if (data.length > CSV_MAX_ROWS) return { ok: false, error: `Máximo ${CSV_MAX_ROWS} linhas por ficheiro (tem ${data.length}).` };

  const rows: CsvRow[] = [];
  for (const rec of data) {
    if (rec.fields.length !== names.length)
      return { ok: false, error: `Linha ${rec.line}: tem ${rec.fields.length} colunas, o cabeçalho tem ${names.length}.` };
    const row = { line: rec.line } as CsvRow;
    for (const c of CSV_COLUMNS) row[c] = "";
    names.forEach((n, i) => {
      row[n as CsvColumn] = rec.fields[i] ?? "";
    });
    rows.push(row);
  }
  return { ok: true, rows };
}

/** Decodes bytes as strict UTF-8 (invalid sequences are rejected, never silently replaced). */
export function decodeUtf8(bytes: ArrayBuffer): string | null {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

const q = (v: string) => (/[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
export function toCsv(rows: string[][]): string {
  return rows.map((r) => r.map(q).join(",")).join("\r\n") + "\r\n";
}
