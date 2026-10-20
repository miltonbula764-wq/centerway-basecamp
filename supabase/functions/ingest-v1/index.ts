import { ingestionHandler } from "../_shared/ingestion-handler.ts";
// Only the public anonymous key is used. The integration RPC enforces its own narrow credential scope.
const url = Deno.env.get("SUPABASE_URL");
const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
if (!url || !anonKey) throw new Error("Supabase public endpoint configuration required");
Deno.serve(ingestionHandler({ url, anonKey }));
