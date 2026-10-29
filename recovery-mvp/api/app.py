"""L01 HTTP transport. Business decisions remain exclusively in F01–F06."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
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
    path = Path(config['session_db'])
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('session database must be private')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, username TEXT, version TEXT, expires REAL)')
    db_adapter = Database(config.get('demo', False))
    dummy = password_hash(secrets.token_urlsafe(32))
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

    def authenticate():
        auth = request.headers.get('Authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            raise APIError(401, 'authentication_required')
        digest = hashlib.sha256(auth[7:].encode()).hexdigest()
        with sqlite3.connect(path) as db:
            row = db.execute('SELECT username,version,expires FROM sessions WHERE digest=?', (digest,)).fetchone()
        user = users.get(row[0]) if row else None
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
            if request.headers.get('Access-Control-Request-Method') not in request.url_rule.methods or not headers <= {'authorization', 'content-type'}:
                raise APIError(403, 'cors_forbidden')
            return '', 204
        if request.path not in ('/health', '/v1/sessions'):
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
        user = users.get(data['username'])
        valid = password_matches(data['password'], user['password_hash'] if user else dummy)
        if not user or not valid:
            raise APIError(401, 'invalid_credentials')
        db_call(user, 'identity')
        token = secrets.token_urlsafe(32)
        with sqlite3.connect(path) as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('DELETE FROM sessions WHERE username=? AND digest NOT IN (SELECT digest FROM sessions WHERE username=? ORDER BY expires DESC LIMIT 9)', (data['username'], data['username']))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), data['username'], version(user), time.time()+ttl))
        return jsonify(access_token=token, token_type='Bearer', expires_in=ttl, demo=bool(config.get('demo'))), 201

    @app.get('/v1/session')
    def session_info():
        principal = db_call(g.user, 'identity')
        return jsonify(username=g.username, principal=principal, operations=g.user['operations'], clients=g.user['clients'], company_tenants=g.user.get('company_tenants', []))

    @app.delete('/v1/session')
    def logout():
        with sqlite3.connect(path) as db:
            db.execute('DELETE FROM sessions WHERE digest=?', (g.digest,))
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
