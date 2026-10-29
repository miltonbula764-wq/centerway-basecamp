"""Isolated C01 synthetic lifecycle. No tunnels, public binds, DNS or ACME calls."""
import json
import os
import re
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'api'))
from demo.provision import provision
from app import Database
from certificates import generate


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]


class LocalStack:
    def __init__(self, caddy):
        self.caddy=str(Path(caddy).resolve()); self.state=Path(tempfile.mkdtemp(prefix='centerway-c01-'))
        self.container='centerway-c01-'+secrets.token_hex(6)
        self.api=None; self.proxy=None; self.logs=[]
        self.api_port=free_port(); self.port=free_port()
        self.env=os.environ.copy()

    def run(self,*args,input=None):
        result=subprocess.run(args,input=input,text=True,capture_output=True)
        if result.returncode: raise RuntimeError('Local infrastructure command failed: '+args[0])
        return result.stdout.strip()

    def sql(self,sql):
        return self.run('docker','exec','-i',self.container,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres',input=sql)

    def __enter__(self):
        try:
            generate(self.state/'pki')
            self.run('docker','run','-d','--name',self.container,'-e','POSTGRES_PASSWORD='+secrets.token_urlsafe(32),'-p','127.0.0.1::5432','postgres:17-alpine')
            for _ in range(60):
                ready=subprocess.run(['docker','exec',self.container,'sh','-c','test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres'],capture_output=True)
                if ready.returncode==0: break
                time.sleep(.25)
            else: raise RuntimeError('PostgreSQL startup timeout')
            for migration in sorted((ROOT/'sql').glob('*.sql')): self.sql(migration.read_text())
            port=self.run('docker','port',self.container,'5432/tcp').split(':')[-1]
            self.config,self.credentials=provision(self.container,port,self.state)
            for suffix in ('crt','key'):
                self.run('docker','cp',str(self.state/'pki'/('db.'+suffix)),self.container+':/var/lib/postgresql/data/c01.'+suffix)
            self.run('docker','exec',self.container,'chown','postgres:postgres','/var/lib/postgresql/data/c01.key','/var/lib/postgresql/data/c01.crt')
            self.run('docker','exec',self.container,'chmod','0600','/var/lib/postgresql/data/c01.key')
            self.sql("ALTER SYSTEM SET ssl='on'; ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/data/c01.crt'; ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/data/c01.key'; SELECT pg_reload_conf();")
            self.config['demo']=False
            self.config['origins']=['https://lovable.example.invalid']
            for user in self.config['users'].values():
                user['dsn']=user['dsn'].replace('sslmode=disable','sslmode=verify-full sslrootcert='+str(self.state/'pki'/'ca.crt'))
            (self.state/'config.json').write_text(json.dumps(self.config))
            for _ in range(30):
                try: Database(False).call(self.config['users']['alice'],'identity'); break
                except Exception: time.sleep(.1)
            else: raise RuntimeError('Verified PostgreSQL TLS did not become ready')
            self.env.update(CENTERWAY_API_CONFIG=str(self.state/'config.json'),CENTERWAY_UPSTREAM_ADDR=f'127.0.0.1:{self.api_port}',
                CENTERWAY_TLS_CERT=str(self.state/'pki'/'api.crt'),CENTERWAY_TLS_KEY=str(self.state/'pki'/'api.key'),
                UPSTREAM_ADDR=f'127.0.0.1:{self.api_port}',UPSTREAM_CA=str(self.state/'pki'/'ca.crt'),
                XDG_DATA_HOME=str(self.state/'caddy-data'),XDG_CONFIG_HOME=str(self.state/'caddy-config'),
                HTTPS_PORT=str(self.port),TLS_CERT=str(self.state/'pki'/'edge.crt'),TLS_KEY=str(self.state/'pki'/'edge.key'))
            self.start_api(); self.start_proxy()
            return self
        except BaseException:
            self.close(); raise

    def wait_port(self,port,process):
        for _ in range(100):
            if process.poll() is not None:
                # Startup error fields only; never dump config, certificates or whole logs.
                diagnostics=[]
                for path in self.state.glob('*.log'):
                    for line in path.read_text().splitlines():
                        try:
                            entry=json.loads(line)
                            if entry.get('level')=='error': diagnostics.append(str(entry.get('error',entry.get('msg','startup error'))))
                        except ValueError:
                            if line.startswith('Error: '): diagnostics.append(line)
                detail='; '.join(diagnostics[-2:])
                if not detail and process is self.proxy:
                    # Caddy can also fail before JSON logging initializes (Go/loader errors).
                    detail=(self.state/'proxy.log').read_text()[-3000:]
                detail=detail.replace(str(self.state),'<private-state>')
                detail=re.sub(r'Bearer [A-Za-z0-9_-]+','Bearer <redacted>',detail)
                detail=re.sub(r'password=[^\s]+','password=<redacted>',detail)
                for user in self.config['users'].values(): detail=detail.replace(user['dsn'],'<redacted>')
                for password in self.credentials.values(): detail=detail.replace(password,'<redacted>')
                raise RuntimeError(f'Local server exited ({process.returncode}): '+(detail[:3000] or 'no sanitized startup diagnostic'))
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1): return
            except OSError: time.sleep(.05)
        raise RuntimeError('Server startup timeout')

    def start_api(self):
        log=open(self.state/'api.log','a'); self.logs.append(log)
        self.api=subprocess.Popen([sys.executable,'-m','gunicorn','-c',str(ROOT/'infra'/'gunicorn.conf.py'),'app:load_app()'],cwd=ROOT/'api',env=self.env,stdout=log,stderr=log)
        self.wait_port(self.api_port,self.api)

    def start_proxy(self,wrong_ca=False):
        env=self.env.copy()
        if wrong_ca: env['UPSTREAM_CA']=str(self.state/'pki'/'edge.crt')
        log=open(self.state/'proxy.log','a'); self.logs.append(log)
        self.proxy=subprocess.Popen([self.caddy,'run','--config',str(ROOT/'infra'/'Caddyfile.local'),'--adapter','caddyfile'],cwd=ROOT/'infra',env=env,stdout=log,stderr=log)
        self.wait_port(self.port,self.proxy)

    @staticmethod
    def stop(process):
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

    def close(self):
        self.stop(self.proxy); self.stop(self.api)
        for log in self.logs: log.close()
        subprocess.run(['docker','rm','-f',self.container],capture_output=True)
        import shutil
        shutil.rmtree(self.state,ignore_errors=True)

    def __exit__(self,*args): self.close()

if __name__=='__main__':
    import signal
    def terminate(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    with LocalStack(sys.argv[1]) as stack:
        print(f'SYNTHETIC LOCAL HTTPS ONLY: https://localhost:{stack.port}')
        print(f'Private credentials/config: {stack.state}')
        print(f'Explicit client trust: --cacert {stack.state}/pki/ca.crt')
        print('No public CA certificate issued; no external connectivity proved. Ctrl-C removes all data.')
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: pass
