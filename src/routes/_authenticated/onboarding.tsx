import { createFileRoute, Link, useNavigate, useRouteContext } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Building2, Loader2, User } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState, Loading } from "@/components/app/ui-bits";
import { membershipsQuery } from "@/lib/memberships";
import { writePreferredTenant, type UnitType } from "@/lib/tenant";
import { friendlyError } from "@/lib/errors";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/onboarding")({
  head: () => ({
    meta: [
      { title: "Criar empresa — CENTERWAY" },
      { name: "description", content: "Configure a sua empresa no CENTERWAY." },
      { property: "og:title", content: "Criar empresa — CENTERWAY" },
      { property: "og:description", content: "Configure a sua empresa no CENTERWAY." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Onboarding,
});

function Onboarding() {
  const { user } = useRouteContext({ from: "/_authenticated" });
  const qc = useQueryClient();
  const navigate = useNavigate();
  const memberships = useQuery(membershipsQuery(user.id));
  const [name, setName] = useState("");
  const [unit, setUnit] = useState<UnitType | null>(null);

  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await supabase.rpc("create_tenant", { _name: name.trim(), _subject_unit_type: unit! });
      if (error) throw error;
      return data as string;
    },
    onSuccess: async (id) => {
      writePreferredTenant(id);
      qc.removeQueries({ queryKey: ["t"] });
      await qc.invalidateQueries({ queryKey: ["memberships"] });
      navigate({ to: "/app", replace: true });
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (name.trim().length < 1 || !unit) return;
    create.mutate();
  }

  const hasTenants = (memberships.data?.length ?? 0) > 0;

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-md bg-primary font-mono text-xs font-bold text-primary-foreground">C</div>
          <span className="font-mono text-sm tracking-[0.2em]">CENTERWAY</span>
        </div>
        {memberships.isLoading ? (
          <Loading />
        ) : (
          <form onSubmit={submit} className="rounded-lg border border-border bg-card p-6">
            <h1 className="text-lg font-semibold">{hasTenants ? "Criar outra empresa" : "Criar a sua empresa"}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              A empresa é o espaço isolado onde ficam os seus clientes, o perfil de valor e os dados. Ficará como administrador.
            </p>
            <div className="mt-6 space-y-5">
              <div>
                <Label htmlFor="tname">Nome da empresa</Label>
                <Input id="tname" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5" required />
              </div>
              <fieldset>
                <legend className="text-sm font-medium">Que tipo de cliente acompanha?</legend>
                <p className="mt-1 text-xs text-muted-foreground">Não pode ser alterado depois. A empresa acompanha muitos clientes deste tipo.</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {(
                    [
                      ["organization", "Organizações", "SaaS B2B: os clientes são empresas.", Building2],
                      ["person", "Pessoas", "SaaS B2C: os clientes são indivíduos.", User],
                    ] as const
                  ).map(([value, label, help, Icon]) => (
                    <label
                      key={value}
                      className={cn(
                        "flex cursor-pointer flex-col gap-1 rounded-md border p-3 transition-colors",
                        unit === value ? "border-primary bg-primary/5" : "border-border hover:bg-accent/50",
                      )}
                    >
                      <input type="radio" name="unit" value={value} className="sr-only" checked={unit === value} onChange={() => setUnit(value)} />
                      <span className="flex items-center gap-2 text-sm font-medium">
                        <Icon className="h-4 w-4" /> {label}
                      </span>
                      <span className="text-xs text-muted-foreground">{help}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              {create.isError && <ErrorState message={friendlyError(create.error)} />}
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                {hasTenants && (
                  <Button asChild variant="ghost">
                    <Link to="/app">Cancelar</Link>
                  </Button>
                )}
                <Button type="submit" disabled={create.isPending || !name.trim() || !unit}>
                  {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Criar empresa
                </Button>
              </div>
            </div>
          </form>
        )}
        <button
          className="mt-4 text-sm text-muted-foreground underline underline-offset-4"
          onClick={async () => {
            await qc.cancelQueries();
            qc.clear();
            writePreferredTenant(null);
            await supabase.auth.signOut();
            navigate({ to: "/auth", search: { redirect: undefined }, replace: true });
          }}
        >
          Terminar sessão
        </button>
      </div>
    </main>
  );
}
