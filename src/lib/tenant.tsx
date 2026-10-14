import { createContext, useContext } from "react";

export type Role = "admin" | "operator" | "viewer";
export type UnitType = "organization" | "person";

export type TenantInfo = {
  id: string;
  name: string;
  subject_unit_type: UnitType;
  role: Role;
};

export type TenantCtx = {
  tenant: TenantInfo;
  tenants: TenantInfo[];
  user: { id: string; email: string };
  switchTenant: (id: string) => void;
  signOut: () => Promise<void>;
  canWrite: boolean;
  isAdmin: boolean;
};

export const TenantContext = createContext<TenantCtx | null>(null);

export function useTenant(): TenantCtx {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("Tenant context missing");
  return ctx;
}

/** Only the *preference* (an id) is stored; membership is always revalidated against the database. */
const PREF_KEY = "centerway.selectedTenant";

export function readPreferredTenant(): string | null {
  try {
    return window.localStorage.getItem(PREF_KEY);
  } catch {
    return null;
  }
}

export function writePreferredTenant(id: string | null) {
  try {
    if (id) window.localStorage.setItem(PREF_KEY, id);
    else window.localStorage.removeItem(PREF_KEY);
  } catch {
    /* ignore */
  }
}

/** Picks the preferred tenant only if the user is still a member; otherwise the first authorised one. */
export function pickTenant(tenants: { id: string }[], preferred: string | null): string | null {
  if (tenants.length === 0) return null;
  if (preferred && tenants.some((t) => t.id === preferred)) return preferred;
  return tenants[0]?.id ?? null;
}

// Guard against writes landing in a tenant that is no longer the active one.
let activeTenantId: string | null = null;
export function setActiveTenantId(id: string | null) {
  activeTenantId = id;
}
export const TENANT_CHANGED = "A empresa ativa mudou. A operação foi cancelada para não gravar na empresa errada.";
export function assertActiveTenant(id: string) {
  if (activeTenantId !== id) throw new Error(TENANT_CHANGED);
}

/** All tenant-scoped query keys start with ["t", tenantId] so they can be dropped together. */
export const tk = (tenantId: string, ...rest: unknown[]) => ["t", tenantId, ...rest];

export const roleLabel: Record<Role, string> = {
  admin: "Administrador",
  operator: "Operador",
  viewer: "Leitor",
};

export const unitLabel: Record<UnitType, string> = {
  organization: "Organizações (B2B)",
  person: "Pessoas (B2C)",
};
