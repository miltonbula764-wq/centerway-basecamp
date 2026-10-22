import {
  challenge,
  ConnectorError,
  type Config,
  jsonFetch,
  literal,
  scopes,
  validScopes,
} from "./security";
export type Tokens = {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  project: number;
  c01?: string | undefined;
};
export class PostHog {
  readonly issuer: string;
  readonly api: string;
  constructor(
    private cfg: Config,
    region: string,
    private budget: () => Promise<void> = async () => {},
  ) {
    if (!["us", "eu"].includes(region)) throw new ConnectorError("invalid_region");
    this.issuer = cfg.mock || `https://${region}.posthog.com`;
    this.api = this.issuer;
  }
  async metadata() {
    const m = await jsonFetch(this.issuer + "/.well-known/oauth-authorization-server");
    if (
      m.issuer !== this.issuer ||
      !m.code_challenge_methods_supported?.includes("S256") ||
      !m.response_types_supported?.includes("code") ||
      !scopes.every((s) => m.scopes_supported?.includes(s)) ||
      !m.token_endpoint_auth_methods_supported?.includes("none")
    )
      throw new ConnectorError("oauth_metadata_invalid", 502);
    for (const [k, path] of Object.entries({
      authorization_endpoint: "/oauth/authorize/",
      token_endpoint: "/oauth/token/",
      revocation_endpoint: "/oauth/revoke/",
    })) {
      if (m[k] !== this.issuer + path) throw new ConnectorError("oauth_endpoint_invalid", 502);
    }
    const resource = await jsonFetch(this.api + "/.well-known/oauth-protected-resource");
    if (
      resource.resource !== this.api ||
      !Array.isArray(resource.authorization_servers) ||
      resource.authorization_servers.length !== 1 ||
      resource.authorization_servers[0] !== this.issuer ||
      !resource.bearer_methods_supported?.includes("header") ||
      !scopes.every((s) => resource.scopes_supported?.includes(s))
    )
      throw new ConnectorError("oauth_resource_metadata_invalid", 502);
    return m;
  }
  async authorization(state: string, nonce: string, verifier: string) {
    const m = await this.metadata();
    const u = new URL(m.authorization_endpoint);
    for (const [k, v] of Object.entries({
      client_id: this.cfg.clientId,
      redirect_uri: this.cfg.redirect,
      response_type: "code",
      scope: scopes.join(" "),
      state,
      nonce,
      code_challenge: challenge(verifier),
      code_challenge_method: "S256",
      required_access_level: "project",
    }))
      u.searchParams.set(k, v);
    return u.href;
  }
  async token(values: Record<string, string>, expected?: number): Promise<Tokens> {
    const m = await this.metadata();
    const t = await jsonFetch(m.token_endpoint, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: this.cfg.clientId, ...values }),
    });
    if (
      typeof t.access_token !== "string" ||
      t.access_token.length < 1 ||
      t.access_token.length > 8192 ||
      typeof t.refresh_token !== "string" ||
      t.refresh_token.length < 1 ||
      t.refresh_token.length > 8192 ||
      t.token_type?.toLowerCase() !== "bearer" ||
      !validScopes(t.scope) ||
      !Number.isFinite(t.expires_in) ||
      t.expires_in <= 0 ||
      t.expires_in > 86400
    )
      throw new ConnectorError("oauth_token_invalid", 502);
    const i = await jsonFetch(this.issuer + "/oauth/introspect/", {
      method: "POST",
      headers: {
        authorization: `Bearer ${t.access_token}`,
        "content-type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ token: t.access_token }),
    });
    if (
      i.active !== true ||
      i.is_impersonated === true ||
      i.client_id !== this.cfg.clientId ||
      !validScopes(i.scope) ||
      !Array.isArray(i.scoped_teams) ||
      i.scoped_teams.length !== 1 ||
      !Number.isSafeInteger(i.scoped_teams[0]) ||
      i.scoped_teams[0] <= 0 ||
      !Array.isArray(i.scoped_organizations) ||
      i.scoped_organizations.length ||
      !Number.isFinite(i.exp) ||
      i.exp * 1000 <= Date.now() ||
      (expected !== undefined && i.scoped_teams[0] !== expected)
    )
      throw new ConnectorError("oauth_project_or_scope_invalid", 403);
    if (
      !Array.isArray(t.scoped_teams) ||
      t.scoped_teams.length !== 1 ||
      t.scoped_teams[0] !== i.scoped_teams[0] ||
      !Array.isArray(t.scoped_organizations) ||
      t.scoped_organizations.length
    )
      throw new ConnectorError("oauth_project_or_scope_invalid", 403);
    return {
      access_token: t.access_token,
      refresh_token: t.refresh_token,
      expires_at: Math.min(Date.now() + t.expires_in * 1000, i.exp * 1000),
      project: i.scoped_teams[0],
    };
  }
  async get(path: string, t: Tokens) {
    if (!path.startsWith(`/api/projects/${t.project}/`) || path.includes(".."))
      throw new ConnectorError("project_path_invalid");
    await this.budget();
    return jsonFetch(this.api + path, { headers: { authorization: `Bearer ${t.access_token}` } });
  }
  async query(t: Tokens, query: string) {
    await this.budget();
    const r = await jsonFetch(`${this.api}/api/projects/${t.project}/query/`, {
      method: "POST",
      headers: { authorization: `Bearer ${t.access_token}`, "content-type": "application/json" },
      body: JSON.stringify({ query: { kind: "HogQLQuery", query } }),
    });
    if (!Array.isArray(r.results) || r.results.length > 10000 || r.error)
      throw new ConnectorError("query_incomplete", 502);
    return r.results as unknown[][];
  }
  async groupTypes(t: Tokens) {
    const r = await this.get(`/api/projects/${t.project}/groups_types/`, t);
    const list = Array.isArray(r) ? r : r.results;
    if (!Array.isArray(list) || list.length > 100)
      throw new ConnectorError("group_types_invalid", 502);
    return list
      .map((x) => ({ index: x.group_type_index, name: x.group_type }))
      .filter(
        (x) =>
          Number.isInteger(x.index) &&
          x.index >= 0 &&
          x.index < 5 &&
          typeof x.name === "string" &&
          x.name.length <= 100,
      );
  }
  async groups(t: Tokens, index: number) {
    const result: { key: string; name: string }[] = [];
    const seen = new Set<string>();
    let cursor = "";
    let truncated = false;
    for (let page = 0; page < 3; page++) {
      const path =
        `/api/projects/${t.project}/groups/?group_type_index=${index}&limit=100` +
        (cursor ? "&cursor=" + encodeURIComponent(cursor) : "");
      const r = await this.get(path, t);
      if (!Array.isArray(r.results) || r.results.length > 100)
        throw new ConnectorError("groups_invalid", 502);
      for (const g of r.results) {
        if (typeof g.group_key !== "string" || !g.group_key || g.group_key.length > 500)
          throw new ConnectorError("group_identity_invalid", 502);
        if (seen.has(g.group_key)) continue;
        seen.add(g.group_key);
        if (result.length >= 200) {
          truncated = true;
          break;
        }
        result.push({
          key: g.group_key,
          name:
            typeof g.group_properties?.name === "string"
              ? g.group_properties.name.slice(0, 300)
              : `Grupo ${result.length + 1}`,
        });
      }
      if (!r.next) break;
      const next = new URL(r.next, this.api);
      if (
        next.origin !== new URL(this.api).origin ||
        next.pathname !== `/api/projects/${t.project}/groups/` ||
        next.searchParams.get("group_type_index") !== String(index)
      )
        throw new ConnectorError("pagination_target_invalid", 502);
      const n = next.searchParams.get("cursor");
      if (!n || n === cursor || n.length > 2000)
        throw new ConnectorError("pagination_cursor_invalid", 502);
      cursor = n;
      if (page === 2 || result.length >= 200) truncated = true;
    }
    return { groups: result, truncated };
  }
  async revoke(t: Tokens) {
    const m = await this.metadata();
    // RFC7009 may return an empty successful response.
    const r = await fetch(m.revocation_endpoint, {
      method: "POST",
      redirect: "error",
      signal: AbortSignal.timeout(15000),
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: this.cfg.clientId,
        token: t.refresh_token,
        token_type_hint: "refresh_token",
      }),
    });
    if (!r.ok) throw new ConnectorError("revocation_pending", 503);
  }
}
export function eventQuery(groupIndex: number, start: string, end: string, events?: string[]) {
  if (!Number.isInteger(groupIndex) || groupIndex < 0 || groupIndex > 4)
    throw new ConnectorError("invalid_group_type");
  // Official EventsTable: $group_N is the native FK to group_key for the selected project/index.
  const group = "events.`$group_" + groupIndex + "`";
  const utc = (value: string) => {
    if (
      !/^\d{4}-\d{2}-\d{2}T00:00:00Z$/.test(value) ||
      !Number.isFinite(Date.parse(value)) ||
      new Date(value).toISOString().replace(".000Z", "Z") !== value
    )
      throw new ConnectorError("invalid_utc_boundary");
    return `toDateTime(${literal(value.slice(0, 10) + " 00:00:00")}, 'UTC')`;
  };
  if (Date.parse(end) <= Date.parse(start)) throw new ConnectorError("invalid_utc_window");
  return `SELECT ${group} AS customer, event, count() AS amount FROM events WHERE timestamp >= ${utc(start)} AND timestamp < ${utc(end)} AND ${group} != ''${events ? " AND event IN (" + events.map(literal).join(",") + ")" : ""} GROUP BY customer, event ORDER BY customer, event LIMIT 10001`;
}
