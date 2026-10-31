"""One-time SYNTHETIC provisioning in an EMPTY dedicated PostgreSQL 17 database.

Private owner DSN JSON input; private runtime config and credentials output.
Never run on an existing installation; never invoked by Render startup/build.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo, conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'api'))
from app import FIELDS, password_hash
from demo.provision import T,B,C,C2,BC,S,K

SPECS = [('alice','http_alice',T,C,list(FIELDS)),
         ('reviewer','http_reviewer',T,C,['append_investigation','investigate']),
         ('reader','http_reader',T,C,[]),('bob','http_bob',B,BC,list(FIELDS))]


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)


def build_bundle(owner_dsn, origin):
    """Generate once before SQL is run; no administrative credential in runtime config."""
    options = conninfo_to_dict(owner_dsn)
    if options.get('sslmode') != 'verify-full' or '-pooler.' in options.get('host',''):
        raise ValueError('direct verified TLS required')
    users, credentials, roles = {}, {}, []
    for username, principal, tenant, client, operations in SPECS:
        password, login = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        roles.append(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {} IN ROLE centerway_api').format(sql.Identifier(principal),sql.Literal(password)).as_string())
        users[username] = dict(principal=principal,dsn=make_conninfo(owner_dsn,user=principal,password=password),password_hash=password_hash(login),clients={tenant:[client]},operations=operations,company_tenants=[])
        credentials[username] = login
    password = secrets.token_urlsafe(32)
    roles.append(sql.SQL('CREATE ROLE cw_sessions_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {} IN ROLE cw_session_store').format(sql.Literal(password)).as_string())
    config = dict(demo=False,synthetic_only=True,origins=[origin],session_ttl=900,session_store='postgres',
                  session_postgres=dict(principal='cw_sessions_runtime',dsn=make_conninfo(owner_dsn,user='cw_sessions_runtime',password=password)),users=users)
    seed = [f"INSERT INTO centerway.companies VALUES ('{T}','SYNTHETIC HTTP A'),('{B}','SYNTHETIC HTTP B')",
            f"INSERT INTO centerway.clients VALUES ('{T}','{C}','SYNTHETIC client A'),('{T}','{C2}','SYNTHETIC restricted client'),('{B}','{BC}','SYNTHETIC client B')"]
    for _, principal, tenant, _, _ in SPECS:
        seed.append(f"INSERT INTO centerway.memberships VALUES ('{principal}','{tenant}')")
    migrations = sorted((ROOT/'sql').glob('*.sql')) + sorted((ROOT/'api/sql').glob('*.sql')) + sorted((ROOT/'managed/sql').glob('*.sql'))
    return config, credentials, [p.read_text() for p in migrations] + roles + seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-config',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--origin',required=True)
    args = parser.parse_args()
    owner = Path(args.owner_config)
    if owner.stat().st_mode & 0o077:
        raise ValueError('private owner config required')
    target = Path(args.output).resolve()
    if ROOT.parent == target or ROOT.parent in target.parents:
        raise ValueError('private output must be outside repository')
    target.mkdir(mode=0o700,parents=True,exist_ok=False)
    dsn = json.loads(owner.read_text())['dsn']
    config, credentials, statements = build_bundle(dsn,args.origin)
    with psycopg.connect(dsn,autocommit=True,connect_timeout=10) as db:
        if db.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN ('centerway','cw_sessions')) OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('centerway_api','cw_session_store','http_alice','http_bob','http_reader','http_reviewer','cw_sessions_runtime'))").fetchone()[0]:
            raise ValueError('fresh database and roles required; no automatic retry/reseed')
        # Migration files contain their own transactions. On failure, leave state for inspection.
        for statement in statements:
            db.execute(statement,prepare=False)
    private_json(target/'config.json',config)
    private_json(target/'credentials.json',credentials)
    print('Synthetic installation provisioned; private runtime configuration written.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Provisioning failed; inspect state before any retry. No credentials emitted.',file=sys.stderr)
        sys.exit(1)
