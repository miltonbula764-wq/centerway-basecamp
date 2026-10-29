"""Persistent SYNTHETIC demonstration. All listeners remain on IPv4 loopback.
No cloud API, DNS, public listener or automatic migration on restart.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'infra'))
from local_stack import LocalStack, free_port
from certificates import command
from demo.provision import provision

POSTGRES_IMAGE = json.loads((Path(__file__).with_name('versions.json')).read_text())['postgres_image']


def private_json(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, indent=2)


def migration_hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'sql').glob('*.sql'))+sorted((ROOT/'api'/'sql').glob('*.sql'))}


def pki(path):
    path.mkdir(mode=0o700)
    # Explicit local trust only. No ACME or public certificate request.
    command('req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-days','90',
            '-subj','/CN=CENTERWAY SYNTHETIC DEMO CA','-addext','basicConstraints=critical,CA:TRUE',
            '-keyout',path/'ca.key','-out',path/'ca.crt')
    (path/'leaf.ext').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n')
    for name in ('edge','api','db'):
        command('req','-new','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes',
                '-subj','/CN=localhost','-keyout',path/f'{name}.key','-out',path/f'{name}.csr')
        command('x509','-req','-in',path/f'{name}.csr','-CA',path/'ca.crt','-CAkey',path/'ca.key',
                '-CAcreateserial','-days','30','-extfile',path/'leaf.ext','-out',path/f'{name}.crt')


class PersistentDemo(LocalStack):
    def __init__(self, state, caddy):
        if Path(state).is_symlink():
            raise ValueError('State must not be a symlink')
        self.state = Path(state).resolve()
        if ROOT.parent == self.state or ROOT.parent in self.state.parents or any(c.isspace() for c in str(self.state)):
            raise ValueError('Private state must be outside the checkout, without whitespace')
        self.caddy = str(Path(caddy).resolve())
        self.api = self.proxy = None
        self.logs = []
        self.env = os.environ.copy()
        self.container = None

    def read_manifest(self):
        for path in (self.state, self.state/'manifest.json', self.state/'config.json', self.state/'credentials.json'):
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise ValueError('Private demonstration state required')
        manifest = json.loads((self.state/'manifest.json').read_text())
        if manifest['status'] != 'ready' or manifest['migrations'] != migration_hashes() or manifest.get('postgres_image') != POSTGRES_IMAGE:
            raise ValueError('Incomplete installation or migration drift; no automatic reseed/upgrade')
        if not manifest['synthetic_only']:
            raise ValueError('Synthetic demonstration state required')
        self.container = manifest['container']
        self.api_port, self.port, self.http_port = (manifest[k] for k in ('api_port','port','http_port'))
        self.config = json.loads((self.state/'config.json').read_text())
        if self.config.get('demo') is not False:
            raise ValueError('Actual HTTPS and PostgreSQL TLS guards are required')
        self.credentials = json.loads((self.state/'credentials.json').read_text())
        self.env.update(CENTERWAY_API_CONFIG=str(self.state/'config.json'),
            CENTERWAY_UPSTREAM_ADDR=f'127.0.0.1:{self.api_port}',
            CENTERWAY_TLS_CERT=str(self.state/'pki'/'api.crt'),CENTERWAY_TLS_KEY=str(self.state/'pki'/'api.key'),
            UPSTREAM_ADDR=f'127.0.0.1:{self.api_port}',UPSTREAM_CA=str(self.state/'pki'/'ca.crt'),
            XDG_DATA_HOME=str(self.state/'caddy-data'),XDG_CONFIG_HOME=str(self.state/'caddy-config'),
            LOCAL_HTTP_PORT=str(self.http_port),HTTPS_PORT=str(self.port),
            TLS_CERT=str(self.state/'pki'/'edge.crt'),TLS_KEY=str(self.state/'pki'/'edge.key'))
        return manifest

    def ready_database(self):
        for _ in range(120):
            result = subprocess.run(['docker','exec',self.container,'sh','-c',
                'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres'],capture_output=True)
            if result.returncode == 0:
                return
            time.sleep(.25)
        raise RuntimeError('Private PostgreSQL startup timeout')

    def create_database(self, manifest):
        self.run('docker','run','-d','--name',manifest['container'],
            '--label','centerway.synthetic=true','--restart','unless-stopped',
            '--env-file',str(self.state/'postgres.env'),
            '--mount',f'type=volume,src={manifest["volume"]},dst=/var/lib/postgresql/data',
            '--mount',f'type=volume,src={manifest["volume"]}-tls,dst=/run/centerway-tls,readonly',
            '-p',f'127.0.0.1:{manifest["db_port"]}:5432','--memory','768m',
            '--log-opt','max-size=5m','--log-opt','max-file=2',POSTGRES_IMAGE,
            '-c','shared_buffers=128MB','-c','max_connections=30',
            '-c','ssl=on','-c','ssl_cert_file=/run/centerway-tls/server.crt',
            '-c','ssl_key_file=/run/centerway-tls/server.key')

    def initialize(self):
        if self.state.exists():
            # bootstrap may create these two installation directories, nothing else.
            if self.state.stat().st_mode & 0o077 or set(p.name for p in self.state.iterdir())-{'venv','bin'}:
                raise ValueError('Initialization requires fresh private state; never reinitialize existing data')
        else:
            self.state.mkdir(mode=0o700, parents=False)
        old = os.umask(0o077)
        try:
            ident = secrets.token_hex(6)
            manifest = dict(status='initializing',synthetic_only=True,container='centerway-c03-'+ident,
                volume='centerway-c03-'+ident,db_port=free_port(),api_port=free_port(),port=free_port(),http_port=free_port(),
                migrations=migration_hashes(),postgres_image=POSTGRES_IMAGE,future_domain='api.getcenterway.com')
            self.container = manifest['container']
            private_json(self.state/'manifest.json',manifest)
            pki(self.state/'pki')
            (self.state/'postgres.env').write_text('POSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\n')
            # Prepare certificate ownership within the named volume, without host UID assumptions.
            self.run('docker','volume','create','--label','centerway.synthetic=true',manifest['volume'])
            self.run('docker','volume','create','--label','centerway.synthetic=true',manifest['volume']+'-tls')
            self.run('docker','run','--rm','--mount',f'type=volume,src={manifest["volume"]}-tls,dst=/data',
                '--mount',f'type=bind,src={self.state / "pki"},dst=/pki,readonly',
                '--entrypoint','sh',POSTGRES_IMAGE,'-c',
                'cp /pki/db.crt /data/server.crt && cp /pki/db.key /data/server.key && chown postgres:postgres /data/server.* && chmod 0600 /data/server.*')
            self.create_database(manifest)
            self.ready_database()
            for migration in sorted((ROOT/'sql').glob('*.sql')):
                self.sql(migration.read_text())
            config, _ = provision(self.container,str(manifest['db_port']),self.state)
            from scenario import setup_policy
            setup_policy(self)
            config['demo'] = False  # Actual WSGI TLS + PG verify-full guards; all data still synthetic.
            config['origins'] = ['https://lovable.example.invalid']
            for user in config['users'].values():
                user['dsn'] = user['dsn'].replace('sslmode=disable','sslmode=verify-full sslrootcert='+str(self.state/'pki'/'ca.crt'))
            (self.state/'config.json').write_text(json.dumps(config,indent=2))
            manifest['status'] = 'ready'
            temporary = self.state/'manifest.ready'
            private_json(temporary,manifest)
            temporary.replace(self.state/'manifest.json')
            self.read_manifest()
        finally:
            os.umask(old)

    def __enter__(self):
        try:
            manifest = self.read_manifest()
            # Fail if state moved, containers changed or administrator replaced bindings.
            inspection = json.loads(self.run('docker','inspect',self.container))[0]
            mounts = inspection['Mounts']
            bindings = inspection['HostConfig']['PortBindings']
            if inspection['Config']['Labels'].get('centerway.synthetic') != 'true' or not any(
                    m.get('Name') == manifest['volume'] and m['Destination'] == '/var/lib/postgresql/data' for m in mounts):
                raise ValueError('Unexpected database container identity')
            if bindings != {'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':str(manifest['db_port'])}]}:
                raise ValueError('PostgreSQL must remain private on loopback')
            self.run('docker','start',self.container)
            self.ready_database()
            self.start_api(); self.start_proxy()
            return self
        except BaseException:
            self.close(); raise

    def close(self):
        # Persistence is intentional: never delete PostgreSQL volume, SQLite, PKI or receipts.
        self.stop(self.proxy); self.stop(self.api)
        self.proxy = self.api = None
        for log in self.logs:
            log.close()
        self.logs.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('init','serve','stop-db','status'))
    parser.add_argument('--state',required=True)
    parser.add_argument('--caddy',required=True)
    args = parser.parse_args()
    demo = PersistentDemo(args.state,args.caddy)
    if args.command == 'init':
        demo.initialize()
        print('SYNTHETIC private installation prepared; no public service. State: '+str(demo.state))
    elif args.command == 'serve':
        signal.signal(signal.SIGTERM,lambda *_: sys.exit(0))
        with demo:
            print(f'SYNTHETIC loopback HTTPS: https://localhost:{demo.port}',flush=True)
            try:
                while True:
                    if demo.api.poll() is not None or demo.proxy.poll() is not None:
                        raise RuntimeError('Local API/gateway stopped; supervisor must restart')
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        demo.read_manifest()
        if args.command == 'stop-db':
            demo.run('docker','stop',demo.container)
        else:
            print(demo.run('docker','inspect','--format','{{.State.Status}}',demo.container))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Do not emit SQL, DSNs, configuration or passwords on operational failure.
        print('Demonstration command failed; private state preserved. Check local setup and runbook.',file=sys.stderr)
        sys.exit(1)
