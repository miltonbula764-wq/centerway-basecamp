"""Private HTTPS lifecycle decisions; no published service or real recovery."""
import json
from datetime import datetime,timezone
from urllib.request import Request
from urllib.error import HTTPError
from jsonschema import Draft202012Validator,FormatChecker
import unittest

from centerway.core import Problem
from centerway.continuity import Continuity
from centerway.http_contract import API_VERSION
from test_ai_proposals import fixture
import test_orchestration_api as api

SPEC=api.SPEC


class ContinuityApiTests(unittest.TestCase):
    setUpClass=classmethod(api.OrchestrationApiTests.setUpClass.__func__)
    tearDownClass=classmethod(api.OrchestrationApiTests.tearDownClass.__func__)
    setUp=api.OrchestrationApiTests.setUp
    tearDown=api.OrchestrationApiTests.tearDown
    new_client=api.OrchestrationApiTests.new_client
    login=api.OrchestrationApiTests.login
    query=api.OrchestrationApiTests.query
    def call(self,path,body=None,method=None,headers=None,client=None):
        method=method or ('POST' if body is not None else 'GET')
        request=Request(self.origin+path,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json','Origin':self.origin,**(headers or {})},method=method)
        try: response=(client or self.client).open(request,timeout=20)
        except HTTPError as error: response=error
        with response:
            raw=response.read();value=json.loads(raw) if raw else None
            self.assertEqual(API_VERSION,response.headers['X-Centerway-API-Version'])
            operation=SPEC['paths'].get(path.split('?')[0],{}).get(method.lower(),{})
            node=operation.get('responses',{}).get(str(response.status),{})
            if '$ref' in node: node=SPEC['components']['responses'][node['$ref'].split('/')[-1]]
            schema=node.get('content',{}).get('application/json',{}).get('schema')
            if value is not None and schema: Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(value)
            if response.status<400 and body is not None and 'requestBody' in operation:
                Draft202012Validator({**operation['requestBody']['content']['application/json']['schema'],'components':SPEC['components']}).validate(body)
            return response.status,value,dict(response.headers)
    def detail(self,case='case-a',tenant='atlas',customer='fictional-account',client=None):
        from urllib.parse import urlencode
        return self.call('/api/orchestration/cycle?'+urlencode({'tenant':tenant,'customer':customer,'case_id':case}),client=client)
    def close_body(self,context,case='case-a',tenant='atlas',customer='fictional-account'):
        return {'tenant':tenant,'customer':customer,'case_id':case,'request_id':'close-'+case,'reason':'Explicit administrative test closure; value recovery is not asserted.',
                'disposition':'cancelled','expected_version':context['context']['checkpoint_version'],'expected_context_hash':context['context']['context_hash'],'human_confirmed':True}
    def fresh(self):
        body=fixture('collaboration','context','c04');body['tenant']='atlas';body['records'][0]['external_id']='new-cycle-api-evidence'
        body['records'][0]['occurred_at']=datetime.now(timezone.utc).isoformat()
        return self.call('/api/evidence',body)

    def test_authenticated_explicit_close_and_successor_open_with_historical_read(self):
        self.assertEqual(401,self.detail()[0]);self.login()
        _,detail,headers=self.detail();self.assertEqual('no-store',headers['Cache-Control'])
        body=self.close_body(detail);status,closed,_=self.call('/api/orchestration/close',body)
        self.assertEqual(200,status);self.assertEqual('founder',closed['actor']);self.assertFalse(closed['payload']['closure_means_recovery'])
        self.assertIsNone(closed['payload']['value_recovered']);self.assertEqual(closed,self.call('/api/orchestration/close',body)[1])
        self.assertEqual('closed',self.detail()[1]['lifecycle'])
        self.assertEqual(1,len(self.query(lifecycle='closed')[1]['items']))
        opening={'tenant':'atlas','customer':'fictional-account','case_id':'next-case','request_id':'open-next','reason':'Explicit new episode, backed by new test evidence.','previous_case_id':'case-a','human_confirmed':True}
        self.assertEqual(409,self.call('/api/orchestration/open',opening)[0]);self.assertEqual(200,self.fresh()[0])
        status,opened,_=self.call('/api/orchestration/open',opening);self.assertEqual(200,status);self.assertEqual(2,opened['payload']['cycle_number'])
        self.assertEqual(opened,self.call('/api/orchestration/open',opening)[1]);self.assertEqual('active',self.detail('next-case')[1]['lifecycle'])
        self.assertEqual(closed,self.detail()[1]['closure'])
        self.assertEqual(['next-case'],[r['case_id'] for r in self.query(customer='fictional-account')[1]['items']])
        self.assertEqual(2,len(self.query(customer='fictional-account',lifecycle='all')[1]['items']))

    def test_roles_scope_origin_confirmation_and_json_claims_cannot_authorize(self):
        self.login();ctx=self.detail()[1];body=self.close_body(ctx)
        self.assertEqual(400,self.call('/api/orchestration/close',body,headers={'Transfer-Encoding':'chunked'})[0])
        self.assertEqual(415,self.call('/api/orchestration/close',body,headers={'Content-Encoding':'gzip'})[0])
        self.assertEqual(400,self.call('/api/orchestration/close',{**body,'actor':'founder'})[0])
        self.assertEqual(400,self.call('/api/orchestration/close',{**body,'session_token':'forged'})[0])
        self.assertEqual(400,self.call('/api/orchestration/close',{**body,'human_confirmed':False})[0])
        self.assertEqual(403,self.call('/api/orchestration/close',body,headers={'Origin':'https://untrusted.invalid'})[0])
        self.assertEqual(403,self.call('/api/orchestration/close',body,headers={'Sec-Fetch-Site':'cross-site'})[0])
        self.assertEqual(409,self.call('/api/orchestration/close',{**body,'expected_context_hash':'0'*64})[0])
        reader=self.new_client();self.login('reader-private',reader)
        other=self.detail(tenant='nimbus',customer='other-account',client=reader)[1]
        self.assertEqual(403,self.call('/api/orchestration/close',self.close_body(other,tenant='nimbus',customer='other-account'),client=reader)[0])
        self.assertEqual(403,self.detail(client=reader)[0])
        restricted=self.new_client();self.login('atlas-private',restricted)
        self.assertEqual(403,self.detail(tenant='nimbus',customer='other-account',client=restricted)[0])
        self.assertEqual('active',self.detail()[1]['lifecycle'])

    def test_fresh_context_required_and_data_from_other_customer_never_enters_closure(self):
        self.login();ctx=self.detail()[1];body=self.close_body(ctx);self.fresh()
        self.assertEqual(409,self.call('/api/orchestration/close',body)[0])
        fresh=self.detail()[1];closed=self.call('/api/orchestration/close',self.close_body(fresh))[1]
        self.assertGreater(len(closed['payload']['snapshot']['evidence']),len(ctx['context']['evidence']))
        self.assertTrue(all(e['source_ref'].startswith('fixture:collaboration:') for e in closed['payload']['snapshot']['evidence']))
        self.assertEqual([],self.detail(case='case-b',customer='Account / 002')[1]['context']['evidence'])
        self.assertEqual(404,self.detail(case='case-a',customer='other-account')[0])
        self.assertEqual(400,self.query(lifecycle='recovered')[0])
        self.assertEqual(400,self.call('/api/orchestration/cycle?tenant=atlas&case_id=case-a')[0])
        self.assertEqual(405,self.call('/api/orchestration/close',method='GET')[0])

    def test_normal_logout_and_demo_expiry_block_lifecycle_writes(self):
        self.login();body=self.close_body(self.detail()[1]);self.call('/api/logout',{})
        self.assertEqual(401,self.call('/api/orchestration/close',body)[0])
        self.login()
        with self.store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
        self.assertEqual(503,self.call('/api/orchestration/close',body)[0]);self.assertEqual(503,self.detail()[0])
        with self.store.transaction() as db: self.assertEqual(0,db.execute('SELECT count(*) FROM continuity_closures').fetchone()[0])

    def test_initial_opening_is_explicit_and_no_second_active_cycle_is_possible(self):
        self.login();body={'tenant':'atlas','customer':'new-client','case_id':'first','request_id':'first-open','reason':'Explicit initial tracking request.','previous_case_id':None,'human_confirmed':True}
        self.assertEqual(200,self.call('/api/orchestration/open',body)[0]);self.assertEqual('active',self.detail(case='first',customer='new-client')[1]['lifecycle'])
        self.assertEqual(409,self.call('/api/orchestration/open',{**body,'case_id':'bypass','request_id':'second-open'})[0])
        self.assertEqual(200,self.call('/api/orchestration/open',body)[0])
        self.assertEqual([],self.detail(case='first',customer='new-client')[1]['context']['evidence'])


class ContinuityProductionTests(unittest.TestCase):
    setUpClass=classmethod(api.OrchestrationApiTests.setUpClass.__func__)
    tearDownClass=classmethod(api.OrchestrationApiTests.tearDownClass.__func__)
    new_client=api.OrchestrationApiTests.new_client
    call=ContinuityApiTests.call
    login=api.OrchestrationApiTests.login
    def test_all_lifecycle_mutations_remain_blocked_in_production(self):
        import tempfile,socket,ssl,threading
        from pathlib import Path
        from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
        from centerway.store import Store
        from centerway.server import make_server
        from centerway.orchestration import install
        from centerway.continuity import Continuity
        from centerway.ai_proposals import install as install_c04
        from centerway.controlled_execution import install as install_c05
        from centerway.recovery import install as install_c06
        import test_ai_proposals as proposals
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'production.sqlite3';accounts=root/'accounts.json'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'company','role':'operator'}]},
                {'user':'viewer','memberships':[{'tenant':'company','role':'viewer'}]}]}));accounts.chmod(0o600)
            with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            self.origin=f'https://127.0.0.1:{port}';secrets=root/'secrets.json';provision(path,secrets,self.origin,accounts)
            self.passwords=json.loads(secrets.read_text())['accounts'];store=Store.open_existing(path)
            proposals.ProposalSafetyTests().prepare(store,'owner','company',declared=True)
            install_c04(store);install_c05(store);install_c06(store);install(store);life=Continuity(store)
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key)
            server=make_server(store,port=port,preview=ProductionPolicy(store),tls_context=tls)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.client=self.new_client()
            try:
                opening={'tenant':'company','customer':'client','case_id':'case','request_id':'request','reason':'Explicit test only.','previous_case_id':None,'human_confirmed':True}
                self.assertEqual(401,self.call('/api/orchestration/open',opening)[0]);self.login('owner')
                self.assertEqual(200,self.call('/api/orchestration/cases?tenant=company')[0])
                self.assertEqual(503,self.call('/api/orchestration/open',opening)[0])
                closing={k:v for k,v in opening.items() if k!='previous_case_id'}
                closing.update(disposition='cancelled',expected_version=0,expected_context_hash='0'*64)
                self.assertEqual(503,self.call('/api/orchestration/close',closing)[0])
                review={k:v for k,v in opening.items() if k not in ('reason','previous_case_id')};review.update(note='Explicit test review.',evidence_ids=[],expected_context_hash='0'*64)
                self.assertEqual(503,self.call('/api/orchestration/review',review)[0])
                viewer=self.new_client();self.login('viewer',viewer)
                self.assertEqual(403,self.call('/api/orchestration/open',opening,client=viewer)[0])
                with self.assertRaises(Problem): life.open('owner','company','client','case','request','test',None,human_confirmed=True,session_token='not-a-valid-session')
                with store.transaction() as db:
                    for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                    for table in ('orchestration_cases','continuity_closures','continuity_openings','continuity_reviews'): self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
            finally: server.shutdown();server.server_close();thread.join()
