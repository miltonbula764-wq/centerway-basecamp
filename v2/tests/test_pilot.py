"""Private pilot contract over real loopback HTTPS; all business inputs are TEST declarations."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import http.cookiejar
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from jsonschema import Draft202012Validator,FormatChecker

from centerway.ai_adapter import AIAdapter
from centerway.core import Problem
from centerway import integrations,evidence,detection,investigation,ai_proposals,controlled_execution,recovery,orchestration,pilot
from centerway.integrations import canonical
from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
from centerway.server import make_server
from centerway.store import Store
import test_evidence as tls_tests
import test_ai_proposals as fixtures

ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'contracts/openapi.json').read_text())


class PilotTests(unittest.TestCase):
    setUpClass=classmethod(tls_tests.EvidenceApiTests.setUpClass.__func__)
    tearDownClass=classmethod(tls_tests.EvidenceApiTests.tearDownClass.__func__)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'production.sqlite3'
        accounts=self.root/'accounts.json';accounts.write_text(canonical({'accounts':[
            {'user':'owner','memberships':[{'tenant':t,'role':'operator'} for t in ('company-a','company-b')]},
            {'user':'viewer','memberships':[{'tenant':'company-a','role':'viewer'}]},
            {'user':'outsider','memberships':[{'tenant':'company-b','role':'operator'}]}]}));accounts.chmod(0o600)
        with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.origin=f'https://127.0.0.1:{port}';secret=self.root/'human.json';provision(self.path,secret,self.origin,accounts)
        self.passwords=json.loads(secret.read_text())['accounts'];self.store=Store.open_existing(self.path)
        for module in (integrations,evidence,detection,investigation,ai_proposals,controlled_execution,recovery,orchestration,pilot): module.install(self.store)
        self.consent(True,False,0);self.ai_file=None;self.start();self.client=self.new_client();self.counter=0
    def consent(self,enabled,allow_ai,version):
        return pilot.authorize(self.store,'owner','company-a',enabled,allow_ai,'Explicit TEST-only private pilot authorization, no real results.',version)
    def start(self):
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=int(self.origin.rsplit(':',1)[1]),preview=ProductionPolicy(self.store),tls_context=tls,pilot_ai_config=self.ai_file)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def stop(self): self.server.shutdown();self.server.server_close();self.thread.join()
    def tearDown(self): self.stop();self.temp.cleanup()
    def new_client(self): return build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(self.cert))),HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,path,body=None,*,headers=None,method=None,raw=None,client=None):
        method=method or ('POST' if body is not None or raw is not None else 'GET')
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request=Request(self.origin+path,data,{'Content-Type':'application/json','Origin':self.origin,**(headers or {})},method=method)
        try: response=(client or self.client).open(request,timeout=30)
        except HTTPError as e: response=e
        with response:
            value=json.loads(response.read());self.assertEqual('1.6.0',response.headers['X-Centerway-API-Version'])
            node=SPEC['paths'].get(path.split('?')[0],{}).get(method.lower(),{}).get('responses',{}).get(str(response.status))
            if node:
                if '$ref' in node: node=SPEC['components']['responses'][node['$ref'].split('/')[-1]]
                schema=node.get('content',{}).get('application/json',{}).get('schema')
                if schema: Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(value)
            if response.status<400 and body is not None:
                operation=SPEC['paths'].get(path.split('?')[0],{}).get(method.lower(),{})
                schema=operation.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema')
                if schema: Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(body)
            return response.status,value
    def get(self,route,**query): return self.call('/api/pilot/'+route+'?'+urlencode({'tenant':'company-a',**query}))
    def post(self,route,**body): return self.call('/api/pilot/'+route,{'tenant':'company-a',**body})
    def login(self,user='owner',client=None): self.assertEqual(200,self.call('/api/login',{'user':user,'password':self.passwords[user]},client=client)[0])
    def count(self,table):
        with self.store.transaction() as db: return db.execute('SELECT count(*) FROM '+table).fetchone()[0]
    def setup_context(self):
        cfg=fixtures.fixture('collaboration','config','c04');cfg.update(tenant='company-a',data_classification='declared');cfg['provenance']['source_ref']='test:unverified-pilot-declaration'
        self.assertEqual(200,self.post('configure',config=cfg,expected_version=0)[0])
        criteria=fixtures.fixture('collaboration','criteria');criteria['tenant']='company-a'
        self.assertEqual(200,self.post('criteria/append',document=criteria,expected_version=0)[0])
        self.assertEqual(200,self.post('customers/append',customer='client-1',name='Explicit TEST customer',context='TEST declaration; no real customer or results.',expected_version=0)[0])
        return cfg,criteria
    def ingest(self,customer='client-1'):
        for name,directory in (('evidence','detection'),('context','c04')):
            body=fixtures.fixture('collaboration',name,directory);body.update(tenant='company-a',customer=customer)
            self.assertEqual(200,self.call('/api/evidence',body)[0])
    def process(self,**changes):
        self.counter+=1
        return self.post('process',customer='client-1',case_id='case-1',request_id='process-'+str(self.counter),as_of=fixtures.AS_OF,**changes)
    def detail(self,**query): return self.get('analysis',customer='client-1',case_id='case-1',**query)
    def investigate(self):
        detail=self.detail()[1];run=detail['c02']['id'];records=evidence.EvidenceRepository(self.store).query('owner','company-a','client-1',1)['records']
        paused=next(r for r in records if r['definition_id']=='operation-state')
        doc=fixtures.fixture('collaboration','declaration','investigation');doc.update(tenant='company-a',customer='client-1',c02_run_id=run)
        doc['hypotheses'][0]['support_refs']=[{'evidence_id':paused['id'],'field':'paused'}]
        status,result=self.post('investigate',customer='client-1',case_id='case-1',c02_run_id=run,document=doc,expected_version=0)
        self.assertEqual(200,status,result);return doc
    def prepared(self): self.login();self.setup_context();self.ingest();self.assertEqual(200,self.process()[0]);self.investigate();self.assertEqual(200,self.process()[0])

    def test_https_complete_declared_path_without_ai_to_human_follow_up(self):
        self.prepared();detail=self.detail()[1]
        self.assertEqual('awaiting_ai',detail['checkpoint']['payload']['state']);self.assertIsNotNone(detail['c02']);self.assertIsNotNone(detail['c03'])
        self.assertEqual('not_requested',detail['c04']['status']);self.assertEqual(0,self.count('c04_requests'))
        self.assertEqual('demonstrated',detail['c02']['payload']['operational_deterioration']['state'])
        review=self.post('review',customer='client-1',case_id='case-1',request_id='review-1',expected_checkpoint_hash=detail['checkpoint']['record_hash'],note='TEST operator follow-up; request corroborating source information.')
        self.assertEqual(200,review[0]);self.assertFalse(review[1]['payload']['execution_authorized'])
        self.assertEqual(200,self.process()[0]);follow=self.detail()[1]
        self.assertEqual('needs_review',follow['checkpoint']['payload']['state']);self.assertIn('human_follow_up_recorded',follow['checkpoint']['payload']['blockers'])
        self.assertFalse(follow['real_recovery_demonstrated']);self.assertEqual('blocked',follow['external_execution'])
        self.assertEqual(0,self.count('c04_requests'));self.assertEqual(0,self.count('c05_intents'))
        self.assertEqual(200,self.get('status')[0]);self.assertTrue(self.get('status')[1]['analysis_ready'])
        for table in BUSINESS_TABLES: self.assertEqual(0,self.count(table))

    def test_default_denial_grant_revocation_and_cli_not_exposed(self):
        self.login();self.assertEqual(403,self.call('/api/pilot/context?tenant=company-b')[0])
        self.assertFalse(self.get('status')[1]['analysis_ready']);self.assertEqual(0,self.count('orchestration_cases'))
        self.assertEqual(404,self.call('/api/pilot/authorize',{'tenant':'company-a','enabled':True})[0])
        self.consent(False,False,1);self.assertEqual(403,self.get('context')[0]);self.assertFalse(self.get('status')[1]['pilot_authorized'])
        with self.assertRaises(Problem): orchestration.Orchestrator(self.store).register('owner','company-a','client','case')
        result=subprocess.run(['python','-m','centerway.pilot','authorize','--db',str(self.path),'--user','viewer','--tenant','company-a','--enabled','yes','--allow-ai','no','--reason','unauthorized test','--expected-version','2'],capture_output=True,text=True)
        self.assertEqual(1,result.returncode);self.assertEqual(2,self.count('pilot_grants'))

    def test_authentication_roles_tenant_customer_isolation_and_csrf(self):
        self.assertEqual(401,self.get('context')[0]);self.login();cfg,_=self.setup_context()
        self.assertEqual(403,self.call('/api/pilot/configure',{'tenant':'company-a','config':cfg,'expected_version':1},headers={'Origin':'https://evil.invalid'})[0])
        self.assertEqual(403,self.call('/api/pilot/configure',{'tenant':'company-a','config':cfg,'expected_version':1},headers={'Sec-Fetch-Site':'cross-site'})[0])
        reader=self.new_client();self.login('viewer',reader)
        self.assertEqual(200,self.call('/api/pilot/context?tenant=company-a',client=reader)[0])
        self.assertEqual(403,self.call('/api/pilot/configure',{'tenant':'company-a','config':cfg,'expected_version':1},client=reader)[0])
        outsider=self.new_client();self.login('outsider',outsider)
        self.assertEqual(403,self.call('/api/pilot/context?tenant=company-a',client=outsider)[0])
        self.assertEqual(404,self.detail()[0]);self.ingest();self.process()
        self.assertEqual(404,self.get('analysis',customer='another-customer',case_id='case-1')[0])
        self.assertEqual(400,self.get('context',tenant_claim='company-b')[0])
        self.call('/api/logout',{});self.assertEqual(401,self.get('context')[0])

    def test_versioned_config_criteria_customers_and_strict_validation(self):
        self.login();cfg,criteria=self.setup_context()
        self.assertEqual(409,self.post('configure',config=cfg,expected_version=0)[0])
        self.assertEqual(409,self.post('criteria/append',document=criteria,expected_version=0)[0])
        bad=deepcopy(cfg);bad['data_classification']='synthetic';self.assertEqual(403,self.post('configure',config=bad,expected_version=1)[0])
        bad=deepcopy(criteria);bad['criteria'][0]['threshold']=None
        self.assertEqual(400,self.post('criteria/append',document=bad,expected_version=1)[0])
        cfg['product']['description']='Explicit revised TEST declaration.';self.assertEqual(200,self.post('configure',config=cfg,expected_version=1)[0])
        self.assertFalse(self.get('status')[1]['analysis_ready']);self.assertEqual(1,self.get('configuration',version=1)[1]['version'])
        criteria['config_version']=2;self.assertEqual(200,self.post('criteria/append',document=criteria,expected_version=1)[0])
        self.assertEqual(1,self.get('criteria',version=1)[1]['version'])
        request={'customer':'client-1','name':'Revised TEST customer','context':'Explicit revised test context.','expected_version':1}
        first=self.post('customers/append',**request);self.assertEqual(200,first[0]);self.assertEqual(first,self.post('customers/append',**request))
        history=self.get('customers',customer='client-1',limit=1)[1];self.assertEqual(1,len(history['items']));self.assertEqual(1,history['next_after'])
        self.assertEqual(2,self.get('customers',customer='client-1',after=1)[1]['items'][0]['version'])
        self.assertEqual(2,len(self.get('context')[1]['configuration_history']))

    def test_insufficient_conflicting_data_remain_unresolved_no_fabrication(self):
        self.login();self.setup_context();first=self.process();self.assertEqual(200,first[0]);self.assertEqual('awaiting_data',first[1]['checkpoint']['payload']['state'])
        self.assertEqual(0,self.count('investigation_versions'));self.ingest()
        body=fixtures.fixture('collaboration','evidence');body.update(tenant='company-a',customer='client-1')
        body['records']=[r for r in body['records'] if 'value' in r['payload'] or 'outcome_count' in r['payload']]
        for r in body['records']:
            r['external_id']='conflict-'+r['external_id']
            if 'value' in r['payload']: r['payload']['value']=999
            elif 'outcome_count' in r['payload']: r['payload']['outcome_count']=999
        self.assertEqual(200,self.call('/api/evidence',body)[0]);self.assertEqual(200,self.process()[0])
        detail=self.detail()[1];self.assertEqual('needs_review',detail['checkpoint']['payload']['state'])
        self.assertIn('contradictory_detection',detail['checkpoint']['payload']['blockers']);self.assertEqual(0,self.count('investigation_versions'))
        self.assertEqual(0,self.count('c04_requests'))

    def test_process_request_idempotency_concurrency_limits_and_resume(self):
        self.login();self.setup_context();self.ingest()
        body={'customer':'client-1','case_id':'case-1','request_id':'same-request','as_of':fixtures.AS_OF}
        first=self.post('process',**body);self.assertEqual(200,first[0]);self.assertEqual(first,self.post('process',**body))
        self.assertEqual(404,self.post('process',**{**body,'customer':'different-customer'})[0])
        before=self.count('detection_runs');self.investigate();self.assertEqual(200,self.process()[0]);self.assertEqual(before,self.count('detection_runs'))
        status,page=self.detail(limit=1);self.assertEqual(200,status);self.assertEqual(1,len(page['history']));self.assertIsNotNone(page['next_after'])
        oldest=self.detail(version=1)[1];self.assertEqual('awaiting_data',oldest['checkpoint']['payload']['state']);self.assertIsNone(oldest['c02'])
        for i in range(8): self.process()
        self.assertEqual(429,self.process()[0]);self.assertEqual(0,self.count('c05_attempts'))

    def test_stale_review_new_evidence_and_c03_versions_preserve_history(self):
        self.prepared();old=self.detail()[1];doc=self.investigate()
        # Exact revision retry is reused; a new explicit document makes a new C03 version.
        doc['hypotheses'][0]['statement']='Revised TEST hypothesis, still unconfirmed.'
        run=old['c02']['id'];self.assertEqual(200,self.post('investigate',customer='client-1',case_id='case-1',c02_run_id=run,document=doc,expected_version=1)[0])
        self.assertEqual(200,self.process()[0]);self.assertEqual(409,self.post('review',customer='client-1',case_id='case-1',request_id='stale',expected_checkpoint_hash=old['checkpoint']['record_hash'],note='stale test')[0])
        self.assertEqual(1,self.detail(version=old['checkpoint']['version'])[1]['c03']['version'])
        body=fixtures.fixture('collaboration','context','c04');body.update(tenant='company-a',customer='client-1');body['records'][0]['external_id']='new-test-evidence'
        body['records'][0]['occurred_at']='2026-01-01T00:04:01Z';self.assertEqual(200,self.call('/api/evidence',body)[0]);self.assertEqual(200,self.process()[0])
        self.assertEqual('awaiting_investigation',self.detail()[1]['checkpoint']['payload']['state']);self.assertEqual(2,self.count('investigation_versions'))

    def test_pending_concurrency_crash_resume_and_read_only_views(self):
        self.login();self.setup_context();self.ingest()
        entered=threading.Event();release=threading.Event();original=orchestration.Orchestrator.process_case
        def paused(repo,*args,**kwargs):
            entered.set();release.wait(5);return original(repo,*args,**kwargs)
        body={'customer':'client-1','case_id':'case-1','request_id':'concurrent','as_of':fixtures.AS_OF}
        with patch.object(orchestration.Orchestrator,'process_case',paused),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(lambda:self.post('process',**body));self.assertTrue(entered.wait(5))
            try: self.assertEqual(409,self.post('process',**body)[0])
            finally: release.set()
            self.assertEqual(200,first.result()[0])
        with self.store.transaction() as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        for route,query in [('context',{}),('status',{}),('customers',{}),('analysis',{'customer':'client-1','case_id':'case-1'})]: self.assertEqual(200,self.get(route,**query)[0])
        with self.store.transaction() as db: self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})
        self.investigate()
        with patch.object(orchestration.Orchestrator,'process_case',side_effect=RuntimeError('crash test: no result invented')):
            self.assertEqual(500,self.process()[0])
        self.assertEqual(409,self.process()[0])
        with patch('centerway.pilot.time.time',return_value=int(time.time())+61):
            self.assertEqual(200,self.process()[0])
        self.assertEqual(0,self.count('c04_requests'));self.assertEqual(1,self.count('detection_runs'))

    def test_framing_payload_claims_session_and_storage_integrity_fail_closed(self):
        self.login();cfg,_=self.setup_context()
        for headers,status in [({'Transfer-Encoding':'chunked'},400),({'Content-Encoding':'gzip'},415)]:
            self.assertEqual(status,self.call('/api/pilot/configure',{'tenant':'company-a','config':cfg,'expected_version':1},headers=headers)[0])
        self.assertEqual(400,self.post('configure',config=cfg,expected_version=1,user='owner')[0])
        self.assertEqual(400,self.call('/api/pilot/process',raw=b'{"tenant":"company-a","tenant":"company-b"}')[0])
        self.assertEqual(413,self.call('/api/pilot/process',raw=b'x'*65537)[0])
        self.assertEqual(400,self.get('analysis',customer='client-1',case_id='case-1',limit=51)[0])
        with self.store.transaction() as db: db.execute('DELETE FROM sessions')
        self.assertEqual(401,self.get('context')[0]);self.login()
        with self.store.transaction() as db: db.execute('DROP TRIGGER '+next(iter(pilot.GUARDS)))
        self.assertEqual(503,self.get('context')[0])

    def test_production_c05_and_c06_storage_guards_and_test_adapter_refusal(self):
        self.prepared();repo=pilot.Pilot(self.store)
        with self.assertRaises(Problem): repo.orch.process_case('owner','company-a','client-1','case-1',fixtures.AS_OF,ai_adapter=fixtures.FixtureAdapter())
        with self.assertRaises(Problem): repo.orch.process_case('owner','company-a','client-1','case-1',fixtures.AS_OF,execution_adapter=object())
        for table in ('c05_intents','c05_approvals','c05_attempts','c05_results','recovery_plans','recovery_runs'):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.store.transaction() as db: db.execute('INSERT INTO '+table+' DEFAULT VALUES')
        self.assertEqual(503,self.call('/api/execute',{'tenant':'company-a','customer':'client-1','case_id':'case-1'})[0])
        self.assertEqual(503,self.call('/api/orchestration/open',{'tenant':'company-a','customer':'client-1','case_id':'other','request_id':'open','reason':'test','previous_case_id':None,'human_confirmed':True})[0])

    def test_ai_requires_private_configuration_and_tenant_consent(self):
        self.prepared()
        with patch('centerway.ai_adapter.HTTPSChatAdapter',side_effect=AssertionError('No provider without consent')):
            self.ai_file='/not-authorized';self.stop();self.start();self.assertEqual(200,self.process()[0])
        self.assertEqual(0,self.count('c04_requests'));self.consent(True,True,1)
        self.assertEqual(200,self.process()[0]);self.assertEqual(0,self.count('c04_requests'));self.assertEqual('awaiting_ai',self.detail()[1]['checkpoint']['payload']['state'])

    def test_local_https_test_provider_proposal_stops_before_c05(self):
        self.prepared();self.consent(True,True,1);state={'calls':0}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(inner):
                envelope=json.loads(inner.rfile.read(int(inner.headers['Content-Length'])));context=json.loads(envelope['messages'][1]['content'])
                state['calls']+=1
                if state.get('callback'): state['callback']()
                reply={'id':'test-fixture-response','model':'explicit-test-server-not-real-ai','choices':[{'finish_reason':'stop','message':{'role':'assistant','content':canonical(fixtures.fixture_response(context))}}]}
                raw=canonical(reply).encode();inner.send_response(200);inner.send_header('Content-Type','application/json');inner.send_header('Content-Length',str(len(raw)));inner.end_headers();inner.wfile.write(raw)
        provider=ThreadingHTTPServer(('127.0.0.1',0),Handler);tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key);provider.socket=tls.wrap_socket(provider.socket,server_side=True)
        thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
        ca=self.root/'ca.pem';ca.write_bytes(self.cert.read_bytes());ca.chmod(0o600)
        secret=self.root/'provider.key';secret.write_text(secrets.token_hex(32));secret.chmod(0o600)
        config={'protocol':'https-chat-completions-v1','endpoint':f'https://127.0.0.1:{provider.server_port}/v1/chat/completions','model':'explicit-test-model-not-real-ai',
                'api_key_file':str(secret),'ca_file':str(ca),'allowed_tenants':['company-a'],'allowed_classifications':['declared'],'allow_production_inference':True,'max_output_tokens':1000,'timeout_seconds':2}
        self.ai_file=self.root/'provider.json';self.ai_file.write_text(canonical(config));self.ai_file.chmod(0o600)
        self.stop();self.start()
        try:
            status,result=self.process();self.assertEqual(200,status,result);self.assertEqual(1,state['calls'])
            card=self.detail()[1];self.assertEqual('proposal_validated',card['c04']['decision']['status']);self.assertFalse(card['c04']['decision']['execution_authorized'])
            self.assertNotIn('context',card['c04']);self.assertNotIn(config['endpoint'],canonical(card['c04']));self.assertNotIn(secret.read_text(),canonical(card))
            self.assertEqual('needs_review',card['checkpoint']['payload']['state']);self.assertNotIn('c05',card['checkpoint']['payload']['refs'])
            self.assertEqual(200,self.process()[0]);self.assertEqual(1,state['calls']);self.assertEqual(0,self.count('c05_intents'))
            # Revocation during HTTPS inference must never leave an actionable recommendation.
            doc=self.investigate();doc['hypotheses'][0]['statement']='New explicit TEST revision before revocation.'
            run=card['c02']['id'];self.assertEqual(200,self.post('investigate',customer='client-1',case_id='case-1',c02_run_id=run,document=doc,expected_version=1)[0])
            state['callback']=lambda:self.consent(False,False,2)
            self.assertEqual(403,self.process()[0]);self.assertEqual(2,state['calls']);self.assertEqual(0,self.count('c05_intents'))
            with self.store.transaction() as db:
                result=db.execute('SELECT payload FROM c04_results ORDER BY rowid DESC LIMIT 1').fetchone()
                self.assertEqual('unavailable',json.loads(result[0])['status'])

        finally: provider.shutdown();provider.server_close();thread.join()


if __name__=='__main__': unittest.main()
