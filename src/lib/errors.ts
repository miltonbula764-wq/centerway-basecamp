import { TENANT_CHANGED } from "./tenant";

type PgLike = { code?: string; message?: string };

export function friendlyError(e: unknown, context?: "subject"): string {
  const err = (e ?? {}) as PgLike;
  const msg = err.message ?? "";
  if (msg === TENANT_CHANGED) return msg;
  switch (err.code) {
    case "23505":
      if (context === "subject") return "Já existe um cliente com esta referência externa nesta empresa.";
      if (msg.includes("profile_id") || msg.includes("key")) return "Já existe um indicador com esta chave neste perfil.";
      return "Já existe um registo com este identificador.";
    case "42501":
      if (msg.includes("immutable")) return "Esta versão já não pode ser alterada. Crie uma nova versão.";
      return "Não tem permissão para esta ação.";
    case "23514":
      return "Algum valor não respeita os limites permitidos.";
    case "23502":
      return "Falta preencher um campo obrigatório.";
    case "22023":
      if (msg.includes("not approvable")) return "O perfil ainda não cumpre os requisitos de aprovação.";
      if (msg.includes("newer version")) return "Já existe uma versão mais recente aprovada.";
      if (msg.includes("only draft")) return "Só rascunhos podem ser aprovados.";
      return "Pedido inválido.";
    case "28000":
    case "PGRST301":
      return "A sessão expirou. Inicie sessão novamente.";
  }
  if (/fetch|network/i.test(msg)) return "Sem ligação ao servidor. Tente novamente.";
  return "Não foi possível concluir a operação.";
}
