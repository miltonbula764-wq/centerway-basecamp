"""Versioned inactive C06 repository; no Core transitions, adapter calls or HTTP."""
import argparse
from contextlib import closing
import sqlite3

from .controlled_execution import ExecutionRepository
from .core import Core,Problem
from .evidence import normalize,utc
from .http_contract import strict_json
from .integrations import canonical,digest
from .recovery_contract import ALGORITHM,assess,instant,validate
from .store import Store,now

TABLES={
 'recovery_metadata': "CREATE TABLE recovery_metadata(marker TEXT PRIMARY KEY CHECK(marker='inactive-c06-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')), algorithm TEXT NOT NULL CHECK(algorithm='c06-recovery-v1'))",
 'recovery_plans': "CREATE TABLE recovery_plans(tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), parent_hash TEXT, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,execution_id,version), FOREIGN KEY(tenant,customer,execution_id) REFERENCES c05_attempts(tenant,customer,execution_id))",
 'recovery_runs': "CREATE TABLE recovery_runs(tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), plan_version INTEGER NOT NULL, parent_hash TEXT, request_hash TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,execution_id,version), UNIQUE(tenant,customer,execution_id,request_hash), FOREIGN KEY(tenant,customer,execution_id,plan_version) REFERENCES recovery_plans(tenant,customer,execution_id,version))",
}
GUARDS={f'recovery_immutable_{table}_{op}':f"CREATE TRIGGER recovery_immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for table in TABLES for op in ('UPDATE','DELETE')}


def install(store):
    execution=ExecutionRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'recovery_*'").fetchone(): raise ValueError('C06 storage exists; no replacement/repair.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO recovery_metadata VALUES (?,?,?)',('inactive-c06-v1',execution.mode,ALGORITHM))
    return {'status':'initialized','algorithm':ALGORITHM,'operational_state':'inactive','external_execution':'blocked'}


class RecoveryRepository:
    def __init__(self,store):
        self.store=store;self.execution=ExecutionRepository(store)
        self.evidence=self.execution.proposals.investigation.detection.evidence
        with closing(store.connect()) as db: self._storage(db)

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'recovery_*'")}
        rows=db.execute('SELECT * FROM recovery_metadata').fetchall() if 'recovery_metadata' in schema else []
        if (any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS}.items()) or len(rows)!=1 or rows[0]['marker']!='inactive-c06-v1'
                or rows[0]['mode']!=self.execution.mode or rows[0]['algorithm']!=ALGORITHM): raise Problem(503,'C06 indisponível; preparação/integridade necessária, sem reparação automática.')

    def _context(self,db,user,tenant,customer,execution_id,write=False):
        self.execution._scope(user,tenant,customer,execution_id)
        self.execution._access(db,user,tenant,write=False)
        Core(self.store).authorize(db,user,tenant,write=write);self._storage(db)
        view=self.execution._view(db,user,tenant,customer,execution_id)
        if not view['attempts']: raise Problem(409,'C06 exige uma tentativa C05; não cria nem repete intervenções.')
        source=view['intent']['payload']['binding']
        binding={k:source[k] for k in ('tenant','customer','capability','configuration','classification')}
        binding.update(execution_id=execution_id,config_version=source['lineage']['config_version'],capability_id=source['capability']['id'])
        if (binding['classification']!='synthetic' or self.execution.mode=='production'
                or view['attempts']['payload']['adapter']['kind']!='test_adapter'):
            raise Problem(503,'C06 desta missão só avalia intervenções/evidências sintéticas, sem operações reais.')
        try:
            configs=self.evidence.integrations._chain(db,tenant)
            self.evidence._snapshot(db,user,tenant,customer,binding['config_version'],write=write)
            if configs[binding['config_version']-1]['config']!=binding['configuration']: raise ValueError('Pinned configuration mismatch.')
            records=self.evidence._records(db,tenant,customer,configs)
            # Independent schema/content/provenance validation of input rows.
            for row in records:
                raw={k:row[k] for k in ('external_id','kind','definition_id','source_ref','occurred_at','payload')}
                raw['period']={'start':row['period_start'],'end':row['period_end']} if row['period_start'] else None
                normalized=normalize(raw,configs[row['config_version']-1]['config'],customer,utc(row['received_at']))
                fact={k:normalized[k] for k in ('kind','definition_id','source_ref','occurred_at','period')}
                if digest(normalized)!=row['content_hash'] or digest(fact)!=row['fact_hash']: raise ValueError('Evidence content mismatch.')
        except (ValueError,TypeError,KeyError,IndexError,sqlite3.Error,Problem): raise Problem(503,'Fontes C06 sem integridade confirmada.')
        return binding,view,records

    def _snapshot(self,view,tip=None):
        audit=view['audit'];tip=tip or audit[-1]['record_hash']
        indices=[i for i,r in enumerate(audit) if r['record_hash']==tip]
        if len(indices)!=1: raise Problem(503,'Âncora de auditoria C05 inexistente.')
        prefix=audit[:indices[0]+1]
        if not any(r['payload']['operation']=='execute' and r['payload']['status']=='dispatch_started' for r in prefix): raise Problem(503,'Snapshot C06 anterior à tentativa C05.')
        has_result=any(r['payload']['operation']=='result' for r in prefix)
        if has_result and not view['results']: raise Problem(503,'Recibo C05 em falta.')
        return {'intent_hash':view['intent']['record_hash'],'approval_hash':view['approvals']['record_hash'],
                'attempt_hash':view['attempts']['record_hash'],'dispatch_at':utc(view['attempts']['payload']['created_at']),
                'result':view['results'] if has_result else None,'audit_tip':tip}

    def _plans(self,db,tenant,customer,execution_id,binding,view):
        history=[];parent=None
        try:
            for row in db.execute('SELECT * FROM recovery_plans WHERE tenant=? AND customer=? AND execution_id=? ORDER BY version',(tenant,customer,execution_id)):
                row=dict(row);claimed=row.pop('record_hash');payload=strict_json(row['payload'].encode('utf-8'))
                document=validate(payload['document'],binding,view['attempts']['payload']['created_at'])
                if (row['version']!=len(history)+1 or row['parent_hash']!=parent or digest(row)!=claimed
                        or payload!={'document':document,'intent_hash':view['intent']['record_hash'],'attempt_hash':view['attempts']['record_hash']}
                        or row['payload']!=canonical(payload)): raise ValueError('Plan history mismatch.')
                history.append({**row,'payload':payload,'record_hash':claimed});parent=claimed
        except (ValueError,TypeError,KeyError,AttributeError): raise Problem(503,'Histórico de planos C06 sem integridade.')
        return history

    def _inputs(self,binding,view,records,plan,as_of,through=None,tip=None):
        as_of=utc(as_of)
        if instant(as_of)>instant(now()) or instant(as_of)<instant(view['attempts']['payload']['created_at']): raise ValueError('C06 as_of must be between dispatch and current time.')
        latest=max((r['id'] for r in records),default=0);through=latest if through is None else through
        if type(through) is not int or not 0<=through<=latest: raise ValueError('Invalid C06 historical evidence cutoff.')
        visible=[r for r in records if r['id']<=through]
        selected=[r for r in visible if r['config_version']==binding['config_version']]
        c05=self._snapshot(view,tip)
        inputs={'algorithm':ALGORITHM,'tenant':binding['tenant'],'customer':binding['customer'],'execution_id':binding['execution_id'],
                'plan_version':plan['version'],'plan_hash':plan['record_hash'],'config_version':binding['config_version'],
                'configuration_hash':digest(binding['configuration']),'capability_id':binding['capability_id'],'c05':c05,'as_of':as_of,'through':through,
                'evidence_refs':[{'evidence_id':r['id'],'record_hash':r['record_hash']} for r in selected],
                'excluded_other_configuration_ids':[r['id'] for r in visible if r['config_version']!=binding['config_version']]}
        return inputs,selected

    def _runs(self,db,tenant,customer,execution_id,binding,view,records,plans):
        history=[];parent=None
        try:
            for row in db.execute('SELECT * FROM recovery_runs WHERE tenant=? AND customer=? AND execution_id=? ORDER BY version',(tenant,customer,execution_id)):
                row=dict(row);claimed=row.pop('record_hash');payload=strict_json(row['payload'].encode('utf-8'))
                if not 1<=row['plan_version']<=len(plans): raise ValueError('Missing plan.')
                plan=plans[row['plan_version']-1]
                inputs,selected=self._inputs(binding,view,records,plan,payload['inputs']['as_of'],payload['inputs']['through'],payload['inputs']['c05']['audit_tip'])
                expected={'inputs':inputs,'plan_snapshot':plan['payload']['document'],
                          'assessment':assess(plan['payload']['document'],binding,inputs['c05'],selected,inputs['as_of'])}
                if (row['version']!=len(history)+1 or row['parent_hash']!=parent or digest(row)!=claimed
                        or digest(inputs)!=row['request_hash'] or row['payload']!=canonical(expected)): raise ValueError('C06 result not reproducible.')
                history.append({**row,'payload':payload,'record_hash':claimed});parent=claimed
        except (ValueError,TypeError,KeyError,AttributeError,IndexError): raise Problem(503,'Histórico C06 sem integridade ou não reproduzível.')
        return history

    def append_plan(self,user,tenant,customer,execution_id,document,expected_version):
        self.evidence._runtime()
        with self.store.transaction() as db:
            binding,view,_=self._context(db,user,tenant,customer,execution_id,write=True)
            document=validate(document,binding,view['attempts']['payload']['created_at'])
            history=self._plans(db,tenant,customer,execution_id,binding,view)
            if type(expected_version) is not int or expected_version!=len(history): raise Problem(409,'Versão de plano alterada; consultar histórico.')
            if len(history)>=1000: raise Problem(413,'Limite de 1000 versões de plano C06.')
            payload={'document':document,'intent_hash':view['intent']['record_hash'],'attempt_hash':view['attempts']['record_hash']}
            row={'tenant':tenant,'customer':customer,'execution_id':execution_id,'version':len(history)+1,'parent_hash':history[-1]['record_hash'] if history else None,
                 'payload':canonical(payload),'actor':user,'created_at':now()}
            row['record_hash']=digest(row)
            db.execute('INSERT INTO recovery_plans VALUES (?,?,?,?,?,?,?,?,?)',tuple(row.values()))
            return {**row,'payload':payload}

    def evaluate(self,user,tenant,customer,execution_id,plan_version,as_of):
        self.evidence._runtime()
        if type(plan_version) is not int or plan_version<1: raise ValueError('Explicit C06 plan version required.')
        with self.store.transaction() as db:
            binding,view,records=self._context(db,user,tenant,customer,execution_id,write=True)
            plans=self._plans(db,tenant,customer,execution_id,binding,view)
            if plan_version>len(plans): raise Problem(404,'Plano C06 inexistente neste escopo.')
            runs=self._runs(db,tenant,customer,execution_id,binding,view,records,plans);plan=plans[plan_version-1]
            inputs,selected=self._inputs(binding,view,records,plan,as_of)
            request_hash=digest(inputs)
            previous=next((r for r in runs if r['request_hash']==request_hash),None)
            if previous: return {**previous,'reused':True}
            if len(runs)>=1000: raise Problem(413,'Limite de 1000 avaliações C06.')
            payload={'inputs':inputs,'plan_snapshot':plan['payload']['document'],
                     'assessment':assess(plan['payload']['document'],binding,inputs['c05'],selected,inputs['as_of'])}
            row={'tenant':tenant,'customer':customer,'execution_id':execution_id,'version':len(runs)+1,'plan_version':plan_version,
                 'parent_hash':runs[-1]['record_hash'] if runs else None,'request_hash':request_hash,'payload':canonical(payload),'actor':user,'created_at':now()}
            row['record_hash']=digest(row)
            db.execute('INSERT INTO recovery_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)',tuple(row.values()))
            return {**row,'payload':payload,'reused':False}

    def history(self,user,tenant,customer,execution_id):
        self.evidence._runtime()
        with self.store.transaction() as db:
            binding,view,records=self._context(db,user,tenant,customer,execution_id)
            plans=self._plans(db,tenant,customer,execution_id,binding,view)
            runs=self._runs(db,tenant,customer,execution_id,binding,view,records,plans)
            return {'tenant':tenant,'customer':customer,'execution_id':execution_id,'plans':plans,'runs':runs,'operational_state':'inactive',
                    'external_execution':'blocked','current_heads':{'evidence_id':max((r['id'] for r in records),default=0),
                    'c05_audit_tip':view['audit'][-1]['record_hash'],'plan_version':len(plans),'run_version':len(runs)}}

    def get(self,user,tenant,customer,execution_id,version):
        if type(version) is not int or version<1: raise ValueError('Explicit C06 result version required.')
        history=self.history(user,tenant,customer,execution_id)
        if version>len(history['runs']): raise Problem(404,'Avaliação C06 inexistente neste escopo.')
        return {**history['runs'][version-1],'reused':True}


