export type IndicatorClass = "outcome" | "usage" | "context";
export type Direction = "higher_is_better" | "lower_is_better";
export type BaselineMethod = "fixed_value" | "trailing_window" | "reference_period";
export type RuleKind = "absolute" | "relative_pct";
export type RuleOperator = "lt" | "lte" | "gt" | "gte";

export const classLabel: Record<IndicatorClass, string> = {
  outcome: "Resultado",
  usage: "Uso",
  context: "Contexto",
};
export const classHelp: Record<IndicatorClass, string> = {
  outcome: "Mede o valor que o cliente realmente obtém. Necessita de regras completas para aprovar.",
  usage: "Mede atividade (ex.: logins). Sozinho não prova perda de valor. Regras opcionais.",
  context: "Informação de enquadramento (ex.: nº de utilizadores). Regras opcionais.",
};
export const directionLabel: Record<Direction, string> = {
  higher_is_better: "Maior é melhor",
  lower_is_better: "Menor é melhor",
};
export const baselineLabel: Record<BaselineMethod, string> = {
  fixed_value: "Valor fixo",
  trailing_window: "Janela móvel anterior",
  reference_period: "Período de referência",
};
export const kindLabel: Record<RuleKind, string> = {
  absolute: "Valor absoluto (na unidade do indicador)",
  relative_pct: "Percentagem do baseline (%)",
};
export const operatorLabel: Record<RuleOperator, string> = {
  lt: "menor que (<)",
  lte: "menor ou igual (≤)",
  gt: "maior que (>)",
  gte: "maior ou igual (≥)",
};
export const statusLabel = { draft: "Rascunho", approved: "Aprovado", superseded: "Substituído" } as const;

const fieldPt: Record<string, string> = {
  baseline_method: "falta o método de baseline",
  baseline_min_period_days: "falta o período mínimo do baseline (dias)",
  observation_window_days: "falta a janela de observação (dias)",
  comparison_window_days: "falta a janela de comparação (dias)",
  min_coverage_pct: "falta a cobertura mínima (%)",
  min_denominator: "falta o denominador mínimo",
};

/** Translates issues returned by value_profile_approval_issues() into Portuguese. */
export function translateIssue(issue: string): string {
  if (issue === "profile needs at least one outcome indicator")
    return "O perfil precisa de pelo menos um indicador de resultado.";
  const m = /^([^:]+): (.+)$/.exec(issue);
  if (!m) return issue;
  const key = m[1] ?? "";
  const rest = m[2] ?? "";
  const field = /^(\w+) missing$/.exec(rest)?.[1];
  if (field && fieldPt[field]) return `${key}: ${fieldPt[field]}`;
  if (rest === "deterioration rule incomplete") return `${key}: regra de deterioração incompleta`;
  if (rest === "recovery rule incomplete") return `${key}: regra de recuperação incompleta`;
  return issue;
}

export type IndicatorForm = {
  key: string;
  name: string;
  definition: string;
  classification: IndicatorClass;
  unit: string;
  direction: Direction;
  baseline_method: BaselineMethod | "";
  baseline_value: string;
  baseline_min_period_days: string;
  observation_window_days: string;
  comparison_window_days: string;
  min_coverage_pct: string;
  min_denominator: string;
  target_value: string;
  deterioration_kind: RuleKind | "";
  deterioration_operator: RuleOperator | "";
  deterioration_value: string;
  deterioration_consecutive_windows: string;
  recovery_kind: RuleKind | "";
  recovery_operator: RuleOperator | "";
  recovery_value: string;
  recovery_consecutive_windows: string;
};

export const emptyIndicatorForm: IndicatorForm = {
  key: "",
  name: "",
  definition: "",
  classification: "outcome",
  unit: "",
  direction: "higher_is_better",
  baseline_method: "",
  baseline_value: "",
  baseline_min_period_days: "",
  observation_window_days: "",
  comparison_window_days: "",
  min_coverage_pct: "",
  min_denominator: "",
  target_value: "",
  deterioration_kind: "",
  deterioration_operator: "",
  deterioration_value: "",
  deterioration_consecutive_windows: "",
  recovery_kind: "",
  recovery_operator: "",
  recovery_value: "",
  recovery_consecutive_windows: "",
};

