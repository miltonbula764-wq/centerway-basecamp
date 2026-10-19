// Presentation integration: identity propagation only, no RPCs or hosted permission proof.
import { cleanup, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CaseWorkspace } from "@/components/app/case-workspace";

const mocks = vi.hoisted(() => ({
  target: {} as Record<string, string>,
  c04: vi.fn(),
  operational: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({ useSearch: () => mocks.target, Link: () => null }));
vi.mock("@/lib/tenant", () => ({ useTenant: () => ({ tenant: { id: "A" }, isAdmin: true, canWrite: true }), tk: (...args: unknown[]) => ["t", ...args], assertActiveTenant: vi.fn() }));
vi.mock("@/components/app/c04-value-state", () => ({ C04ValueState: (props: unknown) => { mocks.c04(props); return null; } }));
vi.mock("@/components/app/operational-cases", () => ({ OperationalCases: (props: unknown) => { mocks.operational(props); return null; } }));
vi.mock("@/integrations/supabase/client", () => ({ supabase: { from: (table: string) => {
  const result = { data: table === "subjects" ? [{ id: "subject-A", display_name: "Test" }] : [], count: 1, error: null };
  const chain = { select: () => chain, eq: () => chain, order: () => chain, limit: () => chain, returns: () => Promise.resolve(result), then: (resolve: (value: unknown) => unknown) => Promise.resolve(result).then(resolve) };
  return chain;
} } }));
beforeEach(() => { vi.clearAllMocks(); mocks.target = { tenant: "A", subject: "subject-A", kind: "operational", case: "case-A" }; });
afterEach(cleanup);
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CaseWorkspace /></QueryClientProvider>);
}
it("preserves the operational deep-link identity and keeps C04 mounted", async () => {
  mount();
  await waitFor(() => expect(mocks.operational).toHaveBeenCalledWith({ subjectId: "subject-A", initialCaseId: "case-A", initialEvaluationId: undefined }));
  expect(mocks.c04).toHaveBeenCalledWith({ subjectId: "subject-A", initialConfigurationId: undefined, initialEvaluationId: undefined });
});
it("preserves C04 configuration and evaluation identities in both original blocks", async () => {
  mocks.target = { tenant: "A", subject: "subject-A", kind: "c04", configuration: "configuration-A", evaluation: "evaluation-A" };
  mount();
  await waitFor(() => expect(mocks.c04).toHaveBeenCalledWith({ subjectId: "subject-A", initialConfigurationId: "configuration-A", initialEvaluationId: "evaluation-A" }));
  expect(mocks.operational).toHaveBeenCalledWith({ subjectId: "subject-A", initialCaseId: undefined, initialEvaluationId: "evaluation-A" });
});
it("does not mount either block for a cross-tenant deep-link", () => {
  mocks.target["tenant"] = "B";
  mount();
  expect(mocks.c04).not.toHaveBeenCalled();
  expect(mocks.operational).not.toHaveBeenCalled();
});