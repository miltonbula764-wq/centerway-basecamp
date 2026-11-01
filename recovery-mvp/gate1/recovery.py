"""T03-G2: trusted logical archives; only fixed errors cross the CLI boundary."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess as sp
import tempfile
import time
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

LIMIT = 64 * 1024 * 1024
TIMEOUT = 180
IMAGE = 'postgres:17-alpine'
ROOT = Path(__file__).resolve().parents[2]


class RecoveryError(Exception):
    pass


def require(value):
    if not value:
        raise RecoveryError('recovery_rejected')


def private(path, directory=False):
    p = Path(path)
    s = p.lstat()
    require((stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))
            and s.st_uid == os.geteuid() and not s.st_mode & 0o077)
    return p


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def command(args, data=None, env=None, limit=LIMIT):
    if args[0] in ('age','age-keygen') and env is None:
        env = {'PATH':os.environ.get('PATH','/usr/bin:/bin')}
    if args[0] == 'docker':
        args = ['docker','--host=unix:///var/run/docker.sock',*args[1:]]
        env = {k:v for k,v in os.environ.items() if k not in
               {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    # Bounded stdout; stderr never enters logs. Only private/synthetic input here.
    with open(os.devnull, 'rb') as unused:
        # stdin defaults to /dev/null; plaintext is never spooled to disk.
        p = sp.Popen(args, stdin=sp.PIPE if data is not None else unused,
                     stdout=sp.PIPE, stderr=sp.DEVNULL, env=env)
        import threading
        def feed():
            try:
                p.stdin.write(data)
                p.stdin.close()
            except (OSError, ValueError):
                pass
        thread = threading.Thread(target=feed, daemon=True) if data is not None else None
        if thread:
            thread.start()
        output = bytearray()
        deadline = time.monotonic() + TIMEOUT
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(p.stdout, selectors.EVENT_READ)
                while True:
                    require(time.monotonic() < deadline)
                    if not selector.select(0.1):
                        continue
                    block = os.read(p.stdout.fileno(), 65536)
                    if not block:
                        break
                    output.extend(block)
                    require(len(output) <= limit)
            require(p.wait(timeout=max(0.01, deadline-time.monotonic())) == 0)
            return bytes(output)
        finally:
            if p.poll() is None:
                p.kill()
            p.wait()
            if thread:
                thread.join(timeout=2)
            p.stdout.close()


@contextmanager
def connection_environment(dsn):
    opts = conninfo_to_dict(dsn)
    allowed = {'host','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'}
    require(set(opts) <= allowed and opts.get('sslmode') == 'verify-full'
            and opts.get('host') and '-pooler.' not in opts['host']
            and ',' not in opts['host'] and not opts['host'].startswith('/')
            and all('\n' not in v and '\r' not in v for v in opts.values()))
    with tempfile.TemporaryDirectory() as temp:
        config = Path(temp)/'service'
        config.touch(mode=0o600)
        config.write_text('[backup]\n'+'\n'.join(f'{k}={v}' for k,v in opts.items())+'\n')
        env = {k:v for k,v in os.environ.items() if k in
               {'PATH','HOME','LANG','LC_ALL','LD_LIBRARY_PATH','SSL_CERT_FILE'}}
        env.update(PGSERVICEFILE=str(config), PGSERVICE='backup', PGCONNECT_TIMEOUT='10')
        yield env


def inventory(db):
    tables = db.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' ORDER BY 1,2").fetchall()
    result = {}
    for schema, table in tables:
        # Same exported snapshot as pg_dump. Preserve duplicate rows and order
        # independently of physical row order. Metadata stays inside age.
        rows = db.execute(sql.SQL('SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(schema),sql.Identifier(table))).fetchall()
        h = hashlib.sha256()
        for row, in rows:
            raw = row.encode(); h.update(len(raw).to_bytes(8,'big')); h.update(raw)
        result[schema+'.'+table] = {'rows':len(rows),'sha256':h.hexdigest()}
    return result


def structure(db):
    # Application constraints, RLS policies, ACLs and SECURITY DEFINER identity.
    return {
        'schemas': db.execute("SELECT nspname,pg_get_userbyid(nspowner),nspacl::text FROM pg_namespace WHERE nspname IN ('centerway','cw_sessions') ORDER BY 1").fetchall(),
        'indexes': db.execute("SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname IN ('centerway','cw_sessions') ORDER BY 1,2,3").fetchall(),
        'triggers': db.execute("SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid,true) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('centerway','cw_sessions')) ORDER BY 1,2").fetchall(),
        'tables': db.execute("SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity,pg_get_userbyid(c.relowner),c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('centerway','cw_sessions') AND c.relkind='r' ORDER BY 1,2").fetchall(),
        'constraints': db.execute("SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid,true) FROM pg_constraint WHERE connamespace IN (SELECT oid FROM pg_namespace WHERE nspname IN ('centerway','cw_sessions')) ORDER BY 1,2").fetchall(),
        'policies': db.execute("SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname IN ('centerway','cw_sessions') ORDER BY 1,2,3").fetchall(),
        'functions': db.execute("SELECT p.oid::regprocedure::text,pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig,p.proacl::text,p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('centerway','cw_sessions') ORDER BY 1").fetchall(),
    }


def export(dsn, destination, recipient):
    dest = Path(destination).absolute()
    private(dest.parent, True)
    require(not dest.exists() and not dest.is_symlink() and ROOT not in dest.parents)
    require(re.fullmatch(r'age1[0-9a-z]{58}',recipient) is not None)
    require(command(['pg_dump','--version']).startswith(b'pg_dump (PostgreSQL) 17.'))
    with connection_environment(dsn) as env, tempfile.TemporaryDirectory(dir=dest.parent) as temp:
        stage = Path(temp)
        with psycopg.connect(dsn,connect_timeout=10) as db:
            db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            db.execute("SET LOCAL statement_timeout='30s'")
            require(db.info.server_version//10000 == 17)
            require(db.execute('SELECT pg_database_size(current_database())').fetchone()[0] <= 256*1024*1024)
            require(db.execute("SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql'").fetchone()[0] == 0)
            require(db.execute('SELECT count(*) FROM pg_largeobject_metadata').fetchone()[0] == 0)
            snapshot = db.execute('SELECT pg_export_snapshot()').fetchone()[0]
            baseline = inventory(db)
            roles = db.execute("SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY 1").fetchall()
            memberships = db.execute("SELECT a.rolname,b.rolname FROM pg_auth_members m JOIN pg_roles a ON a.oid=m.roleid JOIN pg_roles b ON b.oid=m.member WHERE a.rolname NOT LIKE 'pg_%' AND b.rolname NOT LIKE 'pg_%' ORDER BY 1,2").fetchall()
            manifest = {'format':'centerway-g2-v1','tables':baseline,'structure':structure(db),
                        'roles':roles,'memberships':memberships,'sessions':'preserved-quarantined',
                        'runtime_secrets':'excluded-separate-custody-required'}
            output = stage/'database.age'
            with output.open('xb') as stream:
                os.chmod(output,0o600)
                dump = sp.Popen(['pg_dump','--format=custom','--snapshot='+snapshot,'--lock-wait-timeout=10s'],env=env,stdout=sp.PIPE,stderr=sp.DEVNULL)
                cipher = None
                try:
                    cipher = sp.Popen(['age','-r',recipient],stdin=dump.stdout,stdout=stream,stderr=sp.DEVNULL,
                                      env={'PATH':os.environ.get('PATH','/usr/bin:/bin')})
                    dump.stdout.close()
                    deadline=time.monotonic()+TIMEOUT
                    while dump.poll() is None or cipher.poll() is None:
                        require(time.monotonic()<deadline and output.stat().st_size<=LIMIT)
                        require(dump.poll() in (None,0) and cipher.poll() in (None,0))
                        time.sleep(.05)
                    require(dump.returncode==0 and cipher.returncode==0 and 0<output.stat().st_size<=LIMIT)
                    stream.flush(); os.fsync(stream.fileno())
                finally:
                    for process in (dump,cipher):
                        if process is not None:
                            if process.poll() is None: process.kill()
                            process.wait()
            manifest['cipher_sha256']=digest(output.read_bytes())
            sealed=command(['age','-r',recipient],encode(manifest))
            (stage/'manifest.age').touch(mode=0o600)
            (stage/'manifest.age').write_bytes(sealed)
            (stage/'checksums.json').touch(mode=0o600)
            (stage/'checksums.json').write_bytes(encode({p.name:digest(p.read_bytes()) for p in (output,stage/'manifest.age')}))
        # Atomic publish without clobbering an existing bundle, including races.
        os.mkdir(dest,0o700)
        try:
            for p in stage.iterdir(): os.rename(p,dest/p.name)
        except Exception:
            shutil.rmtree(dest)
            raise


def restore(archive, identity):
    folder=private(archive,True); key=private(identity)
    require({p.name for p in folder.iterdir()}=={'database.age','manifest.age','checksums.json'})
    for p in folder.iterdir():
        private(p); require(p.stat().st_size<=LIMIT)
    checks=json.loads((folder/'checksums.json').read_bytes())
    require(checks=={name:digest((folder/name).read_bytes()) for name in ('database.age','manifest.age')})
    manifest=json.loads(command(['age','-d','-i',str(key),str(folder/'manifest.age')]))
    require(manifest['format']=='centerway-g2-v1' and manifest['sessions']=='preserved-quarantined')
    require(manifest['cipher_sha256']==checks['database.age'])
    # Authenticate ALL ciphertext before executing any archived SQL.
    clear=command(['age','-d','-i',str(key),str(folder/'database.age')])
    return restore_payload(manifest, clear)


def restore_payload(manifest, clear):
    # Authenticated local decryption or an explicitly trusted private channel only.
    require(manifest['format']=='centerway-g2-v1' and manifest['sessions']=='preserved-quarantined')
    require(len(clear)<=LIMIT and clear.startswith(b'PGDMP'))
    name='cw-g2-restore-'+uuid.uuid4().hex
    try:
        command(['docker','run','-d','--name',name,'--network','none','--memory','512m','--cpus','1',
                 '--pids-limit','128','--tmpfs','/var/lib/postgresql/data:rw,noexec,nosuid,size=512m',
                 '-e','POSTGRES_HOST_AUTH_METHOD=trust',IMAGE])
        isolated=json.loads(command(['docker','inspect',name]))[0]
        require(isolated['HostConfig']['NetworkMode']=='none' and not isolated['HostConfig']['PortBindings']
                and not isolated['HostConfig']['Binds'])
        for _ in range(60):
            try:
                command(['docker','exec',name,'sh','-c','test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres']); break
            except RecoveryError: time.sleep(.2)
        else: raise RecoveryError('isolated_target_unavailable')
        # No source DSN, network, bind mounts, persistent volumes or published port.
        statements=[]
        for role, in manifest['roles']:
            if role=='postgres': continue
            identifier=sql.Identifier(role).as_string()
            statements.append(f'CREATE ROLE {identifier} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;')
        for group,member in manifest['memberships']:
            statements.append(sql.SQL('GRANT {} TO {};').format(sql.Identifier(group),sql.Identifier(member)).as_string())
        command(['docker','exec','-i',name,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres'], '\n'.join(statements).encode())
        command(['docker','exec','-i',name,'pg_restore','--single-transaction','--exit-on-error','-U','postgres','-d','postgres'],clear)
        # Verifier executes within the networkless sandbox via SQL protocol adapter.
        class Cursor:
            def __init__(self,rows): self.rows=rows
            def fetchall(self): return self.rows
        class Database:
            def execute(self,query):
                query=query.as_string() if hasattr(query,'as_string') else query
                wrapped='SELECT coalesce(json_agg(q),\'[]\'::json) FROM ('+query+') q'
                raw=command(['docker','exec','-i',name,'psql','-X','-At','-v','ON_ERROR_STOP=1','-U','postgres'],wrapped.encode())
                return Cursor([tuple(row.values()) for row in json.loads(raw)])
        db=Database()
        require(inventory(db)==manifest['tables'])
        require(encode(structure(db))==encode(manifest['structure']))
        # Exercise actual session_user identity for every restored membership.
        members=db.execute('SELECT principal::text,tenant_id::text FROM centerway.memberships ORDER BY 1,2').fetchall()
        tenants=db.execute('SELECT tenant_id::text FROM centerway.companies ORDER BY 1').fetchall()
        for principal in sorted({m[0] for m in members}):
            for tenant, in tenants:
                statement=sql.SQL('SET SESSION AUTHORIZATION {}; SELECT centerway.allowed({});').format(sql.Identifier(principal),sql.Literal(tenant)).as_string()
                allowed=command(['docker','exec','-i',name,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','postgres'],statement.encode()).strip()
                require(allowed==(b't' if (principal,tenant) in members else b'f'))
        require(db.execute("SELECT count(*) FROM pg_roles WHERE rolname <> 'postgres' AND rolname NOT LIKE 'pg_%' AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)").fetchall()[0][0]==0)
        return {'status':'isolated_restore_verified','tables':len(manifest['tables']),
                'sessions':'preserved-quarantined','runtime_ready':False}
    finally:
        command(['docker','rm','-fv',name])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('operation',choices=['export','restore'])
    p.add_argument('--archive',required=True)
    p.add_argument('--config'); p.add_argument('--recipient'); p.add_argument('--identity')
    args=p.parse_args()
    if args.operation=='export':
        config=json.loads(private(args.config).read_bytes())
        export(config['dsn'],args.archive,args.recipient or '')
        print('encrypted_export_created_external_custody_pending')
    else:
        print(json.dumps(restore(args.archive,args.identity),sort_keys=True))


if __name__=='__main__':
    try: main()
    except Exception:
        print('recovery_failed',file=__import__('sys').stderr)
        raise SystemExit(1)
