"""Local verified HTTPS and signed TEST sources only; no real supplier integration."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import hmac
import http.client
import io
import json
import secrets
import sqlite3
import ssl
import subprocess
import threading
import time
from unittest.mock import patch
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from jsonschema import Draft202012Validator,FormatChecker

from centerway.evidence import EvidenceRepository
from centerway.integrations import IntegrationRepository,canonical
from centerway.production import ProductionPolicy,BUSINESS_TABLES
from centerway.server import make_server
from centerway.webhooks import PATH,install,load_config,signed_bytes,GUARDS
import test_evidence as base


class WebhookTests(unittest.TestCase):
    setUpClass=classmethod(base.EvidenceApiTests.setUpClass.__func__)
    tearDownClass=classmethod(base.EvidenceApiTests.tearDownClass.__func__)
    new_client=base.EvidenceApiTests.new_client
    def setUp(self):
        base.EvidenceApiTests.setUp(self)
        self.server.shutdown();self.server.server_close();self.thread.join()
        install(self.store)
        self.secret=secrets.token_bytes(32);self.secret_path=self.root/'source.key'
        self.secret_path.write_text(self.secret.hex()+'\n');self.secret_path.chmod(0o600)
        snapshot=IntegrationRepository(self.store).get('owner','saas-a');config=snapshot['config']
        self.source={'id':'test-source-a','tenant':'saas-a','config_version':1,'config_hash':snapshot['content_hash'],'mapping_version':1,
                     'classification':'declared','customers':{'external-1':'client-1','external-2':'client-2'},
                     'routes':{
                         'completed':{'kind':'event','definition_id':config['events'][0]['id'],'source_ref':config['events'][0]['source_ref'],
                                      'fields':{'account_id':'$customer','occurred_at':'$occurred_at'}},
                         'count':{'kind':'metric','definition_id':config['metrics'][0]['id'],'source_ref':config['metrics'][0]['source_ref'],'fields':{'value':'data.total'}},
                         'paused':{'kind':'evidence','definition_id':config['evidence'][0]['id'],'source_ref':config['evidence'][0]['source_ref'],'fields':{'paused':'data.flag'}},
                     },'keys':[{'id':'key-1','secret_file':str(self.secret_path),'not_before':int(time.time())-100,'expires_at':int(time.time())+3600}]}
        self.configuration={'schema_version':1,'mode':'production','sources':[self.source]}
        self.config_file=self.root/'webhooks.json';self.save();self.start()
    def save(self):
        self.config_file.write_text(canonical(self.configuration));self.config_file.chmod(0o600)
    def start(self):
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=int(self.origin.rsplit(':',1)[1]),preview=ProductionPolicy(self.store),tls_context=tls,webhook_config=self.config_file)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    tearDown=base.EvidenceApiTests.tearDown
    def message(self,**changes):
        return {'mapping_version':1,'config_version':1,'customer_id':'external-1','event_type':'completed','event_id':'event-1',
                'occurred_at':base.MOMENT,'period':None,'data':{},**changes}
    def signed(self,body=None,raw=None,*,source='test-source-a',key='key-1',stamp=None,nonce=None,secret=None):
        raw=raw if raw is not None else json.dumps(body or self.message(),ensure_ascii=False).encode()
        stamp=str(int(time.time()) if stamp is None else stamp);nonce=nonce or secrets.token_hex(16)
        signature='v1='+hmac.new(secret or self.secret,signed_bytes(source,key,stamp,nonce,raw),hashlib.sha256).hexdigest()
        return raw,{'X-CW-Source':source,'X-CW-Key-Id':key,'X-CW-Timestamp':stamp,'X-CW-Nonce':nonce,'X-CW-Signature':signature}
    def call(self,signed=None,*,headers=None,path=PATH,method='POST'):
        raw,auth=signed or self.signed()
        request=Request(self.origin+path,raw if method=='POST' else None,{'Content-Type':'application/json',**auth,**(headers or {})},method=method)
        try: response=self.new_client().open(request,timeout=20)
        except HTTPError as error: response=error
        with response:
            result=json.loads(response.read());self.assertNotIn('Access-Control-Allow-Origin',response.headers)
            if path==PATH and method=='POST':
                spec=base.SPEC;node=spec['paths'][PATH]['post']['responses'][str(response.status)]
                if '$ref' in node: node=spec['components']['responses'][node['$ref'].split('/')[-1]]
                schema=node['content']['application/json']['schema']
                Draft202012Validator({**schema,'components':spec['components']},format_checker=FormatChecker()).validate(result)
            return response.status,result
    def count(self,table):
        with self.store.transaction() as db: return db.execute('SELECT count(*) FROM '+table).fetchone()[0]

    def test_verified_https_no_session_m07_provenance_and_inactive_production(self):
        status,reply=self.call();self.assertEqual(200,status);self.assertEqual('source_claim',reply['claim_classification'])
        self.assertEqual('inactive',reply['operational_state']);self.assertEqual(1,reply['inserted'])
        with self.store.transaction() as db:
            item=dict(db.execute('SELECT * FROM evidence_items').fetchone());receipt=dict(db.execute('SELECT * FROM webhook_receipts').fetchone())
            self.assertEqual('webhook:test-source-a',item['actor']);self.assertEqual('saas-a',item['tenant']);self.assertEqual('client-1',item['customer'])
            self.assertEqual(self.source['config_hash'],item['config_hash']);self.assertEqual('[1]',receipt['evidence_ids'])
            for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
            self.assertIsNone(db.execute("SELECT 1 FROM users WHERE id='webhook:test-source-a'").fetchone())
        for path in ('/api/evidence/view?tenant=saas-a&customer=client-1&config_version=1','/api/orchestration/cases?tenant=saas-a','/api/view'):
            self.assertEqual(401,self.call(path=path,method='GET')[0])
        self.assertEqual(403,self.call(path='/api/execute')[0])
        self.client=self.new_client();self.assertEqual(200,base.EvidenceApiTests.call(self,'/api/login',{'user':'owner','password':self.passwords['owner']})[0])
        self.assertEqual(503,base.EvidenceApiTests.call(self,'/api/advance',{'tenant':'saas-a','customer':'client-1'})[0])

    def test_original_bytes_and_all_signed_headers_bound(self):
        signed=self.signed(raw=json.dumps(self.message(),indent=2).encode());self.assertEqual(200,self.call(signed)[0])
        self.assertEqual(401,self.call((json.dumps(self.message()).encode(),signed[1]))[0])
        for header,value in [('X-CW-Source','unknown'),('X-CW-Key-Id','missing'),('X-CW-Nonce','changed_nonce_123456'),('X-CW-Timestamp',str(int(time.time())+1)),('X-CW-Signature','v1='+'0'*64)]:
            self.assertEqual(401,self.call((signed[0],{**signed[1],header:value}))[0])
        self.assertEqual(1,self.count('evidence_items'));self.assertEqual(1,self.count('webhook_receipts'))

    def test_exact_retry_nonce_conflict_deduplication_and_restart(self):
        signed=self.signed();first=self.call(signed);self.assertEqual(first,self.call(signed))
        changed=self.signed(self.message(event_id='changed'),nonce=signed[1]['X-CW-Nonce'],stamp=signed[1]['X-CW-Timestamp'])
        self.assertEqual(409,self.call(changed)[0]);self.assertEqual(1,self.count('evidence_items'))
        result=self.call(self.signed());self.assertEqual(200,result[0]);self.assertEqual(0,result[1]['inserted']);self.assertEqual(1,result[1]['duplicates'])
        self.server.shutdown();self.server.server_close();self.thread.join();self.start()
        self.assertEqual(first,self.call(signed));self.assertEqual(1,self.count('evidence_items'))

    def test_stale_future_missing_unknown_signatures_never_write(self):
        for signed in (self.signed(stamp=int(time.time())-600),self.signed(stamp=int(time.time())+600),self.signed(source='unknown'),self.signed(key='unknown'),(b'{}',{})):
            self.assertEqual(401,self.call(signed)[0])
        self.assertEqual(0,self.count('webhook_receipts'));self.assertEqual(0,self.count('evidence_items'))

    def test_rotation_overlap_expiry_revocation_and_key_id_reuse(self):
        self.assertEqual(200,self.call()[0]);second=secrets.token_bytes(32);path=self.root/'key2'
        path.write_text(second.hex());path.chmod(0o600)
        key2={**self.source['keys'][0],'id':'key-2','secret_file':str(path)};self.source['keys'].append(key2);self.save()
        self.assertEqual(200,self.call(self.signed(key='key-2',secret=second))[0]);self.assertEqual(200,self.call()[0])
        self.source['keys']=[key2];self.save();self.assertEqual(401,self.call()[0]);self.assertEqual(200,self.call(self.signed(key='key-2',secret=second))[0])
        path.write_text(secrets.token_hex(32));new=bytes.fromhex(path.read_text());self.assertEqual(409,self.call(self.signed(key='key-2',secret=new))[0])
        key2['expires_at']=int(time.time())-1;key2['not_before']=int(time.time())-100;self.save()
        self.assertEqual(401,self.call(self.signed(key='key-2',secret=new))[0])

    def test_scope_claims_unknown_customer_and_source_reference(self):
        for body,status in [(self.message(tenant='saas-b'),400),(self.message(customer_id='client-1'),403),(self.message(event_type='execute'),400),(self.message(data={'tenant':'saas-b'}),400)]:
            signed=self.signed(body);self.assertEqual(status,self.call(signed)[0]);self.assertEqual(status,self.call(signed)[0])
        self.assertEqual(0,self.count('evidence_items'))
        self.source['routes']['completed']['source_ref']='unregistered-source';self.source['mapping_version']=2;self.save()
        self.assertEqual(400,self.call(self.signed(self.message(mapping_version=2)))[0]);self.assertEqual(0,self.count('evidence_items'))

    def test_record_kinds_preserve_conflicting_claims(self):
        self.assertEqual(200,self.call()[0]);body=self.message(event_type='count',event_id='metric-1',period=base.PERIOD,data={'total':3})
        self.assertEqual(200,self.call(self.signed(body))[0]);self.assertEqual(200,self.call(self.signed({**body,'event_id':'metric-2','data':{'total':8}}))[0])
        self.assertEqual(409,self.call(self.signed({**body,'data':{'total':9}}))[0])
        self.assertEqual(200,self.call(self.signed(self.message(event_type='paused',event_id='ev-1',data={'flag':True})))[0])
        result=EvidenceRepository(self.store).query('owner','saas-a','client-1',1)
        self.assertTrue(result['quality']['conflicts']);self.assertEqual(4,self.count('evidence_items'))

    def test_contract_versions_types_future_period_and_strict_json(self):
        for body,status in [(self.message(config_version=2),409),(self.message(mapping_version=True),409),
                (self.message(event_type='count',period=base.PERIOD,data={'total':'not-number'}),400),
                (self.message(occurred_at='2099-01-01T00:00:00Z'),400),(self.message(period=base.PERIOD),400)]: self.assertEqual(status,self.call(self.signed(body))[0])
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'[]',b'\xff'): self.assertEqual(400,self.call(self.signed(raw=raw))[0])
        self.assertEqual(0,self.count('evidence_items'));self.call();self.source['customers']['extra']='client-3';self.save()
        self.assertEqual(409,self.call()[0]);self.source['mapping_version']=2;self.save()
        self.assertEqual(200,self.call(self.signed(self.message(mapping_version=2)))[0])
        snapshot=IntegrationRepository(self.store).get('owner','saas-a');config=deepcopy(snapshot['config']);config['product']['description']='New explicit configuration.'
        IntegrationRepository(self.store).append('owner','saas-a',config,1)
        self.assertEqual(409,self.call(self.signed(self.message(mapping_version=2)))[0])

    def test_independent_sources_tenants_and_customers(self):
        second=deepcopy(self.source);snapshot=IntegrationRepository(self.store).get('owner','saas-b')
        second.update(id='test-source-b',tenant='saas-b',config_hash=snapshot['content_hash'])
        secret_b=secrets.token_bytes(32);path_b=self.root/'source-b.key';path_b.write_text(secret_b.hex());path_b.chmod(0o600)
        second['keys'][0]['secret_file']=str(path_b)
        second['routes']={'completed':{'kind':'event','definition_id':snapshot['config']['events'][0]['id'],'source_ref':snapshot['config']['events'][0]['source_ref'],'fields':{'account_id':'$customer','occurred_at':'$occurred_at'}}}
        self.configuration['sources'].append(second);self.save()
        self.assertEqual(200,self.call()[0]);self.assertEqual(200,self.call(self.signed(source='test-source-b',secret=secret_b))[0])
        self.assertEqual(200,self.call(self.signed(self.message(customer_id='external-2')))[0])
        with self.store.transaction() as db: self.assertEqual([('saas-a','client-1'),('saas-b','client-1'),('saas-a','client-2')],[tuple(r) for r in db.execute('SELECT tenant,customer FROM evidence_items ORDER BY id')])
        second['tenant']='saas-a';self.save();self.assertEqual(409,self.call(self.signed(source='test-source-b',secret=secret_b))[0])

    def test_historical_source_and_key_material_cannot_be_reassigned(self):
        self.assertEqual(200,self.call()[0])
        second=deepcopy(self.source);second['id']='replacement-source'
        fresh=secrets.token_bytes(32);path=self.root/'fresh.key';path.write_text(fresh.hex());path.chmod(0o600)
        second['keys'][0]['secret_file']=str(path)
        self.configuration['sources']=[second];self.save()
        self.assertEqual(409,self.call(self.signed(source='replacement-source',secret=fresh))[0])
        snapshot=IntegrationRepository(self.store).get('owner','saas-b')
        second.update(tenant='saas-b',config_hash=snapshot['content_hash'])
        second['routes']={'completed':{'kind':'event','definition_id':snapshot['config']['events'][0]['id'],'source_ref':snapshot['config']['events'][0]['source_ref'],'fields':{'account_id':'$customer','occurred_at':'$occurred_at'}}}
        second['keys'][0]['secret_file']=str(self.secret_path);self.save()
        self.assertEqual(409,self.call(self.signed(source='replacement-source'))[0]);self.assertEqual(1,self.count('evidence_items'))

    def test_concurrent_duplicates_and_failure_rollback(self):
        signed=self.signed()
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(lambda _:self.call(signed),range(4)))
        self.assertTrue(all(r==results[0] for r in results));self.assertEqual(1,self.count('evidence_items'));self.assertEqual(1,self.count('webhook_receipts'))
        original=EvidenceRepository._ingest
        def fail(repo,db,*args): original(repo,db,*args);raise sqlite3.OperationalError('SENSITIVE failure')
        with patch.object(EvidenceRepository,'_ingest',fail): self.assertEqual(500,self.call(self.signed(self.message(event_id='atomic-new')))[0])
        self.assertEqual(1,self.count('evidence_items'));self.assertEqual(1,self.count('webhook_receipts'))
        self.assertEqual(200,self.call(self.signed(self.message(event_id='atomic-new')))[0])

    def test_http_framing_browser_restrictions_and_no_tls_fallback(self):
        for headers,status in [({'Cookie':'untrusted=secret'},403),({'Origin':self.origin},403),({'Sec-Fetch-Site':'same-origin'},403),
                               ({'Transfer-Encoding':'chunked'},400),({'Content-Encoding':'gzip'},415),({'Content-Type':'text/plain'},415)]: self.assertEqual(status,self.call(headers=headers)[0])
        self.assertEqual(405,self.call(method='GET')[0]);self.assertEqual(400,self.call(path=PATH+'?tenant=saas-b')[0])
        self.assertEqual(413,self.call(self.signed(raw=b'a'*65537))[0])
        tls=ssl.create_default_context(cafile=str(self.cert));conn=http.client.HTTPSConnection('127.0.0.1',int(self.origin.rsplit(':',1)[1]),context=tls)
        raw,headers=self.signed();conn.putrequest('POST',PATH);conn.putheader('Content-Length',str(len(raw)));conn.putheader('Content-Length',str(len(raw)));conn.putheader('Content-Type','application/json')
        for k,v in headers.items(): conn.putheader(k,v)
        conn.endheaders(raw);response=conn.getresponse();self.assertEqual(400,response.status);response.read();conn.close()
        with self.assertRaises(ValueError): make_server(self.store,webhook_config=self.config_file)
        self.assertEqual(0,self.count('evidence_items'))

    def test_private_files_integrity_limits_and_sanitized_logs(self):
        self.config_file.chmod(0o644);self.assertEqual(503,self.call()[0]);self.save()
        self.secret_path.chmod(0o644);self.assertEqual(503,self.call()[0]);self.secret_path.chmod(0o600)
        with patch('centerway.webhooks.MAX_PER_MINUTE',1): self.assertEqual(200,self.call()[0]);self.assertEqual(429,self.call()[0])
        raw,headers=self.signed(raw=b'{"sensitive":"DO-NOT-LOG"}')
        with patch('sys.stderr',new_callable=io.StringIO) as output:
            status,reply=self.call((raw,headers));self.assertEqual(400,status);self.assertEqual(401,self.call(headers={'X-CW-Signature':'v1='+'0'*64})[0])
            text=output.getvalue()+json.dumps(reply)
            for value in ('DO-NOT-LOG',self.secret.hex(),headers['X-CW-Signature'],headers['X-CW-Nonce']): self.assertNotIn(value,text)
        with self.store.transaction() as db: db.execute('DROP TRIGGER '+next(iter(GUARDS)))
        self.assertEqual(503,self.call()[0])

    def test_machine_headers_never_authorize_human_api_and_missing_config_is_closed(self):
        _,auth=self.signed()
        for path,body in [('/api/evidence',{'tenant':'saas-a','customer':'client-1','config_version':1,'records':[]}),
                          ('/api/execute',{'tenant':'saas-a','customer':'client-1','case_id':'case'}),
                          ('/api/orchestration/open',{'tenant':'saas-a'})]:
            self.assertEqual(401,base.EvidenceApiTests.call(self,path,body,headers=auth)[0])
        self.assertEqual(0,self.count('evidence_items'))
        self.server.shutdown();self.server.server_close();self.thread.join()
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=int(self.origin.rsplit(':',1)[1]),preview=ProductionPolicy(self.store),tls_context=tls)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.assertEqual(503,self.call()[0]);self.assertEqual(0,self.count('evidence_items'))

    def test_cli_check_and_private_config_validation(self):
        result=subprocess.run(['python','-m','centerway.webhooks','check','--db',self.store.path,'--config',str(self.config_file)],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr);self.assertIn('ready',result.stdout)
        self.assertEqual(0,self.count('webhook_mappings'));self.assertEqual(0,self.count('webhook_keys'))
        self.configuration['sources'].append(deepcopy(self.source));self.save()
        with self.assertRaises(ValueError): load_config(self.config_file)
        self.configuration['sources'].pop()
        duplicate=deepcopy(self.source);duplicate['id']='other-source';duplicate['tenant']='saas-b'
        self.configuration['sources'].append(duplicate);self.save()
        with self.assertRaises(ValueError): load_config(self.config_file)
        self.configuration['sources'].pop();self.source['classification']='test';self.save()
        with self.assertRaises(ValueError): load_config(self.config_file)



class DemoWebhookTests(unittest.TestCase):
    setUpClass=classmethod(base.EvidenceApiTests.setUpClass.__func__)
    tearDownClass=classmethod(base.EvidenceApiTests.tearDownClass.__func__)
    def test_explicit_synthetic_demo_sender_https_and_24h_expiry(self):
        import tempfile,socket
        from pathlib import Path
        from centerway.preview import provision,PreviewPolicy
        from centerway.store import Store
        from centerway.integrations import install as install_config
        from centerway.integration_contract import load
        from centerway.evidence import install as install_evidence
        from centerway.webhooks import WebhookIntake
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'demo.sqlite3'
            with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            origin=f'https://127.0.0.1:{port}';provision(path,root/'human.json',origin,24)
            store=Store.open_existing(path);install_config(store)
            cfg=load(base.ROOT/'examples/integrations/collaboration.json');cfg['tenant']='atlas'
            snapshot=IntegrationRepository(store).append('founder','atlas',cfg,0);install_evidence(store)
            configuration=json.loads((base.ROOT/'examples/webhooks/demo-source.json').read_text());source=configuration['sources'][0]
            source['config_hash']=snapshot['content_hash'];secret=root/'source.key';secret.write_text(secrets.token_hex(32));secret.chmod(0o600)
            source['keys'][0].update(secret_file=str(secret),not_before=int(time.time())-10,expires_at=int(time.time())+3600)
            config=root/'webhooks.json';config.write_text(canonical(configuration));config.chmod(0o600)
            before=None
            with store.transaction() as db: before=[tuple(r) for r in db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
            with self.assertRaises(ValueError): WebhookIntake(store,config)
            with store.transaction() as db: self.assertEqual(before,[tuple(r) for r in db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')])
            install(store)
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key)
            server=make_server(store,port=port,preview=PreviewPolicy(store),tls_context=tls,webhook_config=config)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            command=['python','examples/webhooks/send.py','--url',origin+PATH,'--source',source['id'],'--key-id',source['keys'][0]['id'],'--secret-file',str(secret),
                     '--body-file','examples/webhooks/test-event.json','--ca-file',str(self.cert)]
            try:
                result=subprocess.run(command,capture_output=True,text=True,timeout=20)
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertEqual('acknowledged',json.loads(result.stdout)['delivery'])
                result=subprocess.run(command,capture_output=True,text=True,timeout=20);self.assertEqual(0,result.returncode)
                with store.transaction() as db:
                    self.assertEqual(1,db.execute('SELECT count(*) FROM evidence_items').fetchone()[0]);self.assertEqual(2,db.execute('SELECT count(*) FROM webhook_receipts').fetchone()[0])
                    reply=json.loads(db.execute('SELECT result FROM webhook_receipts LIMIT 1').fetchone()[0]);self.assertEqual('test',reply['source_classification'])
                    self.assertEqual('source_claim',reply['claim_classification'])
                    db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
                result=subprocess.run(command,capture_output=True,text=True,timeout=20);self.assertEqual(1,result.returncode)
                self.assertEqual(503,json.loads(result.stdout)['http_status'])
            finally: server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()