export type IndicatorPayload = {
  key: string;
  name: string;
  definition: string | null;
  classification: IndicatorClass;
  unit: string;
  direction: Direction;
  baseline_method: BaselineMethod | null;
  baseline_value: number | null;
  baseline_min_period_days: number | null;
  observation_window_days: number | null;
  comparison_window_days: number | null;
  min_coverage_pct: number | null;
  min_denominator: number | null;
  target_value: number | null;
  deterioration_kind: RuleKind | null;
  deterioration_operator: RuleOperator | null;
  deterioration_value: number | null;
  deterioration_consecutive_windows: number | null;
  recovery_kind: RuleKind | null;
  recovery_operator: RuleOperator | null;
  recovery_value: number | null;
  recovery_consecutive_windows: number | null;
};

export function formFromRow(input: object): IndicatorForm {
  const row = input as Record<string, unknown>;
  const f = { ...emptyIndicatorForm };
  for (const k of Object.keys(f) as (keyof IndicatorForm)[]) {
    const v = row[k];
    if (v !== null && v !== undefined) (f as Record<string, unknown>)[k] = String(v);
  }
  return f;
}

export type ErrKey = keyof IndicatorForm | "deterioration_rule" | "recovery_rule";
export type FormErrors = Partial<Record<ErrKey, string>>;
type Result = { ok: true; data: IndicatorPayload } | { ok: false; errors: FormErrors };

/** Client-side mirror of the database CHECK constraints, for friendly messages. The database stays authoritative. */
export function buildIndicatorPayload(f: IndicatorForm): Result {
  const errors: FormErrors = {};
  const num = (field: keyof IndicatorForm, opts: { int?: boolean; positive?: boolean; max?: number } = {}) => {
    const raw = String(f[field]).trim().replace(",", ".");
    if (raw === "") return null;
    const n = Number(raw);
    if (!Number.isFinite(n)) {
      errors[field] = "Número inválido.";
      return null;
    }
    if (opts.int && !Number.isInteger(n)) errors[field] = "Use um número inteiro.";
    else if (opts.positive && n <= 0) errors[field] = "Tem de ser maior que 0.";
    else if (opts.max !== undefined && n > opts.max) errors[field] = `Máximo ${opts.max}.`;
    return n;
  };

  const key = f.key.trim();
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(key))
    errors.key = "Use minúsculas, números e _ , começando por uma letra (máx. 64).";
  const name = f.name.trim();
  if (name.length < 1 || name.length > 200) errors.name = "Indique um nome (até 200 caracteres).";
  const unit = f.unit.trim();
  if (unit.length < 1 || unit.length > 50) errors.unit = "Indique a unidade (até 50 caracteres).";
  if (f.definition.length > 4000) errors.definition = "Máximo 4000 caracteres.";

  const data: IndicatorPayload = {
    key,
    name,
    definition: f.definition.trim() || null,
    classification: f.classification,
    unit,
    direction: f.direction,
    baseline_method: f.baseline_method || null,
    baseline_value: num("baseline_value"),
    baseline_min_period_days: num("baseline_min_period_days", { int: true, positive: true }),
    observation_window_days: num("observation_window_days", { int: true, positive: true }),
    comparison_window_days: num("comparison_window_days", { int: true, positive: true }),
    min_coverage_pct: num("min_coverage_pct", { positive: true, max: 100 }),
    min_denominator: num("min_denominator", { int: true, positive: true }),
    target_value: num("target_value"),
    deterioration_kind: f.deterioration_kind || null,
    deterioration_operator: f.deterioration_operator || null,
    deterioration_value: num("deterioration_value"),
    deterioration_consecutive_windows: num("deterioration_consecutive_windows", { int: true, positive: true }),
    recovery_kind: f.recovery_kind || null,
    recovery_operator: f.recovery_operator || null,
    recovery_value: num("recovery_value"),
    recovery_consecutive_windows: num("recovery_consecutive_windows", { int: true, positive: true }),
  };

  if (data.baseline_method === "fixed_value" && data.baseline_value === null && !errors.baseline_value)
    errors.baseline_value = "Com baseline de valor fixo, indique o valor.";

  for (const p of ["deterioration", "recovery"] as const) {
    const parts = [data[`${p}_kind`], data[`${p}_operator`], data[`${p}_value`]];
    const filled = parts.filter((x) => x !== null).length;
    if (filled > 0 && filled < 3)
      errors[`${p}_rule`] = "Preencha tipo, operador e valor da regra, ou deixe os três vazios.";
  }

  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, data };
}
