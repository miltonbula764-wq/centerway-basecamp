"""One local CLI over M06–M14. Synthetic lab only; never opens production/pilot."""
import argparse
from contextlib import closing,contextmanager
from datetime import datetime,timedelta,timezone
import fcntl
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from . import integrations,evidence,detection,investigation,ai_proposals,controlled_execution,recovery,orchestration
from .ai_adapter import AIAdapter,Completion,configured_adapter
from .core import Core,Problem
from .http_contract import strict_json
from .integrations import canonical,digest
from .production import password_hash
from .store import Store,now
from .synthetic_service import SyntheticService,install as install_service

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=('complete','insufficient','contradictory','investigation_pending','ai_unavailable','approval_pending','uncertain','operation_only')
TABLES={
 'journey_metadata':"CREATE TABLE journey_metadata(marker TEXT PRIMARY KEY, payload TEXT NOT NULL, record_hash TEXT NOT NULL)",
 'journey_events':"CREATE TABLE journey_events(id INTEGER PRIMARY KEY, operation TEXT NOT NULL, participation TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, previous_hash TEXT, record_hash TEXT NOT NULL)",
}
GUARDS={f'journey_immutable_{t}_{op}':f"CREATE TRIGGER journey_immutable_{t}_{op} BEFORE {op} ON {t} BEGIN SELECT RAISE(ABORT,'append_only'); END" for t in TABLES for op in ('UPDATE','DELETE')}


def load(path):
    with open(path,'rb') as stream: raw=stream.read(262145)
    if len(raw)>262144: raise ValueError('Input exceeds 256 KiB.')
    return strict_json(raw)


def private_json(path,value):
    with open(path,'x',encoding='utf-8') as out: json.dump(value,out,ensure_ascii=False,indent=2);out.write('\n')
    Path(path).chmod(0o600)


def stamp(value): return evidence.utc(value.isoformat())


def initialize(workspace,scenario):
    workspace=Path(workspace).absolute()
    if ROOT.parent in workspace.resolve().parents or workspace.exists(): raise ValueError('Choose a new private workspace outside the checkout.')
    workspace.mkdir(mode=0o700,parents=True);(workspace/'inputs').mkdir(mode=0o700)
    store=Store(workspace/'centerway.sqlite3',seed_demo=False,seed_accounts=False);Path(store.path).chmod(0o600)
    password=secrets.token_urlsafe(32)
    with store.transaction() as db:
        db.execute('INSERT INTO users VALUES (?,?)',('operator',password_hash(password)))
        db.execute('INSERT INTO memberships VALUES (?,?,?)',('operator','collaboration','operator'))
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
    anchor=datetime.now(timezone.utc).replace(microsecond=0)-timedelta(seconds=1)
    metadata={'scenario':scenario,'tenant':'collaboration','customer':'fictional-account','case_id':'observed-cycle','operator':'operator',
              'as_of':stamp(anchor),'classification':'synthetic','real_recovery_demonstrated':False,
              'usage_step':0 if scenario=='operation_only' else 2,'fault':'uncertain_after_effect' if scenario=='uncertain' else 'none'}
    record={'marker':'observable-synthetic-v1','payload':canonical(metadata)};record['record_hash']=digest(record)
    with store.transaction() as db: db.execute('INSERT INTO journey_metadata VALUES (?,?,?)',tuple(record.values()))
    for module in (integrations,evidence,detection,investigation,ai_proposals,controlled_execution,recovery,orchestration): module.install(store)
    config=load(ROOT/'examples/c04/collaboration-config.json')
    criteria=load(ROOT/'examples/detection/collaboration-criteria.json')
    for criterion in criteria['criteria']: criterion['window_seconds']=2;criterion['cadence_seconds']=1
    originals=[load(ROOT/'examples/detection/collaboration-evidence.json'),load(ROOT/'examples/c04/collaboration-context.json')]
    base=datetime(2026,1,1,0,4,tzinfo=timezone.utc)
    def mapped(value): return stamp(anchor+timedelta(seconds=(datetime.fromisoformat(value.replace('Z','+00:00'))-base).total_seconds()/60))
    records=[]
    for batch in originals:
        for row in batch['records']:
            row['occurred_at']=mapped(row['occurred_at'])
            if row['period']: row['period']={k:mapped(v) for k,v in row['period'].items()}
            records.append(row)
    if scenario=='insufficient': records=records[:1]
    if scenario=='contradictory':
        row=next(r for r in records if r['kind']=='metric' and r['occurred_at']==stamp(anchor));row=json.loads(canonical(row))
        row['external_id']='explicit-contradictory-synthetic-reading';row['payload']['value']=0;records.append(row)
    declaration=load(ROOT/'examples/investigation/collaboration-declaration.json')
    for name,body in [('configuration',config),('criteria',criteria),('initial-evidence',{'tenant':metadata['tenant'],'customer':metadata['customer'],'config_version':1,'records':records}),('investigation',declaration)]:
        private_json(workspace/'inputs'/(name+'.json'),body)
    integrations.IntegrationRepository(store).append('operator',metadata['tenant'],config,0)
    detection.DetectionRepository(store).append_criteria('operator',metadata['tenant'],criteria,0)
    private_json(workspace/'credentials.json',{'user':'operator','password':password})
    install_service(workspace/'synthetic.sqlite3',metadata['tenant'],metadata['customer'],config['capabilities'][0]['id'],metadata['usage_step'],metadata['fault'])
    lab=Journey(workspace);lab.event('initialize','human_supplied_test_profile',{'profile':metadata,'input_hashes':{p.name:digest(load(p)) for p in sorted((workspace/'inputs').glob('*.json'))}})
    return {'workspace':str(workspace),'scenario':scenario,'classification':'synthetic_test_only','next':'login; ingest; advance; inspect','credentials':'private file credentials.json; never include it in a report'}


