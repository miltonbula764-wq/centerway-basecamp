import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Loader2, MailCheck } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { safeRedirect } from "@/lib/safe-redirect";
import { ErrorState } from "@/components/app/ui-bits";

export const Route = createFileRoute("/auth")({
  ssr: false,
  validateSearch: (s: Record<string, unknown>): { redirect?: string | undefined } => ({
    redirect: typeof s["redirect"] === "string" ? s["redirect"] : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Entrar — CENTERWAY" },
      { name: "description", content: "Inicie sessão ou crie a sua conta CENTERWAY." },
      { property: "og:title", content: "Entrar — CENTERWAY" },
      { property: "og:description", content: "Inicie sessão ou crie a sua conta CENTERWAY." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  beforeLoad: async ({ search }) => {
    const { data } = await supabase.auth.getSession();
    if (data.session) throw redirect({ href: safeRedirect(search.redirect), replace: true });
  },
  component: AuthPage,
});

function AuthPage() {
  const search = Route.useSearch();
  const navigate = useNavigate();
  return <AuthForm onAuthenticated={() => navigate({ href: safeRedirect(search.redirect), replace: true })} />;
}

export function AuthForm({ onAuthenticated }: { onAuthenticated: () => void | Promise<void> }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (mode === "signup" && password.length < 8) {
      setError("A palavra-passe deve ter pelo menos 8 caracteres.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "login") {
        const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        // Generic message: never reveal whether an account exists.
        if (error) {
          setError("Não foi possível iniciar sessão. Verifique os dados ou confirme primeiro o seu email.");
          return;
        }
        await onAuthenticated();
      } else {
        const { error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: `${window.location.origin}/auth` },
        });
        if (error && error.status !== 422 && !/registered/i.test(error.message)) {
          if (/password/i.test(error.message)) setError("A palavra-passe não cumpre os requisitos de segurança.");
          else if (/rate|limit/i.test(error.message)) setError("Demasiadas tentativas. Aguarde alguns minutos.");
          else setError("Não foi possível concluir o registo. Tente novamente.");
          return;
        }
        setSent(true);
      }
    } catch {
      setError("Sem ligação ao servidor. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-md bg-primary font-mono text-xs font-bold text-primary-foreground">C</div>
          <span className="font-mono text-sm tracking-[0.2em]">CENTERWAY</span>
        </div>

        {sent ? (
          <div className="rounded-lg border border-border bg-card p-6">
            <MailCheck className="mb-3 h-5 w-5 text-primary" />
            <h1 className="text-lg font-semibold">Confirme o seu email</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Se for possível criar uma conta com <span className="text-foreground">{email}</span>, receberá um email com
              um link de confirmação. Depois de confirmar, inicie sessão.
            </p>
            <Button variant="secondary" className="mt-5 w-full" onClick={() => { setSent(false); setMode("login"); setPassword(""); }}>
              Voltar a iniciar sessão
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} className="rounded-lg border border-border bg-card p-6" noValidate>
            <h1 className="text-lg font-semibold">{mode === "login" ? "Iniciar sessão" : "Criar conta"}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {mode === "login" ? "Aceda à sua empresa no CENTERWAY." : "Será enviado um email de confirmação."}
            </p>
            <div className="mt-5 space-y-4">
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="password">Palavra-passe</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5"
                />
              </div>
              {error && <ErrorState message={error} />}
              <Button type="submit" className="w-full" disabled={busy || !email || !password}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                {mode === "login" ? "Entrar" : "Criar conta"}
              </Button>
            </div>
            <p className="mt-5 text-center text-sm text-muted-foreground">
              {mode === "login" ? "Ainda não tem conta?" : "Já tem conta?"}{" "}
              <button type="button" className="text-foreground underline underline-offset-4" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}>
                {mode === "login" ? "Criar conta" : "Iniciar sessão"}
              </button>
            </p>
          </form>
        )}
      </div>
    </main>
  );
}
