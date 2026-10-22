import { supabase } from "@/integrations/supabase/client";
import { assertActiveTenant } from "./tenant";
export async function connectedRequest(
  tenant: string,
  action: string,
  body?: object,
  signal?: AbortSignal,
) {
  assertActiveTenant(tenant);
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Inicie sessão novamente.");
  assertActiveTenant(tenant);
  const r = await fetch(
    "/api/connected/" + action + (body ? "" : "?tenant=" + encodeURIComponent(tenant)),
    {
      method: body ? "POST" : "GET",
      ...(signal ? { signal } : {}),
      headers: {
        authorization: "Bearer " + session.access_token,
        ...(body ? { "content-type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify({ ...body, tenant }) } : {}),
    },
  );
  const value = await r.json();
  assertActiveTenant(tenant);
  if (!r.ok) throw new Error(value.error || "Ligação indisponível");
  return value;
}