class SuppliedFixture(AIAdapter):
    """Explicit test input, never selected by advance or configured_adapter."""
    def __init__(self,document): self.document=canonical(document)
    def descriptor(self): return {'protocol':'supplied-test-fixture','requested_model':'explicit-fixture-not-ai','inference_kind':'test_fixture'}
    def generate(self,context): return Completion(self.document,'explicit-fixture-not-ai','supplied-fixture')


class Journey:
    def __init__(self,workspace):
        self.root=Path(workspace).resolve(strict=True)
        if self.root.stat().st_mode & 0o077 or ROOT.parent in self.root.parents: raise ValueError('Private workspace outside checkout required.')
        self.store=Store.open_existing(self.root/'centerway.sqlite3')
        with closing(self.store.connect()) as db:
            names={r[0] for r in db.execute('SELECT name FROM sqlite_master')}
            if names & {'production_metadata','preview_metadata','pilot_metadata'}: raise ValueError('Not a standalone synthetic workspace; pilot/production never bypassed.')
            schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'journey_*'")}
            if any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS}.items()): raise ValueError('Journey integrity unavailable.')
            rows=db.execute('SELECT * FROM journey_metadata').fetchall()
            if len(rows)!=1: raise ValueError('Explicit synthetic marker required.')
            row=dict(rows[0]);claimed=row.pop('record_hash')
            if digest(row)!=claimed or row['marker']!='observable-synthetic-v1': raise ValueError('Invalid synthetic provenance.')
            self.meta=strict_json(row['payload'].encode())
        self.orch=orchestration.Orchestrator(self.store)
        if self.orch.execution.mode!='sandbox' or self.meta['classification']!='synthetic': raise ValueError('Synthetic sandbox only.')
        self.service=SyntheticService(self.root/'synthetic.sqlite3')
        if any(self.service.metadata[k]!=self.meta[k] for k in ('tenant','customer','usage_step','fault')): raise ValueError('Service scope/profile mismatch.')
        self.scope=(self.meta['operator'],self.meta['tenant'],self.meta['customer'])
    @contextmanager
    def lock(self):
        with open(self.root/'command.lock','a') as stream:
            try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise Problem(409,'Outro comando está em execução; consultar o relatório.')
            try: yield
            finally: fcntl.flock(stream,fcntl.LOCK_UN)
    def event(self,operation,participation,payload):
        with self.store.transaction() as db:
            old=db.execute('SELECT record_hash FROM journey_events ORDER BY id DESC LIMIT 1').fetchone()
            row={'id':db.execute('SELECT coalesce(max(id),0)+1 FROM journey_events').fetchone()[0],'operation':operation,'participation':participation,
                 'payload':canonical(payload),'actor':self.scope[0],'created_at':now(),'previous_hash':old[0] if old else None}
            row['record_hash']=digest(row);db.execute('INSERT INTO journey_events VALUES (?,?,?,?,?,?,?,?)',tuple(row.values()))
        return row
    def login(self,credentials_file=None):
        if credentials_file:
            path=Path(credentials_file).resolve(strict=True)
            if path.stat().st_mode & 0o077 or ROOT.parent in path.parents: raise ValueError('Private credentials required outside checkout.')
            credentials=load(path);user,password=credentials['user'],credentials['password']
        else: user=self.scope[0];password=getpass.getpass('Palavra-passe privada do operador: ')
        with self.store.transaction() as db:
            row=db.execute('SELECT password_hash FROM users WHERE id=?',(user,)).fetchone()
            salt,expected=row['password_hash'].split(':') if row else ('unknown','invalid')
            actual=hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
            if user!=self.scope[0] or not row or not hmac.compare_digest(actual,expected): raise Problem(401,'Credenciais recusadas.')
            token=secrets.token_urlsafe(32);expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(token,user,expires))
        path=self.root/'session.json'
        # Replace only this private session selector, never history/engine state.
        temporary=self.root/('session-'+secrets.token_hex(8)+'.tmp');private_json(temporary,{'token':token});temporary.replace(path)
        self.event('login','human_session',{'user':user,'expires_at':expires});return {'status':'authenticated','user':user,'expires_at':expires}
    def session(self):
        path=self.root/'session.json'
        if not path.exists() or path.stat().st_mode & 0o077: raise Problem(401,'Login local necessário.')
        token=load(path)['token']
        with self.store.transaction() as db:
            Core(self.store).authorize(db,self.scope[0],self.scope[1],write=True);self.orch.execution._session(db,self.scope[0],token)
        return token
    def _history(self): return self.orch.history(*self.scope,self.meta['case_id'])
    def latest(self): return self._history()['history'][-1]['payload']
    def ingest(self,file):
        self.session();body=load(file)
        if (body.get('tenant'),body.get('customer'))!=self.scope[1:]: raise Problem(403,'Entrada de outro escopo recusada.')
        result=self.orch.evidence.ingest(self.scope[0],body);self.event('M07_ingest','human_supplied_synthetic_evidence',{'input_hash':digest(body),'result':result});return result
    def advance(self,ai_config=None,consent=False,as_of=None):
        self.session()
        if ai_config and not consent: raise Problem(403,'Configuração de IA exige consentimento explícito para estes dados sintéticos.')
        adapter=configured_adapter(ai_config) if ai_config else AIAdapter()
        self.orch.register(*self.scope,self.meta['case_id'])
        cutoff=self.meta['as_of']
        if self._history()['history'][-1]['payload']['refs'].get('c05',{}).get('attempt_hash'):
            cutoff=now();view=self.intent();history=self.orch.recovery.history(*self.scope,view['intent']['execution_id'])
            if history['plans']:
                end=history['plans'][-1]['payload']['document']['checks'][0]['after']['end']
                if evidence.utc(cutoff)>=evidence.utc(end): cutoff=end
        if as_of is not None: cutoff=as_of
        view=self.orch.process_case(*self.scope,self.meta['case_id'],cutoff,ai_adapter=adapter,execution_adapter=self.service,allow_test_dispatch=False)
        result=view['history'][-1];self.event('orchestrator_advance','automatic_bounded_processing',{'checkpoint':result,'ai_kind':adapter.descriptor()['inference_kind'],'external_execution':'blocked'});return result
    def investigate(self,file):
        self.session();refs=self.latest()['refs'];run=refs.get('c02',{}).get('id')
        if not run: raise Problem(409,'Falta C02; não se fabrica investigação.')
        body=load(file)
        if (body.get('tenant'),body.get('customer'),body.get('c02_run_id'))!=(*self.scope[1:],run): raise Problem(409,'Documento exige escopo e C02 exatos; consultar inspect.')
        with self.store.transaction() as db:
            c02,config,records=self.orch.investigation._context(db,*self.scope,run)
            history=self.orch.investigation._history(db,*self.scope[1:],c02,config,records)
        if history and history[-1]['declaration']==body: result=history[-1]
        else: result=self.orch.investigation.append(*self.scope,run,body,len(history))
        self.event('C03_declaration','supplied_document_NOT_autonomous_investigation',{'input_hash':digest(body),'version':result['version'],'record_hash':result['record_hash']});return result
    def fixture(self,acknowledged=False):
        self.session()
        if not acknowledged: raise Problem(403,'Exige --ack-test-fixture; não é inferência de IA.')
        self.advance();refs=self.latest()['refs']
        if not refs.get('c03') or not refs.get('c04'): raise Problem(409,'Falta investigação explícita ou linhagem C04.')
        with self.store.transaction() as db: context=self.orch.proposals._context(db,*self.scope,refs['c02']['id'],refs['c03']['version'])
        # Supplied scenario response, bound to actual engine IDs/hash, never an AI fallback.
        response={'schema_version':1,'context_hash':context['context_hash'],
            'hypothesis_reviews':[{'hypothesis_id':h['id'],'disposition':'retain_unconfirmed','support_refs':h['support_refs'],'contrary_refs':h['contrary_refs']} for h in context['investigation']['hypotheses']],
            'impediment_refs':[r['requirement_id'] for r in context['investigation']['supported_impediments']],
            'contradiction_refs':list(range(len(context['investigation']['contradictions']))),'missing_information_refs':list(range(len(context['investigation']['missing_information']))),
            'analysis_limitation_refs':list(range(len(context['investigation']['analysis_limitations']))),
            'recommendation':{'kind':'action_proposal','capability_id':'reopen-delivery-queue','reason_code':'catalogue_match',
                'evidence_refs':[{'evidence_id':13,'field':'paused'}],'criterion_refs':['operational-degradation','value-loss']}}
        path=self.root/'inputs'/'explicit-test-response.json'
        if not path.exists(): private_json(path,response)
        elif load(path)!=response: raise Problem(409,'Fixture já ligada a outra linhagem; histórico preservado.')
        result=self.orch.proposals.propose(*self.scope,refs['c02']['id'],refs['c03']['version'],refs['c04']['request_id'],SuppliedFixture(load(path)))
        self.event('C04_supplied_fixture','test_fixture_NOT_AI',{'input_hash':digest(response),'result':result['result']})
        self.advance();return result['result']
    def intent(self):
        refs=self.latest()['refs']
        if not refs.get('c05'): raise Problem(409,'Nenhuma intenção C05; sem proposta validada não há avanço.')
        return self.orch.execution.get(*self.scope,refs['c05']['execution_id'])
    def approve(self,intent_hash,confirmation):
        token=self.session();view=self.intent()
        if confirmation!='APROVO '+intent_hash: raise Problem(403,'Confirmação humana explícita do hash concreto necessária.')
        result=self.orch.execution.approve(*self.scope,view['intent']['execution_id'],intent_hash,human_confirmed=True,session_token=token,adapter=self.service)
        self.event('C05_approve','explicit_human_authorization',{'intent_hash':intent_hash,'approval':result});return result
    def execute(self):
        self.session();view=self.intent()
        result=self.orch.execution.execute(*self.scope,view['intent']['execution_id'],self.service)
        self.event('C05_execute','automatic_synthetic_effect_after_authorization',{'execution_id':view['intent']['execution_id'],'state':result['state'],'result_hash':result['results']['record_hash'] if result['results'] else None})
        self.advance();return result
    def plan(self):
        self.session();view=self.intent()
        if not view['attempts']: raise Problem(409,'Plano C06 exige tentativa C05 real no ensaio.')
        history=self.orch.recovery.history(*self.scope,view['intent']['execution_id'])
        if history['plans'] and not history['runs']: return history['plans'][-1]
        anchor=datetime.fromisoformat(self.meta['as_of'].replace('Z','+00:00'))
        start=datetime.now(timezone.utc).replace(microsecond=0)+timedelta(seconds=1)
        document={'schema_version':1,'tenant':self.scope[1],'customer':self.scope[2],'execution_id':view['intent']['execution_id'],
            'config_version':1,'capability_id':self.service.metadata['capability'],'provenance':{'source_ref':'synthetic:local-explicit-verification-windows','supplied_by':self.scope[0],'recorded_at':now()},'checks':[]}
        for dimension,sampling,width,aggregation in [('operational','point',1,'all'),('value','period',2,'mean')]:
            document['checks'].append({'dimension':dimension,'criterion_index':0,'sampling':sampling,'aggregation':aggregation,
                'method':'transition_to_target','coverage':'aligned_complete','before':{'start':stamp(anchor-timedelta(seconds=width)),'end':stamp(anchor),'cadence_seconds':1},
                'after':{'start':stamp(start),'end':stamp(start+timedelta(seconds=2)),'cadence_seconds':1}})
        result=self.orch.recovery.append_plan(*self.scope,view['intent']['execution_id'],document,len(history['plans']))
        self.event('C06_plan','human_supplied_synthetic_verification_profile',{'plan':result});return result
    def collect(self):
        self.session();view=self.intent();history=self.orch.recovery.history(*self.scope,view['intent']['execution_id'])
        if not history['plans']: raise Problem(409,'Registar plano C06 explícito antes de recolher.')
        plan=history['plans'][-1];start=datetime.fromisoformat(plan['payload']['document']['checks'][0]['after']['start'].replace('Z','+00:00'))
        results=[]
        for index in (1,2):
            point=start+timedelta(seconds=index);key='sample-'+digest({'plan':plan['record_hash'],'point':stamp(point)})[:48]
            prior=next((r for r in self.service.inspect()['samples'] if r['key']==key),None)
            if not prior:
                delay=(point-datetime.now(timezone.utc)).total_seconds()
                if delay < -2: raise Problem(409,'Janela de recolha perdida; não se inventam amostras passadas. Criar nova revisão do plano após verificar o estado.')
                if delay>0: time.sleep(delay)
            sample=prior or self.service.sample(key,stamp(point))
            facts=[]
            for definition,payload,period in [('operation-state',{'paused':bool(sample['paused'])},None),('value-snapshot',{'outcome_count':sample['outcome_count']},{'start':stamp(point-timedelta(seconds=1)),'end':stamp(point)})]:
                config=self.orch.evidence.integrations.get(self.scope[0],self.scope[1],1)['config'];d=next(d for d in config['evidence'] if d['id']==definition)
                facts.append({'external_id':key+'-'+definition,'kind':'evidence','definition_id':definition,'source_ref':d['source_ref'],'occurred_at':stamp(point),'period':period,'payload':payload})
            result=self.orch.evidence.ingest(self.scope[0],{'tenant':self.scope[1],'customer':self.scope[2],'config_version':1,'records':facts})
            self.event('M07_post_collection','synthetic_observation_not_real_customer',{'source_sample':sample,'result':result});results.append(result)
        return results
    def verify(self):
        self.session();view=self.intent();history=self.orch.recovery.history(*self.scope,view['intent']['execution_id'])
        if not history['plans']: raise Problem(409,'Plano C06 explícito necessário.')
        cutoff=now();end=history['plans'][-1]['payload']['document']['checks'][0]['after']['end']
        if evidence.utc(cutoff)>=evidence.utc(end): cutoff=end
        result=self.orch.recovery.evaluate(*self.scope,view['intent']['execution_id'],history['plans'][-1]['version'],cutoff)
        self.event('C06_evaluate','automatic_deterministic_verification',{'version':result['version'],'record_hash':result['record_hash'],'assessment':result['payload']['assessment']})
        self.advance(as_of=cutoff);return result
    def resume(self):
        self.session()
        try: view=self.intent()
        except Problem as error:
            if error.status!=409: raise
            self.advance();return self.inspect()
        if not view['approvals']: return self.inspect()
        if not view['attempts']: self.execute()
        view=self.intent();history=self.orch.recovery.history(*self.scope,view['intent']['execution_id'])
        if not history['plans']: self.plan()
        # No re-execution, no automatic renewal of a lost collection window.
        self.collect();self.verify();return self.inspect()
    def report(self):
        self.session();timeline=[];engines={};user,tenant,customer=self.scope
        def add(stage,participation,created,source):
            timeline.append({'recorded_at':created,'stage':stage,'participation':participation,'source':source})
        with self.store.transaction() as db:
            configs=self.orch.evidence.integrations._chain(db,tenant);criteria=self.orch.detection._criteria(db,tenant,configs)
            records=self.orch.evidence._records(db,tenant,customer,configs)
            engines.update(configuration=configs,criteria=criteria,evidence=records,c02=[],c03=[],c04=[],c05=[],c06=[])
            for row in configs: add('M06','supplied_synthetic_contract',row['created_at'],row)
            for row in criteria: add('C02 criteria','supplied_synthetic_criteria',row['created_at'],row)
            for row in records: add('M07','synthetic_source_claim',row['received_at'],row)
            for row in db.execute('SELECT id FROM detection_runs WHERE tenant=? AND customer=? ORDER BY id',(tenant,customer)):
                run=self.orch.detection._read_run(db,user,tenant,customer,dict(db.execute('SELECT * FROM detection_runs WHERE id=? AND tenant=? AND customer=?',(row['id'],tenant,customer)).fetchone()),configs,criteria,True)
                engines['c02'].append(run);add('C02','automatic_deterministic_assessment',run['created_at'],run)
                c02,config,evidence_records=self.orch.investigation._context(db,*self.scope,row['id'])
                for revision in self.orch.investigation._history(db,tenant,customer,c02,config,evidence_records):
                    engines['c03'].append(revision);add('C03','supplied_document_NOT_autonomous',revision['created_at'],revision)
            for row in db.execute('SELECT request_id,actor,created_at,record_hash FROM c04_requests WHERE tenant=? AND customer=? ORDER BY created_at',(tenant,customer)):
                add('C04 request','explicit_fixture_or_authorized_provider_request',row['created_at'],dict(row))
                try: proposal=self.orch.proposals._read(db,*self.scope,row['request_id'])
                except Problem as e:
                    if e.status!=409: raise
                    engines['c04'].append({'request_id':row['request_id'],'status':'pending_no_automatic_retry'});continue
                source={'request':{k:proposal['request'][k] for k in ('request_id','c02_run_id','c03_version','context_hash','actor','created_at','record_hash')},'result':proposal['result']}
                engines['c04'].append(source);kind=source['result']['receipt']['inference_kind']
                add('C04 result','test_fixture_NOT_AI' if kind=='test_fixture' else 'authorized_provider' if kind=='configured_provider' else 'AI_UNAVAILABLE',source['result']['created_at'],source)
            for row in db.execute('SELECT execution_id FROM c05_intents WHERE tenant=? AND customer=?',(tenant,customer)):
                view=self.orch.execution._view(db,*self.scope,row['execution_id']);engines['c05'].append(view)
                for entry in view['audit']: add('C05 '+entry['payload']['operation'],'explicit_human_authorization' if entry['payload']['operation']=='approve' else 'automatic_controlled_synthetic_execution',entry['payload']['created_at'],entry)
            previous=None;events=[]
            for raw in db.execute('SELECT * FROM journey_events ORDER BY id'):
                entry=dict(raw);claimed=entry.pop('record_hash')
                if digest(entry)!=claimed or entry['previous_hash']!=previous: raise ValueError('Journey audit chain unavailable.')
                entry['record_hash']=claimed;entry['payload']=strict_json(entry['payload'].encode());events.append(entry);previous=claimed
                add('command '+entry['operation'],entry['participation'],entry['created_at'],entry)
            engines['commands']=events
        for view in engines['c05']:
            if view['attempts']:
                history=self.orch.recovery.history(*self.scope,view['intent']['execution_id']);engines['c06'].append(history)
                for row in history['plans']: add('C06 plan','explicit_declared_windows_and_targets',row['created_at'],row)
                for row in history['runs']: add('C06 assessment','automatic_deterministic_verification',row['created_at'],row)
        try: case=self._history()
        except Problem as e:
            if e.status!=404: raise
            case=None
        if case:
            for row in case['history']: add('orchestrator checkpoint','automatic_state_and_blockers',row['created_at'],row)
            if case['opening']: add('M14 opening','explicit_local_case_registration',case['opening']['created_at'],case['opening'])
            if case['closure']: add('M14 closure','explicit_human_lifecycle_decision',case['closure']['created_at'],case['closure'])
        service=self.service.inspect()
        for row in service['effects']: add('synthetic persisted effect','synthetic_only_NOT_REAL',row['created_at'],row)
        for row in service['samples']: add('synthetic observed sample','synthetic_only_NOT_REAL',row['observed_at'],row)
        timeline.sort(key=lambda row:(row['recorded_at'],row['stage']))
        summary={'scenario':self.meta['scenario'],'classification':'synthetic_test_only','case_state':case['history'][-1]['payload']['state'] if case and case['history'] else 'not_started',
                 'blockers':case['history'][-1]['payload']['blockers'] if case and case['history'] else ['not_started'],
                 'ai':[{k:r['result']['receipt'][k] for k in ('inference_kind','reported_model','failure')} if 'result' in r else r for r in engines['c04']],
                 'effects':len(service['effects']),'samples':len(service['samples']),'c06':[r['payload']['assessment'] for h in engines['c06'] for r in h['runs']],
                 'case_closed':bool(case and case['closure']),'real_recovery_demonstrated':False,'external_execution':'blocked'}
        return {'report_version':1,'generated_at':now(),'environment':self.meta,'summary':summary,'timeline':timeline,'engines':engines,'case':case,'synthetic_service':service,
                'limitations':['No autonomous investigation: C03 requires an operator-supplied document.','No external research or SaaS connector.',
                    'No real AI verified by a supplied test fixture; no configured AI means unavailable.','Only synthetic persisted effects, never real customer/value recovery.',
                    'No automatic resolution, retry or erasure of uncertain executions.','Human approval is an explicit local session assertion, not biometric verification.',
                    'C06 does not close the case; M14 remains explicit.','CLI only; pilot/production/HTTP unchanged. Local row hashes are not external audit signatures.']}
    def inspect(self):
        r=self.report();result={'environment':self.meta,'summary':r['summary']}
        if r['engines']['c05']:
            view=r['engines']['c05'][-1]
            result['intervention']={'execution_id':view['intent']['execution_id'],'intent_hash':view['intent']['record_hash'],
                'state':view['state'],'capability':view['intent']['payload']['binding']['capability'],'current_synthetic_state':r['synthetic_service']['state'],
                'approval_required':'APROVO '+view['intent']['record_hash'] if not view['approvals'] else 'already recorded; no new permission granted by inspection'}
        return result


