import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
export const Route = createFileRoute("/posthog/callback")({
  component: Callback,
  head: () => ({ meta: [{ name: "referrer", content: "no-referrer" }] }),
});
function Callback() {
  const once = useRef(false);
  const [message, setMessage] = useState("A verificar a autorização…");
  useEffect(() => {
    if (once.current) return;
    once.current = true;
    const params = new URLSearchParams(location.search);
    history.replaceState(null, "", "/posthog/callback");
    const stored = sessionStorage.getItem("cw.posthog.pending");
    sessionStorage.removeItem("cw.posthog.pending");
    void (async () => {
      try {
        if (!stored || params.has("error"))
          throw new Error("Autorização cancelada ou sessão de ligação ausente.");
        const pending = JSON.parse(stored);
        if (
          localStorage.getItem("centerway.selectedTenant") &&
          localStorage.getItem("centerway.selectedTenant") !== pending.tenant
        )
          throw new Error("A empresa ativa mudou. Retome a ligação na empresa original.");
        if (pending.state !== params.get("state") || !params.get("code"))
          throw new Error("Estado de autorização inválido.");
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session) throw new Error("Volte a iniciar sessão e autorize novamente.");
        const response = await fetch("/api/connected/finish", {
          method: "POST",
          headers: {
            authorization: "Bearer " + session.access_token,
            "content-type": "application/json",
          },
          body: JSON.stringify({
            tenant: pending.tenant,
            state: params.get("state"),
            code: params.get("code"),
          }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Autorização não confirmada.");
        setMessage(
          "Escopo de um projeto confirmado. Reveja clientes e objetivos antes da sincronização.",
        );
      } catch (e) {
        setMessage(e instanceof Error ? e.message : "Não foi possível confirmar a autorização.");
      }
    })();
  }, []);
  return (
    <main className="mx-auto max-w-xl p-6 space-y-4">
      <h1 className="text-xl">Ligação PostHog</h1>
      <p role="status">{message}</p>
      <Link to="/app/conectar" className="underline">
        Voltar à ligação
      </Link>
    </main>
  );
}
