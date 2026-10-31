import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { useRouter } from "@tanstack/react-router";
import { getLiveRuntime } from "@/data/live-runtime";
import { ErrorStateFrom, LoadingState } from "./states";

export function useLiveSession() {
  const runtime = getLiveRuntime();
  const state = useSyncExternalStore(runtime.subscribe, runtime.getSnapshot, runtime.getSnapshot);
  return { runtime, state };
}

export function LiveBoundary({ children }: { children: ReactNode }) {
  const { runtime, state } = useLiveSession();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const identity = state.auth.session?.principal ?? "";
  const tenant = state.auth.tenant ?? "";
  const scope = identity + "|" + tenant + "|" + state.revision;
  const [settledScope, setSettledScope] = useState<string | null>(null);
  useEffect(() => {
    const timer = setInterval(() => runtime.checkExpiry(), 1000);
    return () => clearInterval(timer);
  }, [runtime]);
  useEffect(() => {
    let current = true;
    router.clearCache();
    void router.invalidate().then(() => { if (current) setSettledScope(scope); });
    return () => { current = false; };
  }, [scope, router]);
  const authenticated = !!state.auth.session && (state.auth.status === "authenticated" || state.auth.status === "forbidden");
  if (!authenticated) return (
    <div className="mx-auto max-w-md px-5 py-14">
      <h1 className="page-title">Iniciar sessão</h1>
      <p className="mt-2 text-muted-foreground">Demonstração sintética ligada à API pública. Utilize os acessos privados fornecidos pelo operador.</p>
      <form className="mt-6 flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); const secret = password; setPassword(""); void runtime.login(username, secret).then(() => router.invalidate()).catch(() => {}); }}>
        <label className="flex flex-col gap-1">Utilizador<input name="username" autoComplete="username" required value={username} onChange={(e) => setUsername(e.target.value)} className="h-11 rounded-md border bg-surface px-3" /></label>
        <label className="flex flex-col gap-1">Palavra-passe<input name="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="h-11 rounded-md border bg-surface px-3" /></label>
        <button type="submit" disabled={state.busy} className="h-11 rounded-md bg-primary px-4 text-primary-foreground disabled:opacity-50">{state.busy ? "A ligar à API…" : "Entrar"}</button>
        {state.busy && <button type="button" onClick={() => void runtime.logout()} className="h-11 rounded-md border">Cancelar</button>}
      </form>
      {state.error != null && <ErrorStateFrom error={state.error} />}
      <p className="mt-5 text-[12px] text-subtle-foreground">A API gratuita pode demorar a iniciar. A sessão fica apenas em memória: atualizar a página exige novo login. Os registos permanecem na API. Nunca introduza dados reais.</p>
    </div>
  );
  return (
    <>
      <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle px-4 py-2 text-[12px] sm:px-6">
        <span className="text-demo-foreground">API pública · dados sintéticos</span>
        <span>{state.auth.session!.username}</span>
        <label>Empresa <select aria-label="Empresa" value={tenant} onChange={(e) => { void runtime.selectTenant(e.target.value).then(() => router.invalidate()).catch(() => {}); }} className="ml-1 h-9 max-w-56 rounded border bg-surface px-2"><option value="" disabled>Selecionar empresa</option>{state.auth.clientTenants.map((t) => <option key={t} value={t}>Empresa · {t.slice(0, 8)}</option>)}</select></label>
        <button disabled={state.busy || !tenant} onClick={() => void runtime.refresh().then(() => router.invalidate()).catch(() => {})} className="h-9 rounded border px-3 disabled:opacity-40">Atualizar dados</button>
        <button onClick={() => { void runtime.logout().then(() => router.invalidate()); }} className="ml-auto h-9 rounded border px-3">Terminar sessão</button>
      </div>
      {!tenant ? <div className="p-8 text-muted-foreground">Selecione uma empresa autorizada.</div> : state.error != null ? <ErrorStateFrom error={state.error} /> : state.busy || settledScope !== scope ? <LoadingState label="A carregar dados da API…" /> : <div key={scope}>{children}</div>}
    </>
  );
}
