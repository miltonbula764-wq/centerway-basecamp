"""Isolated inactive C02 repository. No HTTP routes or connection to sandbox cycles."""
import argparse
from contextlib import closing
import sqlite3

from .core import Core,Problem
from .detection_contract import ALGORITHM,assess,validate
from .evidence import EvidenceRepository,customer_id,utc
from .http_contract import strict_json
from .integration_contract import identifier,load as load_config
from .integrations import canonical,digest
from .store import Store,now

TABLES = {
    'detection_metadata': "CREATE TABLE detection_metadata(marker TEXT PRIMARY KEY CHECK(marker='inactive-c02-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')), algorithm TEXT NOT NULL CHECK(algorithm='c02-adaptive-v1'))",
    'detection_criteria': "CREATE TABLE detection_criteria(tenant TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), config_version INTEGER NOT NULL CHECK(config_version>0), config_hash TEXT NOT NULL, parent_hash TEXT, content_hash TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,version), FOREIGN KEY(tenant,config_version) REFERENCES integration_versions(tenant,version))",
    'detection_runs': "CREATE TABLE detection_runs(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, criteria_version INTEGER NOT NULL CHECK(criteria_version>0), request_hash TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(tenant,customer,criteria_version,request_hash), FOREIGN KEY(tenant,criteria_version) REFERENCES detection_criteria(tenant,version))",
}
GUARDS = {
    f'detection_immutable_{table}_{operation}':
        f"CREATE TRIGGER detection_immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    for table in TABLES for operation in ('UPDATE','DELETE')
}


def load_document(path):
    with open(path,'rb') as source: payload=source.read(65537)
    if len(payload)>65536: raise ValueError('Criteria exceed 65536 bytes.')
    return strict_json(payload)


def install(store):
    evidence=EvidenceRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'detection_*'").fetchone():
            raise ValueError('Detection storage exists; no replacement or repair.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO detection_metadata VALUES (?,?,?)',('inactive-c02-v1',evidence.integrations.mode,ALGORITHM))
    return {'status':'initialized','algorithm':ALGORITHM,'operational_state':'inactive'}


