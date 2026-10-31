import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import {
  ACTIONS,
  ARGUMENTS,
  EVIDENCE,
  VERIFICATION,
  parseFields,
  fieldValue,
  f,
  validateRequest,
} from "@/data/manual-contract";
import { localApiOrigin } from "@/data/live-runtime";
const id = "a1000000-0000-0000-0000-000000000001";
describe("manual inputs mirror actual contracts without business decisions", () => {
  it("uses only the ten actual OpenAPI operations and exact outer argument keys", () => {
    const schema = JSON.parse(readFileSync(__dirname + "/../../../api/openapi.json", "utf8"));
    for (const op of ACTIONS) {
      const contract = schema.components.schemas.Operation.oneOf.find(
        (s: any) => s.properties.operation.const === op.value,
      );
      expect(contract).toBeDefined();
      expect(
        [
          ...ARGUMENTS[op.value].map((f) => f.key),
          ...(["append_value", "append_investigation"].includes(op.value)
            ? ["data"]
            : op.value === "detect"
              ? ["revisions"]
              : []),
        ].sort(),
      ).toEqual(contract.properties.arguments.required.toSorted());
    }
  });
  it("preserves explicit zero, false and unverifiable null; never fills absent measurements", () => {
    expect(fieldValue(f("value", "Value", "number"), "0")).toBe(0);
    expect(fieldValue(f("assertion", "Assertion", "boolean"), "false")).toBe(false);
    expect(fieldValue(f("checked", "Checked", "boolean", undefined, true), "null")).toBeNull();
    expect(() => fieldValue(f("value", "Value", "number"), "")).toThrow("obrigatório");
    expect(() => fieldValue(f("value", "Value", "number"), "NaN")).toThrow();
  });
  it("requires explicit time zone and source version", () => {
    expect(() => fieldValue(f("time", "Time", "instant"), "2026-10-31T12:00:00")).toThrow("fuso");
    expect(parseFields([f("source_id", "Source", "source")], { source_id: id + "|3" })).toEqual({
      source_id: id,
      source_revision: 3,
    });
    expect(() => parseFields([f("source_id", "Source", "source")], { source_id: id })).toThrow(
      "versão",
    );
  });
  it("does not manufacture evidence/review fields or accept unknown declared quality", () => {
    expect(() => parseFields(EVIDENCE, {})).toThrow();
    expect(() => parseFields(VERIFICATION, {})).toThrow();
    expect(() =>
      fieldValue(
        f("quality", "Quality", undefined, ["verified", "partial", "disputed"]),
        "independent",
      ),
    ).toThrow();
  });
  it("rejects invalid period policy and fractional revisions before any request", () => {
    expect(() =>
      validateRequest({
        request_id: id,
        operation: "detect",
        arguments: {
          contract_id: id,
          revisions: [],
          as_of: "2026-10-31T00:00:00Z",
          required_periods: 2,
        },
      }),
    ).toThrow();
    expect(() =>
      validateRequest({
        request_id: id,
        operation: "plan_recovery",
        arguments: { id, decision_id: id, pre_revision: 1.5, post_revision: 2, reason: "explicit" },
      }),
    ).toThrow();
  });
  it("limits DEV selector to exact loopback HTTPS, with no public runtime setting", () => {
    expect(localApiOrigin("https://localhost:8443")).toBe("https://localhost:8443");
    for (const url of [
      "http://localhost:8443",
      "https://public.example",
      "https://localhost:8443/path",
      "https://user:secret@localhost:8443",
      "https://localhost:8443?x=1",
    ])
      expect(() => localApiOrigin(url)).toThrow();
  });
});
