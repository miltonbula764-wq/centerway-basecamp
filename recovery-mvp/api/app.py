"""L01 HTTP transport. Business decisions remain exclusively in F01–F06."""
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from flask import Flask, request, g, jsonify
from werkzeug.exceptions import HTTPException
from session_store import session_store

FIELDS = {
    'append_value': 'kind id expected_revision reason data',
    'detect': 'contract_id revisions as_of required_periods',
    'discover_company': 'as_of',
    'open_investigation': 'id detection_id contract_revision question',
    'append_investigation': 'investigation_id kind id expected_revision reason data',
    'investigate': 'investigation_id as_of',
    'intervene': 'investigation_id report_id', 'undo': 'execution_id',
    'plan_recovery': 'id decision_id pre_revision post_revision reason',
    'evaluate_recovery': 'plan_id as_of',
}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def password_matches(password, encoded):
    return hmac.compare_digest(password_hash(password, encoded.split(':')[0]), encoded)


def canonical_uuid(value):
    if not isinstance(value, str):
        raise ValueError('uuid')
    return str(UUID(value))


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


class APIError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class Database:
    def __init__(self, demo):
        self.demo = demo

    def call(self, user, kind, params=()):
        dsn = conninfo_to_dict(user['dsn'])
        if not self.demo and dsn.get('sslmode') != 'verify-full':
            raise APIError(503, 'database_configuration')
        with psycopg.connect(user['dsn'], connect_timeout=5) as conn:
            with conn.cursor() as cur:
                if kind == 'manual_context':
                    cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                cur.execute("SET LOCAL statement_timeout='15s'")
                cur.execute("SET LOCAL lock_timeout='3s'")
                cur.execute("""SELECT session_user::text,current_user::text,
                  r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication,
                  pg_has_role(session_user,'centerway_api','USAGE'),
                  has_table_privilege(session_user,'centerway.intervention_policies','INSERT'),
                  EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='centerway' AND nspowner=r.oid),
                  EXISTS(SELECT 1 FROM pg_database WHERE datname=current_database() AND datdba=r.oid),
                  has_schema_privilege(session_user,'centerway','CREATE'),
                  EXISTS(SELECT 1 FROM pg_class cl JOIN pg_namespace n ON n.oid=cl.relnamespace WHERE n.nspname='centerway' AND cl.relowner=r.oid)
                  FROM pg_roles r WHERE rolname=session_user""")
                row = cur.fetchone()
                if not row or row[0] != user['principal'] or row[1] != row[0] or row[2] or not row[3] or any(row[4:]):
                    raise APIError(503, 'database_identity_rejected')
                if kind == 'identity':
                    return row[0]
                if kind == 'manual_context':
                    tenant, client = params
                    cur.execute('SELECT centerway.client_journey(%s,%s) IS NOT NULL', params)
                    if not cur.fetchone()[0]:
                        raise APIError(403, 'forbidden')
                    # Fixed, read-only tables; values remain parameters. RLS uses session_user.
                    collections = {
                        'factors': ('investigation_factor_versions', 'tenant_id=%s AND client_id=%s', params),
                        'evidence': ('investigation_evidence_versions', 'tenant_id=%s AND client_id=%s', params),
                        'verifications': ('investigation_verification_versions', 'tenant_id=%s AND client_id=%s', params),
                        'catalog': ('intervention_catalog', 'tenant_id=%s', (tenant,)),
                        'policies': ('intervention_policies', 'tenant_id=%s AND client_id=%s AND principal=session_user', params),
                        'revocations': ('intervention_revocations', 'tenant_id=%s AND client_id=%s AND policy_id IN (SELECT id FROM centerway.intervention_policies WHERE tenant_id=%s AND client_id=%s AND principal=session_user)', (*params, *params)),
                        'resources': ('sandbox_flags', 'tenant_id=%s AND client_id=%s', params),
                    }
                    result = {'version': 't02-v1', 'tenant_id': tenant, 'client_id': client,
                              'principal': row[0], 'limit_per_collection': 100, 'truncated': {}}
                    for key, (table, clause, values) in collections.items():
                        # Identifiers/clauses above are internal constants, never request data.
                        cur.execute('SELECT to_jsonb(t) FROM centerway.' + table + ' t WHERE ' + clause + (' ORDER BY policy_id DESC' if key == 'revocations' else ' ORDER BY id DESC') + (', revision DESC' if key in ('factors','evidence','verifications') else '') + ' LIMIT 101', values)
                        rows = [r[0] for r in cur.fetchall()]
                        result[key], result['truncated'][key] = rows[:100], len(rows) > 100
                    cur.execute("""SELECT to_jsonb(t) FROM centerway.audit_log t
                        WHERE tenant_id=%s AND snapshot->>'client_id'=%s
                        AND (entity <> 'intervention_policies' OR snapshot->>'principal'=session_user::text)
                        AND (entity <> 'intervention_revocations' OR snapshot->>'policy_id' IN (
                            SELECT id::text FROM centerway.intervention_policies WHERE tenant_id=%s AND client_id=%s AND principal=session_user))
                        ORDER BY sequence DESC LIMIT 101""", (*params, *params))
                    rows = [r[0] for r in cur.fetchall()]
                    # Match journey's HTTP sanitization; immutable DB audit stays intact.
                    for event in rows[:100]:
                        snapshot = event['snapshot']
                        if event['entity'] == 'operation_receipts' and snapshot.get('status') == 'error':
                            snapshot['result'] = {'sqlstate': snapshot['result'].get('sqlstate', ''), 'code': 'engine_rejected'}
                    result['audit'], result['truncated']['audit'] = rows[:100], len(rows) > 100
                    return result
                if kind == 'clients':
                    cur.execute('SELECT client_id::text,display_name FROM centerway.list_authorized_clients(%s,%s::uuid[],%s,%s)', params)
                    return [dict(client_id=row[0], display_name=row[1]) for row in cur.fetchall()]
                if kind == 'journey':
                    cur.execute('SELECT centerway.client_journey(%s,%s)', params)
                elif kind == 'operate':
                    cur.execute('SELECT centerway.operate(%s,%s,%s,%s,%s)', (*params[:4], Jsonb(params[4])))
                else:
                    raise ValueError('unsupported database command')
                return cur.fetchone()[0]