class DetectionRepository:
    """Trusted internal principals only. Operators evaluate; members read scoped results."""
    def __init__(self, store):
        self.store=store;self.evidence=EvidenceRepository(store)
        with closing(store.connect()) as db: self._storage(db)

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'detection_*'")}
        rows=db.execute('SELECT * FROM detection_metadata').fetchall() if 'detection_metadata' in schema else []
        if (any(schema.get(name)!=sql for name,sql in {**TABLES,**GUARDS}.items()) or len(rows)!=1
                or rows[0]['marker']!='inactive-c02-v1' or rows[0]['mode']!=self.evidence.integrations.mode or rows[0]['algorithm']!=ALGORITHM):
            raise Problem(503,'Armazenamento C02 inativo ausente ou sem integridade; sem reparação automática.')

    def _scope(self,db,user,tenant,write=False):
        identifier(tenant,'tenant');Core(self.store).authorize(db,user,tenant,write=write)
        self._storage(db)
        try:
            self.evidence._storage(db);self.evidence.integrations._storage(db)
            return self.evidence.integrations._chain(db,tenant)
        except (ValueError,TypeError,KeyError,sqlite3.Error): raise Problem(503,'Integridade da configuração não confirmada.')

    def _criteria(self,db,tenant,configs):
        result=[];parent=None
        try:
            for row in db.execute('SELECT * FROM detection_criteria WHERE tenant=? ORDER BY version',(tenant,)):
                record=dict(row);claimed=record.pop('record_hash');payload=record.pop('payload')
                if (record['version']!=len(result)+1 or record['parent_hash']!=parent or not 1<=record['config_version']<=len(configs)):
                    raise ValueError('Criteria history mismatch.')
                config=configs[record['config_version']-1]
                doc=validate(strict_json(payload.encode('utf-8')),config['config'])
                if (payload!=canonical(doc) or doc['config_version']!=record['config_version'] or doc['tenant']!=tenant
                        or config['content_hash']!=record['config_hash'] or digest(doc)!=record['content_hash'] or digest(record)!=claimed):
                    raise ValueError('Criteria integrity mismatch.')
                result.append({**record,'record_hash':claimed,'document':doc});parent=claimed
        except (ValueError,TypeError,KeyError,AttributeError): raise Problem(503,'Histórico de critérios sem integridade.')
        return result

    def append_criteria(self,user,tenant,document,expected_version, *, _guard=None):
        self.evidence._runtime()
        with self.store.transaction() as db:
            configs=self._scope(db,user,tenant,write=True)
            if _guard is not None: _guard(db)
            if not isinstance(document,dict) or document.get('tenant')!=tenant: raise Problem(403,'Critérios de outra SaaS não autorizados.')
            version=document.get('config_version')
            if type(version) is not int or version<1: raise ValueError('Explicit configuration version required.')
            if version>len(configs): raise Problem(404,'Configuração inexistente nesta SaaS.')
            document=validate(document,configs[version-1]['config'])
            history=self._criteria(db,tenant,configs)
            if type(expected_version) is not int or expected_version<0: raise ValueError('Invalid expected criteria version.')
            if expected_version!=len(history): raise Problem(409,'Critérios alterados; consultar a versão atual.')
            record={'tenant':tenant,'version':len(history)+1,'config_version':version,'config_hash':configs[version-1]['content_hash'],
                    'parent_hash':history[-1]['record_hash'] if history else None,'content_hash':digest(document),'actor':user,'created_at':now()}
            record['record_hash']=digest(record)
            db.execute('INSERT INTO detection_criteria VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (tenant,record['version'],version,record['config_hash'],record['parent_hash'],record['content_hash'],canonical(document),user,record['created_at'],record['record_hash']))
            return {**record,'document':document}

    def criteria(self,user,tenant,version):
        self.evidence._runtime()
        if type(version) is not int or version<1: raise ValueError('Explicit criteria version required.')
        with self.store.transaction() as db:
            history=self._criteria(db,tenant,self._scope(db,user,tenant))
            if version>len(history): raise Problem(404,'Versão de critérios inexistente nesta SaaS.')
            return history[version-1]

    def _inputs(self,db,tenant,customer,criterion,configs,as_of,through):
        customer_id(customer);as_of=utc(as_of)
        if as_of>utc(now()): raise ValueError('Future evaluation is not supported.')
        rows=self.evidence._records(db,tenant,customer,configs)
        latest=max((r['id'] for r in rows),default=0)
        if through is None: through=latest
        if type(through) is not int or not 0<=through<=latest: raise ValueError('Invalid evidence snapshot cutoff.')
        selected=[r for r in rows if r['config_version']==criterion['config_version'] and r['id']<=through]
        inputs={'algorithm':ALGORITHM,'tenant':tenant,'customer':customer,'criteria_version':criterion['version'],
                'criteria_hash':criterion['content_hash'],'config_version':criterion['config_version'],'config_hash':criterion['config_hash'],
                'as_of':as_of,'through':through,'evidence':[{'id':r['id'],'record_hash':r['record_hash']} for r in selected]}
        return inputs,selected

    def evaluate(self,user,tenant,customer,criteria_version,as_of,through=None):
        self.evidence._runtime()
        if type(criteria_version) is not int or criteria_version<1: raise ValueError('Explicit criteria version required.')
        with self.store.transaction() as db:
            configs=self._scope(db,user,tenant,write=True);criteria=self._criteria(db,tenant,configs)
            if criteria_version>len(criteria): raise Problem(404,'Critérios inexistentes nesta SaaS.')
            criterion=criteria[criteria_version-1]
            inputs,selected=self._inputs(db,tenant,customer,criterion,configs,as_of,through)
            request_hash=digest(inputs)
            previous=db.execute('SELECT * FROM detection_runs WHERE tenant=? AND customer=? AND criteria_version=? AND request_hash=?',
                                (tenant,customer,criteria_version,request_hash)).fetchone()
            if previous: return self._read_run(db,user,tenant,customer,dict(previous),configs,criteria,True)
            config=configs[criterion['config_version']-1]['config']
            result={**inputs,'operational_state':'inactive','classification':config['data_classification'],
                    'proof_scope':'declared_criteria_and_supplied_evidence','criteria_snapshot':criterion['document'],
                    **assess(criterion['document'],config,selected,inputs['as_of'])}
            record={'tenant':tenant,'customer':customer,'criteria_version':criteria_version,'request_hash':request_hash,
                    'payload':canonical(result),'actor':user,'created_at':now()}
            record['id']=db.execute('SELECT coalesce(max(id),0)+1 FROM detection_runs').fetchone()[0]
            record['record_hash']=digest(record)
            db.execute('INSERT INTO detection_runs ('+','.join(record)+') VALUES ('+','.join('?' for _ in record)+')',tuple(record.values()))
            return {**record,'payload':result,'reused':False}

    def _read_run(self,db,user,tenant,customer,row,configs,criteria,reused):
        try:
            claimed=row.pop('record_hash');payload=row['payload']
            if digest(row)!=claimed: raise ValueError('Run hash mismatch.')
            result=strict_json(payload.encode('utf-8'))
            if not 1<=row['criteria_version']<=len(criteria): raise ValueError('Run criteria missing.')
            criterion=criteria[row['criteria_version']-1]
            inputs,selected=self._inputs(db,tenant,customer,criterion,configs,result['as_of'],result['through'])
            config=configs[criterion['config_version']-1]['config']
            expected={**inputs,'operational_state':'inactive','classification':config['data_classification'],
                      'proof_scope':'declared_criteria_and_supplied_evidence','criteria_snapshot':criterion['document'],
                      **assess(criterion['document'],config,selected,inputs['as_of'])}
            if payload!=canonical(expected) or digest(inputs)!=row['request_hash']: raise ValueError('Run cannot be reproduced.')
        except (ValueError,TypeError,KeyError,AttributeError): raise Problem(503,'Resultado C02 sem integridade ou não reproduzível.')
        return {**row,'record_hash':claimed,'payload':result,'reused':reused}

    def get(self,user,tenant,customer,run_id):
        self.evidence._runtime();customer_id(customer)
        if type(run_id) is not int or run_id<1: raise ValueError('Invalid run id.')
        with self.store.transaction() as db:
            configs=self._scope(db,user,tenant);criteria=self._criteria(db,tenant,configs)
            row=db.execute('SELECT * FROM detection_runs WHERE tenant=? AND customer=? AND id=?',(tenant,customer,run_id)).fetchone()
            if not row: raise Problem(404,'Resultado C02 inexistente neste escopo.')
            return self._read_run(db,user,tenant,customer,dict(row),configs,criteria,True)


def main():
    parser=argparse.ArgumentParser(description='Isolated inactive C02; no business activation or new HTTP endpoints.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    lint=sub.add_parser('validate');lint.add_argument('--file',required=True);lint.add_argument('--config-file',required=True)
    append=sub.add_parser('append-criteria')
    for name in ('db','user','tenant','file'): append.add_argument('--'+name,required=True)
    append.add_argument('--expected-version',type=int,required=True)
    for command in ('criteria','evaluate','get'):
        child=sub.add_parser(command)
        for name in ('db','user','tenant'): child.add_argument('--'+name,required=True)
        if command=='criteria': child.add_argument('--version',type=int,required=True)
        else:
            child.add_argument('--customer',required=True)
            if command=='get': child.add_argument('--run-id',type=int,required=True)
            else:
                child.add_argument('--criteria-version',type=int,required=True);child.add_argument('--as-of',required=True)
                child.add_argument('--through',type=int)
    args=parser.parse_args()
    try:
        if args.command=='validate':
            validate(load_document(args.file),load_config(args.config_file));result={'status':'valid','algorithm':ALGORITHM,'operational_state':'inactive'}
        else:
            store=Store.open_existing(args.db)
            if args.command=='init': result=install(store)
            else:
                repo=DetectionRepository(store)
                if args.command=='append-criteria': result=repo.append_criteria(args.user,args.tenant,load_document(args.file),args.expected_version)
                elif args.command=='criteria': result=repo.criteria(args.user,args.tenant,args.version)
                elif args.command=='evaluate': result=repo.evaluate(args.user,args.tenant,args.customer,args.criteria_version,args.as_of,args.through)
                else: result=repo.get(args.user,args.tenant,args.customer,args.run_id)
    except (ValueError,OSError,sqlite3.Error,Problem,RecursionError,OverflowError):
        parser.exit(1,'{"status":"error","code":"detection_refused"}\n')
    print(canonical(result))


if __name__=='__main__': main()
