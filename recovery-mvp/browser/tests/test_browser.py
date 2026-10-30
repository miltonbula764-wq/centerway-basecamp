"""Real TLS sockets with browser request headers; no browser engine or hosted UI claimed."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import subprocess
import ssl
import sys
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra'))
sys.path.insert(0,str(ROOT/'cloud-demo'))
sys.path.insert(0,str(ROOT/'browser'))
from runtime import PersistentDemo
from demo.provision import T,B,C,C2,BC
from app import create_app
from origins import check,validate_origins

ORIGINS=['https://lovable.example.invalid','https://preview.example.invalid']
DIRECTORY=f'/v1/tenants/{T}/clients'
JOURNEY=DIRECTORY+'/'+C+'/journey'
OPERATIONS=DIRECTORY+'/'+C+'/operations'


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='centerway-c04-')
        cls.stack=PersistentDemo(Path(cls.temp.name)/'state',os.environ['CENTERWAY_TEST_CADDY'])
        try:
            cls.stack.initialize(); cls.stack.__enter__()
            cls.stack.stop(cls.stack.api)
            cls.stack.config['origins']=ORIGINS
            (cls.stack.state/'config.json').write_text(json.dumps(cls.stack.config))
            cls.stack.start_api()
            cls.context=ssl.create_default_context(cafile=str(cls.stack.state/'pki'/'ca.crt'))
            cls.tokens={}
            for user in ('alice','reader','reviewer','bob'):
                status,_,body=cls.call('POST','/v1/sessions',dict(username=user,password=cls.stack.credentials[user]))
                if status!=201: raise RuntimeError('Private browser-test login failed')
                cls.tokens[user]=body['access_token']
        except BaseException:
            cls.tearDownClass(); raise

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()
        manifest=cls.stack.state/'manifest.json'
        if manifest.exists():
            m=json.loads(manifest.read_text())
            subprocess.run(['docker','rm','-f',m['container']],capture_output=True)
            for volume in (m['volume'],m['volume']+'-tls'):
                subprocess.run(['docker','volume','rm',volume],capture_output=True)
        cls.temp.cleanup()

    @classmethod
    def call(cls,method,path,data=None,user=None,origin=ORIGINS[0],headers=None):
        h={'Content-Type':'application/json'}
        if origin is not None: h['Origin']=origin
        if user: h['Authorization']='Bearer '+cls.tokens[user]
        h.update(headers or {})
        conn=http.client.HTTPSConnection('localhost',cls.stack.port,context=cls.context,timeout=25)
        try:
            conn.request(method,path,json.dumps(data) if data is not None else None,h)
            r=conn.getresponse(); body=r.read()
            return r.status,dict(r.headers),json.loads(body) if body else None
        finally: conn.close()

    def cors(self,headers,origin=ORIGINS[0]):
        self.assertEqual(headers.get('Access-Control-Allow-Origin'),origin)
        self.assertIn('Origin',headers.get('Vary',''))
        self.assertNotIn('Access-Control-Allow-Credentials',headers)
        self.assertEqual(headers['Cache-Control'],'no-store')

    def test_all_route_preflights_without_authentication(self):
        routes=[('GET','/health'),('POST','/v1/sessions'),('GET','/v1/session'),('DELETE','/v1/session'),('GET',DIRECTORY),('GET',JOURNEY),('POST',OPERATIONS)]
        import psycopg
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            before=db.execute('SELECT count(*) FROM centerway.audit_log').fetchone()[0]
        for origin in ORIGINS:
            for method,path in routes:
                with self.subTest(origin=origin,method=method,path=path):
                    s,h,b=self.call('OPTIONS',path,origin=origin,headers={'Access-Control-Request-Method':method,'Access-Control-Request-Headers':'aUtHoRiZaTiOn, content-type'})
                    self.assertEqual(s,204); self.assertIsNone(b); self.cors(h,origin)
                    self.assertIn(method,h['Access-Control-Allow-Methods'])
                    self.assertEqual(h['Access-Control-Max-Age'],'300')
                    self.assertEqual({x.strip().lower() for x in h['Access-Control-Allow-Headers'].split(',')},{'authorization','content-type'})
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.audit_log').fetchone()[0],before)
        self.assertEqual(self.call('GET',DIRECTORY)[0],401)

    def test_unreviewed_origins_methods_and_headers_fail_closed(self):
        for origin in ('null','*','http://lovable.example.invalid','https://lovable.example.invalid.evil.invalid','https://other.example.invalid',ORIGINS[0]+':8443',ORIGINS[0]+'/',ORIGINS[0]+'/path'):
            for method in ('OPTIONS','GET'):
                s,h,_=self.call(method,DIRECTORY,user='alice',origin=origin,headers={'Access-Control-Request-Method':'GET'})
                self.assertEqual(s,403); self.assertNotIn('Access-Control-Allow-Origin',h)
        for method,headers in [('PATCH','Authorization'),('POST','Authorization'),('GET','Authorization,X-Admin'),('GET','Cookie'),('GET','X-Tenant-Id')]:
            s,_,_=self.call('OPTIONS',DIRECTORY,headers={'Access-Control-Request-Method':method,'Access-Control-Request-Headers':headers})
            self.assertEqual(s,403)
        self.assertEqual(self.call('OPTIONS','/v1/no-route',headers={'Access-Control-Request-Method':'GET'})[0],404)
        self.assertEqual(self.call('GET',DIRECTORY,origin=None)[0],401)
        self.assertEqual(self.call('GET',DIRECTORY,user='alice',origin=None)[0],200)

    def test_sessions_directory_journeys_permissions_logout_and_expiration(self):
        for user in ('alice','reviewer','reader','bob'):
            s,h,b=self.call('GET','/v1/session',user=user)
            self.assertEqual(s,200); self.cors(h); self.assertEqual(b['principal'],'http_'+user)
        for user in ('alice','reviewer','reader'):
            for path in (DIRECTORY,JOURNEY):
                s,h,_=self.call('GET',path,user=user); self.assertEqual(s,200); self.cors(h)
        for user,path in [('bob',DIRECTORY),('alice',f'/v1/tenants/{B}/clients'),('reader',DIRECTORY+'/'+C2+'/journey')]:
            s,h,_=self.call('GET',path,user=user); self.assertEqual(s,403); self.cors(h)
        s,h,b=self.call('GET',f'/v1/tenants/{B}/clients',user='bob',origin=ORIGINS[1])
        self.assertEqual(s,200); self.cors(h,ORIGINS[1]); self.assertEqual(b['data'][0]['client_id'],BC)
        for expire in (False,True):
            s,_,body=self.call('POST','/v1/sessions',dict(username='reader',password=self.stack.credentials['reader']))
            self.assertEqual(s,201)
            headers={'Authorization':'Bearer '+body['access_token']}
            if expire:
                with sqlite3.connect(self.stack.config['session_db']) as db:
                    db.execute('UPDATE sessions SET expires=0 WHERE digest=?',(hashlib.sha256(body['access_token'].encode()).hexdigest(),))
            else:
                s,h,b=self.call('DELETE','/v1/session',headers=headers)
                self.assertEqual(s,204); self.assertIsNone(b); self.cors(h)
            s,h,_=self.call('GET',DIRECTORY,headers=headers); self.assertEqual(s,401); self.cors(h)

    def test_operations_receipts_idempotency_and_cors_errors(self):
        payload=dict(request_id=str(uuid.uuid4()),operation='append_value',arguments=dict(kind='source',id=str(uuid.uuid4()),expected_revision=0,reason='SYNTHETIC C04',data=dict(name='SYNTHETIC C04 source',locator='synthetic://c04',method='SYNTHETIC manual')))
        for user in ('reader','reviewer'):
            s,h,_=self.call('POST',OPERATIONS,payload,user=user); self.assertEqual(s,403); self.cors(h)
        s,h,b=self.call('POST',OPERATIONS,payload,user='alice'); self.assertEqual(s,200); self.cors(h)
        self.assertEqual(b['data']['status'],'completed'); self.assertEqual(b['data']['actor'],'http_alice')
        self.assertEqual(self.call('POST',OPERATIONS,payload,user='alice')[2],b)
        changed=copy.deepcopy(payload); changed['arguments']['reason']='SYNTHETIC conflict'
        s,h,_=self.call('POST',OPERATIONS,changed,user='alice'); self.assertEqual(s,409); self.cors(h)
        invalid=copy.deepcopy(payload); invalid['request_id']=str(uuid.uuid4()); invalid['arguments']['id']=str(uuid.uuid4()); invalid['arguments']['data']={}
        s,h,b=self.call('POST',OPERATIONS,invalid,user='alice'); self.assertEqual(s,422); self.cors(h)
        self.assertEqual(b['data']['status'],'error'); self.assertEqual(b['data']['result']['code'],'engine_rejected')
        import psycopg
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(payload['request_id'],)).fetchone()[0],1)
        with psycopg.connect(self.stack.config['users']['bob']['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.operation_receipts WHERE tenant_id=%s',(T,)).fetchone()[0],0)

    def test_http_errors_remain_readable_for_allowed_origin(self):
        for path,status in [(DIRECTORY,401),('/v1/not-a-route',404),(DIRECTORY+'?limit=101',422)]:
            s,h,b=self.call('GET',path,user=None if status==401 else 'alice')
            self.assertEqual(s,status); self.cors(h); self.assertIn('code',b['error'])
        s,h,_=self.call('POST','/v1/sessions',dict(username='alice',password='SYNTHETIC-invalid'))
        self.assertEqual(s,401); self.cors(h)

    def test_offline_origin_review_blocks_missing_or_mismatched_configuration(self):
        template=json.loads((ROOT/'browser'/'origins.json').read_text())
        with self.assertRaises(ValueError): check(self.stack.config,template)
        # Reserved names exercise parsing only, never authorize actual domains.
        self.assertEqual(validate_origins(ORIGINS,activation=False),ORIGINS)
        for origins in ([],['*'],['null'],['http://ui.example.invalid'],['https://u:p@ui.example.invalid'],['https://ui.example.invalid/path'],['https://ui.example.invalid:443'],['https://UI.example.invalid'],ORIGINS, [ORIGINS[0],ORIGINS[0]]):
            with self.assertRaises(ValueError): validate_origins(origins)
        review=dict(version='c04-origins-v1',origins=['https://ui.centerway-demo.org'])
        config=dict(demo=False,origins=review['origins'])
        check(config,review)  # String syntax only; no DNS or authority asserted.
        with self.assertRaises(ValueError): check(dict(config,origins=['https://other.centerway-demo.org']),review)
        for origins in (['*'],['null'],[ORIGINS[0]+'/path']):
            bad=copy.deepcopy(self.stack.config); bad['origins']=origins
            with self.assertRaises(ValueError): create_app(bad)

    def test_z_database_and_gateway_failure_preflight_behavior(self):
        self.stack.run('docker','stop',self.stack.container)
        try:
            s,h,_=self.call('GET',DIRECTORY,user='alice'); self.assertEqual(s,503); self.cors(h)
            self.assertEqual(self.call('OPTIONS',DIRECTORY,headers={'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization'})[0],204)
        finally:
            self.stack.run('docker','start',self.stack.container)
            for _ in range(60):
                import time
                try:
                    last=self.call('GET',DIRECTORY,user='alice')
                    if last[0]==200: break
                except OSError: pass
                time.sleep(.1)
            else: self.fail('Private database did not recover: '+str(last[2].get('error',{}).get('code')))
        self.stack.stop(self.stack.api)
        try:
            s,h,_=self.call('OPTIONS',DIRECTORY,headers={'Access-Control-Request-Method':'GET'})
            self.assertEqual(s,503); self.assertNotIn('Access-Control-Allow-Origin',h)
        finally: self.stack.start_api()
