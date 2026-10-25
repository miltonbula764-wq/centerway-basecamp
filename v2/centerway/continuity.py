"""Explicit inactive cycle lifecycle. No recovery inference or uncertainty resolution."""
import argparse
from contextlib import closing
import sqlite3

from .core import Core,Problem
from .evidence import customer_id,utc
from .http_contract import strict_json
from .integration_contract import identifier,shape,text
from .integrations import canonical,digest
from .store import Store,now

TABLES={
 'continuity_metadata': "CREATE TABLE continuity_metadata(marker TEXT PRIMARY KEY CHECK(marker='continuity-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')))",
 'continuity_openings': "CREATE TABLE continuity_openings(tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,case_id), UNIQUE(tenant,customer,request_id), FOREIGN KEY(tenant,customer,case_id) REFERENCES orchestration_cases(tenant,customer,case_id))",
 'continuity_closures': "CREATE TABLE continuity_closures(tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,case_id), UNIQUE(tenant,customer,request_id), FOREIGN KEY(tenant,customer,case_id) REFERENCES orchestration_cases(tenant,customer,case_id))",
 'continuity_reviews': "CREATE TABLE continuity_reviews(tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,case_id,request_id), FOREIGN KEY(tenant,customer,case_id) REFERENCES orchestration_cases(tenant,customer,case_id))",
 'continuity_bindings': "CREATE TABLE continuity_bindings(tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('c02','c04','c05')), object_id TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,case_id,kind,object_id), UNIQUE(tenant,customer,kind,object_id), FOREIGN KEY(tenant,customer,case_id) REFERENCES orchestration_cases(tenant,customer,case_id))",
}
GUARDS={f'continuity_immutable_{t}_{op}':f"CREATE TRIGGER continuity_immutable_{t}_{op} BEFORE {op} ON {t} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for t in TABLES for op in ('UPDATE','DELETE')}
GUARDS['continuity_fence_events']="CREATE TRIGGER continuity_fence_events BEFORE INSERT ON orchestration_events WHEN EXISTS (SELECT 1 FROM continuity_closures x WHERE x.tenant=NEW.tenant AND x.customer=NEW.customer AND x.case_id=NEW.case_id) BEGIN SELECT RAISE(ABORT, 'cycle_closed'); END"
GUARDS['continuity_one_active']="CREATE TRIGGER continuity_one_active BEFORE INSERT ON orchestration_cases WHEN EXISTS (SELECT 1 FROM orchestration_cases c WHERE c.tenant=NEW.tenant AND c.customer=NEW.customer AND NOT EXISTS (SELECT 1 FROM continuity_closures x WHERE x.tenant=c.tenant AND x.customer=c.customer AND x.case_id=c.case_id)) BEGIN SELECT RAISE(ABORT, 'active_cycle_exists'); END"
_CLOSED="EXISTS (SELECT 1 FROM continuity_bindings b JOIN continuity_closures x ON x.tenant=b.tenant AND x.customer=b.customer AND x.case_id=b.case_id WHERE b.tenant=NEW.tenant AND b.customer=NEW.customer AND {condition})"
GUARDS['continuity_fence_c03']="CREATE TRIGGER continuity_fence_c03 BEFORE INSERT ON investigation_versions WHEN "+_CLOSED.format(condition="b.kind='c02' AND b.object_id=CAST(NEW.c02_run_id AS TEXT)")+" BEGIN SELECT RAISE(ABORT, 'cycle_closed'); END"
GUARDS['continuity_fence_c04']="CREATE TRIGGER continuity_fence_c04 BEFORE INSERT ON c04_requests WHEN "+_CLOSED.format(condition="(b.kind='c04' AND b.object_id=NEW.request_id OR b.kind='c02' AND b.object_id=CAST(NEW.c02_run_id AS TEXT))")+" BEGIN SELECT RAISE(ABORT, 'cycle_closed'); END"
GUARDS['continuity_fence_intent']="CREATE TRIGGER continuity_fence_intent BEFORE INSERT ON c05_intents WHEN "+_CLOSED.format(condition="(b.kind='c04' AND b.object_id=NEW.request_id OR b.kind='c02' AND b.object_id=CAST((SELECT r.c02_run_id FROM c04_requests r WHERE r.tenant=NEW.tenant AND r.customer=NEW.customer AND r.request_id=NEW.request_id) AS TEXT))")+" BEGIN SELECT RAISE(ABORT, 'cycle_closed'); END"
for table in ('c05_approvals','c05_attempts','recovery_plans','recovery_runs'):
    condition="(b.kind='c05' AND b.object_id=NEW.execution_id OR b.kind='c04' AND b.object_id=(SELECT i.request_id FROM c05_intents i WHERE i.tenant=NEW.tenant AND i.customer=NEW.customer AND i.execution_id=NEW.execution_id))"
    GUARDS['continuity_fence_'+table]=f"CREATE TRIGGER continuity_fence_{table} BEFORE INSERT ON {table} WHEN "+_CLOSED.format(condition=condition)+" BEGIN SELECT RAISE(ABORT, 'cycle_closed'); END"
_UNCERTAIN="EXISTS (SELECT 1 FROM c05_attempts a LEFT JOIN c05_results r ON r.tenant=a.tenant AND r.customer=a.customer AND r.execution_id=a.execution_id WHERE a.tenant=NEW.tenant AND a.customer=NEW.customer AND COALESCE(json_extract(r.payload,'$.status'),'uncertain') NOT IN ('test_applied','failed_no_effect'))"
GUARDS['continuity_no_open_over_uncertainty']="CREATE TRIGGER continuity_no_open_over_uncertainty BEFORE INSERT ON orchestration_cases WHEN "+_UNCERTAIN+" BEGIN SELECT RAISE(ABORT, 'customer_execution_unresolved'); END"
for table in ('c05_approvals','c05_attempts'):
    condition="EXISTS (SELECT 1 FROM c05_intents i JOIN continuity_closures x ON x.tenant=i.tenant AND x.customer=i.customer WHERE i.tenant=NEW.tenant AND i.customer=NEW.customer AND i.execution_id=NEW.execution_id AND json_extract(i.payload,'$.created_at')<=x.created_at)"
    GUARDS['continuity_old_grant_'+table]=f"CREATE TRIGGER continuity_old_grant_{table} BEFORE INSERT ON {table} WHEN "+condition+" BEGIN SELECT RAISE(ABORT, 'grant_predates_closed_cycle'); END"
GUARDS['continuity_customer_dispatch_fence']="CREATE TRIGGER continuity_customer_dispatch_fence BEFORE INSERT ON c05_attempts WHEN "+_UNCERTAIN+" AND EXISTS (SELECT 1 FROM c05_intents i JOIN continuity_bindings b ON b.tenant=i.tenant AND b.customer=i.customer AND b.kind='c04' AND b.object_id=i.request_id WHERE i.tenant=NEW.tenant AND i.customer=NEW.customer AND i.execution_id=NEW.execution_id) BEGIN SELECT RAISE(ABORT, 'customer_execution_unresolved'); END"

DISPOSITIONS=('follow_up_complete','no_intervention_needed','not_recovered','cancelled')


def install_storage(db,mode):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'continuity_*'").fetchone(): raise ValueError('Continuity exists; no replacement/repair.')
    for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
    db.execute('INSERT INTO continuity_metadata VALUES (?,?)',('continuity-v1',mode))


def storage(db,mode):
    schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'continuity_*'")}
    rows=db.execute('SELECT * FROM continuity_metadata').fetchall() if 'continuity_metadata' in schema else []
    if (any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS}.items()) or len(rows)!=1 or rows[0]['marker']!='continuity-v1' or rows[0]['mode']!=mode):
        raise Problem(503,'Continuidade indisponível; atualização explícita/integridade necessária.')


