import { describe, expect, it } from "vitest";
import { csvToRows, decodeUtf8, parseCsv, toCsv, CSV_MAX_ROWS } from "./csv";
import { parseTimestamp, previewErrors, utcFromLocalInput } from "./ingest";

const H = "subject_external_ref,indicator_key,observed_at,value_numeric,value_text,unit,idempotency_key";

describe("parseCsv", () => {
  it("strips BOM, handles CRLF, quotes, escaped quotes, commas and newlines inside quotes", () => {
    const r = parseCsv('\uFEFFa,b\r\n"x, y","he said ""hi""\nline2"\r\n');
    expect(r.ok && r.records.map((x) => x.fields)).toEqual([["a", "b"], ["x, y", 'he said "hi"\nline2']]);
  });
  it("reports the physical line of each record after multi-line fields", () => {
    const r = parseCsv('h\n"a\nb"\nc\n');
    expect(r.ok && r.records.map((x) => x.line)).toEqual([1, 2, 4]);
  });
  it("rejects unterminated quotes and stray quotes", () => {
    expect(parseCsv('a\n"open').ok).toBe(false);
    expect(parseCsv('a\nab"c"').ok).toBe(false);
  });
  it("round-trips through toCsv", () => {
    const rows = [["a", 'q"x', "c,d", "e\nf"]];
    const r = parseCsv(toCsv(rows));
    expect(r.ok && r.records[0]!.fields).toEqual(rows[0]);
  });
});

describe("csvToRows", () => {
  it("rejects unknown/missing columns and wrong column counts", () => {
    expect(csvToRows("foo,bar\n1,2").ok).toBe(false);
    expect(csvToRows("subject_external_ref,unit\n1,2").ok).toBe(false);
    expect(csvToRows(`${H}\na,b`).ok).toBe(false);
  });
  it(`enforces the ${CSV_MAX_ROWS}-row limit`, () => {
    const line = "a,k,2026-01-01T00:00:00Z,1,,%,x";
    expect(csvToRows(`${H}\n${Array(CSV_MAX_ROWS).fill(line).join("\n")}`).ok).toBe(true);
    expect(csvToRows(`${H}\n${Array(CSV_MAX_ROWS + 1).fill(line).join("\n")}`).ok).toBe(false);
  });
  it("rejects invalid UTF-8", () => {
    expect(decodeUtf8(new Uint8Array([0xff, 0xfe, 0x41]).buffer)).toBeNull();
    expect(decodeUtf8(new TextEncoder().encode("ação").buffer as ArrayBuffer)).toBe("ação");
  });
});

describe("preview validation", () => {
  const ctx = {
    subjects: new Set(["a-1"]),
    indicators: new Map([["k", { key: "k", unit: "%", value_type: "numeric" as const }]]),
    coverageStart: new Date("2026-01-01T00:00:00Z"),
    coverageEnd: new Date("2026-03-01T00:00:00Z"),
    now: new Date("2026-10-14T00:00:00Z"),
  };
  const row = (o: Partial<Record<string, string>>, line = 2) => ({
    line, subject_external_ref: "a-1", indicator_key: "k", observed_at: "2026-01-08T00:00:00Z", value_numeric: "80",
    value_text: "", unit: "%", idempotency_key: "i", corrects_observation_id: "", ...o,
  });
  const codes = (o: Partial<Record<string, string>>) => previewErrors([row(o)], ctx)[0]?.errors ?? [];
  it("accepts a valid row", () => expect(codes({})).toEqual([]));
  it("rejects missing value instead of treating it as zero", () => expect(codes({ value_numeric: "" })).toEqual(["missing_value"]));
  it("rejects NaN, Infinity and decimal comma", () => {
    expect(codes({ value_numeric: "NaN" })).toEqual(["invalid_number"]);
    expect(codes({ value_numeric: "Infinity" })).toEqual(["invalid_number"]);
    expect(codes({ value_numeric: "1,5" })).toEqual(["invalid_number"]);
  });
  it("rejects timestamps without timezone, impossible dates, future and out-of-coverage", () => {
    expect(codes({ observed_at: "2026-01-08T00:00:00" })).toEqual(["invalid_timestamp"]);
    expect(codes({ observed_at: "2026-02-30T00:00:00Z" })).toEqual(["invalid_timestamp"]);
    expect(codes({ observed_at: "2027-01-01T00:00:00Z" })).toEqual(["future_timestamp"]);
    expect(codes({ observed_at: "2026-03-01T00:00:00Z" })).toEqual(["outside_coverage"]);
  });
  it("flags unknown subject, unknown indicator, unit mismatch, wrong type, both values", () => {
    expect(codes({ subject_external_ref: "zz" })).toEqual(["unknown_subject"]);
    expect(codes({ indicator_key: "x" })).toEqual(["unknown_indicator"]);
    expect(codes({ unit: "pct" })).toEqual(["unit_mismatch"]);
    expect(codes({ value_numeric: "", value_text: "t" })).toEqual(["type_mismatch"]);
    expect(codes({ value_text: "t" })).toEqual(["both_values"]);
  });
  it("same key twice with different content conflicts; identical repeat does not", () => {
    expect(previewErrors([row({}), row({ value_numeric: "81" }, 3)], ctx)).toEqual([{ line: 3, errors: ["idempotency_conflict"] }]);
    expect(previewErrors([row({}), row({ value_numeric: "80.0" }, 3)], ctx)).toEqual([]);
  });
  it("interprets coverage inputs as UTC and parses offsets", () => {
    expect(utcFromLocalInput("2026-01-01T00:00")?.toISOString()).toBe("2026-01-01T00:00:00.000Z");
    expect(parseTimestamp("2026-01-08T12:00:00+01:00")?.toISOString()).toBe("2026-01-08T11:00:00.000Z");
  });
});
