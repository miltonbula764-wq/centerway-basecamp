import { describe, expect, it } from "vitest";
import { safeRedirect } from "./safe-redirect";

describe("safeRedirect", () => {
  it("keeps internal paths", () => expect(safeRedirect("/app/clientes")).toBe("/app/clientes"));
  it("blocks protocol-relative urls", () => expect(safeRedirect("//evil.com")).toBe("/app"));
  it("blocks absolute urls", () => expect(safeRedirect("https://evil.com")).toBe("/app"));
  it("blocks redirect loops to auth", () => expect(safeRedirect("/auth")).toBe("/app"));
});
