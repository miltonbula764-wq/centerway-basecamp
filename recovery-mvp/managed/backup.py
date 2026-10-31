"""Encrypted logical backups for a trusted operator; never run by the web app.

PostgreSQL 17 tools and age required. Fresh, separately provisioned target only.
Sessions are intentionally excluded: a restored installation requires new logins.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 32 * 1024 * 1024


def hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'sql').glob('*.sql')) + sorted((ROOT/'api/sql').glob('*.sql')) + sorted((ROOT/'managed/sql').glob('*.sql'))}


def fingerprint(dsn):
    c = conninfo_to_dict(dsn)
    return hashlib.sha256(json.dumps([c.get('host'),c.get('port','5432'),c.get('dbname')]).encode()).hexdigest()


def private(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('private regular file required')
    if not path.is_file():
        raise ValueError('regular file required')
    return path


def run(argv, **kwargs):
    return subprocess.run(argv,check=True,capture_output=True,**kwargs).stdout


@contextmanager
def pg_environment(dsn):
    options = conninfo_to_dict(dsn)
    if options.get('sslmode') != 'verify-full' or '-pooler.' in options.get('host',''):
        raise ValueError('direct verified PostgreSQL TLS required')
    with tempfile.TemporaryDirectory(prefix='cw-pg-') as temporary:
        service = Path(temporary)/'pg_service.conf'
        lines = ['[centerway]']
        for key,value in options.items():
            if '\n' in value or '\r' in value:
                raise ValueError('invalid connection option')
            lines.append(f'{key}={value}')
        fd = os.open(service,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:
            stream.write('\n'.join(lines)+'\n')
        env = {k:v for k,v in os.environ.items() if not k.startswith('PG')}
        env.update(PGSERVICEFILE=str(service),PGSERVICE='centerway',PGCONNECT_TIMEOUT='10')
        yield env


def backup(dsn, destination, recipient):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('backup destination exists')
    if not recipient.startswith('age1'):
        raise ValueError('age public recipient required')
    with pg_environment(dsn) as env:
        if not run(['pg_dump','--version']).decode().startswith('pg_dump (PostgreSQL) 17.'):
            raise ValueError('PostgreSQL 17 client required')
        dump = run(['pg_dump','--format=custom','--no-owner','--schema=centerway','--schema=cw_sessions',
                    '--exclude-table-data=cw_sessions.sessions'],env=env)
    if not dump.startswith(b'PGDMP') or len(dump)>MAX_BYTES:
        raise ValueError('invalid or oversized dump')
    envelope = dict(format='centerway-logical-v1',synthetic_only=True,postgres_major=17,
                    source=fingerprint(dsn),migrations=hashes(),sha256=hashlib.sha256(dump).hexdigest(),
                    dump=base64.b64encode(dump).decode(),sessions='invalidated')
    ciphertext = run(['age','-r',recipient],input=json.dumps(envelope).encode())
    fd = os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(ciphertext)


def restore(dsn, source, identity):
    source, identity = private(source), private(identity)
    if source.stat().st_size > 2*MAX_BYTES:
        raise ValueError('oversized backup')
    clear = run(['age','-d','-i',str(identity),str(source)])
    envelope = json.loads(clear)
    if envelope.get('format')!='centerway-logical-v1' or envelope.get('synthetic_only') is not True or envelope.get('postgres_major')!=17 or envelope.get('migrations')!=hashes() or envelope.get('sessions')!='invalidated':
        raise ValueError('backup manifest rejected')
    dump = base64.b64decode(envelope['dump'],validate=True)
    if len(dump)>MAX_BYTES or not dump.startswith(b'PGDMP') or hashlib.sha256(dump).hexdigest()!=envelope['sha256']:
        raise ValueError('backup integrity rejected')
    if fingerprint(dsn)==envelope['source']:
        raise ValueError('restore must target a different database')
    # This tool is for trusted backups only. pg_restore executes archived SQL.
    with psycopg.connect(dsn,connect_timeout=10) as db:
        if db.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN ('centerway','cw_sessions'))").fetchone()[0]:
            raise ValueError('fresh empty target required')
    with pg_environment(dsn) as env:
        run(['pg_restore','--single-transaction','--exit-on-error','--no-owner','--dbname','service=centerway'],input=dump,env=env)
    with psycopg.connect(dsn,connect_timeout=10) as db:
        if db.execute('SELECT count(*) FROM cw_sessions.sessions').fetchone()[0]:
            raise ValueError('restored sessions must be empty')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['backup','restore'])
    p.add_argument('--owner-config',required=True)
    p.add_argument('--archive',required=True)
    p.add_argument('--recipient')
    p.add_argument('--identity')
    a=p.parse_args()
    config=json.loads(private(a.owner_config).read_text())
    if config.get('synthetic_only') is not True:
        raise ValueError('explicit synthetic-only owner configuration required')
    if a.command=='backup':
        backup(config['dsn'],a.archive,a.recipient or '')
    else:
        restore(config['dsn'],a.archive,a.identity or '')
    print('Logical recovery command completed; verify application and RLS separately.')


if __name__=='__main__':
    try:
        main()
    except Exception:
        print('Logical recovery failed. Source preserved; inspect isolated target before retry.',file=sys.stderr)
        sys.exit(1)