def row(db,table,tenant,customer,case_id):
    value=db.execute('SELECT * FROM '+table+' WHERE tenant=? AND customer=? AND case_id=?',(tenant,customer,case_id)).fetchone()
    if not value: return None
    value=dict(value);claimed=value.pop('record_hash')
    if digest(value)!=claimed: raise Problem(503,'Registo de continuidade sem integridade.')
    payload=strict_json(value['payload'].encode('utf-8'))
    if canonical(payload)!=value['payload']: raise Problem(503,'Registo não canónico.')
    if table=='continuity_closures':
        if payload.get('status')!='closed' or payload.get('real_recovery_demonstrated') is not False or payload.get('closure_means_recovery') is not False or payload.get('value_recovered') is not None: raise Problem(503,'Estado de encerramento inválido.')
        snapshot=dict(payload['snapshot']);context_hash=snapshot.pop('context_hash')
        if digest(snapshot)!=context_hash: raise Problem(503,'Snapshot de encerramento sem integridade.')
    return {**value,'payload':payload,'record_hash':claimed}


def active(db,case):
    if row(db,'continuity_openings',case['tenant'],case['customer'],case['case_id']) is None: raise Problem(503,'Proveniência do ciclo em falta.')
    if row(db,'continuity_closures',case['tenant'],case['customer'],case['case_id']): raise Problem(409,'Ciclo encerrado; histórico apenas, sem novos avanços.')


