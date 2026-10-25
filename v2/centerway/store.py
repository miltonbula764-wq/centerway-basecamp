import hashlib
import json
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memberships(user_id TEXT REFERENCES users(id), tenant TEXT, role TEXT CHECK(role IN ('operator','viewer')), PRIMARY KEY(user_id, tenant));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS environments(tenant TEXT, customer TEXT, name TEXT, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant, customer));
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, tenant TEXT, customer TEXT, day TEXT, value INTEGER, source TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant, customer, day), FOREIGN KEY(tenant,customer) REFERENCES environments(tenant,customer));
CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, tenant TEXT, customer TEXT, stage TEXT NOT NULL, observation TEXT, detection TEXT, investigation TEXT, decision TEXT, verification TEXT, created_at TEXT NOT NULL, FOREIGN KEY(tenant,customer) REFERENCES environments(tenant,customer));
CREATE TABLE IF NOT EXISTS ingestion_batches(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, actor TEXT NOT NULL, payload_hash TEXT NOT NULL, inserted INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant,customer,payload_hash), FOREIGN KEY(tenant,customer) REFERENCES environments(tenant,customer));
CREATE INDEX IF NOT EXISTS customer_cases ON cases(tenant,customer,created_at DESC);

CREATE TABLE IF NOT EXISTS executions(case_id TEXT PRIMARY KEY REFERENCES cases(id), tenant TEXT NOT NULL, action TEXT NOT NULL, before_state TEXT NOT NULL, after_state TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, case_id TEXT REFERENCES cases(id), actor TEXT NOT NULL, stage TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
"""


class Store:
    def __init__(self, path, seed_demo=True, seed_accounts=True):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='production_metadata'").fetchone():
                raise ValueError('Base production exige abertura explícita, sem inicialização de demo.')
            db.executescript(SCHEMA)
            # Additive migration from Mission 01; observations and audit rows are preserved.
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('DROP INDEX IF EXISTS one_case_per_customer')
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_case ON cases(tenant,customer) WHERE stage IN ('observed','detected','investigated','decided','executed')")
                db.execute('CREATE INDEX IF NOT EXISTS tenant_history ON history(tenant,case_id,id)')
                db.execute('PRAGMA user_version=2')
                db.commit()
            except BaseException:
                db.rollback()
                raise
            for table in ('observations', 'history', 'executions', 'ingestion_batches'):
                for operation in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END")
            if seed_accounts:
                self.seed(db, seed_demo)

    @classmethod
    def open_existing(cls, path, read_only=False):
        """Open a V2 file without seed, DDL or automatic schema migration."""
        path = Path(path).resolve(strict=True)
        if not path.is_file():
            raise ValueError('A base existente tem de ser um ficheiro.')
        store = cls.__new__(cls)
        store.path = str(path)
        store._existing_only = True
        store._read_only = read_only
        with closing(store.connect()) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 2:
                raise ValueError('Schema incompatível; migração explícita necessária.')
            required = {'users','memberships','sessions','environments','observations',
                        'cases','ingestion_batches','executions','history'}
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables:
                raise ValueError('Schema V2 incompleto.')
            indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            if not {'one_active_case','customer_cases','tenant_history'} <= indexes:
                raise ValueError('Índices de proteção ausentes.')
            triggers = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            required_triggers = {f'immutable_{table}_{operation}'
                for table in ('observations','history','executions','ingestion_batches')
                for operation in ('UPDATE','DELETE')}
            if not required_triggers <= triggers:
                raise ValueError('Proteções append-only ausentes.')
        return store

    def connect(self):
        mode = 'ro' if getattr(self,'_read_only',False) else 'rw'
        target = Path(self.path).as_uri()+'?mode='+mode if getattr(self,'_existing_only',False) else self.path
        db = sqlite3.connect(target,timeout=10,isolation_level=None,uri=getattr(self,'_existing_only',False))
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self, db, seed_demo):
        # An interrupted first boot must not leave a partially seeded laboratory.
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                db.commit()
                return
            for user in ('demo', 'atlas', 'leitor'):
                salt = secrets.token_hex(16)
                digest = hashlib.scrypt(b'centerway-local', salt=salt.encode(), n=16384, r=8, p=1).hex()
                db.execute('INSERT INTO users VALUES (?,?)', (user, salt + ':' + digest))
            db.executemany('INSERT INTO memberships VALUES (?,?,?)', [('demo', 'atlas', 'operator'), ('demo', 'nimbus', 'operator'), ('atlas', 'atlas', 'operator'), ('leitor', 'nimbus', 'viewer')])
            if not seed_demo:
                db.commit()
                return
            for tenant, name, baseline, recent, state in [
                ('atlas', 'AtlasFlow · Clínica Horizonte', 12, 2, {'connector': 'paused', 'backlog': [{'id': f'job-{i}', 'status': 'pending'} for i in range(12)], 'completed_outcomes': 2}),
                ('nimbus', 'NimbusDesk · Estúdio Norte', 8, 1, {'workflow_enabled': False, 'completed_outcomes': 1}),
            ]:
                db.execute('INSERT INTO environments VALUES (?,?,?,?,0)', (tenant, 'customer-01', name, encode(state)))
                for i in range(14):
                    day = date.today() - timedelta(days=13-i)
                    db.execute('INSERT INTO observations(tenant,customer,day,value,source,created_at) VALUES (?,?,?,?,?,?)', (tenant, 'customer-01', day.isoformat(), baseline if i < 7 else recent, 'sandbox-ledger-v1', now()))
            db.commit()
        except BaseException:
            db.rollback()
            raise
