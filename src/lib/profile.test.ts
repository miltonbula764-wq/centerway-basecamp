import { describe, expect, it } from "vitest";
import { buildIndicatorPayload, emptyIndicatorForm, translateIssue } from "./profile";
import { pickTenant } from "./tenant";

const base = { ...emptyIndicatorForm, key: "paid_on_time_pct", name: "Faturas pagas no prazo", unit: "%" };

describe("indicator form rules", () => {
  it("rejects a partially filled deterioration rule", () => {
    const r = buildIndicatorPayload({ ...base, deterioration_kind: "absolute" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors.deterioration_rule).toBeDefined();
  });

  it("allows a usage indicator with no rules at all", () => {
    const r = buildIndicatorPayload({ ...base, classification: "usage" });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.data.deterioration_kind).toBeNull();
  });

  it("rejects coverage above 100%", () => {
    const r = buildIndicatorPayload({ ...base, min_coverage_pct: "101" });
    expect(r.ok).toBe(false);
  });

  it("requires a value for a fixed baseline", () => {
    const r = buildIndicatorPayload({ ...base, baseline_method: "fixed_value" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors.baseline_value).toBeDefined();
  });

  it("rejects keys that are not lowercase identifiers", () => {
    expect(buildIndicatorPayload({ ...base, key: "Paid On Time" }).ok).toBe(false);
  });

  it("has no universal default threshold", () => {
    const r = buildIndicatorPayload(base);
    expect(r.ok && r.data.deterioration_value).toBeNull();
  });
});

describe("approval issue translation", () => {
  it("translates the missing outcome indicator issue", () => {
    expect(translateIssue("profile needs at least one outcome indicator")).toBe(
      "O perfil precisa de pelo menos um indicador de resultado.",
    );
  });
  it("translates field issues keeping the key", () => {
    expect(translateIssue("x: min_denominator missing")).toBe("x: falta o denominador mínimo");
  });
});

describe("tenant preference", () => {
  it("ignores a stored tenant the user is no longer a member of", () => {
    expect(pickTenant([{ id: "a" }, { id: "b" }], "z")).toBe("a");
  });
  it("keeps a stored tenant that is still authorised", () => {
    expect(pickTenant([{ id: "a" }, { id: "b" }], "b")).toBe("b");
  });
  it("returns null without memberships", () => {
    expect(pickTenant([], "a")).toBeNull();
  });
});
