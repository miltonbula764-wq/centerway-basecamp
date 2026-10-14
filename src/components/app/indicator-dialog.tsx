import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { friendlyError } from "@/lib/errors";
import {
  baselineLabel,
  buildIndicatorPayload,
  classHelp,
  classLabel,
  valueTypeLabel,
  aggregationLabel,
  denominatorModeLabel,
  directionLabel,
  emptyIndicatorForm,
  formFromRow,
  kindLabel,
  operatorLabel,
  type IndicatorForm,
  type FormErrors,
} from "@/lib/profile";
import { ErrorState, FieldError, FieldHint, NativeSelect } from "./ui-bits";

type Row = { id: string };

export function IndicatorDialog({
  open,
  onOpenChange,
  profileId,
  indicator,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  profileId: string;
  indicator?: Row | undefined;
}) {
  const { tenant } = useTenant();
  const tenantId = tenant.id;
  const qc = useQueryClient();
  const [f, setF] = useState<IndicatorForm>(emptyIndicatorForm);
  const [errors, setErrors] = useState<FormErrors>({});

  useEffect(() => {
    if (open) {
      setF(indicator ? formFromRow(indicator) : emptyIndicatorForm);
      setErrors({});
    }
  }, [open, indicator]);

  const set = <K extends keyof IndicatorForm>(k: K, v: IndicatorForm[K]) => setF((p) => ({ ...p, [k]: v }));

  const save = useMutation({
    mutationFn: async () => {
      const r = buildIndicatorPayload(f);
      if (!r.ok) {
        setErrors(r.errors);
        throw new Error("validation");
      }
      assertActiveTenant(tenantId);
      if (indicator) {
        const { error } = await supabase.from("profile_indicators").update(r.data).eq("id", indicator.id).eq("tenant_id", tenantId);
        if (error) throw error;
      } else {
        const { error } = await supabase.from("profile_indicators").insert({ ...r.data, tenant_id: tenantId, profile_id: profileId });
        if (error) throw error;
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tk(tenantId, "indicators", profileId) });
      qc.invalidateQueries({ queryKey: tk(tenantId, "issues", profileId) });
      toast.success(indicator ? "Indicador atualizado." : "Indicador adicionado.");
      onOpenChange(false);
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    save.mutate();
  }

  const isOutcome = f.classification === "outcome";
  const numField = (k: keyof IndicatorForm, label: string, hint: ReactNode, suffix?: string) => (
    <div>
      <Label htmlFor={k}>{label}</Label>
      <div className="mt-1.5 flex items-center gap-2">
        <Input id={k} inputMode="decimal" value={f[k]} onChange={(e) => set(k, e.target.value as never)} className="font-mono" />
        {suffix && <span className="shrink-0 text-xs text-muted-foreground">{suffix}</span>}
      </div>
      <FieldHint>{hint}</FieldHint>
      <FieldError>{errors[k]}</FieldError>
    </div>
  );

  const rule = (p: "deterioration" | "recovery", title: string, hint: string) => (
    <Section title={title} hint={hint}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label>Tipo</Label>
          <NativeSelect className="mt-1.5" value={f[`${p}_kind`]} onChange={(e) => set(`${p}_kind`, e.target.value as never)}>
            <option value="">— sem regra —</option>
            {Object.entries(kindLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </NativeSelect>
        </div>
        <div>
          <Label>Operador</Label>
          <NativeSelect className="mt-1.5" value={f[`${p}_operator`]} onChange={(e) => set(`${p}_operator`, e.target.value as never)}>
            <option value="">—</option>
            {Object.entries(operatorLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </NativeSelect>
        </div>
        {numField(`${p}_value`, "Valor", f[`${p}_kind`] === "relative_pct" ? "Percentagem do baseline." : `Na unidade do indicador${f.unit ? ` (${f.unit})` : ""}.`)}
        {numField(`${p}_consecutive_windows`, "Janelas consecutivas", "Quantas janelas seguidas têm de cumprir a regra.", "janelas")}
      </div>
      <FieldError>{errors[`${p}_rule`]}</FieldError>
    </Section>
  );

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) save.reset(); onOpenChange(o); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>{indicator ? "Editar indicador" : "Novo indicador"}</DialogTitle>
            <DialogDescription>Os campos sem valor ficam vazios: não há limiares pré-definidos.</DialogDescription>
          </DialogHeader>

          <div className="my-5 space-y-6">
            <Section title="Identificação">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label htmlFor="key">Chave</Label>
                  <Input id="key" value={f.key} onChange={(e) => set("key", e.target.value)} className="mt-1.5 font-mono" placeholder="paid_on_time_pct" />
                  <FieldHint>Nome técnico que liga as observações a este indicador.</FieldHint>
                  <FieldError>{errors.key}</FieldError>
                </div>
                <div>
                  <Label htmlFor="name">Nome</Label>
                  <Input id="name" value={f.name} onChange={(e) => set("name", e.target.value)} className="mt-1.5" />
                  <FieldError>{errors.name}</FieldError>
                </div>
                <div>
                  <Label>Classificação</Label>
                  <NativeSelect className="mt-1.5" value={f.classification} onChange={(e) => set("classification", e.target.value as never)}>
                    {Object.entries(classLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </NativeSelect>
                  <FieldHint>{classHelp[f.classification]}</FieldHint>
                </div>
                <div>
                  <Label>Tipo de valor</Label>
                  <NativeSelect className="mt-1.5" value={isOutcome ? "numeric" : f.value_type} disabled={isOutcome} onChange={(e) => set("value_type", e.target.value as never)}>
                    {Object.entries(valueTypeLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </NativeSelect>
                  <FieldHint>{isOutcome ? "Indicadores de resultado são sempre numéricos." : "Define se a importação aceita value_numeric ou value_text."}</FieldHint>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="unit">Unidade</Label>
                    <Input id="unit" value={f.unit} onChange={(e) => set("unit", e.target.value)} className="mt-1.5" placeholder="%" />
                    <FieldError>{errors.unit}</FieldError>
                  </div>
                  <div>
                    <Label>Direção</Label>
                    <NativeSelect className="mt-1.5" value={f.direction} onChange={(e) => set("direction", e.target.value as never)}>
                      {Object.entries(directionLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </NativeSelect>
                  </div>
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor="def">Definição</Label>
                  <Textarea id="def" value={f.definition} onChange={(e) => set("definition", e.target.value)} className="mt-1.5" rows={2} placeholder="Como é calculado, quais registos entram no denominador…" />
                  <FieldError>{errors.definition}</FieldError>
                </div>
              </div>
            </Section>

            {!isOutcome && (
              <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                Para indicadores de {classLabel[f.classification].toLowerCase()}, as secções seguintes são opcionais.
              </p>
            )}

            <Section title="Baseline" hint="O ponto de referência contra o qual se mede a evolução.">
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <Label>Método</Label>
                  <NativeSelect className="mt-1.5" value={f.baseline_method} onChange={(e) => set("baseline_method", e.target.value as never)}>
                    <option value="">—</option>
                    {Object.entries(baselineLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </NativeSelect>
                </div>
                {numField("baseline_value", "Valor", "Obrigatório com valor fixo.", f.unit || undefined)}
                {numField("baseline_min_period_days", "Período mínimo", "Dias de histórico antes de haver baseline.", "dias")}
              </div>
            </Section>

            <Section title="Janelas e suficiência" hint="Sem dados suficientes, o sistema declara informação insuficiente.">
              <div className="grid gap-3 sm:grid-cols-2">
                {numField("observation_window_days", "Janela de observação", "Período de cada medição.", "dias")}
                {numField("comparison_window_days", "Janela de comparação", "Período contra o qual se compara.", "dias")}
                {numField("min_coverage_pct", "Cobertura mínima", "Percentagem do período com dados (0–100).", "%")}
                {numField("min_denominator", "Denominador mínimo", "Nº mínimo de casos elegíveis por janela.", "casos")}
                {numField("target_value", "Alvo", "Valor esperado (opcional).", f.unit || undefined)}
              </div>
            </Section>

            <Section title="Cálculo da deteção (C02)" hint="Sem estes campos a deteção devolve “configuração insuficiente”. Não há valores por omissão.">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Agregação por janela</Label>
                  <NativeSelect className="mt-1.5" value={f.aggregation} onChange={(e) => set("aggregation", e.target.value as never)}>
                    <option value="">—</option>
                    {Object.entries(aggregationLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </NativeSelect>
                  <FieldHint>Soma só é comparável se a janela de comparação tiver o mesmo tamanho.</FieldHint>
                </div>
                {numField("expected_cadence_days", "Cadência esperada", "Espera-se pelo menos uma observação a cada N dias; define a cobertura. As janelas têm de ser múltiplos.", "dias")}
                <div>
                  <Label>Denominador</Label>
                  <NativeSelect className="mt-1.5" value={f.denominator_mode} onChange={(e) => set("denominator_mode", e.target.value as never)}>
                    <option value="">—</option>
                    {Object.entries(denominatorModeLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </NativeSelect>
                  <FieldHint>O que se compara com o denominador mínimo em cada janela.</FieldHint>
                </div>
                {f.denominator_mode === "paired_indicator" && (
                  <div>
                    <Label htmlFor="den_key">Chave do indicador de denominador</Label>
                    <Input id="den_key" value={f.denominator_indicator_key} onChange={(e) => set("denominator_indicator_key", e.target.value)} className="mt-1.5 font-mono" placeholder="eligible_invoices" />
                    <FieldError>{errors.denominator_indicator_key}</FieldError>
                  </div>
                )}
              </div>
            </Section>

            {rule("deterioration", "Regra de deterioração", "Quando se considera que o valor piorou.")}
            {rule("recovery", "Regra de recuperação", "Quando se considera que o valor recuperou.")}

            {save.isError && save.error.message !== "validation" && <ErrorState message={friendlyError(save.error)} />}
            {Object.keys(errors).length > 0 && <ErrorState message="Corrija os campos assinalados." />}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">{title}</legend>
      {hint && <p className="mb-3 mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      <div className={hint ? "" : "mt-3"}>{children}</div>
    </fieldset>
  );
}
