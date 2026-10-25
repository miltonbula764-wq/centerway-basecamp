"""Bounded polling coordinator over M06–M12. No invented business inputs or grants."""
import argparse
from contextlib import closing
import sqlite3
from time import monotonic

from .ai_adapter import AIAdapter,configured_adapter
from .core import Core,Problem
from .evidence import customer_id,utc
from .http_contract import strict_json
from .integration_contract import identifier
from .integrations import canonical,digest
from .recovery import RecoveryRepository
from .store import Store,now

VERSION='orchestration-v1'
STATES=('awaiting_data','awaiting_investigation','awaiting_ai','awaiting_approval','awaiting_execution',
        'awaiting_verification','stable','no_action','needs_review','verification_recorded')
POST_DISPATCH={'awaiting_verification','needs_review','verification_recorded'}
# Earlier prerequisites may reopen on changed evidence/configuration. The post-
# dispatch lineage fence below narrows needs_review to POST_DISPATCH once reserved.
TRANSITIONS={
 'awaiting_data':{'awaiting_data','awaiting_investigation','stable','needs_review'},
 'awaiting_investigation':{'awaiting_data','awaiting_investigation','awaiting_ai','stable','needs_review'},
 'awaiting_ai':{'awaiting_data','awaiting_investigation','awaiting_ai','awaiting_execution','stable','no_action','needs_review'},
 'awaiting_approval':{'awaiting_data','awaiting_investigation','awaiting_ai','awaiting_approval','awaiting_execution','awaiting_verification','stable','needs_review'},
 'awaiting_execution':{'awaiting_data','awaiting_investigation','awaiting_ai','awaiting_approval','awaiting_execution','awaiting_verification','stable','needs_review'},
 'stable':{'awaiting_data','awaiting_investigation','stable','needs_review'},
 'no_action':{'awaiting_data','awaiting_investigation','awaiting_ai','no_action','stable','needs_review'},
 'needs_review':set(STATES),
 'awaiting_verification':POST_DISPATCH,
 'verification_recorded':POST_DISPATCH,
}
TABLES={
 'orchestration_metadata': "CREATE TABLE orchestration_metadata(marker TEXT PRIMARY KEY CHECK(marker='orchestration-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')))",
 'orchestration_cases': "CREATE TABLE orchestration_cases(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(tenant,customer), UNIQUE(tenant,customer,case_id))",
 'orchestration_events': "CREATE TABLE orchestration_events(tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), parent_hash TEXT, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,case_id,version), FOREIGN KEY(tenant,customer,case_id) REFERENCES orchestration_cases(tenant,customer,case_id))",
}
GUARDS={f'orchestration_immutable_{table}_{op}':f"CREATE TRIGGER orchestration_immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for table in TABLES for op in ('UPDATE','DELETE')}


def key(stage,*parts): return 'orch-'+digest({'stage':stage,'parts':parts})[:58]


def install(store):
    recovery=RecoveryRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'orchestration_*'").fetchone(): raise ValueError('Orchestration exists; no repair/replacement.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO orchestration_metadata VALUES (?,?)',(VERSION,recovery.execution.mode))
    return {'status':'initialized','operational_state':'inactive','external_execution':'blocked'}


class Orchestrator:
    def __init__(self,store):
        self.store=store;self.recovery=RecoveryRepository(store);self.execution=self.recovery.execution
        self.proposals=self.execution.proposals;self.investigation=self.proposals.investigation
        self.detection=self.investigation.detection;self.evidence=self.detection.evidence
        with closing(store.connect()) as db: self._storage(db)

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'orchestration_*'")}
        rows=db.execute('SELECT * FROM orchestration_metadata').fetchall() if 'orchestration_metadata' in schema else []
        if (any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS}.items()) or len(rows)!=1
                or rows[0]['marker']!=VERSION or rows[0]['mode']!=self.execution.mode): raise Problem(503,'Orquestração indisponível; preparação/integridade necessária.')

    def _access(self,db,user,tenant,write=False):
        identifier(tenant,'tenant');Core(self.store).authorize(db,user,tenant,write=write)
        self.execution._access(db,user,tenant,write=False);self.recovery._storage(db);self._storage(db)
        if write and self.execution.mode=='production': raise Problem(503,'Orquestração operacional de production bloqueada.')

    def _case(self,db,tenant,customer,case_id):
        customer_id(customer);identifier(case_id,'case_id')
        row=db.execute('SELECT * FROM orchestration_cases WHERE tenant=? AND customer=? AND case_id=?',(tenant,customer,case_id)).fetchone()
        if not row: raise Problem(404,'Caso coordenado inexistente neste escopo.')
        row=dict(row);claimed=row.pop('record_hash')
        if digest(row)!=claimed: raise Problem(503,'Caso coordenado sem integridade.')
        return {**row,'record_hash':claimed}

    def _history(self,db,case):
        history=[];parent=None
        for raw in db.execute('SELECT * FROM orchestration_events WHERE tenant=? AND customer=? AND case_id=? ORDER BY version',
                              (case['tenant'],case['customer'],case['case_id'])):
            row=dict(raw);claimed=row.pop('record_hash')
            try:
                p=strict_json(row['payload'].encode('utf-8'))
                if (row['version']!=len(history)+1 or row['parent_hash']!=parent or digest(row)!=claimed or canonical(p)!=row['payload']
                        or set(p)!={'state','blockers','refs','basis','operational_state','real_recovery_demonstrated','core_transition_authorized'}
                        or p['state'] not in STATES or p['operational_state']!='inactive' or p['real_recovery_demonstrated'] is not False
                        or p['core_transition_authorized'] is not False or not isinstance(p['blockers'],list)
                        or any(not isinstance(c,str) or len(c)>80 for c in p['blockers']) or not isinstance(p['refs'],dict) or not isinstance(p['basis'],dict)):
                    raise ValueError('History mismatch.')
                if history:
                    previous=history[-1]['payload']
                    if p['state'] not in TRANSITIONS[previous['state']]: raise ValueError('Invalid transition.')
                    dispatched=previous['refs'].get('c05',{}).get('attempt_hash')
                    if dispatched and (p['state'] not in POST_DISPATCH or p['refs'].get('c05',{}).get('attempt_hash')!=dispatched
                                       or any(p['refs'].get(k)!=previous['refs'].get(k) for k in ('c02','c03','c04'))): raise ValueError('Dispatch lineage cannot change.')
            except (ValueError,KeyError,TypeError,AttributeError): raise Problem(503,'Histórico coordenado sem integridade.')
            history.append({**row,'record_hash':claimed,'payload':p});parent=claimed
        return history

    def _record(self,user,case,expected,state,blockers,refs,basis):
        self.evidence._runtime()
        if state in ('awaiting_verification','verification_recorded') and not refs.get('c05',{}).get('attempt_hash'): return False
        if state=='verification_recorded' and not refs.get('c06',{}).get('record_hash'): raise Problem(409,'Verificação não registada no C06.')
        p={'state':state,'blockers':sorted(set(blockers)),'refs':refs,'basis':basis,'operational_state':'inactive',
           'real_recovery_demonstrated':False,'core_transition_authorized':False}
        with self.store.transaction() as db:
            self._access(db,user,case['tenant'],write=True)
            current=self._case(db,case['tenant'],case['customer'],case['case_id']);history=self._history(db,current)
            if len(history)!=expected: return False
            # Fence a C05 reservation that appeared after the worker read its
            # checkpoint. Never drop that lineage to start another generation.
            if history and history[-1]['payload']['refs'].get('c05'):
                old_refs=history[-1]['payload']['refs'];old_id=old_refs['c05']['execution_id']
                attempt=db.execute('SELECT record_hash FROM c05_attempts WHERE tenant=? AND customer=? AND execution_id=?',
                                   (case['tenant'],case['customer'],old_id)).fetchone()
                if attempt and (refs.get('c05',{}).get('execution_id')!=old_id or refs.get('c05',{}).get('attempt_hash')!=attempt[0]
                                or any(refs.get(k)!=old_refs.get(k) for k in ('c02','c03','c04'))): return False
            if history and history[-1]['payload']==p: return True
            if len(history)>=1000: raise Problem(413,'Limite de 1000 transições por caso.')
            if history:
                previous=history[-1]['payload'];dispatch=previous['refs'].get('c05',{}).get('attempt_hash')
                if state not in TRANSITIONS[previous['state']] or dispatch and (state not in POST_DISPATCH or refs.get('c05',{}).get('attempt_hash')!=dispatch
                        or any(refs.get(k)!=previous['refs'].get(k) for k in ('c02','c03','c04'))): raise Problem(409,'Linhagem/transição incompatível após despacho.')
            row={'tenant':case['tenant'],'customer':case['customer'],'case_id':case['case_id'],'version':len(history)+1,
                 'parent_hash':history[-1]['record_hash'] if history else None,'payload':canonical(p),'actor':user,'created_at':now()}
            row['record_hash']=digest(row)
            db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?,?,?,?,?,?)',tuple(row.values()))
            return True

    def register(self,user,tenant,customer,case_id):
        self.evidence._runtime();customer_id(customer);identifier(case_id,'case_id')
        with self.store.transaction() as db:
            self._access(db,user,tenant,write=True)
            previous=db.execute('SELECT case_id FROM orchestration_cases WHERE tenant=? AND customer=?',(tenant,customer)).fetchone()
            if previous:
                if previous[0]!=case_id: raise Problem(409,'Um caso coordenado contínuo por cliente; sem reinício que contorne C05.')
                self._case(db,tenant,customer,case_id)
            else:
                row={'id':db.execute('SELECT coalesce(max(id),0)+1 FROM orchestration_cases').fetchone()[0],
                     'tenant':tenant,'customer':customer,'case_id':case_id,'actor':user,'created_at':now()}
                row['record_hash']=digest(row);db.execute('INSERT INTO orchestration_cases VALUES (?,?,?,?,?,?,?)',tuple(row.values()))
        case=self.history(user,tenant,customer,case_id)['case']
        self._record(user,case,0,'awaiting_data',['not_processed'],{}, {})
        return self.history(user,tenant,customer,case_id)

    def history(self,user,tenant,customer,case_id):
        self.evidence._runtime()
        with self.store.transaction() as db:
            self._access(db,user,tenant);case=self._case(db,tenant,customer,case_id)
            return {'case':case,'history':self._history(db,case),'operational_state':'inactive','external_execution':'blocked'}

    def query(self,user,tenant,customer=None,case_id=None,state=None,after=0,limit=25):
        self.evidence._runtime()
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=50: raise ValueError('Invalid case pagination.')
        if customer is not None: customer_id(customer)
        if case_id is not None:
            if customer is None: raise ValueError('case_id needs explicit customer.')
            identifier(case_id,'case_id')
        if state is not None and state not in STATES: raise ValueError('Unknown orchestration state.')
        with self.store.transaction() as db:
            self._access(db,user,tenant)
            # Keyset pagination with SQL state filter; limit applies before payload reads.
            rows=db.execute('''SELECT c.* FROM orchestration_cases c LEFT JOIN orchestration_events e
                ON e.tenant=c.tenant AND e.customer=c.customer AND e.case_id=c.case_id
                AND e.version=(SELECT max(v.version) FROM orchestration_events v WHERE v.tenant=c.tenant AND v.customer=c.customer AND v.case_id=c.case_id)
                WHERE c.tenant=? AND c.id>? AND (? IS NULL OR c.customer=?) AND (? IS NULL OR c.case_id=?)
                AND (? IS NULL OR json_extract(e.payload,'$.state')=?) ORDER BY c.id LIMIT ?''',
                (tenant,after,customer,customer,case_id,case_id,state,state,limit+1)).fetchall()
            items=[]
            for raw in rows[:limit]:
                case=self._case(db,tenant,raw['customer'],raw['case_id']);history=self._history(db,case);last=history[-1] if history else None
                items.append({'registry_id':case['id'],'tenant':tenant,'customer':case['customer'],'case_id':case['case_id'],
                              'version':last['version'] if last else 0,'updated_at':last['created_at'] if last else case['created_at'],
                              'state':last['payload']['state'] if last else 'awaiting_data','blockers':last['payload']['blockers'] if last else ['not_processed'],
                              'refs':last['payload']['refs'] if last else {},'operational_state':'inactive','real_recovery_demonstrated':False,
                              'core_transition_authorized':False})
            return {'tenant':tenant,'items':items,'next_after':rows[limit-1]['id'] if len(rows)>limit else None,
                    'operational_state':'inactive','external_execution':'blocked'}

    def _sources(self,user,case,as_of):
        with self.store.transaction() as db:
            t,c=case['tenant'],case['customer'];self._access(db,user,t,write=True)
            configs=self.detection._scope(db,user,t,write=True);criteria=self.detection._criteria(db,t,configs)
            records=self.evidence._records(db,t,c,configs)
            head={'config_version':len(configs),'criteria_version':len(criteria),'through':max((r['id'] for r in records),default=0),
                  'eligible_ids':[r['id'] for r in records if r['occurred_at']<=as_of]}
            return configs,criteria,records,head

    def process_case(self,user,tenant,customer,case_id,as_of,*,ai_adapter=None,execution_adapter=None,allow_test_dispatch=False,max_steps=8,deadline=None):
        self.evidence._runtime();as_of=utc(as_of)
        if as_of>utc(now()): raise ValueError('Future orchestration cutoff refused.')
        if type(max_steps) is not int or not 1<=max_steps<=12 or type(allow_test_dispatch) is not bool: raise ValueError('Invalid processing limits.')
        with self.store.transaction() as db:
            self._access(db,user,tenant,write=True);self._case(db,tenant,customer,case_id)
        adapter=ai_adapter or AIAdapter()
        for _ in range(max_steps):
            if deadline is not None and monotonic()>=deadline: break
            view=self.history(user,tenant,customer,case_id);case=view['case'];events=view['history'];last=events[-1]['payload'] if events else {'refs':{},'basis':{}}
            refs=strict_json(canonical(last['refs']).encode('utf-8'));basis=strict_json(canonical(last['basis']).encode('utf-8'));expected=len(events)
            def record(state,*blockers): return self._record(user,case,expected,state,list(blockers),refs,basis)
            scope=(user,tenant,customer)
            # A reserved C05 attempt permanently freezes the pre-dispatch lineage.
            c05=None
            if refs.get('c05'):
                try: c05=self.execution.get(*scope,refs['c05']['execution_id'])
                except Problem as e:
                    if e.status!=404: raise
            if c05 and c05['attempts']:
                refs['c05'].update(intent_hash=c05['intent']['record_hash'],approval_hash=c05['approvals']['record_hash'],
                                   attempt_hash=c05['attempts']['record_hash'],result_hash=c05['results']['record_hash'] if c05['results'] else None,state=c05['state'])
                recovery=self.recovery.history(*scope,refs['c05']['execution_id'])
                if not recovery['plans']:
                    record('needs_review' if c05['state'] in ('uncertain','uncertain_pending','failed_no_effect') else 'awaiting_verification',
                           'execution_uncertain_or_failed' if c05['state'] in ('uncertain','uncertain_pending','failed_no_effect') else 'verification_plan_missing');break
                plan=recovery['plans'][-1]
                _,_,records,head=self._sources(user,case,as_of)
                maturity=[w['end']<=as_of for check in plan['payload']['document']['checks'] for w in (check['before'],check['after'])]
                c06_basis=digest({'heads':head,'plan_hash':plan['record_hash'],'result_hash':refs['c05']['result_hash'],
                                  'windows_complete':maturity,'receipt_visible':bool(c05['results'] and utc(c05['results']['payload']['created_at'])<=as_of)})
                old=refs.get('c06')
                run=self.recovery.get(*scope,refs['c05']['execution_id'],old['version']) if old and old['basis']==c06_basis else self.recovery.evaluate(*scope,refs['c05']['execution_id'],plan['version'],as_of)
                a=run['payload']['assessment'];refs['c06']={'version':run['version'],'record_hash':run['record_hash'],'basis':c06_basis,
                  'summary_state':a['summary_state'],'execution_state':a['execution']['state'],'operational_state':a['operational_recovery']['state'],'value_state':a['value_recovery']['state']}
                if a['summary_state'] in ('execution_uncertain','contradictory'): record('needs_review',a['summary_state'])
                elif a['summary_state']=='insufficient': record('awaiting_verification','post_evidence_or_coverage_missing')
                else: record('verification_recorded','synthetic_result_only_no_real_closure')
                break
            configs,criteria,records,head=self._sources(user,case,as_of)
            basis={'source_hash':digest(head),'source_heads':head}
            if not configs or not criteria:
                record('awaiting_data','configuration_or_criteria_missing');break
            if criteria[-1]['config_version']!=len(configs): record('awaiting_data','criteria_configuration_outdated');break
            if not any(r['config_version']==len(configs) for r in records): record('awaiting_data','evidence_missing');break
            previous=refs.get('c02')
            if previous and previous['basis']==digest(head): c02=self.detection.get(*scope,previous['id'])
            else:
                c02=self.detection.evaluate(*scope,criteria[-1]['version'],as_of)
                refs={'c02':{'id':c02['id'],'record_hash':c02['record_hash'],'basis':digest(head)}}
                states={c02['payload'][k]['state'] for k in ('operational_deterioration','value_loss')}
                basis['as_of']=c02['payload']['as_of']
                if 'contradictory' in states: record('needs_review','contradictory_detection');break
                if 'demonstrated' not in states:
                    record('awaiting_data' if 'insufficient' in states else 'stable','insufficient_detection' if 'insufficient' in states else 'no_deterioration_demonstrated');break
                record('awaiting_investigation','c02_recorded');continue
            basis['as_of']=c02['payload']['as_of']
            states={c02['payload'][k]['state'] for k in ('operational_deterioration','value_loss')}
            if 'contradictory' in states: record('needs_review','contradictory_detection');break
            if 'demonstrated' not in states:
                record('awaiting_data' if 'insufficient' in states else 'stable','insufficient_detection' if 'insufficient' in states else 'no_deterioration_demonstrated');break
            try: c03=self.investigation.get(*scope,c02['id'])
            except Problem as e:
                if e.status!=404: raise
                record('awaiting_investigation','operator_investigation_missing');break
            refs['c03']={'version':c03['version'],'record_hash':c03['record_hash']}
            request_id=key('c04',case['record_hash'],c02['record_hash'],c03['record_hash'])
            # Save the deterministic binding before provider I/O so interruption is resumable.
            if refs.get('c04',{}).get('request_id')!=request_id:
                refs.pop('c05',None);refs.pop('c06',None);refs['c04']={'request_id':request_id}
                record('awaiting_ai','proposal_not_recorded');continue
            try: proposal=self.proposals.get(*scope,request_id)
            except Problem as e:
                if e.status==409: record('awaiting_ai','inference_pending_or_interrupted_no_retry');break
                if e.status!=404: raise
                if adapter.descriptor().get('inference_kind')=='unavailable': record('awaiting_ai','authorized_ai_not_configured');break
                proposal=self.proposals.propose(*scope,c02['id'],c03['version'],request_id,adapter)
            decision=proposal['result']['payload'];refs['c04'].update(record_hash=proposal['result']['record_hash'],status=decision['status'],inference_kind=proposal['result']['receipt']['inference_kind'])
            if decision['status'] in ('unavailable','human_review','refused'):
                record('awaiting_ai' if decision['status']=='unavailable' else 'needs_review','ai_unavailable_no_automatic_retry' if decision['status']=='unavailable' else 'proposal_requires_review');break
            if decision['status']=='no_action': record('no_action','validated_recommendation_no_action');break
            if decision['status']!='proposal_validated': record('needs_review','proposal_not_validated');break
            execution_id=key('c05',case['record_hash'],proposal['result']['record_hash'])
            if refs.get('c05',{}).get('execution_id')!=execution_id:
                refs['c05']={'execution_id':execution_id};record('awaiting_execution','intent_not_prepared');continue
            try: c05=self.execution.get(*scope,execution_id)
            except Problem as e:
                if e.status!=404: raise
                if execution_adapter is None: record('awaiting_execution','connector_unavailable');break
                try: self.execution.prepare(*scope,request_id,execution_id,execution_adapter)
                except Problem as e:
                    if e.status not in (403,409,503): raise
                    record('awaiting_execution','current_execution_prerequisites_not_met');break
                c05=self.execution.get(*scope,execution_id)
            refs['c05'].update(intent_hash=c05['intent']['record_hash'],state=c05['state'])
            if not c05['approvals']: record('awaiting_approval','explicit_human_approval_required');break
            refs['c05']['approval_hash']=c05['approvals']['record_hash']
            if not allow_test_dispatch: record('awaiting_execution','test_dispatch_not_enabled');break
            if execution_adapter is None: record('awaiting_execution','connector_unavailable');break
            try:
                with self.store.transaction() as db:
                    self._access(db,user,tenant,write=True);self.execution._approval(db,c05['approvals'],c05['intent'])
            except Problem:
                record('needs_review','human_approval_invalid_or_expired');break
            if (last.get('state')=='needs_review' and 'execution_revalidation_refused' in last.get('blockers',[])
                    and last['refs'].get('c05',{}).get('execution_id')==execution_id
                    and last['basis'].get('source_hash')==basis['source_hash']):
                record('needs_review','execution_revalidation_refused');break
            try: self.execution.execute(*scope,execution_id,execution_adapter)
            except Problem as e:
                if e.status not in (403,409,503): raise
                record('needs_review','execution_revalidation_refused');break
            # Re-read on the next bounded step, including uncertain outcomes.
            record('awaiting_verification','c05_dispatch_returned');continue
        return self.history(user,tenant,customer,case_id)

    def process_batch(self,user,tenant,as_of,*,after=0,limit=25,max_steps=8,budget_seconds=30,ai_adapter=None,execution_adapters=None,allow_test_dispatch=False):
        if (type(limit) is not int or not 1<=limit<=25 or type(budget_seconds) is not int or not 1<=budget_seconds<=60
                or type(max_steps) is not int or not 1<=max_steps<=12 or type(allow_test_dispatch) is not bool): raise ValueError('Invalid batch limits.')
        as_of=utc(as_of)
        if as_of>utc(now()): raise ValueError('Future orchestration cutoff refused.')
        # Authorization precedes even an empty batch.
        self.evidence._runtime()
        with self.store.transaction() as db: self._access(db,user,tenant,write=True)
        page=self.query(user,tenant,after=after,limit=limit);results=[];cursor=after;deadline=monotonic()+budget_seconds
        for item in page['items']:
            if monotonic()>=deadline: break
            try:
                view=self.process_case(user,tenant,item['customer'],item['case_id'],as_of,ai_adapter=ai_adapter,
                    execution_adapter=(execution_adapters or {}).get((tenant,item['customer'])),allow_test_dispatch=allow_test_dispatch,max_steps=max_steps,deadline=deadline)
                last=view['history'][-1];results.append({'customer':item['customer'],'case_id':item['case_id'],'version':last['version'],'state':last['payload']['state'],'error':None})
            except Exception:
                failure_state=None;failure_version=None
                try:
                    failed=self.history(user,tenant,item['customer'],item['case_id']);history=failed['history'];last=history[-1]['payload']
                    self._record(user,failed['case'],len(history),'needs_review',['case_processing_refused'],last['refs'],last['basis'])
                    latest=self.history(user,tenant,item['customer'],item['case_id'])['history'][-1]
                    failure_state=latest['payload']['state'];failure_version=latest['version']
                except Exception: pass  # Revocation/integrity failure must never be bypassed to record status.
                results.append({'customer':item['customer'],'case_id':item['case_id'],'version':failure_version,'state':failure_state,'error':'case_processing_refused'})
            cursor=item['registry_id']
        return {'tenant':tenant,'items':results,'next_after':cursor if len(results)<len(page['items']) or page['next_after'] is not None else None,
                'processed':len(results),'operational_state':'inactive','external_execution':'blocked'}