def load(path):
    with open(path,'rb') as source: raw=source.read(65537)
    if len(raw)>65536: raise ValueError('C06 plan exceeds 65536 bytes.')
    return strict_json(raw)


def main():
    parser=argparse.ArgumentParser(description='Inactive internal C06; no execution, connectors or Core transitions.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    for command in ('append-plan','evaluate','history','get'):
        child=sub.add_parser(command)
        for key in ('db','user','tenant','customer','execution-id'): child.add_argument('--'+key,required=True)
        if command=='append-plan': child.add_argument('--file',required=True);child.add_argument('--expected-version',type=int,required=True)
        if command=='evaluate': child.add_argument('--plan-version',type=int,required=True);child.add_argument('--as-of',required=True)
        if command=='get': child.add_argument('--version',type=int,required=True)
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        if args.command=='init': result=install(store)
        else:
            repository=RecoveryRepository(store);scope=(args.user,args.tenant,args.customer,args.execution_id)
            if args.command=='append-plan': result=repository.append_plan(*scope,load(args.file),args.expected_version)
            elif args.command=='evaluate': result=repository.evaluate(*scope,args.plan_version,args.as_of)
            elif args.command=='get': result=repository.get(*scope,args.version)
            else: result=repository.history(*scope)
    except (ValueError,Problem,OSError,sqlite3.Error,RecursionError,OverflowError): parser.exit(1,'{"status":"error","code":"c06_refused"}\n')
    print(canonical(result))


if __name__=='__main__': main()
