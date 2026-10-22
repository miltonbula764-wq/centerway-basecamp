import { randomUUID } from "node:crypto";
import { Store, type Actor, type DB } from "./store";
import { PostHog, eventQuery, type Tokens } from "./posthog";
import {
  config,
  limitedText,
  ConnectorError,
  digest,
  random,
  same,
  seal,
  unseal,
  uuid,
  type Config,
} from "./security";

type Connection = {
  id: string;
  tenant_id: string;
  actor_id: string;
  membership_id: string;
  session_id: string;
  region: string;
  status: string;
  revoked_at: string | null;
  secret_cipher: string | null;
  project_id: number;
  profile_id: string;
  revision: number;
  context: any;
  selection: any;
  preview: any;
  watermarks: any;
  source: string;
  last_error: string | null;
  next_run_at: string;
}; // Private DB rows; never returned directly to the browser.
const day = 86400000;
const date = (d: number) => new Date(d).toISOString().slice(0, 10) + "T00:00:00Z";
const text = (s: unknown, max = 500) =>
  typeof s === "string" && s["trim"]().length > 0 && s["trim"]().length <= max
    ? s["trim"]()
    : (() => {
        throw new ConnectorError("invalid_input");
      })();
export class Connector {
  readonly store: Store;
  constructor(readonly cfg: Config) {
    this.store = new Store(cfg);
  }
  aad(c: Connection) {
    return `${c.tenant_id}:${c.id}:tokens`;
  }
  async current(db: DB, tenant: string): Promise<Connection> {
    const [c] =
      await db`SELECT * FROM connected_private.connections WHERE tenant_id=${tenant} AND status<>'revoked' ORDER BY created_at DESC LIMIT 1`;
    if (!c) throw new ConnectorError("connection_required", 409);
    return c as Connection;
  }
  async attempt(
    db: DB,
    c: Connection,
    kind: string,
    status: string,
    code: string | null = null,
    http: number | null = null,
    details: any = {},
  ) {
    await db`INSERT INTO connected_private.attempts(tenant_id,connection_id,actor_id,membership_id,session_id,kind,status,code,http_status,details,finished_at) VALUES(${c.tenant_id},${c.id},${c.actor_id},${c.membership_id},${c.session_id},${kind},${status},${code},${http},${db.json(details)},clock_timestamp())`;
  }
  provider(db: DB, c: Connection) {
    return new PostHog(this.cfg, c.region, async () => {
      const [q] =
        await db`SELECT count(*)::int AS n FROM connected_private.attempts WHERE connection_id=${c.id} AND kind='discovery' AND started_at>clock_timestamp()-interval '1 hour'`;
      if (q!["n"] >= 120) throw new ConnectorError("provider_budget_exhausted", 429, 3600);
      // Revalidate live consent and membership before every request, not just the first.
      const live = await this.current(db, c.tenant_id);
      if (live.id !== c.id || live.revoked_at) throw new ConnectorError("consent_revoked", 403);
      if (
        ["provider_rate_limited", "provider_budget_exhausted"].includes(live.last_error || "") &&
        new Date(live.next_run_at).getTime() > Date.now()
      )
        throw new ConnectorError(
          "provider_rate_limited",
          429,
          Math.ceil((new Date(live.next_run_at).getTime() - Date.now()) / 1000),
        );
      await this.attempt(db, c, "discovery", "requested");
    });
  }
  async tokens(db: DB, c: Connection) {
    if (!c.secret_cipher) throw new ConnectorError("reauthorization_required", 401);
    let t = unseal<Tokens>(c.secret_cipher, this.cfg.key, this.aad(c));
    if (t.expires_at < Date.now() + 60000) {
      try {
        const n = await this.provider(db, c).token(
          { grant_type: "refresh_token", refresh_token: t.refresh_token },
          Number(c.project_id),
        );
        t = { ...n, c01: t.c01 };
        await db`UPDATE connected_private.connections SET secret_cipher=${seal(t, this.cfg.key, this.aad(c))},token_expires_at=${new Date(t.expires_at)} WHERE id=${c.id}`;
      } catch (e) {
        await db`UPDATE connected_private.connections SET status='failed',last_error='refresh_requires_reauthorization' WHERE id=${c.id}`;
        throw e;
      }
    }
    if (t.project !== Number(c.project_id))
      throw new ConnectorError("project_binding_invalid", 403);
    return t;
  }
  async summary(tenant: string, actor: Actor) {
    return this.store.actor(
      tenant,
      actor,
      false,
      async (db) => (await db`SELECT connected_private.summary(${tenant}) AS value`)[0]!["value"],
    );
  }
  async start(tenant: string, actor: Actor, input: any) {
    return this.store.actor(tenant, actor, true, async (db, a) => {
      if (
        input.consent !== true ||
        !["us", "eu"].includes(input.region) ||
        !["organization", "person"].includes(input.unit)
      )
        throw new ConnectorError("consent_and_context_required");
      const context = {
        service: text(input.service),
        unit: input.unit,
        promise: text(input.promise, 2000),
        sources: text(input.sources, 500),
      };
      const [valid] = await db`SELECT connected_private.tenant_unit(${tenant}) AS unit`;
      if (valid!["unit"] !== input.unit) throw new ConnectorError("tenant_unit_immutable");
      const [oldSummary] = await db`SELECT connected_private.summary(${tenant}) AS value`;
      if (oldSummary?.["value"]?.needs_reauthorization)
        throw new ConnectorError("disconnect_before_reauthorizing", 409);
      const existing =
        await db`SELECT id FROM connected_private.connections WHERE tenant_id=${tenant} AND status<>'revoked'`;
      if (existing.length) throw new ConnectorError("disconnect_before_reauthorizing", 409);
      const id = randomUUID(),
        state = random(),
        nonce = random(),
        verifier = random(),
        stateId = randomUUID();
      const ph = new PostHog(this.cfg, input.region);
      const authorization = await ph.authorization(state, nonce, verifier);
      await db`BEGIN`;
      try {
        await db`INSERT INTO connected_private.connections(id,tenant_id,actor_id,membership_id,session_id,status,context,region,issuer,source,consent_at) VALUES(${id},${tenant},${a.actor_id},${a.membership_id},${a.session_id},'authorization_pending',${db.json(context)},${input.region},${ph.issuer},${"posthog:pending:" + id},clock_timestamp())`;
        await db`INSERT INTO connected_private.oauth_states(id,state_hash,nonce_hash,verifier_cipher,tenant_id,connection_id,actor_id,membership_id,session_id,region,issuer,expires_at) VALUES(${stateId},${digest(state)},${digest(nonce)},${seal(verifier, this.cfg.key, `${tenant}:${stateId}:pkce`)},${tenant},${id},${a.actor_id},${a.membership_id},${a.session_id},${input.region},${ph.issuer},clock_timestamp()+interval '10 minutes')`;
        await db`COMMIT`;
      } catch (e) {
        await db`ROLLBACK`;
        throw e;
      }
      return { authorization, nonce };
    });
  }
  async finish(tenant: string, actor: Actor, input: any, nonce: string) {
    return this.store.actor(tenant, actor, true, async (db) => {
      const state = text(input.state, 100),
        code = text(input.code, 2000);
      const c = await this.current(db, tenant);
      const [s] =
        await db`UPDATE connected_private.oauth_states SET consumed_at=clock_timestamp() WHERE state_hash=${digest(state)} AND connection_id=${c.id} AND consumed_at IS NULL AND expires_at>clock_timestamp() AND nonce_hash=${digest(nonce)} RETURNING *`;
      if (!s || !same(s["nonce_hash"], digest(nonce)))
        throw new ConnectorError("oauth_state_invalid", 403);
      // State consumption is committed before the network exchange, including failed callbacks.
      try {
        const verifier = unseal<string>(
          s["verifier_cipher"],
          this.cfg.key,
          `${tenant}:${s["id"]}:pkce`,
        );
        const ph = this.provider(db, c);
        const t = await ph.token({
          grant_type: "authorization_code",
          code,
          code_verifier: verifier,
          redirect_uri: this.cfg.redirect,
        });
        const project = await ph.get(`/api/projects/${t.project}/`, t);
        if (Number(project.id) !== t.project || typeof project.name !== "string")
          throw new ConnectorError("project_identity_invalid", 403);
        const types = await ph.groupTypes(t);
        await db`UPDATE connected_private.connections SET status=${types.length ? "needs_mapping" : "insufficient_data"},project_id=${t.project},project_name=${project.name.slice(0, 200)},source=${"posthog:" + c.region + ":" + t.project},secret_cipher=${seal(t, this.cfg.key, this.aad(c))},token_expires_at=${new Date(t.expires_at)},preview=${db.json({ group_types: types, limitations: ["Amostragem limitada; eventos não comprovam resultados ou causas. Sem grupos B2B não há clientes descobertos."] })},last_error=NULL WHERE id=${c.id}`;
        await this.attempt(db, c, "oauth", "completed");
        return { status: "connected" };
      } catch (e) {
        await db`UPDATE connected_private.connections SET status='failed',last_error='oauth_exchange_failed' WHERE id=${c.id}`;
        throw e;
      }
    });
  }
  async discover(tenant: string, actor: Actor, input: any) {
    return this.store.actor(tenant, actor, true, async (db) => {
      const c = await this.current(db, tenant);
      if (c.context.unit !== "organization")
        throw new ConnectorError("b2c_mapping_not_supported", 422);
      if (c.profile_id) throw new ConnectorError("mapping_already_prepared", 409);
      const t = await this.tokens(db, c),
        ph = this.provider(db, c);
      const types = await ph.groupTypes(t);
      const type = types.find((x: any) => x.index === input.group_type_index);
      if (!type) throw new ConnectorError("explicit_group_type_required");
      const { groups, truncated } = await ph.groups(t, type.index);
      const end = date(Date.now()),
        start = date(Date.parse(end) - 7 * day);
      const rows = await ph.query(t, eventQuery(type.index, start, end));
      const known = new Set(groups.map((g) => g.key));
      const events = new Set<string>();
      for (const row of rows) {
        if (
          row!["length"] !== 3 ||
          typeof row[0] !== "string" ||
          typeof row[1] !== "string" ||
          !Number.isSafeInteger(Number(row[2])) ||
          Number(row[2]) <= 0
        )
          throw new ConnectorError("aggregate_invalid", 502);
        if (known.has(row[0]) && row[1].length <= 200) events.add(row[1]);
      }
      const metrics = Array.from(events)
        .sort()
        .slice(0, 20)
        .map((event) => ({
          event,
          key: "ph_" + digest(event).slice(0, 24),
          name: event,
          unit: "events",
          aggregation: "sum",
          cadence_days: 1,
          classification: "unclassified",
        }));
      const remote_groups = groups.map((g) => ({
        ...g,
        ref: "posthog:" + digest(`${c.region}:${t.project}:${type.index}:${g.key}`),
      }));
      const preview = {
        group_types: types,
        group_type: type.name,
        group_type_index: type.index,
        groups: remote_groups.map((g) => ({ ref: g.ref, name: g.name })),
        remote_groups,
        metrics,
        coverage: { start, end, declared: false },
        truncated: truncated || events.size > 20,
        limitations: [
          "Amostra de sete dias UTC; até 200 grupos e 20 eventos. Não há zeros fabricados para grupos sem eventos.",
          "Contagem de eventos mede atividade; resultado e metas exigem confirmação humana.",
          "Grupos fora da amostra e B2C exigem percurso manual.",
        ],
      };
      await db`UPDATE connected_private.connections SET status=${groups.length && metrics.length ? "needs_mapping" : "insufficient_data"},preview=${db.json(preview)},last_error=NULL WHERE id=${c.id}`;
      return { status: "needs_mapping" };
    });
  }
  async prepare(tenant: string, actor: Actor, input: any) {
    return this.store.actor(tenant, actor, true, async (db) => {
      const c = await this.current(db, tenant);
      if (
        !input ||
        typeof input !== "object" ||
        Array.isArray(input) ||
        !Array.isArray(input.groups) ||
        input.groups.length < 1 ||
        input.groups.length > 200
      )
        throw new ConnectorError("confirmed_mapping_required");
      for (const g of input.groups) {
        if (!g || typeof g !== "object") throw new ConnectorError("invalid_input");
        text(g.ref, 300);
        text(g.name, 300);
      }
      const start = text(input.start, 30);
      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(start) ||
        !Number.isFinite(Date.parse(start)) ||
        new Date(start).toISOString().slice(0, 10) !== start ||
        Date.parse(start) >= Date.parse(date(Date.now())) ||
        Date.parse(start) < Date.now() - 366 * day
      )
        throw new ConnectorError("explicit_initial_window_required");
      if (
        input.confirmed !== true ||
        !Array.isArray(input.metrics) ||
        input.metrics.length < 1 ||
        input.metrics.length > 5
      )
        throw new ConnectorError("confirmation_required");
      for (const m of input.metrics) {
        if (
          !m ||
          typeof m !== "object" ||
          !/^[a-z][a-z0-9_]{0,63}$/.test(m.key) ||
          !["usage", "outcome", "context"].includes(m.classification) ||
          !["higher_is_better", "lower_is_better"].includes(m.direction)
        )
          throw new ConnectorError("indicator_mapping_invalid");
      }
      const [r] =
        await db`SELECT connected_private.prepare_profile(${c.id},${db.json(input)}) AS profile_id`;
      return r;
    });
  }
  async activate(tenant: string, actor: Actor) {
    return this.store.actor(tenant, actor, true, async (db) => {
      const c = await this.current(db, tenant);
      if (c.status === "active") return { status: "active" };
      if (c.status !== "needs_mapping") throw new ConnectorError("reauthorization_required", 409);
      const t = await this.tokens(db, c);
      await db`BEGIN`;
      try {
        const [r] = await db`SELECT connected_private.activate(${c.id}) AS key`;
        if (r!["key"].secret) t.c01 = r!["key"].secret;
        if (!t.c01) throw new ConnectorError("credential_requires_reconnect", 409);
        await db`UPDATE connected_private.connections SET status='active',secret_cipher=${seal(t, this.cfg.key, this.aad(c))},last_error=NULL,next_run_at=clock_timestamp() WHERE id=${c.id}`;
        await db`COMMIT`;
      } catch (e) {
        await db`ROLLBACK`;
        throw e;
      }
      return { status: "active" };
    });
  }
  async disconnect(tenant: string, actor: Actor) {
    return this.store.actor(tenant, actor, true, async (db) => {
      await db`SELECT connected_private.disconnect(${tenant})`;
      return { status: "revoked", provider_revocation: "queued" };
    });
  }
  async sync(tenant: string, actor: Actor) {
    return this.store.actor(tenant, actor, true, async (db) => {
      const c = await this.current(db, tenant);
      if (c.status !== "active") throw new ConnectorError("sync_not_active", 409);
      const [p] = await db`SELECT connected_private.approved_profile(${tenant}) AS id`;
      if (p!["id"] !== c.profile_id) {
        await db`UPDATE connected_private.connections SET status='needs_mapping',last_error='approved_profile_changed' WHERE id=${c.id}`;
        throw new ConnectorError("approved_profile_changed", 409);
      }
      const t = await this.tokens(db, c);
      if (!t.c01) throw new ConnectorError("credential_requires_reconnect", 409);
      const [pending] =
        await db`SELECT * FROM connected_private.batches WHERE connection_id=${c.id} AND status='pending' ORDER BY created_at LIMIT 1`;
      if (pending) {
        if (new Date(pending["due_at"]).getTime() > Date.now()) return { status: "backoff" };
        return this.deliver(db, c, t, pending);
      }
      const end = date(Date.now()),
        initial = c.selection.start + "T00:00:00Z";
      const wm = c.watermarks.through || initial;
      // One UTC day per job; two-day overlap, replay every third run to make forward progress.
      const count = Number(c.watermarks.pass || 0);
      const through = Math.max(
        Date.parse(initial),
        Date.parse(wm) - (count % 3 === 2 ? 0 : 2 * day),
      );
      if (through >= Date.parse(end)) return { status: "no_op" };
      const start = date(through),
        stop = date(Math.min(through + day, Date.parse(end)));
      const ph = this.provider(db, c);
      const raw = await ph.query(
        t,
        eventQuery(
          c.preview.group_type_index,
          start,
          stop,
          c.selection.metrics.map((m: any) => m.event),
        ),
      );
      const selected = new Map<string, string>();
      for (const g of c.preview.remote_groups) {
        if (c.selection.groups.some((s: any) => s["ref"] === g.ref)) selected.set(g.key, g.ref);
      }
      const metrics = new Map<string, any>(c.selection.metrics.map((m: any) => [m.event, m]));
      const rows: any[] = [];
      const identities = new Set<string>();
      for (const r of raw) {
        if (
          r!["length"] !== 3 ||
          typeof r[0] !== "string" ||
          typeof r[1] !== "string" ||
          !Number.isSafeInteger(Number(r[2])) ||
          Number(r[2]) <= 0
        )
          throw new ConnectorError("aggregate_invalid", 502);
        const ref = selected.get(r[0]),
          metric = metrics.get(r[1]);
        if (!ref || !metric) continue;
        const identity = ref + ":" + metric.key;
        if (identities.has(identity)) throw new ConnectorError("duplicate_aggregate", 502);
        identities.add(identity);
        const [old] =
          await db`SELECT * FROM connected_private.measurements WHERE connection_id=${c.id} AND revision=${c.revision} AND external_ref=${ref} AND indicator_key=${metric.key} AND observed_at=${start}`;
        if (old && Number(old["value_numeric"]) === Number(r[2])) continue;
        const key =
          "ph:" +
          digest(
            `${c.id}:${c.revision}:${ref}:${metric.key}:${start}:${r[2]}:${old?.["observation_key"] || ""}`,
          );
        let correction: string | undefined;
        if (old) {
          const [receipt] =
            await db`SELECT connected_private.receipt(${c.id},${old["observation_key"]}) AS value`;
          if (!uuid(receipt!["value"]?.id))
            throw new ConnectorError("correction_receipt_missing", 409);
          correction = receipt!["value"].id;
        }
        rows.push({
          subject_external_ref: ref,
          indicator_key: metric.key,
          observed_at: start,
          value_numeric: String(r[2]),
          unit: "events",
          idempotency_key: key,
          ...(correction ? { corrects_observation_id: correction } : {}),
        });
      }
      // Do not mark a truncated query as complete; no partial coverage or silent client loss.
      if (raw.length >= 10001 || rows.length > 1000)
        throw new ConnectorError("sync_slice_exceeds_limit", 422);
      const throughDate = date(Math.max(Date.parse(wm), Date.parse(stop)));
      const next = {
        ...c.watermarks,
        pass: count + 1,
        through: throughDate,
        indicators: Object.fromEntries(
          c.selection.metrics.map((m: any) => [
            m.key,
            { through: throughDate, project: Number(c.project_id), revision: c.revision },
          ]),
        ),
      };
      if (!rows.length) {
        await db`UPDATE connected_private.connections SET watermarks=${db.json(next)},last_success_at=clock_timestamp(),next_run_at=clock_timestamp()+interval '5 minutes',last_error=NULL WHERE id=${c.id}`;
        await this.attempt(db, c, "sync", "no_op");
        return { status: "no_op", rows: 0 };
      }
      const payload = {
        profile_id: c.profile_id,
        source: c.source,
        coverage: { start, end: stop, declared: true },
        rows,
      };
      if (Buffer.byteLength(JSON.stringify(payload)) > 1_000_000)
        throw new ConnectorError("sync_slice_exceeds_limit", 422);
      const id = randomUUID();
      await db`INSERT INTO connected_private.batches(id,tenant_id,connection_id,actor_id,membership_id,session_id,revision,profile_id,payload,payload_hash) VALUES(${id},${tenant},${c.id},${c.actor_id},${c.membership_id},${c.session_id},${c.revision},${c.profile_id},${db.json(payload)},${digest(JSON.stringify(payload))})`;
      // The committed request is retried verbatim even after process termination or an ambiguous response.
      return this.deliver(db, c, t, { id, payload, next });
    });
  }
  async deliver(db: DB, c: Connection, t: Tokens, batch: any) {
    const [q] =
      await db`SELECT count(*)::int AS n FROM connected_private.attempts WHERE connection_id=${c.id} AND kind='c01' AND started_at>clock_timestamp()-interval '1 minute'`;
    if (q!["n"] >= 10) throw new ConnectorError("c01_backpressure", 429);
    await this.current(db, c.tenant_id);
    await this.attempt(db, c, "c01", "requested");
    let response: Response;
    try {
      response = await fetch(this.cfg.c01, {
        method: "POST",
        redirect: "error",
        signal: AbortSignal.timeout(35000),
        headers: {
          authorization: `Bearer ${t.c01}`,
          "content-type": "application/json",
          "idempotency-key": batch.id,
        },
        body: JSON.stringify(batch.payload),
      });
    } catch {
      await this.defer(db, c, batch, 60, "c01_transport_unavailable");
      throw new ConnectorError("c01_transport_unavailable", 503);
    }
    const retry = Math.max(1, Math.min(3600, Number(response.headers.get("retry-after")) || 60));
    if (response.status === 429 || response.status >= 500) {
      await this.defer(db, c, batch, retry, "c01_retry_pending");
      throw new ConnectorError("c01_retry_pending", 503, retry);
    }
    let result: any;
    try {
      const body = await limitedText(response, 200000);
      if (body.length > 200000) throw new Error();
      result = JSON.parse(body);
    } catch {
      await this.defer(db, c, batch, 60, "c01_ambiguous_response");
      throw new ConnectorError("c01_ambiguous_response", 503);
    }
    if (
      !response.ok ||
      result.status !== "completed" ||
      result.row_count !== batch.payload.rows.length ||
      result.rejected !== 0 ||
      result.inserted + result.duplicates !== batch.payload.rows.length
    ) {
      await db`UPDATE connected_private.batches SET status='blocked' WHERE id=${batch.id}`;
      await db`UPDATE connected_private.connections SET status='failed',last_error='c01_rejected' WHERE id=${c.id}`;
      await this.attempt(db, c, "c01", "rejected", "c01_rejected", response.status);
      throw new ConnectorError("c01_rejected", 422);
    }
    await db`BEGIN`;
    try {
      for (const r of batch.payload.rows) {
        await db`INSERT INTO connected_private.measurements(tenant_id,connection_id,actor_id,membership_id,session_id,revision,external_ref,indicator_key,observed_at,value_numeric,observation_key,batch_id) VALUES(${c.tenant_id},${c.id},${c.actor_id},${c.membership_id},${c.session_id},${c.revision},${r!["subject_external_ref"]},${r!["indicator_key"]},${r!["observed_at"]},${r!["value_numeric"]},${r!["idempotency_key"]},${batch.id}) ON CONFLICT(connection_id,revision,external_ref,indicator_key,observed_at) DO UPDATE SET previous_key=connected_private.measurements.observation_key,observation_key=EXCLUDED.observation_key,value_numeric=EXCLUDED.value_numeric,batch_id=EXCLUDED.batch_id`;
      }
      const stop = batch.payload.coverage.end,
        wm = c.watermarks.through || c.selection.start + "T00:00:00Z";
      const watermarks = batch.next || {
        ...c.watermarks,
        pass: Number(c.watermarks.pass || 0) + 1,
        through: date(Math.max(Date.parse(wm), Date.parse(stop))),
        indicators: Object.fromEntries(
          c.selection.metrics.map((m: any) => [
            m.key,
            {
              through: date(Math.max(Date.parse(wm), Date.parse(stop))),
              project: Number(c.project_id),
              revision: c.revision,
            },
          ]),
        ),
      };
      await db`UPDATE connected_private.batches SET status='completed' WHERE id=${batch.id}`;
      await db`UPDATE connected_private.connections SET watermarks=${db.json(watermarks)},last_success_at=clock_timestamp(),last_error=NULL,next_run_at=clock_timestamp()+interval '5 minutes' WHERE id=${c.id}`;
      await this.attempt(db, c, "sync", "completed", null, response.status, {
        rows: batch.payload.rows.length,
        inserted: result.inserted,
        duplicates: result.duplicates,
      });
      await db`COMMIT`;
    } catch (e) {
      await db`ROLLBACK`;
      throw e;
    }
    return {
      status: "completed",
      rows: batch.payload.rows.length,
      inserted: result.inserted,
      duplicates: result.duplicates,
    };
  }
  async defer(db: DB, c: Connection, batch: any, seconds: number, code: string) {
    await db`UPDATE connected_private.batches SET due_at=clock_timestamp()+${seconds}*interval '1 second' WHERE id=${batch.id}`;
    await db`UPDATE connected_private.connections SET last_error=${code},next_run_at=clock_timestamp()+${seconds}*interval '1 second' WHERE id=${c.id}`;
    await this.attempt(db, c, "c01", "retry_pending", code);
  }
  async worker() {
    const candidates = await this.store.backend(
      async (db) => await db`SELECT connected_private.worker_candidates() AS actor`,
    );
    const result = [];
    for (const row of candidates) {
      const a = row!["actor"];
      try {
        result.push(await this.sync(a.tenant, a));
      } catch (e) {
        const code = e instanceof ConnectorError ? e.code : "internal_error";
        if (code !== "connector_busy") {
          try {
            await this.store.actor(a.tenant, a, true, async (db) => {
              const c = await this.current(db, a.tenant);
              const retry = e instanceof ConnectorError ? e.retryAfter : 60;
              await db`UPDATE connected_private.connections SET last_error=${code},last_attempt_at=clock_timestamp(),next_run_at=clock_timestamp()+${retry}*interval '1 second',status=CASE WHEN ${code}='provider_authorization_lost' THEN 'failed' ELSE status END WHERE id=${c.id}`;
              await this.attempt(db, c, "sync", "failed", code);
            });
          } catch {
            /* Membership/session revocation takes precedence over worker diagnostics. */
          }
        }
        result.push({ status: "failed", code });
      }
    }
    await this.revokeQueued();
    return result;
  }
  async revokeQueued() {
    await this.store.backend(async (db) => {
      const list =
        await db`SELECT * FROM connected_private.revocations WHERE next_try_at<=clock_timestamp() ORDER BY created_at LIMIT 20`;
      for (const r of list) {
        try {
          const region =
            r!["issuer"] === this.cfg.mock
              ? "us"
              : r!["issuer"] === "https://us.posthog.com"
                ? "us"
                : r!["issuer"] === "https://eu.posthog.com"
                  ? "eu"
                  : null;
          if (!region) throw new ConnectorError("issuer_invalid");
          const t = unseal<Tokens>(
            r!["secret_cipher"],
            this.cfg.key,
            `${r!["tenant_id"]}:${r!["connection_id"]}:tokens`,
          );
          await new PostHog(this.cfg, region).revoke(t);
          await db`DELETE FROM connected_private.revocations WHERE id=${r!["id"]}`;
        } catch {
          await db`UPDATE connected_private.revocations SET tries=tries+1,last_error='provider_revocation_pending',next_try_at=clock_timestamp()+interval '5 minutes' WHERE id=${r!["id"]}`;
        }
      }
    });
  }
}
let singleton: Connector | undefined;
export async function handler(request: Request): Promise<Response> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  };
  let failedContext:
    { connector: Connector; actor: Actor; tenant: string; action: string } | undefined;
  try {
    const cfg = config();
    singleton ||= new Connector(cfg);
    const connector = singleton;
    const url = new URL(request.url),
      action = url.pathname.split("/").pop();
    if (action === "metadata" && request.method === "GET")
      return Response.json(
        {
          client_id: cfg.clientId,
          client_name: "CENTERWAY",
          redirect_uris: [cfg.redirect],
          "com.posthog": {
            scopes: ["project:read", "group:read", "query:read"],
            optional_scopes: [],
          },
        },
        { headers },
      );
    if (!["GET", "POST"].includes(request.method))
      throw new ConnectorError("method_not_allowed", 405);
    if (request.method === "POST" && request.headers.get("origin") !== cfg.origin)
      throw new ConnectorError("origin_invalid", 403);
    if (
      request.method === "POST" &&
      !request.headers.get("content-type")?.startsWith("application/json")
    )
      throw new ConnectorError("json_required", 415);
    const actor = await connector.store.authenticate(request);
    let input: any = {};
    if (request.method === "POST") {
      const body = await limitedText(request, 128000);
      if (body.length > 128000) throw new ConnectorError("request_too_large", 413);
      try {
        input = JSON.parse(body);
        if (!input || typeof input !== "object" || Array.isArray(input))
          throw new ConnectorError("json_object_required");
      } catch {
        throw new ConnectorError("json_invalid");
      }
    }
    const tenant = request.method === "GET" ? url.searchParams.get("tenant") : input.tenant;
    if (!uuid(tenant)) throw new ConnectorError("tenant_required");
    failedContext = { connector, actor, tenant, action: action || "" };
    let result;
    if (action === "status" && request.method === "GET")
      result = await connector.summary(tenant, actor);
    else if (action === "start" && request.method === "POST") {
      const r = await connector.start(tenant, actor, input);
      headers["set-cookie"] =
        `cw_posthog_nonce=${r!["nonce"]}; HttpOnly; SameSite=Lax; Path=/api/connected; Max-Age=600${cfg.local ? "" : "; Secure"}`;
      result = { authorization: r!["authorization"] };
    } else if (action === "finish" && request.method === "POST") {
      const nonce =
        request.headers.get("cookie")?.match(/(?:^|;\s*)cw_posthog_nonce=([\w-]+)/)?.[1] || "";
      result = await connector.finish(tenant, actor, input, nonce);
      headers["set-cookie"] =
        "cw_posthog_nonce=; HttpOnly; SameSite=Lax; Path=/api/connected; Max-Age=0";
    } else if (action === "discover" && request.method === "POST")
      result = await connector.discover(tenant, actor, input);
    else if (action === "prepare" && request.method === "POST")
      result = await connector.prepare(tenant, actor, input.selection);
    else if (action === "activate" && request.method === "POST")
      result = await connector.activate(tenant, actor);
    else if (action === "sync" && request.method === "POST")
      result = await connector.sync(tenant, actor);
    else if (action === "disconnect" && request.method === "POST") {
      result = await connector.disconnect(tenant, actor);
      await connector.revokeQueued();
    } else throw new ConnectorError("not_found", 404);
    return Response.json(result, { headers });
  } catch (e) {
    const known = e instanceof ConnectorError;
    const dbAuth = (e as any)?.code === "42501";
    const status = known ? e.status : dbAuth ? 403 : (e as any)?.code === "22023" ? 422 : 500;
    if (failedContext && known && ![403, 409].includes(status)) {
      const { connector, actor, tenant, action } = failedContext;
      try {
        await connector.store.actor(tenant, actor, false, async (db) => {
          const c = await connector.current(db, tenant);
          await db`UPDATE connected_private.connections SET last_error=${e.code},status=CASE WHEN ${e.code}='provider_authorization_lost' THEN 'failed' ELSE status END,last_attempt_at=clock_timestamp(),next_run_at=CASE WHEN ${status}=429 THEN clock_timestamp()+${e.retryAfter}*interval '1 second' ELSE next_run_at END WHERE id=${c.id}`;
          await connector.attempt(
            db,
            c,
            action === "finish" ? "oauth" : "sync",
            "failed",
            e.code,
            status,
          );
        });
      } catch {
        /* Revoked or missing consent: do not manufacture history. */
      }
    }
    // Never log upstream response bodies, SQL parameters, codes or credentials.
    return Response.json(
      {
        error: known
          ? e.code
          : dbAuth
            ? "admin_session_required"
            : status === 422
              ? "profile_contract_not_satisfied"
              : "connector_failed",
      },
      {
        status,
        headers: {
          ...headers,
          ...(status === 429 || status === 503
            ? { "retry-after": String(known ? e.retryAfter : 60) }
            : {}),
        },
      },
    );
  }
}