def main():
    parser=argparse.ArgumentParser(description='Inactive bounded M06–M12 coordinator. No default AI or execution adapters.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    for command in ('register','history','list','run-batch'):
        child=sub.add_parser(command)
        for name in ('db','user','tenant'): child.add_argument('--'+name,required=True)
        if command in ('register','history'):
            child.add_argument('--customer',required=True);child.add_argument('--case-id',required=True)
        if command in ('list','run-batch'):
            child.add_argument('--after',type=int,default=0);child.add_argument('--limit',type=int,default=25)
        if command=='run-batch':
            child.add_argument('--as-of',required=True);child.add_argument('--ai-config');child.add_argument('--budget-seconds',type=int,default=30)
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        if args.command=='init': output=install(store)
        else:
            repo=Orchestrator(store);scope=(args.user,args.tenant)
            if args.command=='register': output=repo.register(*scope,args.customer,args.case_id)
            elif args.command=='history': output=repo.history(*scope,args.customer,args.case_id)
            elif args.command=='list': output=repo.query(*scope,after=args.after,limit=args.limit)
            else: output=repo.process_batch(*scope,args.as_of,after=args.after,limit=args.limit,budget_seconds=args.budget_seconds,ai_adapter=configured_adapter(args.ai_config))
    except (Problem,ValueError,OSError,sqlite3.Error,RecursionError,OverflowError): parser.exit(1,'{"status":"error","code":"orchestration_refused"}\n')
    print(canonical(output))


if __name__=='__main__': main()
