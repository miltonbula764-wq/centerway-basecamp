"""Permanent private authentication foundation. Business operations remain disabled."""
from contextlib import closing
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import uuid

from .core import Core, Problem
from .http_contract import strict_json
from .preview import canonical_origin, LoginLimiter, REPOSITORY
from .store import Store, encode, now

BUSINESS_TABLES = ('environments','observations','cases','ingestion_batches','executions','history')
RESERVED_USERS = {'demo','atlas','leitor','founder','atlas-private','reader-private'}
IDENTIFIER = r'[a-z0-9][a-z0-9_-]{0,63}'
MARKER = 'centerway-production-foundation-v1'
COUNTS = ('observation','deterioration','investigation','intervention','recovery','exceptions','stable')


def private_file(path):
    path=Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Ficheiro privado com permissões 0600 necessário.')
    return path


def new_private_path(path):
    path=Path(path).resolve()
    if REPOSITORY in path.parents or path.exists():
        raise ValueError('Usar um ficheiro novo, fora do checkout.')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.parent.stat().st_mode & 0o077:
        raise ValueError('Diretório privado 0700 necessário.')
    return path


def accounts_config(path):
    path=private_file(path)
    if path.stat().st_size>65536:
        raise ValueError('Configuração demasiado grande.')
    body=strict_json(path.read_bytes())
    if not isinstance(body,dict) or set(body)!={'accounts'} or not isinstance(body['accounts'],list) or not 1<=len(body['accounts'])<=100:
        raise ValueError('Configuração exige entre 1 e 100 contas explícitas.')
    result={}
    for account in body['accounts']:
        if not isinstance(account,dict) or set(account)!={'user','memberships'}:
            raise ValueError('Conta admite apenas user e memberships, nunca passwords.')
        user=account['user'];memberships=account['memberships']
        if not isinstance(user,str) or not re.fullmatch(IDENTIFIER,user) or user in RESERVED_USERS or user in result:
            raise ValueError('Utilizador inválido, duplicado ou reservado à demo.')
        if not isinstance(memberships,list) or not 1<=len(memberships)<=20:
            raise ValueError('Cada conta exige entre 1 e 20 memberships.')
        rows={}
        for membership in memberships:
            if not isinstance(membership,dict) or set(membership)!={'tenant','role'}:
                raise ValueError('Membership exige tenant e role.')
            tenant,role=membership['tenant'],membership['role']
            if not isinstance(tenant,str) or not re.fullmatch(IDENTIFIER,tenant) or tenant in ('atlas','nimbus') or tenant in rows or role not in ('operator','viewer'):
                raise ValueError('Membership inválida, duplicada ou reservada à demo.')
            rows[tenant]=role
        result[user]=rows
    if not any(role=='operator' for rows in result.values() for role in rows.values()):
        raise ValueError('É necessária pelo menos uma conta operator.')
    return result


def password_hash(password):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()


def secret_output(path, payload):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            output.write(encode(payload));output.flush();os.fsync(output.fileno())
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def guards():
    result={}
    for table in BUSINESS_TABLES:
        for operation in ('INSERT','UPDATE','DELETE'):
            name=f'production_block_{table}_{operation}'
            result[name]=f"CREATE TRIGGER {name} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'production_operations_disabled'); END"
    for table in ('production_metadata','production_auth_audit'):
        for operation in ('UPDATE','DELETE'):
            name=f'production_immutable_{table}_{operation}'
            result[name]=f"CREATE TRIGGER {name} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    return result


def audit(db,event,detail):
    db.execute('INSERT INTO production_auth_audit(event,actor,detail,created_at) VALUES (?,?,?,?)',(event,'local-operator',encode(detail),now()))


