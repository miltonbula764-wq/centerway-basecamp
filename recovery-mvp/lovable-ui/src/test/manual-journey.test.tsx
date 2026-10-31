import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { ManualJourney } from "@/components/cw/manual-journey";
import { LiveRuntime } from "@/data/live-runtime";
import { L01Error, type L01Transport } from "@/data/transport";
import type { ClientJourney, ManualContext } from "@/domain/f06";
const h = vi.hoisted(() => ({ runtime: null as unknown as LiveRuntime, invalidate: vi.fn() }));
vi.mock("@tanstack/react-router", () => ({ useRouter: () => ({ invalidate: h.invalidate }) }));
vi.mock("@/components/cw/live-session", () => ({
  useLiveSession: () => ({ runtime: h.runtime, state: h.runtime.getSnapshot() }),
}));
const bundle = JSON.parse(readFileSync(__dirname + "/fixtures/l03-prep-v1/capture.json", "utf8"));
const journey = bundle.cases.find((c: { id: string }) => c.id === "journey-initial").response.json
  .data as ClientJourney;
const T = journey.tenant_id,
  C = journey.client_id;
const empty = {
  version: "t02-v1",
  tenant_id: T,
  client_id: C,
  principal: "cw_t01_operator",
  limit_per_collection: 100,
  truncated: {
    factors: false,
    evidence: false,
    verifications: false,
    catalog: false,
    policies: false,
    revocations: false,
    resources: false,
    audit: false,
  },
  factors: [],
  evidence: [],
  verifications: [],
  catalog: [],
  policies: [],
  revocations: [],
  resources: [],
  audit: [],
} as ManualContext;
let transport: L01Transport;
async function setup(reader = false) {
  transport = {
    mode: "live",
    createSession: async () => ({
      access_token: "[memory-only]",
      token_type: "Bearer",
      expires_in: 900,
      demo: false,
    }),
    getSession: async () => ({
      username: "synthetic",
      principal: empty.principal,
      clients: { [T]: [C] },
      operations: reader ? [] : ["append_value", "detect", "intervene"],
      company_tenants: [],
    }),
    deleteSession: vi.fn(async () => {}),
    listClients: async () => ({
      data: [{ client_id: C, display_name: "Synthetic API client" }],
      next_cursor: null,
      demo: false,
    }),
    getJourney: vi.fn(async () => structuredClone(journey)),
    getManualContext: vi.fn(async () => structuredClone(empty)),
    operate: vi.fn<L01Transport["operate"]>(async (t, c, req) => ({
      tenant_id: t,
      client_id: c,
      request_id: req.request_id,
      operation: req.operation,
      arguments: req.arguments,
      status: "completed",
      result: { status: "blocked" },
      actor: empty.principal,
      recorded_at: "2026-10-31T12:00:00Z",
    })),
  };
  h.runtime = new LiveRuntime(transport);
  await h.runtime.login("synthetic", "test");
  render(<ManualJourney client={C} />);
  fireEvent.click(screen.getByRole("button", { name: "Operar jornada F01–F06" }));
  await screen.findByRole("combobox", { name: "Ação manual" });
}
async function source() {
  fireEvent.change(screen.getByRole("combobox", { name: "Ação manual" }), {
    target: { value: "append_value" },
  });
  for (const [label, value] of Object.entries({
    "Motivo do registo": "Explicit synthetic test",
    "Nome da fonte": "Synthetic source",
    "Localizador da fonte": "synthetic://t02/unit",
    "Método da fonte": "Synthetic test",
  }))
    fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Pré-visualizar pedido" }));
  await screen.findByRole("button", { name: "Confirmar envio manual" });
}
beforeEach(() => {
  vi.clearAllMocks();
});
describe("manual editor with actual runtime/controller and typed requests", () => {
  it("loads only real transport reads and refuses writes for the reader", async () => {
    await setup(true);
    expect(transport.getManualContext).toHaveBeenCalledWith(T, C);
    expect(screen.getByRole("button", { name: "Pré-visualizar pedido" })).toBeDisabled();
    expect(transport.operate).not.toHaveBeenCalled();
  });
  it("requires frozen preview and explicit scope confirmation, then shows actual blocked result", async () => {
    await setup();
    await source();
    const send = screen.getByRole("button", { name: "Confirmar envio manual" });
    expect(send).toBeDisabled();
    expect(transport.operate).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Confirmo este pedido sintético e o âmbito apresentado.",
      }),
    );
    fireEvent.click(send);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("blocked"));
    expect(transport.operate).toHaveBeenCalledTimes(1);
  });
  it("does not repeat a lost response; resend keeps identical UUID and payload", async () => {
    await setup();
    vi.mocked(transport.operate).mockRejectedValueOnce(
      new L01Error("network", null, "network_unreachable"),
    );
    await source();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Confirmo este pedido sintético e o âmbito apresentado.",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirmar envio manual" }));
    await screen.findByRole("button", { name: "Reenviar exatamente o mesmo pedido" });
    expect(transport.operate).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("combobox", { name: "Ação manual" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reenviar exatamente o mesmo pedido" }));
    await screen.findByRole("status");
    expect(vi.mocked(transport.operate).mock.calls[0]).toEqual(
      vi.mocked(transport.operate).mock.calls[1],
    );
  });
  it("never posts after logout changed the principal/scope during confirmation", async () => {
    await setup();
    await source();
    await h.runtime.logout();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Confirmo este pedido sintético e o âmbito apresentado.",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirmar envio manual" }));
    expect(transport.operate).not.toHaveBeenCalled();
  });
  it("does not invent evidence defaults or semantic document interpretation", async () => {
    await setup();
    fireEvent.change(screen.getByRole("combobox", { name: "Ação manual" }), {
      target: { value: "append_value" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Tipo de registo" }), {
      target: { value: "evidence" },
    });
    expect(screen.getByLabelText("Valor observado", { exact: true })).toHaveValue(null);
    expect(screen.getByRole("combobox", { name: "Qualidade declarada" })).toHaveValue("");
    expect(screen.getByText(/não há interpretação semântica/)).toBeVisible();
  });
});
