"""Tenant-scoped append-only configuration repository; optional explicit setup only.

No HTTP routes, Core changes, connector adapters or business operation enablement.
"""
import argparse
from contextlib import closing
import hashlib
import json
import sqlite3

from .core import Core, Problem
from .integration_contract import identifier, load, validate
from .http_contract import strict_json
from .store import Store, now

MARKER = 'centerway-integration-contract-v1'
TABLES = {
    'integration_metadata': "CREATE TABLE integration_metadata(marker TEXT PRIMARY KEY CHECK(marker='centerway-integration-contract-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')))",
    'integration_versions': "CREATE TABLE integration_versions(tenant TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), parent_hash TEXT, content_hash TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,version))",
}
GUARDS = {
    f'integration_immutable_{table}_{operation}':
        f"CREATE TRIGGER integration_immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    for table in TABLES for operation in ('UPDATE','DELETE')
}


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def runtime_mode(store):
    with closing(store.connect()) as db:
        production=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='production_metadata'").fetchone())
        preview=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='preview_metadata'").fetchone())
    if production:
        from .production import ProductionPolicy
        ProductionPolicy(store)  # Includes existing production guards; no writes.
        return 'production'
    if preview:
        from .preview import PreviewPolicy
        policy=PreviewPolicy(store)
        if policy.expired(): raise ValueError('Demo lease expired.')
        return 'demo'
    return 'sandbox'


def install(store):
    """Trusted local owner explicitly installs optional tables; never on server startup."""
    mode=runtime_mode(store)
    with store.transaction() as db:
        existing=db.execute("SELECT name FROM sqlite_master WHERE name GLOB 'integration_*'").fetchall()
        if existing:
            raise ValueError('Integration storage already exists; no replacement or repair.')
        for sql in TABLES.values(): db.execute(sql)
        for sql in GUARDS.values(): db.execute(sql)
        db.execute('INSERT INTO integration_metadata VALUES (?,?)',(MARKER,mode))
    return {'status':'initialized','contract_version':1,'mode':mode,'business_operations':'unchanged'}


class IntegrationRepository:
    """Internal callers pass a trusted authenticated user, never a browser role claim.

    get(user, tenant, version=None) pins a complete immutable configuration snapshot.
    history(user, tenant) lists provenance/version metadata. Neither runs C01–C06.
    append(user, tenant, config, expected_version) requires current operator membership.
    """
    def __init__(self, store):
        self.store=store
        self.mode=runtime_mode(store)
        with closing(store.connect()) as db: self._storage(db)

    def _storage(self, db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'integration_*'")}
        if any(schema.get(name)!=sql for name,sql in {**TABLES,**GUARDS}.items()):
            raise ValueError('Integration schema/protections unavailable; no repair.')
        metadata=db.execute('SELECT marker,mode FROM integration_metadata').fetchall()
        if len(metadata)!=1 or metadata[0]['marker']!=MARKER or metadata[0]['mode']!=self.mode:
            raise ValueError('Integration mode mismatch.')

    def _authorize(self, db, user, tenant, write=False):
        identifier(tenant,'tenant')
        Core(self.store).authorize(db,user,tenant,write=write)
        self._storage(db)

    def _chain(self, db, tenant):
        result=[];parent=None
        for row in db.execute('SELECT * FROM integration_versions WHERE tenant=? ORDER BY version',(tenant,)):
            record=dict(row)
            payload=record.pop('payload')
            config=validate(strict_json(payload.encode('utf-8')))
            if payload!=canonical(config): raise ValueError('Integration payload is not canonical.')
            if config['tenant']!=tenant or (self.mode=='production' and config['data_classification']!='declared'):
                raise ValueError('Integration scope/classification mismatch.')
            claimed=record.pop('record_hash')
            if (record['version']!=len(result)+1 or record['parent_hash']!=parent
                    or record['content_hash']!=digest(config) or claimed!=digest(record)):
                raise ValueError('Integration history integrity failure.')
            result.append({**record,'record_hash':claimed,'config':config})
            parent=claimed
        return result

    def _runtime(self):
        # Outside the write transaction: private demo validation has its own transaction.
        if runtime_mode(self.store)!=self.mode: raise ValueError('Runtime mode changed.')

    def append(self, user, tenant, config, expected_version, *, _guard=None):
        self._runtime()
        with self.store.transaction() as db:
            self._authorize(db,user,tenant,write=True)
            if _guard is not None: _guard(db)
            config=validate(config)
            if config['tenant']!=tenant: raise Problem(403,'Configuration belongs to another SaaS.')
            if self.mode=='production' and config['data_classification']!='declared':
                raise Problem(403,'Synthetic integration configurations are forbidden in production.')
            chain=self._chain(db,tenant)
            if type(expected_version) is not int or expected_version<0: raise ValueError('Expected version must be a nonnegative integer.')
            if expected_version!=len(chain): raise Problem(409,'Configuration changed; read its current version before appending.')
            record={'tenant':tenant,'version':len(chain)+1,'parent_hash':chain[-1]['record_hash'] if chain else None,
                    'content_hash':digest(config),'actor':user,'created_at':now()}
            record['record_hash']=digest(record)
            db.execute('INSERT INTO integration_versions VALUES (?,?,?,?,?,?,?,?)',
                       (tenant,record['version'],record['parent_hash'],record['content_hash'],canonical(config),user,record['created_at'],record['record_hash']))
            return {**record,'config':config}

    def get(self, user, tenant, version=None):
        self._runtime()
        if version is not None and (type(version) is not int or version<1): raise ValueError('Invalid configuration version.')
        with self.store.transaction() as db:
            self._authorize(db,user,tenant)
            chain=self._chain(db,tenant)
            selected=version if version is not None else len(chain)
            if not 1<=selected<=len(chain): raise Problem(404,'Integration configuration not found for this SaaS/version.')
            return chain[selected-1]

    def history(self, user, tenant):
        self._runtime()
        with self.store.transaction() as db:
            self._authorize(db,user,tenant)
            return [{**{key:value for key,value in row.items() if key!='config'},
                     'provenance':row['config']['provenance'],
                     'data_classification':row['config']['data_classification']}
                    for row in self._chain(db,tenant)]


def main():
    parser=argparse.ArgumentParser(description='Local declarative configurations only; no connectors or business activation.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    lint=sub.add_parser('validate');lint.add_argument('--file',required=True)
    put=sub.add_parser('append')
    for name in ('db','user','tenant','file'): put.add_argument('--'+name,required=True)
    put.add_argument('--expected-version',type=int,required=True)
    for command in ('get','history'):
        child=sub.add_parser(command)
        for name in ('db','user','tenant'): child.add_argument('--'+name,required=True)
        if command=='get': child.add_argument('--version',type=int)
    args=parser.parse_args()
    try:
        if args.command=='validate':
            load(args.file);result={'status':'valid','contract_version':1,'execution':'disabled'}
        else:
            store=Store.open_existing(args.db)
            if args.command=='init': result=install(store)
            else:
                repo=IntegrationRepository(store)
                if args.command=='append':
                    record=repo.append(args.user,args.tenant,load(args.file),args.expected_version)
                    result={key:value for key,value in record.items() if key!='config'}
                elif args.command=='get': result=repo.get(args.user,args.tenant,args.version)
                else: result=repo.history(args.user,args.tenant)
    except (ValueError,OSError,sqlite3.Error,Problem,RecursionError):
        parser.exit(1,'{"status":"error","code":"integration_refused"}\n')
    print(canonical(result))


if __name__=='__main__': main()
