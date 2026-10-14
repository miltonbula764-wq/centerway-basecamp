import type { CsvRow } from "./csv";

/** Error codes returned by public.import_observations (server is authoritative; the preview mirrors it). */
export const errorLabel: Record<string, string> = {
  invalid_row: "Linha inválida.",
  missing_subject: "Falta subject_external_ref.",
  unknown_subject: "Cliente não encontrado nesta empresa (referência externa exata).",
  missing_indicator: "Falta indicator_key.",
  unknown_indicator: "Indicador não existe no perfil aprovado.",
  unit_mismatch: "Unidade diferente da definida no indicador.",
  missing_unit: "Falta a unidade.",
  both_values: "Preencha só value_numeric ou só value_text, não os dois.",
  missing_value: "Sem valor: preencha value_numeric ou value_text (vazio não é zero).",
  invalid_number: "Número inválido (use ponto decimal; NaN/Infinity não são aceites).",
  type_mismatch: "Tipo de valor errado para este indicador.",
  text_too_long: "Texto com mais de 2000 caracteres.",
  missing_timestamp: "Falta observed_at.",
  invalid_timestamp: "Data inválida: use ISO 8601 com fuso, ex. 2026-01-08T00:00:00Z.",
  future_timestamp: "Data no futuro.",
  outside_coverage: "Data fora do intervalo de cobertura declarado.",
  invalid_idempotency_key: "idempotency_key vazia ou com mais de 300 caracteres.",
  invalid_correction_ref: "corrects_observation_id não é um identificador válido.",
  correction_target_not_found: "Observação a corrigir não encontrada para este cliente, indicador e unidade.",
  idempotency_conflict: "Esta idempotency_key já foi usada com conteúdo diferente.",
};
export const labelFor = (code: string) => errorLabel[code] ?? code;

export type IndicatorContract = { key: string; unit: string; value_type: "numeric" | "text" };
export type LineErrors = { line: number; errors: string[] };

const NUM_RE = /^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]{1,3})?$/;
const TS_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(:(\d{2})(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Strict ISO 8601 with explicit offset; rejects impossible dates such as 2026-02-30. */
export function parseTimestamp(raw: string): Date | null {
  const m = TS_RE.exec(raw);
  if (!m) return null;
  const [, y, mo, d, h, mi, , s] = m;
  const yy = +y!, mm = +mo!, dd = +d!, hh = +h!, mn = +mi!, ss = s ? +s : 0;
  if (mm < 1 || mm > 12 || hh > 23 || mn > 59 || ss > 59) return null;
  const dim = new Date(Date.UTC(yy, mm, 0)).getUTCDate();
  if (dd < 1 || dd > dim) return null;
  const t = new Date(raw);
  return Number.isNaN(t.getTime()) ? null : t;
}

/** Preview only. The server revalidates everything on commit. */
export function previewErrors(
  rows: CsvRow[],
  ctx: { subjects: Set<string>; indicators: Map<string, IndicatorContract>; coverageStart: Date; coverageEnd: Date; now: Date },
): LineErrors[] {
  const out: LineErrors[] = [];
  const seen = new Map<string, string>();
  for (const r of rows) {
    const e: string[] = [];
    const ref = r.subject_external_ref.trim();
    const key = r.indicator_key.trim();
    const unit = r.unit.trim();
    const num = r.value_numeric.trim();
    const txt = r.value_text;
    const ind = key ? ctx.indicators.get(key) : undefined;
    if (!ref) e.push("missing_subject");
    else if (!ctx.subjects.has(ref)) e.push("unknown_subject");
    if (!key) e.push("missing_indicator");
    else if (!ind) e.push("unknown_indicator");
    else if (unit !== ind.unit) e.push("unit_mismatch");
    if (!unit) e.push("missing_unit");
    if (num && txt.trim()) e.push("both_values");
    else if (!num && !txt.trim()) e.push("missing_value");
    else if (num) {
      if (!NUM_RE.test(num)) e.push("invalid_number");
      else if (ind && ind.value_type !== "numeric") e.push("type_mismatch");
    } else {
      if (txt.length > 2000) e.push("text_too_long");
      if (ind && ind.value_type !== "text") e.push("type_mismatch");
    }
    const rawTs = r.observed_at.trim();
    if (!rawTs) e.push("missing_timestamp");
    else {
      const t = parseTimestamp(rawTs);
      if (!t) e.push("invalid_timestamp");
      else if (t > ctx.now) e.push("future_timestamp");
      else if (t < ctx.coverageStart || t >= ctx.coverageEnd) e.push("outside_coverage");
    }
    const idem = r.idempotency_key.trim();
    if (idem.length < 1 || idem.length > 300) e.push("invalid_idempotency_key");
    const corr = r.corrects_observation_id.trim();
    if (corr && !UUID_RE.test(corr)) e.push("invalid_correction_ref");
    if (idem && e.length === 0) {
      const sig = [ref, key, num ? String(Number(num)) : "", num ? "" : txt, unit, parseTimestamp(rawTs)?.toISOString(), corr].join("\u0000");
      const prev = seen.get(idem);
      if (prev !== undefined && prev !== sig) e.push("idempotency_conflict");
      else seen.set(idem, sig);
    }
    if (e.length) out.push({ line: r.line, errors: e });
  }
  return out;
}

/** Interprets a <input type="datetime-local"> value as UTC (never the browser's local zone). */
export function utcFromLocalInput(v: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v)) return null;
  const d = new Date(`${v}:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export const TEMPLATE_ROWS: string[][] = [
  ["subject_external_ref", "indicator_key", "observed_at", "value_numeric", "value_text", "unit", "idempotency_key", "corrects_observation_id"],
  ["EXEMPLO-SINTETICO-001", "exemplo_indicador", "2026-01-08T00:00:00Z", "80", "", "%", "exemplo-001-2026-01-08", ""],
  ["EXEMPLO-SINTETICO-001", "exemplo_nota", "2026-01-08T00:00:00Z", "", "texto de exemplo", "texto", "exemplo-001-nota-2026-01-08", ""],
];
