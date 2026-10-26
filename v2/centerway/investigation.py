"""Versioned, reproducible and inactive C03; no causal confirmation or Core changes."""
import argparse
from contextlib import closing
import sqlite3

from .core import Problem
from .detection import DetectionRepository
from .evidence import customer_id
from .http_contract import strict_json
from .investigation_contract import ALGORITHM,build,validate
from .integrations import canonical,digest
from .store import Store,now

TABLES={
    'investigation_metadata': "CREATE TABLE investigation_metadata(marker TEXT PRIMARY KEY CHECK(marker='inactive-c03-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')), algorithm TEXT NOT NULL CHECK(algorithm='c03-structured-v1'))",
    'investigation_versions': "CREATE TABLE investigation_versions(tenant TEXT NOT NULL, customer TEXT NOT NULL, c02_run_id INTEGER NOT NULL REFERENCES detection_runs(id), version INTEGER NOT NULL CHECK(version>0), parent_hash TEXT, c02_hash TEXT NOT NULL, input_hash TEXT NOT NULL, declaration TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,c02_run_id,version))",
}
GUARDS={
    f'investigation_immutable_{table}_{operation}':
        f"CREATE TRIGGER investigation_immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    for table in TABLES for operation in ('UPDATE','DELETE')
}
GUARDS['investigation_parent_scope']="CREATE TRIGGER investigation_parent_scope BEFORE INSERT ON investigation_versions WHEN NOT EXISTS (SELECT 1 FROM detection_runs WHERE id=NEW.c02_run_id AND tenant=NEW.tenant AND customer=NEW.customer) BEGIN SELECT RAISE(ABORT, 'parent_scope_mismatch'); END"


def load_document(path):
    with open(path,'rb') as source: raw=source.read(65537)
    if len(raw)>65536: raise ValueError('Investigation declaration exceeds 65536 bytes.')
    return strict_json(raw)


def install(store):
    detection=DetectionRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'investigation_*'").fetchone():
            raise ValueError('Investigation storage exists; no replacement/repair.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO investigation_metadata VALUES (?,?,?)',('inactive-c03-v1',detection.evidence.integrations.mode,ALGORITHM))
    return {'status':'initialized','algorithm':ALGORITHM,'operational_state':'inactive'}


