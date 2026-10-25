"""Real authenticated TLS API; inactive evidence only, discarded production fixtures."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.cookiejar
import io
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from jsonschema import Draft202012Validator,FormatChecker

from centerway.core import Core,Problem
from centerway.evidence import EvidenceRepository,install as install_evidence,GUARDS
from centerway.http_contract import API_VERSION
from centerway.integration_contract import load
from centerway.integrations import IntegrationRepository,install as install_integrations
from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
from centerway.server import make_server
from centerway.store import Store

ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'contracts/openapi.json').read_text())
MOMENT='2026-01-02T00:00:00Z'
PERIOD={'start':'2026-01-01T00:00:00Z','end':MOMENT}


def event(config,external='event-1',customer='client-1'):
    d=config['events'][0]
    return {'external_id':external,'kind':'event','definition_id':d['id'],'source_ref':d['source_ref'],
            'occurred_at':MOMENT,'period':None,'payload':{d['customer_id_field']:customer,'occurred_at':MOMENT}}


def metric(config,external='metric-1',value=3):
    d=config['metrics'][0]
    return {'external_id':external,'kind':'metric','definition_id':d['id'],'source_ref':d['source_ref'],
            'occurred_at':MOMENT,'period':deepcopy(PERIOD),'payload':{'value':value}}


def evidence(config,external='evidence-1',index=0,value=True):
    d=config['evidence'][index];field=d['fields'][0]['name']
    return {'external_id':external,'kind':'evidence','definition_id':d['id'],'source_ref':d['source_ref'],
            'occurred_at':MOMENT,'period':deepcopy(PERIOD) if d['kind']=='metric' else None,'payload':{field:value}}


class EvidenceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certs=tempfile.TemporaryDirectory();cls.cert=Path(cls.certs.name)/'cert.pem';cls.key=Path(cls.certs.name)/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.certs.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        accounts=self.root/'accounts.json'
        accounts.write_text(json.dumps({'accounts':[
            {'user':'owner','memberships':[{'tenant':t,'role':'operator'} for t in ('saas-a','saas-b','saas-c')]},
            {'user':'reader','memberships':[{'tenant':'saas-a','role':'viewer'}]},
            {'user':'restricted','memberships':[{'tenant':'saas-b','role':'operator'}]},
        ]}));accounts.chmod(0o600)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.origin=f'https://127.0.0.1:{port}';self.path=self.root/'production.sqlite3'
        secrets=self.root/'secrets.json';provision(self.path,secrets,self.origin,accounts)
        self.passwords=json.loads(secrets.read_text())['accounts'];self.store=Store.open_existing(self.path)
        install_integrations(self.store);self.configs={}
        for tenant,example in zip(('saas-a','saas-b','saas-c'),('collaboration','billing','support')):
            config=load(ROOT/'examples/integrations'/f'{example}.json')
            config['tenant']=tenant;config['data_classification']='declared'
            config['provenance']['source_ref']='test:unverified-declaration'
            IntegrationRepository(self.store).append('owner',tenant,config,0);self.configs[tenant]=config
        install_evidence(self.store)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=port,preview=ProductionPolicy(self.store),tls_context=context)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=self.new_client()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def new_client(self):
        return build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(self.cert))),HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self,path,body=None,headers=None,raw=None,method=None,client=None):
        method=method or ('POST' if body is not None or raw is not None else 'GET')
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request=Request(self.origin+path,data,{'Content-Type':'application/json','Origin':self.origin,**(headers or {})},method=method)
        try: response=(client or self.client).open(request,timeout=10)
        except HTTPError as error: response=error
        with response:
            payload=response.read();result=json.loads(payload) if payload else None
            self.assertEqual(API_VERSION,response.headers['X-Centerway-API-Version'])
            operation=SPEC['paths'].get(path.split('?')[0],{}).get(method.lower(),{})
            node=operation.get('responses',{}).get(str(response.status))
            if node:
                if '$ref' in node: node=SPEC['components']['responses'][node['$ref'].split('/')[-1]]
                schema=node.get('content',{}).get('application/json',{}).get('schema')
                if schema: Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(result)
            if response.status<400 and body is not None and 'requestBody' in operation:
                schema=operation['requestBody']['content']['application/json']['schema']
                Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(body)
            return response.status,result,response.headers

    def login(self,user='owner',client=None):
        status,_,headers=self.call('/api/login',{'user':user,'password':self.passwords[user]},client=client)
        self.assertEqual(200,status);return headers

    def body(self,records=None,tenant='saas-a',customer='client-1',version=1):
        return {'tenant':tenant,'customer':customer,'config_version':version,'records':records or [evidence(self.configs[tenant])]}

    def view(self,tenant='saas-a',customer='client-1',version=1,**pagination):
        return self.call('/api/evidence/view?'+urlencode({'tenant':tenant,'customer':customer,'config_version':version,**pagination}))

    def counts(self):
        with self.store.transaction() as db:
            return tuple(db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('evidence_items','evidence_batches'))

    def test_three_saas_event_metric_and_evidence_ingest_and_pinned_provenance(self):
        self.login()
        for tenant,config in self.configs.items():
            records=[event(config),metric(config),evidence(config),evidence(config,'value-1',1)]
            status,result,_=self.call('/api/evidence',self.body(records,tenant))
            self.assertEqual(200,status);self.assertEqual(4,result['inserted']);self.assertEqual('inactive',result['operational_state'])
            status,view,_=self.view(tenant)
            self.assertEqual(200,status);self.assertEqual('compatible',view['quality']['status'])
            self.assertEqual('not_evaluated',view['quality']['conclusion'])
            self.assertEqual(4,len(view['records']))
            for record in view['records']:
                self.assertEqual('owner',record['actor']);self.assertEqual(tenant,record['tenant'])
                self.assertEqual(view['config_hash'],record['config_hash']);self.assertTrue(record['received_at'].endswith('Z'))
                self.assertEqual(1,record['config_version']);self.assertEqual('client-1',record['customer'])
        self.assertEqual((12,3),self.counts())

    def test_retry_record_deduplication_identity_collision_and_atomic_rollback(self):
        self.login();body=self.body()
        first=self.call('/api/evidence',body)[1]
        second=self.call('/api/evidence',body)[1]
        self.assertTrue(second['reused']);self.assertEqual(first['batch_id'],second['batch_id'])
        self.assertEqual(0,second['inserted']);self.assertEqual(1,second['duplicates']);self.assertEqual((1,1),self.counts())
        original=deepcopy(body['records'][0]);collision=deepcopy(original);collision['payload']['paused']=False
        pending=event(self.configs['saas-a'],'new-before-collision')
        self.assertEqual(409,self.call('/api/evidence',self.body([pending,collision]))[0])
        self.assertEqual((1,1),self.counts())
        alias=deepcopy(original);alias['external_id']='different-identity-same-snapshot'
        self.assertEqual(409,self.call('/api/evidence',self.body([alias]))[0]);self.assertEqual((1,1),self.counts())
        duplicate_body=self.body([original,original])
        result=self.call('/api/evidence',duplicate_body)[1]
        self.assertEqual(0,result['inserted']);self.assertEqual(2,result['duplicates'])
        self.assertEqual((1,2),self.counts())

    def test_contradictory_snapshots_are_preserved_and_never_resolved(self):
        self.login();config=self.configs['saas-a']
        self.call('/api/evidence',self.body([metric(config,'claim-1',3)]))
        through=self.view()[1]['through']
        self.call('/api/evidence',self.body([metric(config,'claim-2',4)]))
        view=self.view()[1];self.assertEqual('contradictory',view['quality']['status'])
        self.assertEqual(2,len(view['quality']['conflicts'][0]['record_ids']))
        self.assertEqual([3,4],[r['payload']['value'] for r in view['records']])
        self.assertEqual('not_evaluated',view['quality']['conclusion'])
        historical=self.view(through=through)[1]
        self.assertEqual([],historical['quality']['conflicts']);self.assertEqual(1,len(historical['records']))
        # Distinct events at the same instant are not assumed to be the same event.
        self.assertEqual(2,self.call('/api/evidence',self.body([event(config,'event-a'),event(config,'event-b')]))[1]['inserted'])

    def test_insufficiency_and_other_configuration_versions_never_get_coerced(self):
        self.login();empty=self.view()[1]
        self.assertEqual('insufficient',empty['quality']['status']);self.assertEqual(4,len(empty['quality']['missing']))
        config=deepcopy(self.configs['saas-a']);config['metrics'][0]['value_type']='number'
        IntegrationRepository(self.store).append('owner','saas-a',config,1)
        self.call('/api/evidence',self.body([metric(self.configs['saas-a'])]))
        newer=self.view(version=2)[1]
        self.assertEqual([],newer['records']);self.assertEqual('incompatible',newer['quality']['status'])
        self.assertEqual(1,newer['quality']['excluded_other_versions'])
        self.assertEqual(409,self.call('/api/evidence',self.body([metric(config)],version=2))[0])
        changed=metric(config,'number-version-2',2.5)
        self.assertEqual(200,self.call('/api/evidence',self.body([changed],version=2))[0])
        self.assertEqual(1,len(self.view(version=1)[1]['records']))
        self.assertEqual(2.5,self.view(version=2)[1]['records'][0]['payload']['value'])

    def test_authentication_permissions_origin_host_session_and_subject_isolation(self):
        self.assertEqual(401,self.call('/api/evidence',self.body())[0]);self.assertEqual(401,self.view()[0])
        cookie=self.login()['Set-Cookie']
        for flag in ('__Host-cw_production_session=','Secure','HttpOnly','SameSite=Strict'): self.assertIn(flag,cookie)
        self.assertEqual(403,self.call('/api/evidence',self.body(),headers={'Origin':'https://evil.example'})[0])
        self.assertEqual(421,self.call('/api/evidence',self.body(),headers={'Host':'evil.example'})[0])
        self.assertEqual(403,self.call('/api/evidence',self.body(),headers={'Sec-Fetch-Site':'cross-site'})[0])
        self.assertEqual(200,self.call('/api/evidence',self.body())[0])
        self.assertEqual([],self.view(customer='another-client')[1]['records'])
        self.assertEqual([],self.view(tenant='saas-b')[1]['records'])
        self.call('/api/logout',{});self.login('reader')
        self.assertEqual(200,self.view()[0]);self.assertEqual(403,self.call('/api/evidence',self.body())[0])
        self.assertEqual(403,self.view(tenant='saas-b')[0])
        self.call('/api/logout',{});self.login('restricted')
        self.assertEqual(403,self.view()[0]);self.assertEqual(403,self.call('/api/evidence',self.body())[0])
        self.assertEqual(200,self.call('/api/evidence',self.body(tenant='saas-b'))[0])
        with self.store.transaction() as db: db.execute("UPDATE memberships SET tenant='saas-c' WHERE user_id='restricted'")
        self.assertEqual(403,self.view(tenant='saas-b')[0])
        self.call('/api/logout',{});self.login()
        with self.store.transaction() as db: db.execute("UPDATE sessions SET expires='2000-01-01T00:00:00+00:00'")
        self.assertEqual(401,self.view()[0])

    def test_strict_contract_source_customer_time_period_types_and_atomic_validation(self):
        self.login();config=self.configs['saas-a']
        invalid=[]
        for field,value in [('source_ref','foreign:source'),('definition_id','invoice-delivered'),('occurred_at','2099-01-01T00:00:00Z'),('occurred_at','2026-01-01T00:00:00'),('kind','action')]:
            row=event(config);row[field]=value;invalid.append(row)
        row=event(config);row['payload']['account_id']='another-client';invalid.append(row)
        row=event(config);row['payload']['occurred_at']='2026-01-01T00:00:00Z';invalid.append(row)
        row=event(config);row['payload']['extra']='not-declared';invalid.append(row)
        row=event(config);del row['payload']['account_id'];invalid.append(row)
        for value in (True,2.5,2**53,float('inf')): invalid.append(metric(config,value=value))
        row=metric(config);row['period']=None;invalid.append(row)
        row=metric(config);row['period']['end']=row['period']['start'];invalid.append(row)
        row=evidence(config);row['payload']={};invalid.append(row)
        for row in invalid:
            self.assertEqual(400,self.call('/api/evidence',self.body([event(config,'valid-first'),row]))[0])
            self.assertEqual((0,0),self.counts())
        bad=self.body();bad['records'][0]['role']='operator'
        self.assertEqual(400,self.call('/api/evidence',bad)[0])
        self.assertEqual(404,self.call('/api/evidence',self.body(version=99))[0])
        self.assertEqual(400,self.call('/api/evidence',self.body(version=True))[0])
        unavailable=deepcopy(config);unavailable['evidence'][0]['availability']='unavailable';unavailable['capabilities']=[]
        IntegrationRepository(self.store).append('owner','saas-a',unavailable,1)
        self.assertEqual(400,self.call('/api/evidence',self.body(version=2))[0])
        # A generic string declaration cannot bypass envelope/payload time consistency.
        string_time=deepcopy(config)
        string_time['events'][0]['fields'][1]['type']='string'
        IntegrationRepository(self.store).append('owner','saas-a',string_time,2)
        row=event(string_time);row['payload']['occurred_at']='2026-01-01T00:00:00Z'
        self.assertEqual(400,self.call('/api/evidence',self.body([row],version=3))[0])
        row['payload']['occurred_at']=MOMENT
        self.assertEqual(200,self.call('/api/evidence',self.body([row],version=3))[0])

    def test_timestamp_canonicalization_and_number_equivalence_are_not_false_conflicts(self):
        self.login();config=deepcopy(self.configs['saas-a']);config['metrics'][0]['value_type']='number'
        IntegrationRepository(self.store).append('owner','saas-a',config,1)
        row=metric(config,value=3.0)
        first=self.call('/api/evidence',self.body([row],version=2))[1]
        row['payload']['value']=3;row['occurred_at']=MOMENT.replace('Z','+00:00')
        row['period']['end']=MOMENT.replace('Z','+00:00')
        second=self.call('/api/evidence',self.body([row],version=2))[1]
        self.assertEqual(first['batch_id'],second['batch_id']);self.assertTrue(second['reused'])
        self.assertEqual([],self.view(version=2)[1]['quality']['conflicts'])

    def test_pagination_snapshot_is_scoped_and_stable_during_later_ingestion(self):
        self.login();config=self.configs['saas-a']
        self.call('/api/evidence',self.body([event(config,'event-'+str(i)) for i in range(3)]))
        first=self.view(limit=1)[1];self.assertEqual(1,len(first['records']));self.assertIsNotNone(first['next_after'])
        self.call('/api/evidence',self.body([event(config,'new-later')]))
        second=self.view(after=first['next_after'],through=first['through'],limit=100)[1]
        self.assertEqual(2,len(second['records']));self.assertIsNone(second['next_after'])
        self.assertEqual(4,len(self.view()[1]['records']))
        for query in ('tenant=saas-a','tenant=saas-a&customer=client-1&config_version=1&config_version=2',
                      'tenant=saas-a&customer=client-1&config_version=1&limit=101',
                      'tenant=saas-a&customer=client-1&config_version=1&after=-1',
                      'tenant=saas-a&customer=client-1&config_version=1&limit=NaN',
                      'tenant=saas-a&customer=client-1&config_version=1&unknown=x'):
            self.assertEqual(400,self.call('/api/evidence/view?'+query)[0])

    def test_limits_http_formats_methods_preflight_and_no_secret_leak(self):
        self.login()
        for raw in (b'{"tenant":"saas-a","tenant":"saas-b"}',b'{"x":NaN}',b'[]',b'\xff',b'['*1100+b'0'+b']'*1100):
            self.assertEqual(400,self.call('/api/evidence',raw=raw)[0])
        self.assertEqual(413,self.call('/api/evidence',raw=b' '*65537)[0])
        self.assertEqual(415,self.call('/api/evidence',self.body(),headers={'Content-Type':'text/plain'})[0])
        self.assertEqual(415,self.call('/api/evidence',self.body(),headers={'Content-Encoding':'gzip'})[0])
        too_many=self.body([event(self.configs['saas-a'],str(i)) for i in range(101)])
        self.assertEqual(400,self.call('/api/evidence',too_many)[0])
        for path,method in (('/api/evidence','GET'),('/api/evidence/view','POST'),('/api/evidence','DELETE')):
            self.assertEqual(405,self.call(path,method=method)[0])
        self.assertEqual(204,self.call('/api/evidence',method='OPTIONS',headers={'Access-Control-Request-Method':'POST'})[0])
        with patch('sys.stderr',new_callable=io.StringIO) as logs:
            result=self.call('/api/evidence?secret=do-not-log',self.body())
            self.assertEqual(400,result[0]);self.assertNotIn('do-not-log',logs.getvalue()+json.dumps(result[1]))
        # Exercise the documented resource boundary, not a reduced mocked quota.
        first_batch=None
        for offset in range(0,1000,100):
            batch=self.body([event(self.configs['saas-a'],'quota-'+str(i)) for i in range(offset,offset+100)])
            first_batch=first_batch or batch
            self.assertEqual(100,self.call('/api/evidence',batch)[1]['inserted'])
        self.assertEqual((1000,10),self.counts())
        self.assertEqual(413,self.call('/api/evidence',self.body([event(self.configs['saas-a'],'over-quota')]))[0])
        self.assertTrue(self.call('/api/evidence',first_batch)[1]['reused'])
        self.assertEqual((1000,10),self.counts())

    def test_different_metric_periods_and_complementary_fields_are_not_contradictions(self):
        self.login();config=deepcopy(self.configs['saas-a'])
        config['evidence'][0]['fields'].append({'name':'note','type':'string','required':False})
        IntegrationRepository(self.store).append('owner','saas-a',config,1)
        first=metric(config,'period-a',3);second=metric(config,'period-b',4)
        second['period']['start']='2025-12-31T00:00:00Z'
        base=evidence(config,'snapshot-a');extra=evidence(config,'snapshot-b');extra['payload']['note']='Additional declared context'
        self.assertEqual(200,self.call('/api/evidence',self.body([first,second,base,extra],version=2))[0])
        self.assertEqual([],self.view(version=2)[1]['quality']['conflicts'])

    def test_per_record_size_and_noncanonical_framing_are_rejected(self):
        self.login();config=deepcopy(self.configs['saas-a'])
        config['evidence'][0]['fields'] += [{'name':'text'+str(i),'type':'string','required':False} for i in range(5)]
        IntegrationRepository(self.store).append('owner','saas-a',config,1)
        record=evidence(config);record['payload'].update({'text'+str(i):'x'*1800 for i in range(5)})
        self.assertEqual(413,self.call('/api/evidence',self.body([record],version=2))[0])
        self.assertEqual((0,0),self.counts())
        self.assertEqual(400,self.call('/api/evidence',self.body(),headers={'Content-Length':'+5'})[0])
        self.assertEqual(400,self.call('/api/evidence',self.body(),headers={'Transfer-Encoding':'chunked'})[0])

    def test_concurrent_duplicate_ingestion_is_single_persisted_record_and_batch(self):
        # Internal callers use the same authorized repository and SQLite transaction boundary.
        repository=EvidenceRepository(self.store);body=self.body()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:repository.ingest('owner',body),range(2)))
        self.assertEqual([False,True],sorted(r['reused'] for r in results));self.assertEqual((1,1),self.counts())

    def test_sql_failure_rolls_back_and_integrity_failures_never_repair_or_return_data(self):
        self.login()
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER qa_batch_failure BEFORE INSERT ON evidence_batches BEGIN SELECT RAISE(ABORT,'private-marker'); END")
        with patch('sys.stderr',new_callable=io.StringIO) as logs:
            status,result,_=self.call('/api/evidence',self.body())
            self.assertEqual(500,status);self.assertNotIn('private-marker',logs.getvalue()+json.dumps(result))
        self.assertEqual((0,0),self.counts())
        with self.store.transaction() as db: db.execute('DROP TRIGGER qa_batch_failure')
        self.call('/api/evidence',self.body())
        with self.store.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM evidence_items')
            db.execute('DROP TRIGGER evidence_immutable_evidence_items_UPDATE')
        self.assertEqual(503,self.view()[0])
        with self.store.transaction() as db:
            db.execute("UPDATE evidence_items SET payload='{}'")
            db.execute(GUARDS['evidence_immutable_evidence_items_UPDATE'])
        self.assertEqual(503,self.view()[0]);self.assertEqual(503,self.call('/api/evidence',self.body())[0])
        with self.store.transaction() as db: self.assertEqual('{}',db.execute('SELECT payload FROM evidence_items').fetchone()[0])

    def test_production_business_remains_disabled_and_evidence_survives_reopening(self):
        self.login();self.call('/api/evidence',self.body())
        before=self.view()[1]
        reopened=EvidenceRepository(Store.open_existing(self.path)).query('owner','saas-a','client-1',1)
        self.assertEqual(before,reopened)
        self.assertEqual([],self.call('/api/view')[1]['registry'])
        for path in ('/api/advance','/api/execute','/api/verify','/api/simulate-usage'):
            self.assertEqual(503,self.call(path,{'tenant':'saas-a','customer':'client-1','case_id':'none'})[0])
        self.assertEqual(503,self.call('/api/customers',{'tenant':'saas-a','customer':'client-1','name':'blocked'})[0])
        self.assertEqual(503,self.call('/api/observations',{'tenant':'saas-a','customer':'client-1','observations':[]})[0])
        with self.store.transaction() as db:
            for table in BUSINESS_TABLES: self.assertEqual(0,db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])


class EvidenceSetupTests(unittest.TestCase):
    def test_optional_storage_is_never_created_by_http_and_sandbox_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'sandbox.sqlite3';store=Store(path)
            server=make_server(store,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin=f'http://127.0.0.1:{server.server_port}'
            client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def call(route,body=None):
                request=Request(origin+route,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json'})
                try: response=client.open(request)
                except HTTPError as error: response=error
                with response: return response.status,json.loads(response.read())
            try:
                call('/api/login',{'user':'demo','password':'centerway-local'})
                before=Core(store).view('demo')
                self.assertEqual(503,call('/api/evidence/view?tenant=atlas&customer=test&config_version=1')[0])
                with store.transaction() as db:
                    self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'evidence_*'").fetchone())
                install_integrations(store);config=load(ROOT/'examples/integrations/collaboration.json');config['tenant']='atlas'
                IntegrationRepository(store).append('demo','atlas',config,0);install_evidence(store)
                body=json.loads((ROOT/'examples/evidence/collaboration-batch.json').read_text())
                body['tenant']='atlas'
                schema=SPEC['components']['schemas']['EvidenceIngestRequest']
                Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker()).validate(body)
                self.assertEqual(200,call('/api/evidence',body)[0])
                self.assertEqual('synthetic',call('/api/evidence/view?tenant=atlas&customer=fictional-account&config_version=1')[1]['classification'])
                self.assertEqual(before,Core(store).view('demo'))
                self.assertEqual(200,call('/api/view')[0])
                with self.assertRaises(ValueError): install_evidence(store)
            finally: server.shutdown();server.server_close();thread.join()

    def test_private_demo_expiry_remains_enforced_for_evidence(self):
        from centerway.preview import provision as provision_demo
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'demo.sqlite3'
            provision_demo(path,root/'credentials.json','https://demo.example.invalid')
            store=Store.open_existing(path);install_integrations(store)
            config=load(ROOT/'examples/integrations/collaboration.json');config['tenant']='atlas'
            IntegrationRepository(store).append('founder','atlas',config,0);install_evidence(store)
            repository=EvidenceRepository(store)
            body={'tenant':'atlas','customer':'c','config_version':1,'records':[evidence(config)]}
            repository.ingest('founder',body)
            with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
            for operation in (lambda:repository.query('founder','atlas','c',1),lambda:repository.ingest('founder',body)):
                with self.assertRaises(Problem) as error: operation()
                self.assertEqual(503,error.exception.status)
