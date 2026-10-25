"""Private preview transport and provisioning; never deploys or opens a tunnel."""
import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import ipaddress
import re
from pathlib import Path
import secrets
import sqlite3
import ssl
import signal
import threading
import time
from urllib.parse import urlparse

from .store import Store, encode

PRINCIPALS = {'founder': [('atlas','operator'),('nimbus','operator')],
              'atlas-private': [('atlas','operator')],
              'reader-private': [('nimbus','viewer')]}
MARKER = 'centerway-synthetic-preview-v1'
REPOSITORY = Path(__file__).resolve().parents[2]


def canonical_origin(origin):
    parsed = urlparse(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or any(c.isspace() for c in origin)
            or parsed.hostname != parsed.hostname.lower()):
        raise ValueError('É necessária uma origem HTTPS exata, sem caminho ou credenciais.')
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',parsed.hostname,flags=re.ASCII):
            raise ValueError('Hostname HTTPS inválido; não são permitidos wildcards.')
    if parsed.netloc!=parsed.netloc.lower() or '%' in parsed.hostname:
        raise ValueError('Usar hostname canónico, sem escapes.')
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError('Porta HTTPS inválida.')
    return origin


def provision(db_path, credentials_file, origin, hours=24):
    from .synthetic import populate
    origin = canonical_origin(origin)
    if not 1 <= hours <= 24:
        raise ValueError('A pré-visualização deve expirar entre 1 e 24 horas.')
    db_path, credentials_file = Path(db_path).resolve(), Path(credentials_file).resolve()
    if REPOSITORY in credentials_file.parents or REPOSITORY in db_path.parents:
        raise ValueError('Base e credenciais privadas devem ficar fora do checkout Git.')
    if db_path == credentials_file or db_path.exists() or credentials_file.exists():
        raise ValueError('Usar caminhos novos e distintos; não se substituem bases ou credenciais.')
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive file creation prevents accidental reuse of a lab database.
    db_path.touch(mode=0o600, exist_ok=False)
    try:
        store = Store(db_path,seed_demo=False)
        passwords = {user:secrets.token_urlsafe(32) for user in PRINCIPALS}
        with store.transaction() as db:
            db.execute('DELETE FROM sessions')
            db.execute('DELETE FROM memberships')
            db.execute('DELETE FROM users')
            for user,memberships in PRINCIPALS.items():
                salt = secrets.token_hex(16)
                digest = hashlib.scrypt(passwords[user].encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
                db.execute('INSERT INTO users VALUES (?,?)',(user,salt+':'+digest))
                db.executemany('INSERT INTO memberships VALUES (?,?,?)',[(user,*membership) for membership in memberships])
        populate(store, actor='founder')
        expires = (datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat()
        with store.transaction() as db:
            db.execute('CREATE TABLE preview_metadata(marker TEXT PRIMARY KEY, origin TEXT NOT NULL, expires TEXT NOT NULL)')
            db.execute('INSERT INTO preview_metadata VALUES (?,?,?)',(MARKER,origin,expires))
        fd = os.open(credentials_file,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as descriptor:
            descriptor.write(encode({'origin':origin,'expires':expires,'accounts':passwords}))
    except BaseException:
        # Only paths exclusively created by this invocation are removed.
        db_path.unlink(missing_ok=True)
        raise
    return {'db':str(db_path),'credentials_file':str(credentials_file),'expires':expires}


class LoginLimiter:
    """Bound both source address and account; forwarded headers are never identity."""
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = {}

    def allow(self, peer, user):
        instant = time.monotonic()
        keys = ('ip:'+peer,'account:'+user)
        with self.lock:
            self.entries = {key:deque(t for t in values if t>instant-60)
                            for key,values in self.entries.items() if values and values[-1]>instant-60}
            if len(self.entries)>2048 or any(len(self.entries.get(key,()))>=10 for key in keys):
                return False
            for key in keys:
                self.entries.setdefault(key,deque()).append(instant)
            return True


class PreviewPolicy:
    mode = 'demo'
    def __init__(self, store):
        with store.transaction() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='production_metadata'").fetchone():
                raise ValueError('Uma base production não pode ser aberta como demo.')
            try:
                row = db.execute('SELECT * FROM preview_metadata WHERE marker=?',(MARKER,)).fetchone()
            except sqlite3.OperationalError:
                row = None
            if not row:
                raise ValueError('Base sem proveniência de sandbox privado; arranque recusado.')
            self.origin = canonical_origin(row['origin'])
            self.expires = datetime.fromisoformat(row['expires'])
            if self.expires.tzinfo is None or self.expired():
                raise ValueError('Pré-visualização expirada ou sem prazo válido.')
            users = db.execute('SELECT id,password_hash FROM users').fetchall()
            memberships = {(r['user_id'],r['tenant'],r['role']) for r in db.execute('SELECT * FROM memberships')}
            expected = {(user,*membership) for user,rows in PRINCIPALS.items() for membership in rows}
            if {r['id'] for r in users} != set(PRINCIPALS) or memberships != expected:
                raise ValueError('A base deve conter apenas as contas privadas e permissões previstas.')
            for user in users:
                salt,digest = user['password_hash'].split(':')
                public = hashlib.scrypt(b'centerway-local',salt=salt.encode(),n=16384,r=8,p=1).hex()
                if hmac.compare_digest(digest,public):
                    raise ValueError('Credencial pública detetada; arranque recusado.')
        self.authority = urlparse(self.origin).netloc
        self.limiter = LoginLimiter()

    def expired(self):
        return datetime.now(timezone.utc)>=self.expires


def main():
    parser = argparse.ArgumentParser(description='Pré-visualização privada HTTPS; não publica nem cria túneis.')
    sub = parser.add_subparsers(dest='operation',required=True)
    init = sub.add_parser('init')
    init.add_argument('--db',required=True)
    init.add_argument('--credentials-file',required=True)
    init.add_argument('--origin',required=True)
    init.add_argument('--hours',type=int,default=24)
    serve = sub.add_parser('serve')
    serve.add_argument('--db',required=True)
    serve.add_argument('--certfile',required=True)
    serve.add_argument('--keyfile',required=True)
    serve.add_argument('--host',default='127.0.0.1')
    serve.add_argument('--port',type=int,default=8443)
    serve.add_argument('--frontend-origin',action='append',default=[],help='Origem HTTPS exata do frontend same-site; CORS desativado por omissão.')
    args = parser.parse_args()
    try:
        if args.operation=='init':
            print(encode(provision(args.db,args.credentials_file,args.origin,args.hours)))
            return
        if not Path(args.db).is_file():
            raise ValueError('Base privada inexistente; nenhuma base de laboratório será criada.')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.certfile,args.keyfile)
        store = Store.open_existing(args.db)
        policy = PreviewPolicy(store)
        from .server import make_server
        server = make_server(store,args.host,args.port,preview=policy,tls_context=context,frontend_origins=args.frontend_origin)
    except (ValueError,OSError,sqlite3.Error) as error:
        parser.exit(1,'Arranque recusado: '+str(error)+'\n')
    run_private_server(server)


def run_private_server(server):
    server.daemon_threads = False
    def terminate(_signal, _frame):
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,terminate)
    print('Servidor HTTPS privado iniciado. URL pública e certificado válido têm de ser fornecidos pela infraestrutura.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
