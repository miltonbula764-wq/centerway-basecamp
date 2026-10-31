"""Operator-only T01 preparation. No network on prepare; no engine runs on apply.

Private bundle is reusable after interruption. Existing tenants/config stay intact.
Remote apply requires a separate explicit operator gate; never used in tests/CI.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'api'))
from app import FIELDS, password_hash, create_app

SPECS = {'t01_operator': ('cw_t01_operator', list(FIELDS)),
         't01_reviewer': ('cw_t01_reviewer', ['append_investigation', 'investigate']),
         't01_reader': ('cw_t01_reader', [])}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture():
    data = json.loads((HERE / 'initial.json').read_text())
    # Only explicitly listed initial documents; future/ is NEVER read here.
    documents = {p.name: p.read_bytes() for p in sorted((HERE / 'documents').glob('*.json'))}
    csv = json.loads(documents['vendor-s6.json'])
    if csv['csv_sha256'] != digest((HERE / 'documents' / 'vendor-s6.csv').read_bytes()):
        raise ValueError('CSV document digest mismatch')
    for record in data['records']:
        if record['kind'] == 'evidence':
            name = record['data']['reference'].split('/')[-1].split('#')[0]
            record['data']['content_sha256'] = digest(documents[name])
    for item in data['discovery_inputs']:
        for evidence in item['evidence']:
            name = evidence['reference'].split('/')[-1].split('#')[0]
            evidence['content_sha256'] = digest(documents[name])
    # Attach declared file digests to contextual source metadata (no document table exists).
    for record in data['records']:
        if record['kind'] == 'source':
            name = record['data']['locator'].split('/')[-1].split('#')[0]
            record['data']['method'] += '; sha256=' + digest(documents[name])
    return data, digest(json.dumps(data, sort_keys=True).encode())


def private_read(path):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_mode & 0o077:
        raise ValueError('private regular file (0600) required')
    return json.loads(path.read_text())


def private_write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)


def target(dsn):
    options = conninfo_to_dict(dsn)
    if options.get('sslmode') != 'verify-full' or not options.get('host') or options.get('hostaddr') or options.get('service') or '-pooler.' in options['host']:
        raise ValueError('direct verified TLS connection required')
    return {k: options.get(k, default) for k, default in [('host',''),('port','5432'),('dbname','postgres')]}


def check_target(owner_dsn, bundle, allow_remote=False, confirmation=''):
    expected = bundle['target']
    if target(owner_dsn) != expected:
        raise ValueError('bundle belongs to another database')
    if expected['host'] not in ('localhost', '127.0.0.1'):
        if not allow_remote or confirmation != bundle['tenant_id']:
            raise ValueError('remote activation requires separate explicit approval and tenant confirmation')


def prepare(owner, config, output):
    """Offline only. Never replaces runtime config or deploys it."""
    if owner.get('synthetic_only') is not True or config.get('synthetic_only') is not True:
        raise ValueError('explicit synthetic-only owner and runtime configuration required')
    dest = Path(output).resolve()
    if ROOT.parent == dest or ROOT.parent in dest.parents:
        raise ValueError('private bundle must be outside checkout')
    if dest.exists():
        raise ValueError('bundle already exists; reuse it, never rotate during retry')
    parent = dest.parent
    if parent.stat().st_mode & 0o077:
        raise ValueError('private output parent (0700) required')
    t = target(owner['dsn'])
    data, fingerprint = fixture()
    runtime = copy.deepcopy(config)
    credentials = {}
    for username, (principal, operations) in SPECS.items():
        if username in runtime['users'] or any(u['principal'] == principal for u in runtime['users'].values()):
            raise ValueError('T01 user/principal already configured; reuse original bundle')
        db_password, login = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        runtime['users'][username] = dict(principal=principal,
            dsn=make_conninfo(owner['dsn'], user=principal, password=db_password),
            password_hash=password_hash(login), clients={data['tenant_id']: [data['client_id']]},
            operations=operations, company_tenants=[data['tenant_id']] if username == 't01_operator' else [])
        credentials[username] = login
    # Runtime retains existing individual DSNs, sessions, scopes and CORS exactly.
    for user in config['users'].values():
        if target(user['dsn']) != t:
            raise ValueError('existing runtime database differs from owner')
    if target(config['session_postgres']['dsn']) != t:
        raise ValueError('session database differs')
    if config.get('session_store') != 'postgres' or config.get('demo') is not False:
        raise ValueError('managed synthetic runtime required')
    # Constructor validates configuration without making any database connection.
    create_app(runtime)
    bundle = dict(version='adversarial-t01-v1', tenant_id=data['tenant_id'], target=t,
                  fixture_sha256=fingerprint, previous_config_sha256=digest(json.dumps(config,sort_keys=True).encode()),
                  users={u: runtime['users'][u] for u in SPECS})
    dest.mkdir(mode=0o700, exist_ok=False)
    private_write(dest / 'bundle.json', bundle)
    private_write(dest / 'runtime-config.json', runtime)
    private_write(dest / 'credentials.json', credentials)
    return bundle


def same_row(db, table, keys, expected):
    """Idempotence compares declared fields, never overwrites immutable records."""
    query = sql.SQL('SELECT to_jsonb(t) FROM centerway.{} t WHERE {}').format(
        sql.Identifier(table), sql.SQL(' AND ').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in keys))
    rows = db.execute(query, tuple(keys.values())).fetchall()
    if not rows:
        return False
    if len(rows) != 1 or any(rows[0][0].get(k) != v for k,v in expected.items()):
        raise ValueError('T01 collision or drift; inspect instead of reseeding')
    return True


def bootstrap(db, bundle, data):
    """One owner transaction; names/ACLs/tenant checks fail closed on collision."""
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended('adversarial-t01-bootstrap',0))")
    exists = db.execute('SELECT name FROM centerway.companies WHERE tenant_id=%s', (data['tenant_id'],)).fetchone()
    if exists:
        if exists[0] != data['tenant_name']:
            raise ValueError('tenant collision')
        expected_members = {u['principal'] for u in bundle['users'].values()}
        actual = {r[0] for r in db.execute('SELECT principal::text FROM centerway.memberships WHERE tenant_id=%s', (data['tenant_id'],))}
        if actual != expected_members:
            raise ValueError('membership drift')
    elif db.execute('SELECT 1 FROM centerway.companies WHERE name=%s', (data['tenant_name'],)).fetchone():
        raise ValueError('tenant name collision')
    for user in bundle['users'].values():
        principal = user['principal']
        role = db.execute('SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s',(principal,)).fetchone()
        if role:
            memberships = {r[0] for r in db.execute('SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles p ON p.oid=m.member WHERE p.rolname=%s',(principal,))}
            tenants = {str(r[0]) for r in db.execute('SELECT tenant_id FROM centerway.memberships WHERE principal=%s',(principal,))}
            if not exists or role != (True,False,False,False,False,False) or memberships != {'centerway_api'} or tenants != {data['tenant_id']}:
                raise ValueError('existing principal collision or privileges changed')
        else:
            if exists:
                raise ValueError('missing role in existing T01 installation')
            db.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {} IN ROLE centerway_api').format(sql.Identifier(principal),sql.Literal(conninfo_to_dict(user['dsn'])['password'])))
    if not exists:
        db.execute('INSERT INTO centerway.companies VALUES(%s,%s)',(data['tenant_id'],data['tenant_name']))
        for user in bundle['users'].values():
            db.execute('INSERT INTO centerway.memberships VALUES(%s,%s)',(user['principal'],data['tenant_id']))
    keys = dict(tenant_id=data['tenant_id'],client_id=data['client_id'])
    if not same_row(db,'clients', keys, dict(keys,name=data['client_name'])):
        db.execute('INSERT INTO centerway.clients VALUES(%s,%s,%s)',(*keys.values(),data['client_name']))
    clients = db.execute('SELECT client_id::text FROM centerway.clients WHERE tenant_id=%s',(data['tenant_id'],)).fetchall()
    if clients != [(data['client_id'],)]:
        raise ValueError('unexpected T01 clients')
    # Catalog is ONLY a reversible synthetic flag, with NO policy/grant to execute.
    catalog = dict(tenant_id=data['tenant_id'],id=data['catalog_id'],name='SYNTHETIC T01 integration flag; not a real integration',
        category='integration_configuration',scope='internal',control='saas',action='set_synthetic_flag',expected_value=False,desired_value=True,risk=1,priority=1)
    resource = dict(tenant_id=data['tenant_id'],client_id=data['client_id'],id=data['resource_id'],environment='isolated_synthetic')
    for table, keys, row in [('intervention_catalog',dict(tenant_id=data['tenant_id'],id=data['catalog_id']),catalog),
                             ('sandbox_flags',resource,dict(resource,value=False,last_execution=None))]:
        # A subsequent legitimate manual execution can change a resource; never reset it.
        expected = resource if table == 'sandbox_flags' else row
        if not same_row(db,table,keys,expected):
            db.execute(sql.SQL('INSERT INTO centerway.{} ({}) VALUES ({})').format(sql.Identifier(table),
                sql.SQL(',').join(map(sql.Identifier,row)),sql.SQL(',').join(sql.Placeholder() for _ in row)),tuple(row.values()))


def load_initial(db, data):
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended('adversarial-t01-data',0))")
    for record in data['records']:
        keys = dict(tenant_id=data['tenant_id'],client_id=data['client_id'],id=record['id'],revision=record['expected_revision']+1)
        # JSON timestamp normalization via PostgreSQL preserves equality with recorded rows.
        normalized = db.execute(sql.SQL('SELECT to_jsonb(jsonb_populate_record(NULL::centerway.{},%s))').format(sql.Identifier(record['kind']+'_versions')), (Jsonb(record['data']),)).fetchone()[0]
        expected = {k: normalized[k] for k in record['data']}
        if not same_row(db,record['kind']+'_versions',keys,expected):
            db.execute('SELECT centerway.append_version(%s,%s,%s,%s,%s,%s,%s)',
                (data['tenant_id'],data['client_id'],record['kind'],record['id'],record['expected_revision'],record['reason'],Jsonb(record['data'])))
    for item in data['discovery_inputs']:
        rule = dict(tenant_id=data['tenant_id'],id=item['rule_id'],category=item['factor']['category'],purpose='condition_met',assertion=False)
        if not same_row(db,'discovery_rules',dict(tenant_id=data['tenant_id'],id=item['rule_id']),rule):
            db.execute('SELECT centerway.register_discovery_rule(%s,%s,%s,%s,%s)',tuple(rule.values()))
        row = dict(tenant_id=data['tenant_id'],client_id=data['client_id'],id=item['id'],contract_id=data['contract_id'],contract_revision=item['contract_revision'],factor=item['factor'],evidence=item['evidence'])
        if not same_row(db,'discovery_inputs',{k:row[k] for k in ('tenant_id','client_id','id')},row):
            db.execute('SELECT centerway.register_discovery_input(%s,%s,%s,%s,%s,%s,%s)',(*list(row.values())[:5],Jsonb(row['factor']),Jsonb(row['evidence'])))


def apply(owner, bundle, allow_remote=False, confirmation=''):
    if owner.get('synthetic_only') is not True:
        raise ValueError('synthetic-only owner required')
    data, fingerprint = fixture()
    if bundle['version'] != 'adversarial-t01-v1' or bundle['fixture_sha256'] != fingerprint or bundle['tenant_id'] != data['tenant_id']:
        raise ValueError('fixture changed; no automatic reseed')
    check_target(owner['dsn'],bundle,allow_remote,confirmation)
    if set(bundle['users']) != set(SPECS):
        raise ValueError('unexpected users')
    for username, (principal, operations) in SPECS.items():
        user = bundle['users'][username]
        if user['principal'] != principal or target(user['dsn']) != bundle['target'] or user['clients'] != {data['tenant_id']:[data['client_id']]} or user['operations'] != operations or user['company_tenants'] != ([data['tenant_id']] if username == 't01_operator' else []):
            raise ValueError('bundle scope changed')
    # DDL/metadata commit separately so actual individual login can author F01 data.
    # No main/old tenant tables or rows are updated; interruption is resumable.
    with psycopg.connect(owner['dsn'],connect_timeout=5) as db:
        db.execute("SET LOCAL lock_timeout='5s'")
        bootstrap(db,bundle,data)
    # Exercise the same runtime identity guard before loading data, with no writes.
    from app import Database
    for user in bundle['users'].values():
        Database(False).call(user,'identity')
    with psycopg.connect(bundle['users']['t01_operator']['dsn'],connect_timeout=5) as db:
        db.execute("SET LOCAL lock_timeout='5s'")
        load_initial(db,data)


def check_activation(previous, bundle, candidate):
    """Offline race/drift guard before a human updates the existing runtime secret."""
    if digest(json.dumps(previous,sort_keys=True).encode()) != bundle['previous_config_sha256']:
        raise ValueError('runtime changed since preparation; do not overwrite new users/settings')
    expected = copy.deepcopy(previous)
    expected['users'].update(bundle['users'])
    if candidate != expected:
        raise ValueError('candidate runtime differs from exact additive bundle')
    create_app(candidate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    plan = commands.add_parser('prepare')
    plan.add_argument('--owner-config',required=True)
    plan.add_argument('--runtime-config',required=True)
    plan.add_argument('--output',required=True)
    run = commands.add_parser('apply')
    run.add_argument('--owner-config',required=True)
    run.add_argument('--bundle',required=True)
    run.add_argument('--allow-remote-demo',action='store_true')
    run.add_argument('--confirm-tenant',default='')
    check = commands.add_parser('check-activation')
    check.add_argument('--runtime-config',required=True)
    check.add_argument('--bundle-dir',required=True)
    args=parser.parse_args()
    if args.command == 'check-activation':
        directory=Path(args.bundle_dir)
        check_activation(private_read(args.runtime_config),private_read(directory/'bundle.json'),private_read(directory/'runtime-config.json'))
        print('Offline runtime comparison passed; no deployment or authorization granted.')
        return
    owner=private_read(args.owner_config)
    if args.command == 'prepare':
        prepare(owner,private_read(args.runtime_config),args.output)
        print('T01 private bundle prepared OFFLINE; no database or runtime changed.')
    else:
        apply(owner,private_read(args.bundle),args.allow_remote_demo,args.confirm_tenant)
        print('T01 initial fixture applied; no detection, investigation, intervention or recovery executed. Runtime activation remains separate.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('T01 refused/failed. Inspect private state; reuse original bundle after interruption. No credentials emitted.',file=sys.stderr)
        sys.exit(1)
