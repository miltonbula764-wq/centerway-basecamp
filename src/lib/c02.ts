/** Labels for C02 (deterioration detector) results. Computation happens only in the database RPC. */
export type C02Status =
  | "deterioration_candidate" | "no_deterioration" | "persistent_condition"
  | "insufficient_data" | "insufficient_config" | "unsupported" | "not_evaluated";

export const c02StatusLabel: Record<C02Status, string> = {
  deterioration_candidate: "Sinal candidato de deterioração",
  no_deterioration: "Critério não satisfeito nas janelas analisadas",
  persistent_condition: "Condição persistente (não é piora nova)",
  insufficient_data: "Dados insuficientes",
  insufficient_config: "Configuração insuficiente",
  unsupported: "Não suportado",
  not_evaluated: "Não avaliado (contexto)",
};

const reasonPt: Record<string, string> = {
  no_observations: "sem observações (ausência não é zero)",
  coverage_below_minimum: "cobertura abaixo do mínimo",
  multiple_sources: "mais de uma fonte na janela (não combinadas)",
  ambiguous_correction: "cadeia de correções ambígua",
  ambiguous_last_value: "dois valores no mesmo instante final",
  denominator_missing: "sem dados de denominador",
  denominator_multiple_sources: "denominador com várias fontes",
  invalid_denominator: "denominador negativo",
  denominator_below_minimum: "denominador abaixo do mínimo",
  baseline_zero: "baseline igual a zero (variação relativa indefinida)",
  context_indicator: "indicador de contexto",
  text_indicator: "indicador de texto",
  deterioration_rule_missing: "falta a regra de deterioração",
  observation_window_missing: "falta a janela de observação",
  aggregation_missing: "falta a agregação",
  cadence_missing: "falta a cadência esperada",
  window_not_multiple_of_cadence: "janela não é múltiplo da cadência",
  comparison_not_multiple_of_cadence: "janela de comparação não é múltiplo da cadência",
  min_coverage_missing: "falta a cobertura mínima",
  min_denominator_missing: "falta o denominador mínimo",
  denominator_mode_missing: "falta o tipo de denominador",
  denominator_indicator_invalid: "indicador de denominador inválido",
  baseline_method_missing: "falta o método de baseline",
  baseline_method_unsupported: "baseline por período de referência ainda não suportado",
  baseline_value_missing: "falta o valor do baseline",
  comparison_window_missing: "falta a janela de comparação",
  baseline_min_period_missing: "falta o período mínimo do baseline",
  comparison_window_shorter_than_baseline_min: "janela de comparação menor que o período mínimo",
  operator_contradicts_direction: "operador contradiz a direção",
  relative_threshold_not_a_worsening: "limiar relativo não representa piora",
  sum_requires_equal_windows: "soma exige janelas de igual tamanho",
  source_mismatch_across_windows: "fontes diferentes entre janelas (não comparáveis sem regra explícita)",
  denominator_source_mismatch_across_windows: "denominador com fontes diferentes entre janelas",
  denominator_source_mismatch: "denominador de outra fonte que o numerador",
  denominator_coverage_below_minimum: "cobertura do denominador abaixo do mínimo",
  denominator_incompatible_observations: "dados do denominador de versão/unidade incompatível",
  denominator_ambiguous_correction: "cadeia de correções do denominador ambígua",
  denominator_cadence_missing: "falta a cadência própria do indicador de denominador",
  denominator_min_coverage_missing: "falta a cobertura mínima própria do indicador de denominador",
  denominator_window_not_multiple_of_cadence: "janela não é múltiplo da cadência do denominador",
  denominator_comparison_not_multiple_of_cadence: "janela de comparação não é múltiplo da cadência do denominador",
};
const scopePt: Record<string, string> = { reference: "referência", baseline: "baseline" };

export function translateReason(r: string): string {
  const m = /^([a-z_0-9]+):(.+)$/.exec(r);
  if (!m) return reasonPt[r] ?? r;
  const [, scope, code] = m;
  const s = scope!.startsWith("current_") ? `janela atual ${scope!.slice(8)}` : scopePt[scope!] ?? scope!;
  return `${s}: ${reasonPt[code!] ?? code}`;
}

export const analysisErrorPt: Record<string, string> = {
  "analysis: no approved value profile": "A empresa não tem perfil de valor aprovado.",
  "analysis: approved value profile changed": "O perfil aprovado mudou entretanto. Recarregue a página.",
  "analysis: unknown subject": "Cliente não encontrado nesta empresa.",
  "analysis: as_of in the future": "A data de corte não pode estar no futuro.",
};

/** Known limits per algorithm version. Shown next to every stored run; old runs are never recomputed. */
export const algorithmLimitations: Record<string, string[]> = {
  "c02-v1": [
    "Não verificava se a fonte era a mesma entre janelas (só dentro de cada janela).",
    "O denominador emparelhado só era verificado pela soma mínima, sem cobertura própria nem fonte igual ao numerador.",
    "Não guardava a prova da cadeia de correções usada.",
  ],
};
export const generalLimitations = [
  "Só compara as janelas analisadas: uma descida progressiva que fica acima do limiar, ou que o cruzou antes da janela de referência, não é sinalizada.",
  "“Critério não satisfeito” não prova ausência de piora; “condição persistente” não prova que não houve deterioração anterior.",
];