def markdown(report):
    rows=['# CENTERWAY — execução local observável','', '**SOMENTE ENSAIO SINTÉTICO. Uma fixture C04 não comprova inferência real; efeitos/resultados sintéticos não comprovam execução externa ou recuperação real.**','',
          'Gerado: '+report['generated_at'],'', '## Resultado efetivamente calculado','', '```json',json.dumps(report['summary'],ensure_ascii=False,indent=2),'```','',
          '## Cronologia completa','', 'A ordenação usa o momento de registo; occurred_at/períodos das declarações permanecem nos outputs, sem transformar uma fixture histórica numa observação real.','']
    for i,event in enumerate(report['timeline'],1):
        rows.extend([f"### {i}. {event['recorded_at']} — {event['stage']}",'', 'Participação: '+event['participation'],'', '```json',json.dumps(event['source'],ensure_ascii=False,indent=2),'```',''])
    rows.extend(['## Limitações','']+['- '+line for line in report['limitations']])
    return '\n'.join(rows)+'\n'


def prepare_suite(workspace,acknowledged=False):
    if acknowledged is not True: raise Problem(403,'A preparação técnica exige --ack-test-fixtures; nenhuma inferência real é realizada.')
    root=Path(workspace).absolute()
    if root.exists() or ROOT.parent in root.resolve().parents: raise ValueError('New suite directory outside checkout required.')
    root.mkdir(mode=0o700,parents=True);summaries={}
    for scenario in SCENARIOS:
        directory=root/scenario;initialize(directory,scenario);journey=Journey(directory)
        journey.login(directory/'credentials.json');journey.ingest(directory/'inputs/initial-evidence.json');journey.advance()
        if scenario not in ('insufficient','contradictory','investigation_pending'):
            journey.investigate(directory/'inputs/investigation.json');journey.advance()
        if scenario in ('complete','approval_pending','uncertain','operation_only'): journey.fixture(True)
        summaries[scenario]=journey.inspect()
    private_json(root/'prepared-scenarios.json',summaries)
    return {'status':'prepared_NOT_executed','classification':'synthetic_test_only','scenarios':summaries,
            'approval':'Each concrete intent must be reviewed and explicitly approved; prepare-suite never approves or dispatches.'}


