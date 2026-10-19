import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { User } from "@supabase/supabase-js";
import { supabase } from "@/integrations/supabase/client";
import { AuthForm } from "./auth";
import { roleLabel, setActiveTenantId, writePreferredTenant, type Role } from "@/lib/tenant";
import { teamError } from "@/lib/team";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading, formatDate } from "@/components/app/ui-bits";
export const Route = createFileRoute("/convite")({
  ssr: false,
  component: Invitation,
  head: () => ({
    meta: [{ title: "Aceitar convite — CENTERWAY" }, { name: "referrer", content: "no-referrer" }],
  }),
});
type Preview = {
  id: string;
  tenant_id: string;
  tenant_name: string;
  role: Role;
  expires_at: string;
  already_member: boolean;
};
function Invitation() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  const generation = useRef(0);
  const operation = useRef(crypto.randomUUID());
  const qc = useQueryClient();
  const navigate = useNavigate();
  useEffect(() => {
    live.current = true;
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const raw = hash.get("token") || "";
    // Keep the bearer secret only in component memory, not in URL history, storage or query keys.
    window.history.replaceState(window.history.state, "", window.location.pathname);
    if (/^[0-9a-f]{64}$/.test(raw)) setToken(raw);
    const { data } = supabase.auth.onAuthStateChange(() => {
      void refresh();
    });
    void refresh();
    return () => {
      live.current = false;
      generation.current++;
      data.subscription.unsubscribe();
    };
  }, []);
  async function refresh() {
    const g = ++generation.current;
    setLoading(true);
    setPreview(null);
    setError("");
    const { data } = await supabase.auth.getUser();
    if (!live.current || generation.current !== g) return;
    setUser(data.user);
    setLoading(false);
  }
  useEffect(() => {
    if (!user || !token) return;
    const g = ++generation.current;
    setLoading(true);
    setError("");
    void supabase.rpc("inspect_tenant_invitation", { _token: token }).then(({ data, error }) => {
      if (!live.current || generation.current !== g) return;
      if (error) setError(teamError(error));
      else setPreview(data as Preview);
      setLoading(false);
    });
  }, [user, token]);
  async function accept() {
    if (!preview) return;
    setBusy(true);
    setError("");
    const actor = user?.id;
    try {
      const { data: identity } = await supabase.auth.getUser();
      if (identity.user?.id !== actor) throw Error("session_changed");
      const { data, error } = await supabase.rpc("accept_tenant_invitation", {
        _token: token,
        _operation_id: operation.current,
      });
      if (error) throw error;
      if (!live.current) return;
      const { data: current } = await supabase.auth.getUser();
      if (current.user?.id !== actor) return;
      const result = data as { tenant_id: string };
      setToken("");
      setPreview(null);
      setActiveTenantId(null);
      qc.removeQueries({ queryKey: ["t"] });
      await qc.invalidateQueries({ queryKey: ["memberships"] });
      writePreferredTenant(result.tenant_id);
      await navigate({ to: "/app/configuracoes", replace: true });
    } catch (e) {
      if (live.current) setError(teamError(e));
    } finally {
      if (live.current) setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-lg space-y-4 px-4 py-8">
      <h1 className="text-xl font-semibold">Convite para uma equipa CENTERWAY</h1>
      {!token && !loading ? (
        <p>
          Ligação ausente ou inválida. Abra novamente a ligação partilhada pelo administrador. Por
          segurança, a ligação não é guardada neste navegador.
        </p>
      ) : loading ? (
        <Loading />
      ) : !user ? (
        <>
          <p className="text-sm">
            Entre ou crie uma conta com o email indicado pelo administrador. Se precisar de
            confirmar o email, confirme-o e volte a abrir a ligação original.
          </p>
          <AuthForm onAuthenticated={refresh} />
        </>
      ) : (
        <>
          <p className="text-sm">
            Conta atual: <strong>{user.email}</strong>. O servidor verifica a confirmação e a
            correspondência do email.
          </p>
          {preview && (
            <div className="space-y-3 rounded border p-4">
              <h2 className="font-medium">{preview.tenant_name}</h2>
              <p>Papel proposto: {roleLabel[preview.role]}</p>
              <p>Válido até {formatDate(preview.expires_at)}</p>
              {preview.already_member && (
                <p>
                  Já pertence a esta empresa. Aceitar consome o convite e preserva o seu papel
                  atual.
                </p>
              )}
              <Button disabled={busy} onClick={accept}>
                Aceitar convite
              </Button>
            </div>
          )}
          {error && <ErrorState message={error} />}
          <Button
            variant="secondary"
            disabled={busy}
            onClick={async () => {
              await supabase.auth.signOut();
              qc.clear();
              await refresh();
            }}
          >
            Utilizar outra conta
          </Button>
        </>
      )}
    </main>
  );
}
