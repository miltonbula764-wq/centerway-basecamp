// Controlled response identity checks, not a substitute for PostgreSQL/Auth authorization tests.
import { beforeEach, expect, it, vi } from "vitest";
const mock = vi.hoisted(() => ({ rpc: vi.fn() }));
vi.mock("@/integrations/supabase/client", () => ({ supabase: mock }));
import { inboxQuery, myWorkQuery, responsibilityQuery } from "@/lib/responsibilities";
beforeEach(() => vi.clearAllMocks());
function call(
  q:
    | ReturnType<typeof inboxQuery>
    | ReturnType<typeof myWorkQuery>
    | ReturnType<typeof responsibilityQuery>,
) {
  return (q.queryFn as Function)({ signal: new AbortController().signal });
}
it("rejects private notifications for a different recipient or company", async () => {
  for (const data of [
    { tenant_id: "B", user_id: "me", items: [] },
    { tenant_id: "A", user_id: "other", items: [] },
    { tenant_id: "A", user_id: "me", items: [{ tenant_id: "A", recipient_id: "other" }] },
  ]) {
    mock.rpc.mockReturnValue({ abortSignal: () => Promise.resolve({ data, error: null }) });
    await expect(call(inboxQuery("A", "me"))).rejects.toThrow(/Identidade/);
  }
});
it("scopes cache to tenant, account, cursor; rejects a foreign case response", async () => {
  expect(inboxQuery("A", "me").queryKey.slice(0, 4)).toEqual(["t", "A", "notifications", "me"]);
  expect(myWorkQuery("A", "me", "").queryKey).not.toEqual(myWorkQuery("B", "me", "").queryKey);
  mock.rpc.mockReturnValue({
    abortSignal: () =>
      Promise.resolve({
        data: { tenant_id: "A", case_id: "wrong", items: [], current: null },
        error: null,
      }),
  });
  await expect(call(responsibilityQuery("A", "case", null))).rejects.toThrow(/Identidade/);
});