def create_app(config):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 65536
    origins = frozenset(config['origins'])
    if not origins or '*' in origins or 'null' in origins or any(
            not o.startswith('https://') and not (config.get('demo') and re.fullmatch(r'http://(localhost|127\.0\.0\.1):\d+', o)) for o in origins):
        raise ValueError('exact HTTPS origins required (loopback HTTP only in demo)')
    for origin in origins:
        parsed = urlsplit(origin)
        if not parsed.hostname or parsed.username or parsed.password or origin != f'{parsed.scheme}://{parsed.netloc}':
            raise ValueError('invalid origin')
    users = config['users']
    for user in users.values():
        if not set(user['operations']) <= FIELDS.keys():
            raise ValueError('unknown configured operation')
        for tenant, clients in user['clients'].items():
            canonical_uuid(tenant)
            for client in clients:
                canonical_uuid(client)
        password_matches('configuration-check', user['password_hash'])
    ttl = config.get('session_ttl', 900)
    if not isinstance(ttl, int) or not 1 <= ttl <= 3600:
        raise ValueError('session_ttl must be 1..3600')
    sessions = session_store(config)
    db_adapter = Database(config.get('demo', False))
    dummy = password_hash(secrets.token_urlsafe(32))
    # Explicitly optional. Only the isolated synthetic demo may accept an invite.
    signup_key = os.environ.get('CENTERWAY_TEST_SIGNUP_KEY', '')
    signup_enabled = (
        config.get('synthetic_only') is True
        and config.get('session_store') == 'postgres'
        and 'alice' in users
        and len(signup_key) >= 32
    )

    def resolve_user(username):
        if username in users:
            return users[username]
        if not signup_enabled:
            return None
        encoded = session_call('get_test_user', username)
        return {**users['alice'], 'password_hash': encoded} if encoded else None
    attempts, limiter_lock = OrderedDict(), threading.Lock()

    def version(user):
        # Any provisioned credential, scope or operation change invalidates old sessions after restart.
        return hashlib.sha256(json.dumps(user, sort_keys=True).encode()).hexdigest()

    def body():
        if request.mimetype != 'application/json':
            raise APIError(415, 'json_required')
        try:
            data = json.loads(request.get_data(), object_pairs_hook=strict_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise APIError(400, 'invalid_json')
        if not isinstance(data, dict):
            raise APIError(422, 'invalid_parameters')
        return data

    def db_call(user, kind, params=()):
        try:
            return db_adapter.call(user, kind, params)
        except psycopg.Error as error:
            code = error.sqlstate or ''
            if code == '42501':
                raise APIError(403, 'forbidden')
            if code == '22023':
                raise APIError(409, 'request_conflict')
            if code.startswith(('22', '23', 'P0')):
                raise APIError(422, 'operation_rejected')
            raise APIError(503, 'database_unavailable')

    def session_call(method, *args):
        try:
            return getattr(sessions, method)(*args)
        except psycopg.Error:
            raise APIError(503, 'session_store_unavailable')

    def authenticate():
        auth = request.headers.get('Authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            raise APIError(401, 'authentication_required')
        digest = hashlib.sha256(auth[7:].encode()).hexdigest()
        row = session_call('get', digest)
        user = resolve_user(row[0]) if row else None
        if not user or row[1] != version(user) or row[2] <= time.time():
            raise APIError(401, 'session_expired_or_invalid')
        g.username, g.user, g.digest = row[0], user, digest

    @app.before_request
    def guard():
        if not config.get('demo') and not request.is_secure:
            raise APIError(400, 'https_required')
        origin = request.headers.get('Origin')
        if origin is not None and origin not in origins:
            raise APIError(403, 'origin_forbidden')
        if request.method == 'OPTIONS':
            if request.url_rule is None:
                raise APIError(404, 'not_found')
            headers = {x.strip().lower() for x in request.headers.get('Access-Control-Request-Headers', '').split(',') if x.strip()}
            methods = app.url_map.bind_to_environ(request.environ).allowed_methods()
            if request.headers.get('Access-Control-Request-Method') not in (set(methods) & {'GET', 'POST', 'DELETE'}) or not headers <= {'authorization', 'content-type'}:
                raise APIError(403, 'cors_forbidden')
            return '', 204
        if request.path not in ('/health', '/v1/sessions', '/v1/test-signup'):
            authenticate()

    @app.after_request
    def response_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
        if request.headers.get('Origin') in origins:
            response.headers['Access-Control-Allow-Origin'] = request.headers['Origin']
            response.headers['Vary'] = 'Origin'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE'
            response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
            response.headers['Access-Control-Max-Age'] = '300'
        return response

    @app.errorhandler(APIError)
    def api_error(error):
        return jsonify(error={'code': error.code}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={'code': 'http_' + str(error.code)}), error.code

    @app.errorhandler(Exception)
    def internal_error(error):
        # Never send/log exception strings, SQL, DSNs, passwords or bearer tokens.
        return jsonify(error={'code': 'internal_error'}), 500

    @app.get('/health')
    def health():
        return jsonify(status='alive', readiness='not_assessed', demo=bool(config.get('demo')))

    @app.post('/v1/sessions')
    def login():
        data = body()
        if set(data) != {'username', 'password'} or not isinstance(data['username'], str) or not isinstance(data['password'], str) or not 1 <= len(data['username']) <= 64 or not 1 <= len(data['password']) <= 256:
            raise APIError(422, 'invalid_parameters')
        ip = request.remote_addr or 'unknown'
        with limiter_lock:
            now = time.monotonic()
            recent = [x for x in attempts.pop(ip, []) if x > now - 60]
            if len(recent) >= 10:
                attempts[ip] = recent
                raise APIError(429, 'login_rate_limited')
            attempts[ip] = recent + [now]
            while len(attempts) > 2048:
                attempts.popitem(last=False)
        user = resolve_user(data['username'])
        valid = password_matches(data['password'], user['password_hash'] if user else dummy)
        if not user or not valid:
            raise APIError(401, 'invalid_credentials')
        db_call(user, 'identity')
        token = secrets.token_urlsafe(32)
        session_call('put', hashlib.sha256(token.encode()).hexdigest(), data['username'], version(user), time.time()+ttl)
        return jsonify(access_token=token, token_type='Bearer', expires_in=ttl, demo=bool(config.get('demo'))), 201

    @app.post('/v1/test-signup')
    def test_signup():
        # Owner-controlled invitation for the synthetic sandbox. Never open registration.
        if not signup_enabled:
            raise APIError(404, 'not_found')
        data = body()
        if set(data) != {'username', 'password', 'invite_code'}:
            raise APIError(422, 'invalid_parameters')
        username, password, invite_code = data.values()
        if (not isinstance(username, str) or
            not re.fullmatch(r'[a-z][a-z0-9_]{2,31}', username) or
            username in users or
            not isinstance(password, str) or not 12 <= len(password) <= 128 or
            not isinstance(invite_code, str) or len(invite_code) > 256):
            raise APIError(422, 'invalid_parameters')
        # Constant-time compare; no invite or password is ever logged.
        if not hmac.compare_digest(
            hashlib.sha256(invite_code.encode()).digest(),
            hashlib.sha256(signup_key.encode()).digest(),
        ):
            raise APIError(403, 'invite_invalid')
        if not session_call('register_test_user', username, password_hash(password)):
            raise APIError(409, 'test_account_already_created')
        return jsonify(created=True, synthetic_only=True), 201

    @app.get('/v1/session')
    def session_info():
        principal = db_call(g.user, 'identity')
        return jsonify(username=g.username, principal=principal, operations=g.user['operations'], clients=g.user['clients'], company_tenants=g.user.get('company_tenants', []))

    @app.delete('/v1/session')
    def logout():
        session_call('delete', g.digest)
        return '', 204

    def scope(tenant, client):
        try:
            tenant, client = canonical_uuid(tenant), canonical_uuid(client)
        except ValueError:
            raise APIError(422, 'invalid_uuid')
        if client not in g.user['clients'].get(tenant, []):
            raise APIError(403, 'forbidden')
        return tenant, client

    @app.get('/v1/tenants/<tenant>/clients')
    def clients(tenant):
        try:
            tenant = canonical_uuid(tenant)
        except ValueError:
            raise APIError(422, 'invalid_uuid')
        if tenant not in g.user['clients']:
            raise APIError(403, 'forbidden')
        if set(request.args) - {'limit', 'after'} or any(len(request.args.getlist(k)) != 1 for k in request.args):
            raise APIError(422, 'invalid_parameters')
        try:
            raw_limit = request.args.get('limit', '50')
            if not re.fullmatch(r'[1-9][0-9]{0,2}', raw_limit):
                raise ValueError()
            limit = int(raw_limit)
            if limit > 100:
                raise ValueError()
            after = canonical_uuid(request.args['after']) if 'after' in request.args else None
        except ValueError:
            raise APIError(422, 'invalid_parameters')
        rows = db_call(g.user, 'clients', (tenant, g.user['clients'][tenant], after, limit))
        next_cursor = rows[limit-1]['client_id'] if len(rows) > limit else None
        return jsonify(data=rows[:limit], next_cursor=next_cursor, demo=bool(config.get('demo')))

    @app.get('/v1/tenants/<tenant>/clients/<client>/journey')
    def journey(tenant, client):
        tenant, client = scope(tenant, client)
        result = db_call(g.user, 'journey', (tenant, client))
        if result is None:
            raise APIError(404, 'client_not_found')
        for receipt in result.get('operations', []):
            if receipt.get('status') == 'error':
                receipt['result'] = {'sqlstate': receipt['result'].get('sqlstate', ''), 'code': 'engine_rejected'}
        return jsonify(data=result, demo=bool(config.get('demo')))

    @app.get('/v1/tenants/<tenant>/clients/<client>/manual-context')
    def manual_context(tenant, client):
        tenant, client = scope(tenant, client)
        if request.args:
            raise APIError(422, 'invalid_parameters')
        return jsonify(data=db_call(g.user, 'manual_context', (tenant, client)), demo=bool(config.get('demo')))

    @app.post('/v1/tenants/<tenant>/clients/<client>/operations')
    def operate(tenant, client):
        tenant, client = scope(tenant, client)
        data = body()
        if set(data) != {'request_id', 'operation', 'arguments'}:
            raise APIError(422, 'invalid_parameters')
        try:
            rid = canonical_uuid(data['request_id'])
            op, args = data['operation'], data['arguments']
            if not isinstance(op, str) or op not in FIELDS or not isinstance(args, dict) or set(args) != set(FIELDS[op].split()):
                raise ValueError()
            for key, value in args.items():
                if value is None:
                    raise ValueError()
                if key == 'id' or key.endswith('_id'):
                    canonical_uuid(value)
                elif key in ('expected_revision', 'required_periods', 'contract_revision', 'pre_revision', 'post_revision'):
                    if type(value) is not int or value < 0:
                        raise ValueError()
                elif key == 'revisions':
                    if not isinstance(value, list) or not 1 <= len(value) <= 120 or any(type(v) is not int or v <= 0 for v in value):
                        raise ValueError()
                elif key == 'as_of':
                    if not isinstance(value, str) or datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
                        raise ValueError()
                elif key == 'data':
                    if not isinstance(value, dict):
                        raise ValueError()
                elif not isinstance(value, str) or not 1 <= len(value) <= 2000:
                    raise ValueError()
        except (ValueError, TypeError, OverflowError):
            raise APIError(422, 'invalid_parameters')
        if op not in g.user['operations'] or (op == 'discover_company' and tenant not in g.user.get('company_tenants', [])):
            raise APIError(403, 'operation_forbidden')
        # Confirm current membership and client visibility even on receipt replays.
        if db_call(g.user, 'journey', (tenant, client)) is None:
            raise APIError(403, 'forbidden')
        receipt = db_call(g.user, 'operate', (tenant, client, rid, op, args))
        status = 200
        if receipt['status'] == 'error':
            state = receipt['result'].get('sqlstate', '')
            receipt['result'] = {'sqlstate': state, 'code': 'engine_rejected'}
            status = 403 if state == '42501' else 409 if state == '40001' else 422
        return jsonify(data=receipt, demo=bool(config.get('demo'))), status

    return app


def load_app():
    path = Path(os.environ['CENTERWAY_API_CONFIG'])
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('API configuration must be private')
    return create_app(json.loads(path.read_text()))