def bind(db,case,refs):
    for kind,field in (('c02','id'),('c04','request_id'),('c05','execution_id')):
        if kind not in refs: continue
        identity=str(refs[kind][field]);record={k:case[k] for k in ('tenant','customer','case_id')};record.update(kind=kind,object_id=identity)
        previous=db.execute('SELECT * FROM continuity_bindings WHERE tenant=? AND customer=? AND kind=? AND object_id=?',
                            (case['tenant'],case['customer'],kind,identity)).fetchone()
        if previous:
            stored=dict(previous);claimed=stored.pop('record_hash')
            if digest(stored)!=claimed: raise Problem(503,'Vínculo de continuidade sem integridade.')
            if stored!=record: raise Problem(409,'Fonte pertence a outro ciclo; decisão/autorização não reutilizável.')
        else: db.execute('INSERT INTO continuity_bindings VALUES (?,?,?,?,?,?)',(*record.values(),digest(record)))


def write(db,table,case,request_id,payload,actor):
    record={k:case[k] for k in ('tenant','customer','case_id')};record.update(request_id=request_id,payload=canonical(payload),actor=actor,created_at=now())
    record['record_hash']=digest(record)
    db.execute('INSERT INTO '+table+' VALUES (?,?,?,?,?,?,?,?)',tuple(record.values()))
    return {**record,'payload':payload}


def uncertain_executions(db,execution,user,tenant,customer):
    result=[]
    ids=db.execute('SELECT execution_id FROM c05_attempts WHERE tenant=? AND customer=? ORDER BY execution_id',(tenant,customer)).fetchall()
    for r in ids:
        view=execution._view(db,user,tenant,customer,r['execution_id'])
        if view['state'] not in ('test_applied','failed_no_effect'): result.append(r['execution_id'])
    return result


def initial_opening(db,case,reason='initial_registration',request_id=None,session_hash=None,legacy=False):
    return write(db,'continuity_openings',case,request_id or case['case_id'],
                 {'previous_case_id':None,'predecessor_closure_hash':None,'cycle_number':1,'reason':reason,'session_hash':session_hash,
                  'new_evidence_ids':[],'legacy_upgrade':legacy},case['actor'])


