import { expect, it, vi } from "vitest";
const mock = vi.hoisted(() => ({ rpc: vi.fn() }));
vi.mock("@/integrations/supabase/client", () => ({ supabase: mock }));
import { indicatorSetup, onboardingQuery, type SetupIndicator } from "@/lib/onboarding";
const item: SetupIndicator = {
  tenant_id: "A",
  subject_id: "customer",
  indicator_key: "minutes",
  name: "Minutes",
  unit: "min",
  configuration: {
    id: "config",
    version: 1,
    profile_id: "profile",
    pending_fields: [],
    compatibility: "compatible",
  },
  profile_changed: false,
  has_observations: false,
  new_observations: false,
  run: null,
  bundle: null,
  evaluation: null,
};
it("counts only persisted milestones, without inventing sufficiency before C04", () => {
  expect(indicatorSetup(item)).toMatchObject({ stage: "measurements", valid: false });
  expect(
    indicatorSetup({
      ...item,
      configuration: { ...item.configuration!, pending_fields: ["customer_ref"] },
    }).stage,
  ).toBe("goal");
  const measured = { ...item, has_observations: true };
  expect(indicatorSetup(measured).stage).toBe("analysis");
  const run = { id: "run", as_of: "x", data_cutoff: "x", status: "insufficient_data", reasons: [] };
  const withRun = { ...measured, run };
  expect(indicatorSetup(withRun).stage).toBe("evidence");
  const evidence = { ...withRun, bundle: { id: "bundle", status: "complete", reasons: [] } };
  expect(indicatorSetup(evidence)).toMatchObject({ stage: "evaluation", valid: false });
  const evaluated = {
    ...evidence,
    evaluation: {
      id: "e",
      bundle_id: "bundle",
      configuration_state: "compatible",
      evidence: "sufficient",
      result: "not_achieved",
      core_disposition: "assessment_available",
      reasons: [],
    },
  };
  expect(indicatorSetup(evaluated)).toMatchObject({ valid: true, stage: "review" });
  expect(indicatorSetup({ ...evaluated, bundle: null })).toMatchObject({
    valid: false,
    stale: true,
  });
  expect(indicatorSetup({ ...evaluated, new_observations: true })).toMatchObject({
    valid: false,
    stale: true,
  });
  expect(
    indicatorSetup({
      ...evaluated,
      evaluation: { ...evaluated.evaluation, configuration_state: "contradiction" },
    }).valid,
  ).toBe(false);
  expect(indicatorSetup(evaluated).valid).toBe(true); // Independent indicator remains unaffected.
});
it("rejects foreign tenant/subject/role replies and propagates cancellation", async () => {
  const signal = new AbortController().signal;
  const abort = vi.fn().mockResolvedValue({
    data: { tenant_id: "B", role: "admin", subjects: [], indicators: [] },
    error: null,
  });
  mock.rpc.mockReturnValue({ abortSignal: abort });
  const q = onboardingQuery("A", "admin", "customer", "", "");
  await expect((q.queryFn as Function)({ signal })).rejects.toThrow(/Resposta/);
  expect(abort).toHaveBeenCalledWith(signal);
  expect(q.queryKey.slice(0, 4)).toEqual(["t", "A", "onboarding", "admin"]);
});
