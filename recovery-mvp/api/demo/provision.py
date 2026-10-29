"""Provision ONLY a fresh disposable demo container. Prints paths, never credentials."""
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import password_hash, FIELDS

T = 'a1000000-0000-0000-0000-000000000001'
B = 'b1000000-0000-0000-0000-000000000001'
C = 'a2000000-0000-0000-0000-000000000001'
C2 = 'a2000000-0000-0000-0000-000000000002'
BC = 'b2000000-0000-0000-0000-000000000001'
S = 'a3000000-0000-0000-0000-000000000001'
K = 'a4000000-0000-0000-0000-000000000001'


def provision(container, port, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise ValueError('Demo directory must be private (0700)')
    # Additive HTTP read port, installed only in this fresh disposable database.
    migrations = sorted((Path(__file__).resolve().parents[1]/'sql').glob('*.sql'))
    users, credentials, statements = {}, {}, [p.read_text() for p in migrations]
    specs = [('alice','http_alice',T,C,list(FIELDS)), ('reviewer','http_reviewer',T,C,['append_investigation','investigate']),
             ('reader','http_reader',T,C,[]), ('bob','http_bob',B,BC,list(FIELDS))]
    for username, principal, tenant, client, operations in specs:
        db_password, login_password = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        statements.append(f"CREATE ROLE {principal} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{db_password}' IN ROLE centerway_api;")
        users[username] = dict(principal=principal, dsn=f'host=127.0.0.1 port={port} dbname=postgres user={principal} password={db_password} sslmode=disable',
                               password_hash=password_hash(login_password), clients={tenant:[client]}, operations=operations, company_tenants=[])
        credentials[username] = login_password
    statements += [f"INSERT INTO centerway.companies VALUES ('{T}','SYNTHETIC HTTP A'),('{B}','SYNTHETIC HTTP B');",
                   f"INSERT INTO centerway.clients VALUES ('{T}','{C}','SYNTHETIC client A'),('{T}','{C2}','SYNTHETIC restricted client'),('{B}','{BC}','SYNTHETIC client B');"]
    for username, principal, tenant, client, operations in specs:
        statements.append(f"INSERT INTO centerway.memberships VALUES ('{principal}','{tenant}');")
    statements += ["SET SESSION AUTHORIZATION http_alice;",
      f"SELECT centerway.append_version('{T}','{C}','source','{S}',0,'Synthetic fixture'," +
        "'"+json.dumps(dict(name='SYNTHETIC source',locator='synthetic://http',method='synthetic test total'))+"'::jsonb);",
      f"SELECT centerway.append_version('{T}','{C}','contract','{K}',0,'Synthetic fixture',"+
       "'"+json.dumps(dict(objective='SYNTHETIC business objective',expected_outcome='SYNTHETIC expected outcome',indicator='SYNTHETIC outcome metric',
            unit='units',measurement_method='synthetic test total',direction='higher',baseline=10,minimum_acceptable=15,target=20,
            baseline_start='2024-01-01T00:00:00Z',baseline_end='2024-02-01T00:00:00Z',period_start='2024-02-01T00:00:00Z',period_end='2024-03-01T00:00:00Z',
            source_id=S,source_revision=1,baseline_reference='synthetic://baseline'))+"'::jsonb);"]
    result = subprocess.run(['docker','exec','-i',container,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres'],input='\n'.join(statements),text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError('Demo provisioning failed; do not use an existing database')
    config = dict(demo=True,origins=['http://localhost:5173'],session_db=str(directory/'sessions.sqlite'),session_ttl=900,users=users)
    for filename, content in [('config.json', config),('credentials.json', credentials)]:
        fd = os.open(directory/filename,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as out: json.dump(content,out)
    return config, credentials

if __name__ == '__main__':
    provision(sys.argv[1],sys.argv[2],sys.argv[3])
    print('Synthetic demo provisioned. Private config and credentials are in the selected directory.')