class Continuity:
    def __init__(self,store):
        from .orchestration import Orchestrator
        self.orch=Orchestrator(store);self.store=store

    def _scope(self,db,user,tenant,customer,case_id,write_access=False):
        self.orch._access(db,user,tenant,write=write_access)
        case=self.orch._case(db,tenant,customer,case_id)
        if row(db,'continuity_openings',tenant,customer,case_id) is None: raise Problem(503,'Proveniência do ciclo em falta.')
        return case

    def _session(self,db,user,tenant,token):
        self.orch._access(db,user,tenant,write=True)
        return self.orch.execution._session(db,user,token)[0]

    def _snapshot(self,db,user,case):
        t,c=case['tenant'],case['customer'];history=self.orch._history(db,case)
        refs=history[-1]['payload']['refs'] if history else {};bindings=[]
        for r in db.execute('SELECT * FROM continuity_bindings WHERE tenant=? AND customer=? AND case_id=? ORDER BY kind,object_id',(t,c,case['case_id'])):
            record=dict(r);claimed=record.pop('record_hash')
            if digest(record)!=claimed: raise Problem(503,'Vínculo sem integridade.')
            bindings.append(record)
        # Validate every historical C04 binding, not only the last checkpoint.
        pending=[];proposals=[]
        for b in bindings:
            if b['kind']!='c04': continue
            request=db.execute('SELECT 1 FROM c04_requests WHERE tenant=? AND customer=? AND request_id=?',(t,c,b['object_id'])).fetchone()
            if not request: continue
            try:
                p=self.orch.proposals._read(db,user,t,c,b['object_id'])
                proposals.append({'request_id':b['object_id'],'record_hash':p['result']['record_hash'],'status':p['result']['payload']['status']})
            except Problem as e:
                if e.status!=409: raise
                pending.append(b['object_id'])
        request_ids=[b['object_id'] for b in bindings if b['kind']=='c04']
        intent_rows=db.execute('SELECT execution_id,request_id FROM c05_intents WHERE tenant=? AND customer=?',(t,c)).fetchall()
        execution_ids={b['object_id'] for b in bindings if b['kind']=='c05'}|{r['execution_id'] for r in intent_rows if r['request_id'] in request_ids}
        executions=[];unresolved=[];verifications=[];other_prepared=[]
        for intent in intent_rows:
            if intent['execution_id'] in execution_ids: continue
            view=self.orch.execution._view(db,user,t,c,intent['execution_id'])
            if not view['attempts']:
                other_prepared.append({'execution_id':intent['execution_id'],'state':view['state'],'intent_hash':view['intent']['record_hash'],
                                       'approval_hash':view['approvals']['record_hash'] if view['approvals'] else None,'future_dispatch_invalidated_on_close':True})
        for execution_id in sorted(execution_ids):
            exists=db.execute('SELECT 1 FROM c05_intents WHERE tenant=? AND customer=? AND execution_id=?',(t,c,execution_id)).fetchone()
            if not exists: continue
            view=self.orch.execution._view(db,user,t,c,execution_id)
            executions.append({'execution_id':execution_id,'state':view['state'],'intent_hash':view['intent']['record_hash'],
                               'attempt_hash':view['attempts']['record_hash'] if view['attempts'] else None,'result_hash':view['results']['record_hash'] if view['results'] else None})
            if view['attempts'] and view['state'] in ('uncertain','uncertain_pending'): unresolved.append(execution_id)
            if view['attempts']:
                binding,v,records=self.orch.recovery._context(db,user,t,c,execution_id)
                plans=self.orch.recovery._plans(db,t,c,execution_id,binding,v)
                runs=self.orch.recovery._runs(db,t,c,execution_id,binding,v,records,plans)
                if runs:
                    run=runs[-1];a=run['payload']['assessment'];verifications.append({'execution_id':execution_id,'version':run['version'],'record_hash':run['record_hash'],
                         'execution_state':a['execution']['state'],'operational_state':a['operational_recovery']['state'],'value_state':a['value_recovery']['state'],'summary_state':a['summary_state']})
        self.orch.evidence._storage(db);configs=self.orch.evidence.integrations._chain(db,t)
        records=self.orch.evidence._records(db,t,c,configs)
        available=[{k:r[k] for k in ('id','record_hash','kind','definition_id','source_ref','occurred_at','received_at','config_version','config_hash')} for r in records]
        unresolved=sorted(set(unresolved)|set(uncertain_executions(db,self.orch.execution,user,t,c)))
        snapshot={'case_hash':case['record_hash'],'checkpoint_version':len(history),'checkpoint_hash':history[-1]['record_hash'] if history else None,
                  'state':history[-1]['payload']['state'] if history else 'awaiting_data','refs':refs,'proposals':proposals,'executions':executions,'verifications':verifications,
                  'evidence':available,'evidence_through':max((r['id'] for r in records),default=0),'pending_inferences':pending,'unresolved_executions':unresolved,'other_prepared_intents':other_prepared}
        snapshot['context_hash']=digest(snapshot)
        return snapshot

    def context(self,user,tenant,customer,case_id):
        self.orch.evidence._runtime()
        with self.store.transaction() as db:
            case=self._scope(db,user,tenant,customer,case_id)
            opening=row(db,'continuity_openings',tenant,customer,case_id);closure=row(db,'continuity_closures',tenant,customer,case_id)
            reviews=[]
            for raw in db.execute('SELECT * FROM continuity_reviews WHERE tenant=? AND customer=? AND case_id=? ORDER BY created_at,request_id',(tenant,customer,case_id)):
                record=dict(raw);claimed=record.pop('record_hash')
                if digest(record)!=claimed: raise Problem(503,'Revisão sem integridade.')
                payload=strict_json(record['payload'].encode('utf-8'))
                if payload.get('status')!='unresolved' or payload.get('allows_closure') is not False or payload.get('allows_new_cycle') is not False: raise Problem(503,'Estado de revisão inválido.')
                reviews.append({**record,'payload':payload,'record_hash':claimed})
            return {'case':case,'opening':opening,'closure':closure,'reviews':reviews,'lifecycle':'closed' if closure else 'active',
                    'context':closure['payload']['snapshot'] if closure else self._snapshot(db,user,case),
                    'operational_state':'inactive','real_recovery_demonstrated':False,'external_execution':'blocked'}

    def close(self,user,tenant,customer,case_id,request_id,reason,disposition,expected_version,expected_context_hash,*,human_confirmed=False,session_token=None):
        self.orch.evidence._runtime();identifier(request_id,'request_id');text(reason,'reason',1000)
        if disposition not in DISPOSITIONS or human_confirmed is not True or type(expected_version) is not int or expected_version<0: raise ValueError('Explicit closure decision required.')
        request={'reason':reason,'disposition':disposition,'expected_version':expected_version,'expected_context_hash':expected_context_hash}
        with self.store.transaction() as db:
            session_hash=self._session(db,user,tenant,session_token);case=self._scope(db,user,tenant,customer,case_id,True)
            collision=db.execute('SELECT case_id FROM continuity_closures WHERE tenant=? AND customer=? AND request_id=?',(tenant,customer,request_id)).fetchone()
            if collision and collision[0]!=case_id: raise Problem(409,'Pedido de encerramento pertence a outro ciclo.')
            previous=row(db,'continuity_closures',tenant,customer,case_id)
            if previous:
                if previous['request_id']!=request_id or previous['actor']!=user or previous['payload']['request']!=request: raise Problem(409,'Encerramento já registado; não substituível.')
                return previous
            snapshot=self._snapshot(db,user,case)
            if expected_version!=snapshot['checkpoint_version'] or expected_context_hash!=snapshot['context_hash']: raise Problem(409,'Contexto mudou; rever o snapshot antes de encerrar.')
            if snapshot['unresolved_executions'] or snapshot['pending_inferences']: raise Problem(409,'Execução incerta/pendente ou IA em curso; encerramento e novo ciclo bloqueados.')
            # Bind even an intent written after the checkpoint but before this transaction.
            for execution in snapshot['executions']: bind(db,case,{'c05':{'execution_id':execution['execution_id']}})
            return write(db,'continuity_closures',case,request_id,{'status':'closed','request':request,'snapshot':snapshot,'session_hash':session_hash,'human_confirmed':True,
                         'value_recovered':None,'real_recovery_demonstrated':False,'closure_means_recovery':False},user)

    def review(self,user,tenant,customer,case_id,request_id,note,evidence_ids,expected_context_hash,*,human_confirmed=False,session_token=None):
        self.orch.evidence._runtime();identifier(request_id,'request_id');text(note,'note',1000)
        if human_confirmed is not True or not isinstance(evidence_ids,list) or len(evidence_ids)>100 or any(type(i) is not int for i in evidence_ids) or len(evidence_ids)!=len(set(evidence_ids)): raise ValueError('Explicit review required.')
        with self.store.transaction() as db:
            session_hash=self._session(db,user,tenant,session_token);case=self._scope(db,user,tenant,customer,case_id,True);active(db,case)
            snapshot=self._snapshot(db,user,case)
            available={e['id'] for e in snapshot['evidence']}
            if set(evidence_ids)-available: raise Problem(403,'Evidências fora do escopo disponível.')
            request={'note':note,'evidence_ids':evidence_ids,'expected_context_hash':expected_context_hash}
            previous=db.execute('SELECT * FROM continuity_reviews WHERE tenant=? AND customer=? AND case_id=? AND request_id=?',(tenant,customer,case_id,request_id)).fetchone()
            if previous:
                record=dict(previous);claimed=record.pop('record_hash')
                if digest(record)!=claimed: raise Problem(503,'Revisão sem integridade.')
                payload=strict_json(record['payload'].encode('utf-8'))
                if record['actor']!=user or payload['request']!=request: raise Problem(409,'request_id já vinculado a outra revisão.')
                return {**record,'payload':payload,'record_hash':claimed}
            if db.execute('SELECT count(*) FROM continuity_reviews WHERE tenant=? AND customer=? AND case_id=?',(tenant,customer,case_id)).fetchone()[0]>=100: raise Problem(413,'Limite de 100 revisões por ciclo.')
            if snapshot['context_hash']!=expected_context_hash or not snapshot['unresolved_executions']: raise Problem(409,'Não há incerteza correspondente neste snapshot.')
            return write(db,'continuity_reviews',case,request_id,{'request':request,'snapshot':snapshot,'session_hash':session_hash,'status':'unresolved',
                         'allows_closure':False,'allows_new_cycle':False,'human_confirmed':True},user)

    def open(self,user,tenant,customer,case_id,request_id,reason,previous_case_id,*,human_confirmed=False,session_token=None):
        self.orch.evidence._runtime();customer_id(customer);identifier(case_id,'case_id');identifier(request_id,'request_id');text(reason,'reason',1000)
        if previous_case_id is not None: identifier(previous_case_id,'previous_case_id')
        if human_confirmed is not True: raise ValueError('Explicit opening required.')
        with self.store.transaction() as db:
            session_hash=self._session(db,user,tenant,session_token)
            existing=db.execute('SELECT case_id FROM continuity_openings WHERE tenant=? AND customer=? AND request_id=?',(tenant,customer,request_id)).fetchone()
            if existing:
                old=row(db,'continuity_openings',tenant,customer,existing['case_id'])
                if old['case_id']!=case_id or old['actor']!=user or old['payload']['reason']!=reason or old['payload']['previous_case_id']!=previous_case_id: raise Problem(409,'Pedido de abertura já utilizado.')
                return old
            if uncertain_executions(db,self.orch.execution,user,tenant,customer): raise Problem(409,'Execução pendente/incerta do cliente impede novo ciclo.')
            prior=db.execute('SELECT * FROM orchestration_cases WHERE tenant=? AND customer=? ORDER BY id DESC LIMIT 1',(tenant,customer)).fetchone()
            closure=None;predecessor=None;new_ids=[]
            if prior:
                predecessor=self.orch._case(db,tenant,customer,prior['case_id']);closure=row(db,'continuity_closures',tenant,customer,predecessor['case_id'])
                if not closure or previous_case_id!=predecessor['case_id']: raise Problem(409,'Ciclo ativo ou predecessor incorreto; novo ciclo recusado.')
                # Recheck all intents: closure can never erase an uncertain attempt.
                old_snapshot=self._snapshot(db,user,predecessor)
                if old_snapshot['unresolved_executions'] or old_snapshot['pending_inferences']: raise Problem(409,'Incerteza anterior não resolvida.')
                configs=self.orch.evidence.integrations._chain(db,tenant)
                records=self.orch.evidence._records(db,tenant,customer,configs)
                new_ids=[r['id'] for r in records if r['id']>closure['payload']['snapshot']['evidence_through'] and r['config_version']==len(configs) and r['occurred_at']>utc(closure['created_at']) and (r['period_start'] is None or r['period_start']>utc(closure['created_at']))]
                if not new_ids: raise Problem(409,'Novo ciclo exige evidência nova posterior ao encerramento, na configuração atual.')
            elif previous_case_id is not None: raise Problem(409,'Predecessor inexistente.')
            record={'id':db.execute('SELECT coalesce(max(id),0)+1 FROM orchestration_cases').fetchone()[0],
                    'tenant':tenant,'customer':customer,'case_id':case_id,'actor':user,'created_at':now()}
            record['record_hash']=digest(record)
            try: db.execute('INSERT INTO orchestration_cases VALUES (?,?,?,?,?,?,?)',tuple(record.values()))
            except sqlite3.IntegrityError: raise Problem(409,'Caso já existente ou outro ciclo ativo.')
            number=row(db,'continuity_openings',tenant,customer,predecessor['case_id'])['payload']['cycle_number']+1 if predecessor else 1
            opening=write(db,'continuity_openings',record,request_id,{'previous_case_id':previous_case_id,'predecessor_closure_hash':closure['record_hash'] if closure else None,
                        'cycle_number':number,'reason':reason,'session_hash':session_hash,'new_evidence_ids':new_ids,'legacy_upgrade':False},user)
            event={'tenant':tenant,'customer':customer,'case_id':case_id,'version':1,'parent_hash':None,
                   'payload':canonical({'state':'awaiting_data','blockers':['not_processed'],'refs':{},'basis':{},'operational_state':'inactive',
                                        'real_recovery_demonstrated':False,'core_transition_authorized':False}),'actor':user,'created_at':now()}
            event['record_hash']=digest(event);db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?,?,?,?,?,?)',tuple(event.values()))
            return opening


