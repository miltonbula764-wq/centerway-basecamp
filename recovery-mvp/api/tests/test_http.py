"""Real HTTP sockets and real PostgreSQL logins. No business engine is mocked."""
import concurrent.futures
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app, Database, APIError
from demo.provision import provision,T,B,C,C2,BC
from werkzeug.serving import make_server

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.credentials = provision(os.environ['CW_HTTP_CONTAINER'],os.environ['CW_HTTP_PORT'],os.environ['CW_HTTP_STATE'])
        cls.app=create_app(cls.config)
        cls.server=make_server('127.0.0.1',0,cls.app,threaded=True)
        cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.tokens={}
        for username in ('alice','bob','reader'):
            status,_,body=cls.http('POST','/v1/sessions',dict(username=username,password=cls.credentials[username]))
            assert status==201,body
            cls.tokens[username]=body['access_token']
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=5)
    @classmethod
    def http(cls,method,path,data=None,token=None,headers=None,raw=None):
        h={'Content-Type':'application/json'}
        if token: h['Authorization']='Bearer '+token
        h.update(headers or {})
        connection=http.client.HTTPConnection('127.0.0.1',cls.port,timeout=25)
        connection.request(method,path,body=raw if raw is not None else json.dumps(data) if data is not None else None,headers=h)
        response=connection.getresponse(); payload=response.read(); result=(response.status,dict(response.headers),json.loads(payload) if payload else None)
        connection.close(); return result
    def route(self,tenant=T,client=C,kind='journey'):
        return f'/v1/tenants/{tenant}/clients/{client}/{kind}'
    def command(self,**changes):
        return dict(request_id=str(uuid.uuid4()),operation='append_value',arguments=dict(kind='source',id=str(uuid.uuid4()),expected_revision=0,reason='SYNTHETIC HTTP test',data=dict(name='SYNTHETIC source',locator='synthetic://http-test',method='manual'))) | changes

    def test_authentication_session_logout_and_secret_storage(self):
        self.assertEqual(self.http('GET',self.route())[0],401)
        status,headers,result=self.http('POST','/v1/sessions',dict(username='alice',password=self.credentials['alice']))
        self.assertEqual(status,201); token=result['access_token']
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertNotIn('Set-Cookie',headers)
        self.assertEqual(self.http('GET','/v1/session',token=token)[2]['principal'],'http_alice')
        with sqlite3.connect(self.config['session_db']) as db:
            self.assertIsNone(db.execute('SELECT digest FROM sessions WHERE digest=?',(token,)).fetchone())
            self.assertIsNotNone(db.execute('SELECT digest FROM sessions WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone())
        self.assertEqual(self.http('DELETE','/v1/session',token=token)[0],204)
        self.assertEqual(self.http('GET','/v1/session',token=token)[0],401)
        self.assertEqual(self.http('POST','/v1/sessions',dict(username='alice',password='wrong'))[2],{'error':{'code':'invalid_credentials'}})
        self.assertEqual(self.http('POST','/v1/sessions',dict(username='unknown',password='wrong'))[0],401)

    def test_client_tenant_and_sensitive_operation_permissions(self):
        self.assertEqual(self.http('GET',self.route(),token=self.tokens['alice'])[0],200)
        self.assertEqual(self.http('GET',self.route(T,C2),token=self.tokens['alice'])[0],403)
        self.assertEqual(self.http('GET',self.route(B,BC),token=self.tokens['alice'])[0],403)
        self.assertEqual(self.http('GET',self.route(),token=self.tokens['bob'])[0],403)
        self.assertEqual(self.http('POST',self.route(kind='operations'),self.command(),token=self.tokens['reader'])[0],403)
        discovery=self.command(operation='discover_company',arguments={'as_of':'2026-01-01T00:00:00Z'})
        self.assertEqual(self.http('POST',self.route(kind='operations'),discovery,token=self.tokens['alice'])[0],403)
        self.assertEqual(self.http('POST',self.route(kind='operations'),self.command(operation='grant_policy'),token=self.tokens['alice'])[0],422)

    def test_cors_and_transport_validation(self):
        self.assertEqual(self.http('GET',self.route(),token=self.tokens['alice'],headers={'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.http('POST','/v1/sessions',{},headers={'Origin':'null'})[0],403)
        status,headers,_=self.http('OPTIONS',self.route(),headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization'})
        self.assertEqual(status,204); self.assertEqual(headers['Access-Control-Allow-Origin'],'http://localhost:5173')
        self.assertNotIn('Access-Control-Allow-Credentials',headers)
        self.assertEqual(self.http('OPTIONS',self.route(),headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'PATCH'})[0],403)
        for raw in ['{"username":"alice","username":"bob"}', '{"password":NaN}', '[]', '{broken']:
            self.assertIn(self.http('POST','/v1/sessions',raw=raw)[0],(400,422))
        self.assertEqual(self.http('POST','/v1/sessions',raw='x'*70000)[0],413)
        self.assertEqual(self.http('POST','/v1/sessions',raw='x',headers={'Content-Type':'text/plain'})[0],415)
        invalid=self.command(); invalid['principal']='postgres'
        self.assertEqual(self.http('POST',self.route(kind='operations'),invalid,token=self.tokens['alice'])[0],422)
        self.assertEqual(self.http('GET',self.route('not-a-uuid',C),token=self.tokens['alice'])[0],422)

    def test_expiry_and_identity_mismatch_fail_closed(self):
        status,_,body=self.http('POST','/v1/sessions',dict(username='alice',password=self.credentials['alice']))
        self.assertEqual(status,201)
        token=body['access_token']
        with sqlite3.connect(self.config['session_db']) as db:
            db.execute('UPDATE sessions SET expires=0 WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),))
        self.assertEqual(self.http('GET','/v1/session',token=token)[0],401)
        user=copy.deepcopy(self.config['users']['alice']); user['principal']='http_bob'
        with self.assertRaises(APIError) as caught: Database(True).call(user,'identity')
        self.assertEqual(caught.exception.code,'database_identity_rejected')
        password=secrets.token_urlsafe(32)
        result=subprocess.run(['docker','exec','-i',os.environ['CW_HTTP_CONTAINER'],'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres'],input=f"CREATE ROLE http_unsafe LOGIN CREATEROLE PASSWORD '{password}' IN ROLE centerway_api;",text=True,capture_output=True)
        self.assertEqual(result.returncode,0,'unsafe negative-test role provisioning failed')
        user['principal']='http_unsafe'
        user['dsn']=f"host=127.0.0.1 port={os.environ['CW_HTTP_PORT']} user=http_unsafe dbname=postgres password={password}"
        with self.assertRaises(APIError): Database(True).call(user,'identity')
        with self.assertRaises(APIError): Database(False).call(self.config['users']['alice'],'identity')

    def test_operations_audit_idempotency_errors_and_concurrency(self):
        payload=self.command()
        def submit(_): return self.http('POST',self.route(kind='operations'),payload,token=self.tokens['alice'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(submit,range(2)))
        self.assertEqual([x[0] for x in results],[200,200])
        self.assertEqual(results[0][2],results[1][2])
        receipt=results[0][2]['data']
        self.assertEqual(receipt['actor'],'http_alice'); self.assertEqual(receipt['result']['actor'],'http_alice')
        self.assertTrue(results[0][2]['demo'])
        import psycopg
        with psycopg.connect(self.config['users']['alice']['dsn']) as db:
            row=db.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(payload['request_id'],)).fetchone()
            self.assertEqual(row[0],1)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute('INSERT INTO centerway.intervention_policies DEFAULT VALUES')
        changed=copy.deepcopy(payload); changed['arguments']['reason']='different'
        self.assertEqual(self.http('POST',self.route(kind='operations'),changed,token=self.tokens['alice'])[0],409)
        invalid=self.command(); invalid['arguments']['data']['actor']='postgres'
        status,_,result=self.http('POST',self.route(kind='operations'),invalid,token=self.tokens['alice'])
        self.assertEqual(status,422); self.assertEqual(result['data']['status'],'error')
        self.assertNotIn('message',result['data']['result'])
        leaked=json.dumps(result)
        self.assertNotIn('password=',leaked); self.assertNotIn('CONTEXT:',leaked)
        journey=self.http('GET',self.route(),token=self.tokens['alice'])[2]['data']
        failed=next(x for x in journey['operations'] if x['request_id']==invalid['request_id'])
        self.assertNotIn('message',failed['result'])

    def test_session_config_changes_invalidate_old_tokens(self):
        altered=copy.deepcopy(self.config)
        altered['users']['alice']['operations']=[]
        application=create_app(altered)
        response=application.test_client().get('/v1/session',headers={'Authorization':'Bearer '+self.tokens['alice']})
        self.assertEqual(response.status_code,401)

    def test_zlogin_rate_limit(self):
        codes=[self.http('POST','/v1/sessions',dict(username='nobody',password='wrong'))[0] for _ in range(11)]
        self.assertIn(429,codes)

if __name__=='__main__': unittest.main()
