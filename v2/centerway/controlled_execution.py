"""Isolated C05: explicit human approval, fenced test dispatch, immutable receipts.

No HTTP route, production execution, default adapter, retries or C06 evaluation.
Local callers must supply a trusted authenticated human principal (as prior CLIs).
"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import re
import sqlite3

from .ai_proposals import ProposalRepository
from .c04_contract import validate
from .core import Core, Problem
from .evidence import scalar, utc, customer_id
from .execution_adapter import ExecutionReceipt
from .http_contract import strict_json
from .integration_contract import fields, identifier, shape, text
from .integrations import canonical, digest
from .investigation_contract import COMPARISONS
from .store import Store, now

VERSION='controlled-c05-v1'
TABLES={
 'c05_metadata': "CREATE TABLE c05_metadata(marker TEXT PRIMARY KEY CHECK(marker='controlled-c05-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')))",
 'c05_intents': "CREATE TABLE c05_intents(tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, request_id TEXT NOT NULL, intervention_key TEXT NOT NULL, payload TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,execution_id), UNIQUE(tenant,customer,request_id), UNIQUE(tenant,customer,intervention_key), FOREIGN KEY(tenant,customer,request_id) REFERENCES c04_results(tenant,customer,request_id))",
 'c05_approvals': "CREATE TABLE c05_approvals(tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, payload TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,execution_id), FOREIGN KEY(tenant,customer,execution_id) REFERENCES c05_intents(tenant,customer,execution_id))",
 'c05_attempts': "CREATE TABLE c05_attempts(tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, payload TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,execution_id), FOREIGN KEY(tenant,customer,execution_id) REFERENCES c05_approvals(tenant,customer,execution_id))",
 'c05_results': "CREATE TABLE c05_results(tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, payload TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,execution_id), FOREIGN KEY(tenant,customer,execution_id) REFERENCES c05_attempts(tenant,customer,execution_id))",
 'c05_audit': "CREATE TABLE c05_audit(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, execution_id TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)",
}
GUARDS={f'c05_immutable_{table}_{op}':f"CREATE TRIGGER c05_immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for table in TABLES for op in ('UPDATE','DELETE')}


def install(store):
    proposals=ProposalRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'c05_*'").fetchone(): raise ValueError('C05 already exists; no replacement/repair.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO c05_metadata VALUES (?,?)',(VERSION,proposals.investigation.detection.evidence.integrations.mode))
    return {'status':'initialized','external_execution':'blocked','adapter':'not_configured'}


def refuse(status=409,code='c05_refused'):
    error=Problem(status,'C05 recusado; consultar o contrato e a auditoria. Nenhum sucesso presumido.')
    error.c05_code=code
    raise error


def detached(value): return strict_json(canonical(value).encode('utf-8'))


def _time(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


class ExecutionRepository:
    def __init__(self,store):
        self.store=store;self.proposals=ProposalRepository(store)
        self.mode=self.proposals.investigation.detection.evidence.integrations.mode
        with closing(store.connect()) as db: self._storage(db)

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'c05_*'")}
        rows=db.execute('SELECT * FROM c05_metadata').fetchall() if 'c05_metadata' in schema else []
        if (any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS}.items()) or len(rows)!=1
                or rows[0]['marker']!=VERSION or rows[0]['mode']!=self.mode): refuse(503)

    def _access(self,db,user,tenant,write=True):
        self.proposals._storage(db);self._storage(db)
        markers={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name IN ('preview_metadata','production_metadata')")}
        expected={'demo':{'preview_metadata'},'production':{'production_metadata'},'sandbox':set()}[self.mode]
        if markers!=expected: refuse(503,'runtime_mode_changed')
        if self.mode=='demo':
            rows=db.execute('SELECT expires FROM preview_metadata').fetchall()
            if len(rows)!=1 or _time(rows[0][0])<=datetime.now(timezone.utc): refuse(503,'demo_expired')
        Core(self.store).authorize(db,user,tenant,write=write)
        if write and self.mode=='production': refuse(503,'production_execution_blocked')

    def _audit(self,db,tenant,customer,execution_id,actor,operation,status,reason=None):
        previous=db.execute('SELECT record_hash FROM c05_audit WHERE tenant=? AND customer=? AND execution_id=? ORDER BY id DESC LIMIT 1',(tenant,customer,execution_id)).fetchone()
        payload=canonical({'actor':actor,'operation':operation,'status':status,'reason_code':reason,'identity_basis':'claimed_principal' if status=='refused' else 'session_verified' if operation=='approve' else 'trusted_local_core_principal','created_at':now()})
        row={'tenant':tenant,'customer':customer,'execution_id':execution_id,'payload':payload,'previous_hash':previous[0] if previous else ''}
        db.execute('INSERT INTO c05_audit(tenant,customer,execution_id,payload,previous_hash,record_hash) VALUES (?,?,?,?,?,?)',(*row.values(),digest(row)))

    def _denial(self,user,tenant,customer,execution_id,operation,error):
        # No exception/provider text is retained. Even revoked/unknown principals
        # leave a denial receipt, but cannot read any scoped state.
        with self.store.transaction() as db:
            self._storage(db);self._audit(db,tenant,customer,execution_id,user,operation,'refused',getattr(error,'c05_code','access_or_runtime_refused'))

    def _insert(self,db,table,tenant,customer,execution_id,payload,request_id=None,intervention_key=None):
        row={'tenant':tenant,'customer':customer,'execution_id':execution_id}
        if request_id is not None:
            row['request_id']=request_id;row['intervention_key']=intervention_key
        row['payload']=canonical(payload);row['record_hash']=digest(row)
        db.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
        return row['record_hash']

    def _row(self,db,table,tenant,customer,execution_id,required=True):
        row=db.execute('SELECT * FROM '+table+' WHERE tenant=? AND customer=? AND execution_id=?',(tenant,customer,execution_id)).fetchone()
        if not row:
            if required: refuse(404)
            return None
        row=dict(row);claimed=row.pop('record_hash')
        if digest(row)!=claimed: refuse(503)
        return {**row,'payload':strict_json(row['payload'].encode('utf-8')),'record_hash':claimed}

    def _proposal(self,db,user,tenant,customer,request_id):
        result=self.proposals._read(db,user,tenant,customer,request_id)
        request=result['request'];decision=result['result']['payload']
        if decision['status']!='proposal_validated': refuse(409,'proposal_not_validated')
        context=self.proposals._context(db,user,tenant,customer,request['c02_run_id'],request['c03_version'])
        if context['context_hash']!=request['context_hash'] or context['freshness_issues']: refuse(409,'proposal_context_changed')
        if validate(canonical(decision['model_response']),context)!=decision: refuse(503)
        cap=next(c for c in context['configuration']['capabilities'] if c['id']==decision['validated_capability_id'])
        if Core(self.store).authorize(db,user,tenant,write=True)!=cap['permissions']['required_role']: refuse(403)
        return {'tenant':tenant,'customer':customer,'request_id':request_id,'proposal_hash':result['result']['record_hash'],
                'context_hash':context['context_hash'],'lineage':context['lineage'],'capability':cap,
                'classification':context['classification'],'configuration':context['configuration']}

    def _adapter(self,adapter,binding):
        if self.mode=='production' or binding['classification']!='synthetic' or adapter is None: refuse(503,'test_adapter_unavailable_or_forbidden')
        try:
            d=detached(adapter.descriptor())
            shape(d,'kind adapter_id version tenant capability_id idempotent atomic_conditions','adapter')
            identifier(d['adapter_id'],'adapter_id');identifier(d['version'],'version')
            if (d['kind']!='test_adapter' or d['tenant']!=binding['tenant'] or d['capability_id']!=binding['capability']['id']
                    or d['idempotent'] is not True or d['atomic_conditions'] is not True): refuse(503)
            return d
        except (ValueError,TypeError,KeyError,AttributeError,RecursionError): refuse(503)

    def _observe(self,adapter,binding):
        started=datetime.now(timezone.utc)
        try:
            s=detached(adapter.observe(detached(binding)))
            if len(canonical(s).encode('utf-8'))>16384: refuse()
            shape(s,'tenant customer capability_id revision observed_at facts','snapshot')
            identifier(s['revision'],'revision')
            if (s['tenant']!=binding['tenant'] or s['customer']!=binding['customer'] or s['capability_id']!=binding['capability']['id']
                    or not started<=_time(s['observed_at'])<=datetime.now(timezone.utc)): refuse()
            if not isinstance(s['facts'],list) or len(s['facts'])>100: refuse()
            required={(c['evidence_ref'],c['field']) for c in binding['capability']['conditions']}
            values={};definitions={d['id']:d for d in binding['configuration']['evidence']}
            for fact in s['facts']:
                shape(fact,'evidence_ref field value','current_fact');key=(fact['evidence_ref'],fact['field'])
                if key not in required or key in values: refuse()
                kind=fields(definitions[key[0]]['fields'],'fields')[key[1]]['type']
                values[key]=scalar(fact['value'],kind)
                if kind=='timestamp': values[key]=utc(values[key])
            if set(values)!=required: refuse()
            for condition in binding['capability']['conditions']:
                if condition['operator']=='exists': continue
                actual=values[(condition['evidence_ref'],condition['field'])];expected=condition['value']
                kind=fields(definitions[condition['evidence_ref']]['fields'],'fields')[condition['field']]['type']
                if kind=='timestamp': expected=utc(expected)
                if type(actual) in (int,float): actual,expected=Fraction(str(actual)),Fraction(str(expected))
                if not COMPARISONS[condition['operator']](actual,expected): refuse(409,'current_condition_not_satisfied')
            return s
        except Problem: raise
        except Exception: refuse(503)

    def _fresh(self,snapshot):
        # Security dispatch lease; never a business measurement/coverage rule.
        age=(datetime.now(timezone.utc)-_time(snapshot['observed_at'])).total_seconds()
        if not 0<=age<=5: refuse(409,'current_observation_expired')

    def _state_hash(self,snapshot):
        s={k:v for k,v in snapshot.items() if k!='observed_at'}
        s['facts']=sorted(s['facts'],key=lambda f:(f['evidence_ref'],f['field']))
        return digest(s)

    def _scope(self,user,tenant,customer,*values):
        text(user,'user',128);identifier(tenant,'tenant');customer_id(customer)
        for value in values: identifier(value,'scope')

    def prepare(self,user,tenant,customer,request_id,execution_id,adapter=None):
        self._scope(user,tenant,customer,request_id,execution_id)
        try:
            self.proposals._runtime()
            with self.store.transaction() as db:
                self._access(db,user,tenant)
                binding=self._proposal(db,user,tenant,customer,request_id)
            descriptor=self._adapter(adapter,binding);snapshot=self._observe(adapter,binding)
            self.proposals._runtime()
            with self.store.transaction() as db:
                self._access(db,user,tenant);self._fresh(snapshot)
                if descriptor!=self._adapter(adapter,binding): refuse()
                if binding!=self._proposal(db,user,tenant,customer,request_id): refuse()
                existing=self._row(db,'c05_intents',tenant,customer,execution_id,False)
                if existing:
                    self._view(db,user,tenant,customer,execution_id)
                    if existing['request_id']!=request_id or existing['payload']['binding']!=binding or existing['payload']['adapter']!=descriptor: refuse()
                    return existing
                if db.execute('SELECT 1 FROM c05_intents WHERE tenant=? AND customer=? AND request_id=?',(tenant,customer,request_id)).fetchone(): refuse()
                intervention_key=digest({'lineage':binding['lineage'],'capability':binding['capability'],'state_hash':self._state_hash(snapshot),'adapter':descriptor})
                if db.execute('SELECT 1 FROM c05_intents WHERE tenant=? AND customer=? AND intervention_key=?',(tenant,customer,intervention_key)).fetchone(): refuse()
                payload={'version':VERSION,'actor':user,'created_at':now(),'binding':binding,'adapter':descriptor,
                         'snapshot':snapshot,'state_hash':self._state_hash(snapshot),'operational_state':'test_only'}
                self._insert(db,'c05_intents',tenant,customer,execution_id,payload,request_id,intervention_key)
                self._audit(db,tenant,customer,execution_id,user,'prepare','prepared')
                return self._row(db,'c05_intents',tenant,customer,execution_id)
        except Problem as error:
            self._denial(user,tenant,customer,execution_id,'prepare',error);raise

    def approve(self,user,tenant,customer,execution_id,intent_hash,*,human_confirmed=False,ttl_seconds=300,session_token=None,adapter=None):
        self._scope(user,tenant,customer,execution_id)
        try:
            if human_confirmed is not True or type(ttl_seconds) is not int or not 1<=ttl_seconds<=300: refuse(400,'explicit_human_confirmation_required')
            self.proposals._runtime()
            with self.store.transaction() as db:
                self._access(db,user,tenant)
                session_hash,session_expires=self._session(db,user,session_token)
                intent=self._row(db,'c05_intents',tenant,customer,execution_id)
                self._view(db,user,tenant,customer,execution_id)
                if intent_hash!=intent['record_hash']: refuse(409,'approval_scope_mismatch')
                binding=self._proposal(db,user,tenant,customer,intent['request_id'])
                if binding!=intent['payload']['binding']: refuse()
            descriptor=self._adapter(adapter,binding)
            if descriptor!=intent['payload']['adapter']: refuse()
            snapshot=self._observe(adapter,binding)
            if self._state_hash(snapshot)!=intent['payload']['state_hash']: refuse(409,'current_state_changed')
            self.proposals._runtime()
            with self.store.transaction() as db:
                self._access(db,user,tenant);self._session(db,user,session_token);self._fresh(snapshot)
                if descriptor!=self._adapter(adapter,binding): refuse()
                if binding!=self._proposal(db,user,tenant,customer,intent['request_id']): refuse()
                existing=self._row(db,'c05_approvals',tenant,customer,execution_id,False)
                if existing:
                    if existing['payload']['actor']!=user or existing['payload']['intent_hash']!=intent_hash: refuse()
                    return existing
                payload={'actor':user,'human_confirmed':True,'session_hash':session_hash,'intent_hash':intent_hash,'created_at':now(),
                         'expires_at':min(_time(session_expires),datetime.now(timezone.utc)+timedelta(seconds=ttl_seconds)).isoformat(),
                         'snapshot':snapshot,'state_hash':self._state_hash(snapshot),'scope':'one_test_intervention','external_execution_authorized':False}
                self._insert(db,'c05_approvals',tenant,customer,execution_id,payload)
                self._audit(db,tenant,customer,execution_id,user,'approve','human_approved_test_only')
                return self._row(db,'c05_approvals',tenant,customer,execution_id)
        except Problem as error:
            self._denial(user,tenant,customer,execution_id,'approve',error);raise

    def execute(self,user,tenant,customer,execution_id,adapter=None):
        self._scope(user,tenant,customer,execution_id)
        try:
            self.proposals._runtime()
            with self.store.transaction() as db:
                self._access(db,user,tenant)
                intent=self._row(db,'c05_intents',tenant,customer,execution_id)
                approval=self._row(db,'c05_approvals',tenant,customer,execution_id)
                self._view(db,user,tenant,customer,execution_id)
                # No second dispatch even with a different actor/adapter after crash.
                if self._row(db,'c05_attempts',tenant,customer,execution_id,False):
                    return self._view(db,user,tenant,customer,execution_id)
                binding=self._proposal(db,user,tenant,customer,intent['request_id'])
                if binding!=intent['payload']['binding']: refuse()
                self._approval(db,approval,intent)
            descriptor=self._adapter(adapter,binding)
            if descriptor!=intent['payload']['adapter']: refuse()
            snapshot=self._observe(adapter,binding)
            if self._state_hash(snapshot)!=approval['payload']['state_hash']: refuse(409,'current_state_changed')
            self.proposals._runtime()
            # Reserve exactly once, recheck the current Core/heads/approval. The
            # adapter must atomically fence a state change after this observation.
            with self.store.transaction() as db:
                self._access(db,user,tenant);self._approval(db,approval,intent);self._fresh(snapshot)
                if descriptor!=self._adapter(adapter,binding): refuse()
                if binding!=self._proposal(db,user,tenant,customer,intent['request_id']): refuse()
                if self._row(db,'c05_attempts',tenant,customer,execution_id,False): return self._view(db,user,tenant,customer,execution_id)
                key=digest({'version':VERSION,'database_scope':intent['record_hash'],'approval':approval['record_hash']})
                attempt={'actor':user,'created_at':now(),'execution_key':key,'intent_hash':intent['record_hash'],
                         'approval_hash':approval['record_hash'],'adapter':descriptor,'snapshot':snapshot,'state':'dispatch_started'}
                self._insert(db,'c05_attempts',tenant,customer,execution_id,attempt)
                self._audit(db,tenant,customer,execution_id,user,'execute','dispatch_started')
            # No database write lock across adapter I/O; any interruption leaves
            # an uncertain pending attempt and will NEVER automatically retry.
            status='uncertain';receipt=None
            try:
                candidate=adapter.apply(key,detached(binding),detached(snapshot))
                if (isinstance(candidate,ExecutionReceipt) and candidate.status in ('test_applied','failed_no_effect','uncertain')
                        and isinstance(candidate.receipt_id,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',candidate.receipt_id)
                        and candidate.before_revision==snapshot['revision']
                        and (candidate.after_revision is None or isinstance(candidate.after_revision,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',candidate.after_revision))
                        and (candidate.status!='test_applied' or candidate.after_revision is not None and candidate.after_revision!=candidate.before_revision)
                        and (candidate.status!='failed_no_effect' or candidate.after_revision is None)):
                    status=candidate.status;receipt=vars(candidate)
            except Exception: pass  # Could have acted; never infer no effect or leak error/secret.
            with self.store.transaction() as db:
                self._storage(db)
                payload={'status':status,'receipt':receipt,'attempt_hash':self._row(db,'c05_attempts',tenant,customer,execution_id)['record_hash'],
                         'recorded_by':user,'created_at':now(),'effect_scope':'test_adapter_only','verification_status':'not_performed',
                         'operational_recovered':None,'value_recovered':None,'external_execution_authorized':False}
                self._insert(db,'c05_results',tenant,customer,execution_id,payload)
                self._audit(db,tenant,customer,execution_id,user,'result',status)
            # Preserve the receipt even if access expires/revokes during I/O.
            return self.get(user,tenant,customer,execution_id)
        except Problem as error:
            self._denial(user,tenant,customer,execution_id,'execute',error);raise

    def _session(self,db,user,token):
        if not isinstance(token,str) or not 16<=len(token)<=512: refuse(403,'approval_session_invalid')
        row=db.execute('SELECT expires FROM sessions WHERE token=? AND user_id=?',(token,user)).fetchone()
        if not row or _time(row['expires'])<=datetime.now(timezone.utc): refuse(403,'approval_session_invalid')
        return digest({'session_token':token}),row['expires']

    def _approval(self,db,approval,intent):
        a=approval['payload']
        if self.mode=='production' or a['human_confirmed'] is not True or a['intent_hash']!=intent['record_hash'] or _time(a['expires_at'])<=datetime.now(timezone.utc): refuse()
        Core(self.store).authorize(db,a['actor'],intent['tenant'],write=True)
        sessions=db.execute('SELECT token,expires FROM sessions WHERE user_id=?',(a['actor'],)).fetchall()
        if not any(digest({'session_token':r['token']})==a['session_hash'] and _time(r['expires'])>datetime.now(timezone.utc) for r in sessions): refuse(403,'approval_session_revoked_or_expired')

    def _view(self,db,user,tenant,customer,execution_id):
        intent=self._row(db,'c05_intents',tenant,customer,execution_id)
        proposal=self.proposals._read(db,user,tenant,customer,intent['request_id'])
        b=intent['payload']['binding'];context=proposal['request']['context']
        if (b['proposal_hash']!=proposal['result']['record_hash'] or b['context_hash']!=context['context_hash']
                or b['configuration']!=context['configuration'] or b['lineage']!=context['lineage']
                or b['capability'] not in context['configuration']['capabilities']): refuse(503)
        records={'intent':intent}
        for name in ('approvals','attempts','results'): records[name]=self._row(db,'c05_'+name,tenant,customer,execution_id,False)
        if records['approvals'] and records['approvals']['payload']['intent_hash']!=intent['record_hash']: refuse(503)
        if records['attempts'] and (not records['approvals'] or records['attempts']['payload']['approval_hash']!=records['approvals']['record_hash']): refuse(503)
        if records['results'] and (not records['attempts'] or records['results']['payload']['attempt_hash']!=records['attempts']['record_hash']): refuse(503)
        chain=[];previous=''
        for row in db.execute('SELECT * FROM c05_audit WHERE tenant=? AND customer=? AND execution_id=? ORDER BY id',(tenant,customer,execution_id)):
            r=dict(row);r.pop('id');claimed=r.pop('record_hash')
            if r['previous_hash']!=previous or digest(r)!=claimed: refuse(503)
            chain.append({**r,'payload':strict_json(r['payload'].encode('utf-8')),'record_hash':claimed});previous=claimed
        return {**records,'audit':chain,'state':records['results']['payload']['status'] if records['results'] else 'uncertain_pending' if records['attempts'] else 'approved_test_only' if records['approvals'] else 'awaiting_human_approval',
                'verification_status':'not_performed','external_execution':'blocked'}

    def get(self,user,tenant,customer,execution_id):
        self._scope(user,tenant,customer,execution_id)
        self.proposals._runtime()
        with self.store.transaction() as db:
            self._access(db,user,tenant,write=False);return self._view(db,user,tenant,customer,execution_id)


def main():
    parser=argparse.ArgumentParser(description='C05 local setup/read only. No runtime adapters or execution command.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    get=sub.add_parser('get')
    for key in ('db','user','tenant','customer','execution-id'): get.add_argument('--'+key,required=True)
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        output=install(store) if args.command=='init' else ExecutionRepository(store).get(args.user,args.tenant,args.customer,args.execution_id)
    except (Problem,ValueError,OSError,sqlite3.Error,RecursionError): parser.exit(1,'{"status":"error","code":"c05_refused"}\n')
    print(canonical(output))


if __name__=='__main__': main()
