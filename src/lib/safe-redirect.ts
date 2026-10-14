/** Only same-origin app paths are allowed as post-login destinations. */
export function safeRedirect(target: unknown, fallback = "/app"): string {
  if (typeof target !== "string") return fallback;
  if (!target.startsWith("/") || target.startsWith("//") || target.startsWith("/\\")) return fallback;
  if (target.startsWith("/auth")) return fallback;
  return target;
}