class InvestigationRepository:
    """Operators append; current SaaS members read scoped immutable investigations."""
    def __init__(self,store):
        self.store=store;self.detection=DetectionRepository(store)
        with closing(store.connect()) as db: self._storage(db)

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'investigation_*'")}
        rows=db.execute('SELECT * FROM investigation_metadata').fetchall() if 'investigation_metadata' in schema else []
        if (any(schema.get(name)!=sql for name,sql in {**TABLES,**GUARDS}.items()) or len(rows)!=1
                or rows[0]['marker']!='inactive-c03-v1' or rows[0]['algorithm']!=ALGORITHM or rows[0]['mode']!=self.detection.evidence.integrations.mode):
            raise Problem(503,'Armazenamento C03 ausente ou sem integridade; sem reparação automática.')

    def _context(self,db,user,tenant,customer,c02_run_id,write=False):
        customer_id(customer)
        if type(c02_run_id) is not int or not 1<=c02_run_id<=2**53-1: raise ValueError('Explicit C02 run id required.')
        configs=self.detection._scope(db,user,tenant,write=write);self._storage(db)
        criteria=self.detection._criteria(db,tenant,configs)
        row=db.execute('SELECT * FROM detection_runs WHERE tenant=? AND customer=? AND id=?',(tenant,customer,c02_run_id)).fetchone()
        if not row: raise Problem(404,'Resultado C02 inexistente neste escopo.')
        c02=self.detection._read_run(db,user,tenant,customer,dict(row),configs,criteria,True)
        all_records=self.detection.evidence._records(db,tenant,customer,configs)
        ids={r['id'] for r in c02['payload']['evidence']};records=[r for r in all_records if r['id'] in ids]
        config=configs[c02['payload']['config_version']-1]['config']
        return c02,config,records

    def _history(self,db,tenant,customer,c02,config,records):
        result=[];parent=None
        try:
            for row in db.execute('SELECT * FROM investigation_versions WHERE tenant=? AND customer=? AND c02_run_id=? ORDER BY version',(tenant,customer,c02['id'])):
                record=dict(row);claimed=record.pop('record_hash');declaration=record.pop('declaration');payload=record.pop('payload')
                if record['version']!=len(result)+1 or record['parent_hash']!=parent or record['c02_hash']!=c02['record_hash']:
                    raise ValueError('Investigation history/parent mismatch.')
                document=validate(strict_json(declaration.encode('utf-8')),c02,config,records)
                expected=build(document,c02,config,records,record['version'])
                if (declaration!=canonical(document) or digest(document)!=record['input_hash'] or payload!=canonical(expected) or digest(record)!=claimed):
                    raise ValueError('Investigation is not reproducible.')
                result.append({**record,'record_hash':claimed,'declaration':document,'payload':expected});parent=claimed
        except (ValueError,TypeError,KeyError,AttributeError,RecursionError,Problem):
            raise Problem(503,'Investigação sem integridade ou não reproduzível.')
        return result

    def append(self,user,tenant,customer,c02_run_id,document,expected_version, *, _guard=None):
        self.detection.evidence._runtime()
        if type(expected_version) is not int or not 0<=expected_version<=2**31-1: raise ValueError('Expected version must be explicit and nonnegative.')
        with self.store.transaction() as db:
            c02,config,records=self._context(db,user,tenant,customer,c02_run_id,write=True)
            if _guard is not None: _guard(db)
            document=validate(document,c02,config,records)
            history=self._history(db,tenant,customer,c02,config,records);input_hash=digest(document)
            # An exact retry refers to the revision it originally created, even if later revisions exist.
            if expected_version<len(history):
                previous=history[expected_version]
                if previous['input_hash']==input_hash: return {**previous,'reused':True}
                raise Problem(409,'A investigação mudou; consultar a versão atual.')
            if expected_version!=len(history): raise Problem(409,'Versão esperada da investigação desatualizada.')
            version=len(history)+1;payload=build(document,c02,config,records,version)
            record={'tenant':tenant,'customer':customer,'c02_run_id':c02_run_id,'version':version,
                    'parent_hash':history[-1]['record_hash'] if history else None,'c02_hash':c02['record_hash'],
                    'input_hash':input_hash,'actor':user,'created_at':now()}
            record['record_hash']=digest(record)
            db.execute('INSERT INTO investigation_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (tenant,customer,c02_run_id,version,record['parent_hash'],record['c02_hash'],input_hash,canonical(document),canonical(payload),user,record['created_at'],record['record_hash']))
            return {**record,'declaration':document,'payload':payload,'reused':False}

    def get(self,user,tenant,customer,c02_run_id,version=None):
        self.detection.evidence._runtime()
        if version is not None and (type(version) is not int or version<1): raise ValueError('Invalid investigation version.')
        with self.store.transaction() as db:
            c02,config,records=self._context(db,user,tenant,customer,c02_run_id)
            history=self._history(db,tenant,customer,c02,config,records)
            selected=version if version is not None else len(history)
            if not 1<=selected<=len(history): raise Problem(404,'Investigação inexistente neste escopo/versão.')
            return {**history[selected-1],'reused':True}


def main():
    parser=argparse.ArgumentParser(description='Isolated inactive C03; no AI, decisions, confirmed causes or actions.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    for command in ('append','get'):
        child=sub.add_parser(command)
        for name in ('db','user','tenant','customer'): child.add_argument('--'+name,required=True)
        child.add_argument('--c02-run-id',type=int,required=True)
        if command=='append':
            child.add_argument('--file',required=True);child.add_argument('--expected-version',type=int,required=True)
        else: child.add_argument('--version',type=int)
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        if args.command=='init': result=install(store)
        else:
            repository=InvestigationRepository(store)
            if args.command=='append': result=repository.append(args.user,args.tenant,args.customer,args.c02_run_id,load_document(args.file),args.expected_version)
            else: result=repository.get(args.user,args.tenant,args.customer,args.c02_run_id,args.version)
    except (ValueError,OSError,sqlite3.Error,Problem,RecursionError):
        parser.exit(1,'{"status":"error","code":"investigation_refused"}\n')
    print(canonical(result))


if __name__=='__main__': main()