def main():
    parser=argparse.ArgumentParser(description='Observable synthetic-only local M06–M14 journey. Never production/pilot, no GUI.')
    parser.add_argument('--workspace',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    suite=sub.add_parser('prepare-suite');suite.add_argument('--ack-test-fixtures',action='store_true')
    init=sub.add_parser('init');init.add_argument('--scenario',choices=SCENARIOS,required=True)
    login=sub.add_parser('login');login.add_argument('--credentials-file')
    ingest=sub.add_parser('ingest');ingest.add_argument('--file',required=True)
    sub.add_parser('inspect')
    advance=sub.add_parser('advance');advance.add_argument('--ai-config');advance.add_argument('--consent-synthetic-ai',action='store_true')
    investigate=sub.add_parser('investigate');investigate.add_argument('--file',required=True)
    fixture=sub.add_parser('supply-test-proposal');fixture.add_argument('--ack-test-fixture',action='store_true')
    approve=sub.add_parser('approve');approve.add_argument('--intent-hash',required=True);approve.add_argument('--human-confirmation')
    for cmd in ('execute','plan','collect','verify','resume'): sub.add_parser(cmd)
    report=sub.add_parser('report');report.add_argument('--out-dir',required=True)
    args=parser.parse_args()
    try:
        if args.command=='prepare-suite': result=prepare_suite(args.workspace,args.ack_test_fixtures)
        elif args.command=='init': result=initialize(args.workspace,args.scenario)
        else:
            journey=Journey(args.workspace)
            if args.command=='inspect': result=journey.inspect()
            elif args.command=='report':
                data=journey.report();directory=Path(args.out_dir)
                if directory.exists(): raise ValueError('New report directory required; earlier exports are preserved.')
                directory.mkdir(parents=True,mode=0o700);private_json(directory/'engine-output.json',data)
                body=markdown(data);(directory/'chronology.md').write_text(body);(directory/'chronology.md').chmod(0o600)
                manifest={'report_version':1,'classification':'synthetic_test_only','files':{'engine-output.json':hashlib.sha256((directory/'engine-output.json').read_bytes()).hexdigest(),
                          'chronology.md':hashlib.sha256(body.encode()).hexdigest()},'summary':data['summary']}
                private_json(directory/'manifest.json',manifest);result={'report_directory':str(directory),'summary':data['summary']}
            else:
                with journey.lock():
                    journey.event('command_requested','local_request_NOT_authorization',{'command':args.command})
                    try:
                        if args.command=='login': result=journey.login(args.credentials_file)
                        elif args.command=='ingest': result=journey.ingest(args.file)
                        elif args.command=='advance': result=journey.advance(args.ai_config,args.consent_synthetic_ai)
                        elif args.command=='investigate': result=journey.investigate(args.file)
                        elif args.command=='supply-test-proposal': result=journey.fixture(args.ack_test_fixture)
                        elif args.command=='approve':
                            confirmation=args.human_confirmation
                            if confirmation is None:
                                if not os.isatty(0): raise Problem(403,'Aprovação requer confirmação humana explícita; consultar inspect.')
                                confirmation=input('Escreva APROVO seguido do hash revisto: ')
                            result=journey.approve(args.intent_hash,confirmation)
                        else: result=getattr(journey,args.command)()
                    except (Problem,ValueError,OSError,sqlite3.Error,KeyError,TypeError,RecursionError):
                        journey.event('command_failed','refused_or_failed_NOT_success',{'command':args.command,'details':'omitted; consult engine audit/state'})
                        raise
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (Problem,ValueError,OSError,sqlite3.Error,KeyError,TypeError,RecursionError) as error:
        # Never print raw provider/input/credential exceptions.
        status=error.status if isinstance(error,Problem) else 400
        print(canonical({'status':'blocked_or_failed','http_equivalent':status,'message':error.message if isinstance(error,Problem) else 'Local input/runtime refused; no success presumed.'}))
        return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