def provision(db_path, credentials_file, origin, config_file):
    origin=canonical_origin(origin);config=accounts_config(config_file)
    path=new_private_path(db_path);output=new_private_path(credentials_file)
    if path==output:
        raise ValueError('Base e credenciais exigem caminhos distintos.')
    path.touch(mode=0o600,exist_ok=False)
    wrote_secret=False
    try:
        # No demo accounts, customers, observations or cases are ever seeded.
        store=Store(path,seed_demo=False,seed_accounts=False)
        passwords={user:secrets.token_urlsafe(32) for user in config}
        with store.transaction() as db:
            db.execute('CREATE TABLE production_metadata(marker TEXT PRIMARY KEY, mode TEXT NOT NULL CHECK(mode=\'production\'), origin TEXT NOT NULL, instance_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)')
            db.execute('INSERT INTO production_metadata VALUES (?,?,?,?,?)',(MARKER,'production',origin,uuid.uuid4().hex,now()))
            db.execute('CREATE TABLE production_auth_audit(id INTEGER PRIMARY KEY,event TEXT NOT NULL,actor TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL)')
            for name,sql in guards().items(): db.execute(sql)
            for user,rows in config.items():
                db.execute('INSERT INTO users VALUES (?,?)',(user,password_hash(passwords[user])))
                db.executemany('INSERT INTO memberships VALUES (?,?,?)',[(user,tenant,role) for tenant,role in rows.items()])
            audit(db,'provision',{'accounts':len(config),'business_operations':'disabled'})
            secret_output(output,{'mode':'production','origin':origin,'accounts':passwords});wrote_secret=True
        ProductionPolicy(Store.open_existing(path))
    except BaseException:
        path.unlink(missing_ok=True)
        if wrote_secret: output.unlink(missing_ok=True)
        raise
    return {'status':'initialized','mode':'production','business_operations':'disabled'}