def upgrade(store):
    """Explicit offline M13 schema upgrade. Copies rows unchanged, no source-engine migration."""
    from .orchestration import TABLES as BASE,GUARDS as BASE_GUARDS,Orchestrator
    from .recovery import RecoveryRepository
    recovery=RecoveryRepository(store);mode=recovery.execution.mode
    old_case_sql=BASE['orchestration_cases'].replace('UNIQUE(tenant,customer,case_id)', 'UNIQUE(tenant,customer), UNIQUE(tenant,customer,case_id)')
    with closing(store.connect()) as db:
        db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN IMMEDIATE')
        try:
            schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'orchestration_*'")}
            expected={**BASE,**BASE_GUARDS,'orchestration_cases':old_case_sql}
            marker=db.execute('SELECT * FROM orchestration_metadata').fetchall() if 'orchestration_metadata' in schema else []
            dependencies={r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE tbl_name IN ('orchestration_cases','orchestration_events','orchestration_metadata') AND type IN ('trigger','index') AND sql IS NOT NULL")}
            if (set(schema)!=set(expected) or dependencies!=set(BASE_GUARDS) or any(schema.get(k)!=v for k,v in expected.items())
                    or len(marker)!=1 or marker[0]['mode']!=mode or marker[0]['marker']!='orchestration-v1'): raise ValueError('Exact M13 schema required; no repair/replacement.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'continuity_*'").fetchone(): raise ValueError('Continuity already present.')
            cases=[dict(r) for r in db.execute('SELECT * FROM orchestration_cases ORDER BY id')]
            checker=object.__new__(Orchestrator);histories=[]
            for case in cases:
                original=dict(case);claimed=original.pop('record_hash')
                if digest(original)!=claimed: raise ValueError('Case integrity mismatch.')
                histories.append(checker._history(db,case))
            for op in ('UPDATE','DELETE'): db.execute('DROP TRIGGER orchestration_immutable_orchestration_cases_'+op)
            db.execute('CREATE TEMP TABLE continuity_upgrade_cases AS SELECT * FROM orchestration_cases')
            db.execute('DROP TABLE orchestration_cases');db.execute(BASE['orchestration_cases'])
            db.execute('INSERT INTO orchestration_cases SELECT * FROM continuity_upgrade_cases');db.execute('DROP TABLE continuity_upgrade_cases')
            for op in ('UPDATE','DELETE'): db.execute(BASE_GUARDS['orchestration_immutable_orchestration_cases_'+op])
            install_storage(db,mode)
            for case,history in zip(cases,histories):
                initial_opening(db,case,reason='m13_legacy_registration',legacy=True)
                for event in history: bind(db,case,event['payload']['refs'])
            if db.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Foreign key check failed.')
            db.commit()
        except BaseException: db.rollback();raise
    return {'status':'upgraded','cases_preserved':len(cases),'operational_state':'inactive'}


REQUEST_FIELDS={
 'open':'tenant customer case_id request_id reason previous_case_id human_confirmed',
 'close':'tenant customer case_id request_id reason disposition expected_version expected_context_hash human_confirmed',
 'review':'tenant customer case_id request_id note evidence_ids expected_context_hash human_confirmed',
}


def request_body(operation,body):
    shape(body,REQUEST_FIELDS[operation],operation)
    return body


def main():
    parser=argparse.ArgumentParser(description='Explicit offline M13 continuity upgrade; no service startup migration.')
    parser.add_argument('command',choices=['upgrade']);parser.add_argument('--db',required=True);args=parser.parse_args()
    try: result=upgrade(Store.open_existing(args.db))
    except (Problem,ValueError,OSError,sqlite3.Error): parser.exit(1,'{"status":"error","code":"continuity_upgrade_refused"}\n')
    print(canonical(result))


if __name__=='__main__': main()
