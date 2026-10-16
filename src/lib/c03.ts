/** Labels for C03 (evidence builder) results. Assembly happens only in the database RPC. */
import { translateReason } from "@/lib/c02";

export type C03IndicatorStatus = "complete" | "insufficient" | "context_facts";
export type C03AttemptStatus = "built" | "reused" | "rejected" | "failed";
export type C03RefRole = "numerator" | "denominator" | "superseded" | "denominator_superseded" | "unclassified";

export const c03StatusLabel: Record<C03IndicatorStatus, string> = {
  complete: "Evidência íntegra",
  insufficient: "Evidência insuficiente",
  context_facts: "Factos de contexto",
};

export const c03AttemptLabel: Record<C03AttemptStatus, string> = {
  built: "Pacote montado",
  reused: "Pacote existente reutilizado",
  rejected: "Montagem recusada",
  failed: "Falha na montagem",
};

export const c03RoleLabel: Record<C03RefRole, string> = {
  numerator: "Numerador (efetiva)",
  denominator: "Denominador (efetiva)",
  superseded: "Substituída por correção",
  denominator_superseded: "Denominador substituído por correção",
  unclassified: "Sem classificação (análise antiga)",
};

/** Códigos de recusa/falha devolvidos pela RPC (migration 0010). */
const c03CodePt: Record<string, string> = {
  run_not_found: "A análise pedida não existe nesta empresa.",
  unknown_c02_algorithm: "Versão de algoritmo da análise desconhecida.",
  c02_result_subject_mismatch: "Resultado da análise pertence a outro cliente.",
  c02_result_algorithm_mismatch: "Resultado da análise foi calculado por outra versão do algoritmo.",
  c02_result_parameters_mismatch: "Parâmetros guardados não correspondem ao indicador.",
  ref_missing: "Uma observação referenciada não existe nesta empresa.",
  ref_wrong_subject: "Uma observação referenciada pertence a outro cliente.",
  ref_after_cutoff: "Uma observação foi importada depois da data de corte da análise.",
  ref_wrong_indicator: "Uma observação referenciada pertence a outro indicador.",
  ref_payload_hash_mismatch: "O conteúdo de uma observação não corresponde ao hash guardado.",
  ref_outside_window: "Uma observação está fora da janela temporal referenciada.",
  ref_value_incompatible: "Valor ou unidade incompatível com o papel referenciado.",
  ref_not_effective: "Uma observação referenciada como efetiva já foi substituída por correção.",
  correction_chain_invalid: "A cadeia de correções não corresponde ao registado na análise.",
  ref_set_mismatch: "O conjunto de referências não corresponde às observações da análise.",
  window_boundary_mismatch: "Os limites de uma janela não correspondem aos parâmetros da análise.",
  calculation_mismatch: "Um cálculo guardado não é reproduzido pelas observações referenciadas.",
  baseline_mismatch: "O valor de baseline guardado não é reproduzido pela configuração.",
  ref_changed_during_build: "As referências mudaram durante a montagem; nada foi gravado.",
};

/** Motivos por indicador (coluna reasons de c03_indicators). */
const c03ReasonPt: Record<string, string> = {
  no_temporal_evaluation: "indicador sem avaliação temporal (contexto/texto)",
  context_not_collected_by_c02: "a análise não recolheu observações para este indicador",
  legacy_c02_v1_known_gaps: "análise calculada pela versão antiga (c02-v1), com lacunas conhecidas",
  c02_insufficient_data: "a análise já tinha dados insuficientes",
  c02_insufficient_config: "a análise já tinha configuração insuficiente",
  ref_budget_exceeded:
    "o número de referências excede o limite de armazenamento; nenhuma referência foi guardada para não apresentar um pacote parcial como completo",
};

export function translateC03Code(code: string | null | undefined): string {
  if (!code) return "Sem detalhe adicional.";
  if (code.startsWith("internal_error:")) return `Erro interno (${code.slice("internal_error:".length)}). A tentativa ficou registada.`;
  return c03CodePt[code] ?? `Código não reconhecido: ${code}`;
}

export function translateC03Reason(r: string): string {
  return c03ReasonPt[r] ?? translateReason(r);
}