class ProductionPolicy:
    mode='production'
    expires=None

    def __init__(self,store):
        private_file(store.path)
        with closing(store.connect()) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='preview_metadata'").fetchone():
                raise ValueError('Base demo não pode ser aberta como production.')
            row=db.execute('SELECT * FROM production_metadata WHERE marker=?',(MARKER,)).fetchone()
            if not row or row['mode']!='production':
                raise ValueError('Marcador production ausente.')
            self.origin=canonical_origin(row['origin']);self.instance_id=row['instance_id']
            self.validate_runtime(store)
            users=db.execute('SELECT id,password_hash FROM users').fetchall()
            if not users or len(users)>100:
                raise ValueError('Contas privadas necessárias.')
            for user in users:
                if not isinstance(user['id'],str) or user['id'] in RESERVED_USERS or not re.fullmatch(IDENTIFIER,user['id']):
                    raise ValueError('Conta de demo ou inválida em production.')
                if not isinstance(user['password_hash'],str) or user['password_hash'].count(':')!=1:
                    raise ValueError('Formato de credencial não autorizado.')
                salt,digest=user['password_hash'].split(':')
                if not re.fullmatch(r'[a-f0-9]{32}',salt) or not re.fullmatch(r'[a-f0-9]{128}',digest):
                    raise ValueError('Formato de credencial não autorizado.')
                public=hashlib.scrypt(b'centerway-local',salt=salt.encode(),n=16384,r=8,p=1).hex()
                if hmac.compare_digest(digest,public):
                    raise ValueError('Credencial pública não autorizada.')
            rows=db.execute('SELECT user_id,tenant,role FROM memberships').fetchall()
            if not rows or not any(r['role']=='operator' for r in rows) or {u['id'] for u in users}!={r['user_id'] for r in rows}:
                raise ValueError('Memberships incompletas.')
            if any(not isinstance(r['tenant'],str) or r['tenant'] in ('atlas','nimbus') or not re.fullmatch(IDENTIFIER,r['tenant']) or r['role'] not in ('operator','viewer') for r in rows):
                raise ValueError('Membership não autorizada.')
        from urllib.parse import urlparse
        self.authority=urlparse(self.origin).netloc;self.limiter=LoginLimiter()

    def expired(self):
        return False  # This separate mode has no preview lease; sessions still expire.

    def validate_runtime(self,store):
        private_file(store.path)
        with closing(store.connect()) as db:
            row=db.execute('SELECT * FROM production_metadata WHERE marker=?',(MARKER,)).fetchone()
            if not row or row['mode']!='production' or row['origin']!=self.origin or row['instance_id']!=self.instance_id:
                raise ValueError('Configuração de modo/origem/instância alterada.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='preview_metadata'").fetchone():
                raise ValueError('Modos misturados.')
            present={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")}
            if any(present.get(name)!=sql for name,sql in guards().items()):
                raise ValueError('Bloqueios de production ausentes ou alterados.')
            if any(db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in BUSINESS_TABLES):
                raise ValueError('Dados de negócio não autorizados nesta fundação.')

    def view(self,store,user,tenant=None,customer=None,case_id=None):
        with store.transaction() as db:
            if tenant: Core(store).authorize(db,user,tenant)
            if customer or case_id:
                raise Problem(503,'Consulta operacional indisponível em production; nenhum dado simulado será apresentado.')
            memberships=[dict(r) for r in db.execute('SELECT tenant,role FROM memberships WHERE user_id=? ORDER BY tenant',(user,))]
            return {'user':user,'memberships':memberships,'environment_type':'production',
                    'decision_mode':'disabled','registry':[],'counts':dict.fromkeys(COUNTS,0)}

    def block_operation(self,store,user,tenant):
        with store.transaction() as db: Core(store).authorize(db,user,tenant,write=True)
        raise Problem(503,'Operação indisponível em production: não preparada/autorizada; nenhum efeito foi executado.')


def apply_accounts(db_path,config_file,credentials_file):
    config=accounts_config(config_file);store=Store.open_existing(private_file(db_path));ProductionPolicy(store)
    output=new_private_path(credentials_file);wrote_secret=False
    try:
        with store.transaction() as db:
            existing={r['id'] for r in db.execute('SELECT id FROM users')}
            passwords={user:secrets.token_urlsafe(32) for user in set(config)-existing}
            changed=set()
            for user in existing|set(config):
                before={r['tenant']:r['role'] for r in db.execute('SELECT tenant,role FROM memberships WHERE user_id=?',(user,))}
                if user not in config or before!=config[user]: changed.add(user)
            for user in changed: db.execute('DELETE FROM sessions WHERE user_id=?',(user,))
            for user in existing-set(config):
                db.execute('DELETE FROM memberships WHERE user_id=?',(user,));db.execute('DELETE FROM users WHERE id=?',(user,))
            for user,rows in config.items():
                if user in passwords: db.execute('INSERT INTO users VALUES (?,?)',(user,password_hash(passwords[user])))
                db.execute('DELETE FROM memberships WHERE user_id=?',(user,))
                db.executemany('INSERT INTO memberships VALUES (?,?,?)',[(user,tenant,role) for tenant,role in rows.items()])
            audit(db,'apply-accounts',{'created':len(passwords),'removed':len(existing-set(config)),'sessions_revoked_for':sorted(changed)})
            secret_output(output,{'mode':'production','accounts':passwords});wrote_secret=True
    except BaseException:
        if wrote_secret: output.unlink(missing_ok=True)
        raise
    return {'status':'configured','mode':'production','new_accounts':len(passwords)}


def rotate_password(db_path,user,credentials_file):
    store=Store.open_existing(private_file(db_path));ProductionPolicy(store)
    output=new_private_path(credentials_file);wrote_secret=False
    try:
        with store.transaction() as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(user,)).fetchone():
                raise ValueError('Conta inexistente.')
            password=secrets.token_urlsafe(32)
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),user))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user,))
            audit(db,'rotate-password',{'user':user,'sessions_revoked':True})
            secret_output(output,{'mode':'production','accounts':{user:password}});wrote_secret=True
    except BaseException:
        if wrote_secret: output.unlink(missing_ok=True)
        raise
    return {'status':'rotated','mode':'production'}
