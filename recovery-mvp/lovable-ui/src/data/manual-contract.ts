/** Input shape only; PostgreSQL remains the business/authorization authority. */
import type { OperationName, OperationRequest } from "@/domain/l01";
export interface Field {
  key: string;
  label: string;
  type?:
    | "number"
    | "instant"
    | "uuid"
    | "hash"
    | "boolean"
    | "source"
    | "factor"
    | "evidence"
    | undefined;
  choices?: string[] | undefined;
  nullable?: boolean | undefined;
}
export const f = (
  key: string,
  label: string,
  type?: Field["type"],
  choices?: string[],
  nullable?: boolean,
): Field => ({ key, label, type, choices, nullable });
export const SOURCE = [
  f("name", "Nome da fonte"),
  f("locator", "Localizador da fonte"),
  f("method", "Método da fonte"),
];
export const CONTRACT = [
  f("objective", "Objetivo"),
  f("expected_outcome", "Resultado esperado"),
  f("indicator", "Indicador de negócio"),
  f("unit", "Unidade"),
  f("measurement_method", "Método de medição"),
  f("direction", "Sentido", undefined, ["higher", "lower"]),
  f("baseline", "Baseline", "number"),
  f("minimum_acceptable", "Mínimo aceitável", "number"),
  f("target", "Alvo", "number"),
  f("baseline_start", "Início da baseline", "instant"),
  f("baseline_end", "Fim da baseline", "instant"),
  f("period_start", "Início da janela", "instant"),
  f("period_end", "Fim da janela", "instant"),
  f("source_id", "Fonte e versão", "source"),
  f("baseline_reference", "Referência da baseline"),
];
export const EVIDENCE = [
  f("contract_id", "Contrato", "uuid"),
  f("contract_revision", "Revisão do contrato", "number"),
  f("source_id", "Fonte e versão", "source"),
  f("evidence_type", "Tipo de evidência", undefined, ["outcome", "usage"]),
  f("quality", "Qualidade declarada", undefined, ["verified", "partial", "disputed"]),
  f("observed_value", "Valor observado", "number"),
  f("unit", "Unidade"),
  f("measurement_method", "Método de medição"),
  f("period_start", "Início da janela", "instant"),
  f("period_end", "Fim da janela", "instant"),
  f("reference", "Referência documental"),
  f("content_sha256", "SHA-256 do documento", "hash"),
];
export const FACTOR = [
  f("scope", "Âmbito", undefined, ["internal", "external", "mixed"]),
  f("category", "Categoria"),
  f("hypothesis", "Hipótese não comprovada"),
  f("requirement", "Requisito a verificar"),
  f("condition", "Condição a testar"),
  f("test_protocol", "Protocolo de verificação"),
  f("assessment_at", "Instante da condição", "instant"),
  f("control", "Controlo", undefined, ["saas", "client", "third_party", "unknown", "none"]),
  f("responsible_party", "Parte responsável (vazio se unknown/none)", undefined, undefined, true),
];
export const INVESTIGATION_EVIDENCE = [
  f("factor_id", "Fator e versão", "factor"),
  f("purpose", "Proposição", undefined, ["requirement_applies", "condition_met"]),
  f("kind", "Suporte", undefined, [
    "direct_observation",
    "document",
    "reproduction",
    "usage_context",
  ]),
  f("assertion", "Afirmação declarada", "boolean"),
  f("source_id", "Fonte e versão", "source"),
  f("reference", "Referência documental"),
  f("content_sha256", "SHA-256 do documento", "hash"),
  f("collected_at", "Instante da recolha", "instant"),
];
export const VERIFICATION = [
  f("evidence_id", "Evidência e versão", "evidence"),
  f("verdict", "Veredicto", undefined, ["confirmed", "rejected", "unverifiable"]),
  f("checked_assertion", "Afirmação verificada (null se unverifiable)", "boolean", undefined, true),
  f("method", "Método de verificação"),
  f("explanation", "Explicação da revisão"),
  f("source_id", "Fonte e versão", "source"),
  f("reference", "Referência documental"),
  f("content_sha256", "SHA-256 do documento", "hash"),
  f("checked_at", "Instante da revisão", "instant"),
];
export const ACTIONS: { value: OperationName; label: string }[] = [
  { value: "append_value", label: "F01 — Registar fonte, contrato ou observação" },
  { value: "detect", label: "F02 — Detetar deterioração" },
  { value: "open_investigation", label: "F03 — Abrir investigação" },
  { value: "append_investigation", label: "F03 — Registar fator, evidência ou revisão" },
  { value: "discover_company", label: "F03.1 — Descobrir fatores da empresa" },
  { value: "investigate", label: "F03 — Avaliar investigação" },
  { value: "intervene", label: "F04 — Pedir intervenção sintética" },
  { value: "undo", label: "F04 — Reverter execução sintética" },
  { value: "plan_recovery", label: "F05 — Definir janelas de recuperação" },
  { value: "evaluate_recovery", label: "F05 — Avaliar recuperação observada" },
];
export const ARGUMENTS: Record<OperationName, Field[]> = {
  append_value: [
    f("kind", "Tipo"),
    f("id", "ID do registo", "uuid"),
    f("expected_revision", "Revisão esperada (0 cria)", "number"),
    f("reason", "Motivo do registo"),
  ],
  detect: [
    f("contract_id", "Contrato a avaliar", "uuid"),
    f("as_of", "Instante de corte", "instant"),
    f("required_periods", "Períodos exigidos (2–120)", "number"),
  ],
  discover_company: [f("as_of", "Instante de corte", "instant")],
  open_investigation: [
    f("id", "ID da investigação", "uuid"),
    f("detection_id", "Deteção explícita", "uuid"),
    f("contract_revision", "Período da deteção", "number"),
    f("question", "Pergunta de investigação"),
  ],
  append_investigation: [
    f("investigation_id", "Investigação", "uuid"),
    f("kind", "Tipo"),
    f("id", "ID do registo", "uuid"),
    f("expected_revision", "Revisão esperada (0 cria)", "number"),
    f("reason", "Motivo do registo"),
  ],
  investigate: [
    f("investigation_id", "Investigação", "uuid"),
    f("as_of", "Instante de corte", "instant"),
  ],
  intervene: [
    f("investigation_id", "Investigação", "uuid"),
    f("report_id", "Relatório persistido", "uuid"),
  ],
  undo: [f("execution_id", "Execução a reverter", "uuid")],
  plan_recovery: [
    f("id", "ID do plano", "uuid"),
    f("decision_id", "Decisão de intervenção", "uuid"),
    f("pre_revision", "Janela anterior", "number"),
    f("post_revision", "Janela posterior", "number"),
    f("reason", "Motivo do plano"),
  ],
  evaluate_recovery: [
    f("plan_id", "Plano de recuperação", "uuid"),
    f("as_of", "Instante de corte", "instant"),
  ],
};
export function dataFields(op: OperationName, kind: string) {
  return op === "append_value"
    ? kind === "source"
      ? SOURCE
      : kind === "contract"
        ? CONTRACT
        : EVIDENCE
    : kind === "factor"
      ? FACTOR
      : kind === "evidence"
        ? INVESTIGATION_EVIDENCE
        : VERIFICATION;
}
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function fieldValue(field: Field, raw: string): unknown {
  if (!raw.trim()) {
    if (field.nullable) return null;
    throw new Error(`${field.label}: obrigatório`);
  }
  if (field.nullable && raw === "null") return null;
  if (field.type === "number") {
    const n = Number(raw);
    if (!Number.isFinite(n)) throw new Error(`${field.label}: número finito obrigatório`);
    return n;
  }
  if (
    field.type === "instant" &&
    (!/(Z|[+-]\d\d:\d\d)$/.test(raw) || !Number.isFinite(Date.parse(raw)))
  )
    throw new Error(`${field.label}: instante com fuso obrigatório`);
  if (field.type === "uuid" && !UUID.test(raw)) throw new Error(`${field.label}: UUID inválido`);
  if (field.type === "hash" && !/^[a-f0-9]{64}$/.test(raw))
    throw new Error(`${field.label}: SHA-256 inválido`);
  if (field.type === "boolean") {
    if (!["true", "false"].includes(raw)) throw new Error(`${field.label}: escolher true/false`);
    return raw === "true";
  }
  if (field.choices && !field.choices.includes(raw))
    throw new Error(`${field.label}: opção inválida`);
  if (raw.length > 2000) throw new Error(`${field.label}: máximo 2000 caracteres`);
  return raw;
}
export function parseFields(
  fields: Field[],
  values: Record<string, string>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    if (["source", "factor", "evidence"].includes(field.type ?? "")) {
      const [id, revision] = (values[field.key] ?? "").split("|");
      fieldValue({ ...field, type: "uuid" }, id ?? "");
      if (!revision || !/^[1-9]\d*$/.test(revision))
        throw new Error(`${field.label}: versão obrigatória`);
      result[field.key] = id;
      result[field.key.replace(/_id$/, "_revision")] = Number(revision);
    } else result[field.key] = fieldValue(field, values[field.key] ?? "");
  }
  return result;
}
export function validateRequest(request: OperationRequest) {
  fieldValue(f("request_id", "Pedido", "uuid"), request.request_id);
  for (const [key, value] of Object.entries(request.arguments)) {
    if (key === "id" || key.endsWith("_id")) fieldValue(f(key, key, "uuid"), String(value));
    if (
      [
        "expected_revision",
        "required_periods",
        "contract_revision",
        "pre_revision",
        "post_revision",
      ].includes(key) &&
      (typeof value !== "number" ||
        !Number.isInteger(value) ||
        value < (key === "expected_revision" ? 0 : 1))
    )
      throw new Error(`${key}: revisão/limite inteiro inválido`);
  }
  if (request.operation === "detect") {
    const a = request.arguments as { revisions: number[]; required_periods: number };
    if (
      !a.revisions.length ||
      a.revisions.length > 120 ||
      new Set(a.revisions).size !== a.revisions.length ||
      a.revisions.some((r) => !Number.isInteger(r) || r < 1) ||
      a.required_periods < 2 ||
      a.required_periods > 120
    )
      throw new Error("Selecione revisões e uma política de 2–120 períodos");
  }
  return request;
}
