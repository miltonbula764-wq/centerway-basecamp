"""Authenticated HTTPS queries over inactive state. No publication, Lovable or real AI."""
import http.cookiejar
import json
from pathlib import Path
import socket
import ssl
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from jsonschema import Draft202012Validator,FormatChecker

from centerway.ai_proposals import install as install_c04
from centerway.controlled_execution import install as install_c05
from centerway.core import Problem
from centerway.http_contract import API_VERSION
from centerway.orchestration import Orchestrator,install
from centerway.preview import provision,PreviewPolicy
from centerway.recovery import install as install_c06
from centerway.server import make_server
from centerway.store import Store
import test_ai_proposals as proposal_tests

ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'contracts/openapi.json').read_text())


class OrchestrationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certs=tempfile.TemporaryDirectory();cls.cert=Path(cls.certs.name)/'cert.pem';cls.key=Path(cls.certs.name)/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls): cls.certs.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'demo.sqlite3'
        with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.origin=f'https://127.0.0.1:{port}';secrets=self.root/'private.json';provision(self.path,secrets,self.origin)
        self.passwords=json.loads(secrets.read_text())['accounts'];self.store=Store.open_existing(self.path)
        proposal_tests.ProposalSafetyTests().prepare(self.store,'founder','atlas')
        install_c04(self.store);install_c05(self.store);install_c06(self.store);install(self.store)
        self.orch=Orchestrator(self.store)
        self.orch.register('founder','atlas','fictional-account','case-a')
        self.orch.register('founder','atlas','Account / 002','case-b')
        self.orch.register('founder','nimbus','other-account','case-a')
        self.orch.process_batch('founder','atlas',proposal_tests.AS_OF)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=port,preview=PreviewPolicy(self.store),tls_context=context,frontend_origins=('https://frontend.example.invalid',))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.client=self.new_client()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def new_client(self): return build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(self.cert))),HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,path,body=None,method=None,headers=None,client=None):
        request=Request(self.origin+path,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json','Origin':self.origin,**(headers or {})},method=method or ('POST' if body is not None else 'GET'))
        try: response=(client or self.client).open(request,timeout=15)
        except HTTPError as e: response=e
        with response:
            raw=response.read();value=json.loads(raw) if raw else None
            self.assertEqual(API_VERSION,response.headers['X-Centerway-API-Version'])
            if value is not None:
                schema={'$ref':'#/components/schemas/Error'} if response.status>=400 else {'$ref':'#/components/schemas/OrchestrationPage'} if path.startswith('/api/orchestration/') else None
                if schema: Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(value)
            return response.status,value,dict(response.headers)
    def login(self,user='founder',client=None):
        return self.call('/api/login',{'user':user,'password':self.passwords[user]},client=client)
    def query(self,tenant='atlas',**kwargs): return self.call('/api/orchestration/cases?'+urlencode({'tenant':tenant,**kwargs}))

    def test_https_session_query_pagination_schema_filters_and_no_processing_on_get(self):
        self.assertEqual(401,self.query()[0]);status,_,headers=self.login();self.assertEqual(200,status)
        self.assertIn('Secure',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        with self.store.transaction() as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        status,page,headers=self.query(limit=1);self.assertEqual(200,status);self.assertEqual(1,len(page['items']));self.assertIsNotNone(page['next_after'])
        self.assertEqual('awaiting_ai',page['items'][0]['state']);self.assertEqual(['authorized_ai_not_configured'],page['items'][0]['blockers'])
        self.assertEqual('no-store',headers['Cache-Control']);self.assertEqual('nosniff',headers['X-Content-Type-Options'])
        self.assertEqual('Account / 002',self.query(after=page['next_after'])[1]['items'][0]['customer'])
        self.assertEqual(1,len(self.query(state='awaiting_ai')[1]['items']))
        self.assertEqual('case-b',self.query(customer='Account / 002',case_id='case-b')[1]['items'][0]['case_id'])
        with self.store.transaction() as db: self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})
        self.call('/api/logout',{});self.assertEqual(401,self.query()[0])

    def test_current_membership_reader_and_tenant_customer_isolation(self):
        self.login('atlas-private');self.assertEqual(200,self.query()[0]);self.assertEqual(403,self.query('nimbus')[0])
        self.assertEqual([],self.query(customer='other-account')[1]['items'])
        reader=self.new_client();self.login('reader-private',reader)
        self.assertEqual(200,self.call('/api/orchestration/cases?tenant=nimbus',client=reader)[0])
        self.assertEqual(403,self.call('/api/orchestration/cases?tenant=atlas',client=reader)[0])
        self.assertEqual(405,self.call('/api/orchestration/cases',{},client=reader)[0])

    def test_bad_queries_origin_cross_site_preflight_and_unprepared_storage_fail_closed(self):
        self.login()
        for query in ('','tenant=','tenant=atlas&tenant=nimbus','tenant=atlas&role=operator','tenant=atlas&limit=51','tenant=atlas&after=-1','tenant=atlas&state=recovered','tenant=atlas&case_id=case-a','tenant=atlas&limit=%EF%BC%91'):
            self.assertEqual(400,self.call('/api/orchestration/cases?'+query)[0])
        self.assertEqual(403,self.call('/api/orchestration/cases?tenant=atlas',headers={'Origin':'https://untrusted.invalid'})[0])
        self.assertEqual(403,self.call('/api/orchestration/cases?tenant=atlas',headers={'Sec-Fetch-Site':'cross-site'})[0])
        status,_,headers=self.call('/api/orchestration/cases',method='OPTIONS',headers={'Origin':'https://frontend.example.invalid','Access-Control-Request-Method':'GET'})
        self.assertEqual(204,status);self.assertEqual('https://frontend.example.invalid',headers['Access-Control-Allow-Origin'])
        with self.store.transaction() as db: db.execute('DROP TRIGGER orchestration_immutable_orchestration_events_UPDATE')
        self.assertEqual(503,self.query()[0])

    def test_expired_demo_cannot_query_or_run_batches(self):
        self.login()
        with self.store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
        self.assertEqual(503,self.query()[0])
        with self.assertRaises(Problem): self.orch.process_batch('founder','atlas',proposal_tests.AS_OF)


class OrchestrationProductionTests(unittest.TestCase):
    def test_production_keeps_processing_blocked_even_for_an_empty_batch(self):
        from centerway.production import provision as production_provision,ProductionPolicy,BUSINESS_TABLES
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);accounts=root/'accounts.json';path=root/'production.sqlite3'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
            production_provision(path,root/'private.json','https://production.example.invalid',accounts)
            store=Store.open_existing(path);proposal_tests.ProposalSafetyTests().prepare(store,'owner','collaboration',declared=True)
            install_c04(store);install_c05(store);install_c06(store);install(store);repo=Orchestrator(store)
            self.assertEqual([],repo.query('owner','collaboration')['items'])
            with self.assertRaises(Problem): repo.register('owner','collaboration','client','case')
            with self.assertRaises(Problem): repo.process_batch('owner','collaboration',proposal_tests.AS_OF)
            with self.assertRaises(Problem): ProductionPolicy(store).block_operation(store,'owner','collaboration')
            with store.transaction() as db:
                for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                for table in ('orchestration_cases','orchestration_events','c05_attempts'): self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
