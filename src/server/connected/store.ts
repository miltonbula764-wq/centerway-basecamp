import postgres from "postgres";
import { ConnectorError, type Config, jsonFetch, uuid } from "./security";
export type Actor = { sub: string; session_id: string };
export type DB = postgres.ReservedSql;
export class Store {
  readonly sql: ReturnType<typeof postgres>;
  constructor(readonly cfg: Config) {
    this.sql = postgres(cfg.database, {
      max: 5,
      ssl: cfg.local ? false : "verify-full",
      prepare: false,
      connect_timeout: 5,
      idle_timeout: 30,
      onnotice: () => {},
    });
  }
  async authenticate(request: Request): Promise<Actor> {
    const token = request.headers.get("authorization")?.match(/^Bearer ([\w.-]+)$/)?.[1];
    if (!token) throw new ConnectorError("authentication_required", 401);
    const user = await jsonFetch(this.cfg.authUrl + "/auth/v1/user", {
      headers: { apikey: this.cfg.publicKey, authorization: `Bearer ${token}` },
    }).catch(() => {
      throw new ConnectorError("authentication_required", 401);
    });
    let claims;
    try {
      claims = JSON.parse(Buffer.from(token.split(".")[1]!, "base64url").toString());
    } catch {
      throw new ConnectorError("authentication_required", 401);
    }
    if (
      claims.sub !== user.id ||
      claims.role !== "authenticated" ||
      !uuid(claims.sub) ||
      !uuid(claims.session_id) ||
      claims.exp * 1000 <= Date.now()
    )
      throw new ConnectorError("authentication_required", 401);
    return { sub: claims.sub, session_id: claims.session_id };
  }
  async verifyRuntime(db: DB) {
    const [r] =
      await db`SELECT rolsuper,rolbypassrls,rolinherit,pg_has_role(current_user,'centerway_connector_backend','MEMBER') AS member,pg_has_role(current_user,'service_role','MEMBER') AS service FROM pg_roles WHERE rolname=current_user`;
    if (!r || r["rolsuper"] || r["rolbypassrls"] || r["rolinherit"] || !r["member"] || r["service"])
      throw new ConnectorError("unsafe_connector_database_role", 503);
  }
  async actor<T>(
    tenant: string,
    actor: Actor,
    write: boolean,
    fn: (db: DB, a: { actor_id: string; membership_id: string; session_id: string }) => Promise<T>,
  ): Promise<T> {
    if (!uuid(tenant)) throw new ConnectorError("tenant_required");
    const db = await this.sql.reserve();
    let locked = false;
    try {
      await this.verifyRuntime(db);
      await db`SET ROLE centerway_connector_backend`;
      await db`SELECT set_config('request.jwt.claims',${JSON.stringify({ ...actor, role: "authenticated" })},false)`;
      const [row] = await db`SELECT connected_private.actor(${tenant}::uuid) AS actor`;
      if (write) {
        const [r] =
          await db`SELECT pg_try_advisory_lock(hashtextextended(${tenant},208)) AS locked`;
        locked = r!["locked"];
        if (!locked) throw new ConnectorError("connector_busy", 409);
      }
      return await fn(db, row!["actor"]);
    } finally {
      if (locked) await db`SELECT pg_advisory_unlock(hashtextextended(${tenant},208))`;
      await db`RESET ROLE`;
      await db`SELECT set_config('request.jwt.claims','',false)`;
      db.release();
    }
  }
  async backend<T>(fn: (db: DB) => Promise<T>) {
    const db = await this.sql.reserve();
    try {
      await this.verifyRuntime(db);
      await db`SET ROLE centerway_connector_backend`;
      return await fn(db);
    } finally {
      await db`RESET ROLE`;
      db.release();
    }
  }
}
