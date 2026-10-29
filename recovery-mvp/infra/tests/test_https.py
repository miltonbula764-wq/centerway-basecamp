"""Real Caddy -> Gunicorn HTTPS -> PostgreSQL verify-full, synthetic data only."""
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_stack import LocalStack, ROOT, free_port
from demo.provision import T,B,C,BC

class HTTPSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack=LocalStack(os.environ['CENTERWAY_TEST_CADDY']).__enter__()
        cls.context=ssl.create_default_context(cafile=str(cls.stack.state/'pki'/'ca.crt'))
        cls.tokens={}
        for user in ('alice','bob'):
            status,_,result=cls.call('POST','/v1/sessions',dict(username=user,password=cls.stack.credentials[user]))
            if status!=201: cls.stack.close(); raise RuntimeError('TLS login failed')
            cls.tokens[user]=result['access_token']
    @classmethod
    def tearDownClass(cls): cls.stack.close()
    @classmethod
    def call(cls,method,path,data=None,token=None,headers=None,port=None,context=None):
        h={'Content-Type':'application/json'}
        if token: h['Authorization']='Bearer '+token
        h.update(headers or {})
        conn=http.client.HTTPSConnection('localhost',port or cls.stack.port,context=context or cls.context,timeout=25)
        conn.request(method,path,body=json.dumps(data) if data is not None else None,headers=h)
        response=conn.getresponse(); payload=response.read(); status=response.status; rh=dict(response.headers); conn.close()
        try: result=json.loads(payload) if payload else None
        except ValueError: result=payload.decode()
        return status,rh,result
    def route(self,t=T,c=C,kind='journey'): return f'/v1/tenants/{t}/clients/{c}/{kind}'

    def test_certificate_trust_hostname_and_private_database(self):
        self.assertEqual(self.call('GET','/health')[0],200)
        with self.assertRaises(ssl.SSLError):
            self.call('GET','/health',context=ssl.create_default_context())
        with socket.create_connection(('127.0.0.1',self.stack.port),timeout=5) as raw:
            with self.assertRaises(ssl.SSLError):
                self.context.wrap_socket(raw,server_hostname='wrong.example.invalid')
        import psycopg
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as conn:
            ssl_used=conn.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()[0]
            self.assertTrue(ssl_used)
            self.assertEqual(conn.execute('SELECT session_user::text').fetchone()[0],'http_alice')
        legacy=subprocess.run(['openssl','s_client','-tls1_1','-cipher','DEFAULT:@SECLEVEL=0','-connect',f'127.0.0.1:{self.stack.port}','-servername','localhost','-CAfile',str(self.stack.state/'pki'/'ca.crt'),'-verify_return_error'],input='',text=True,capture_output=True,timeout=5)
        self.assertNotEqual(legacy.returncode,0)
        self.assertIn('protocol version',legacy.stderr.lower())
        ports=self.stack.run('docker','port',self.stack.container)
        self.assertTrue(all('127.0.0.1:' in line for line in ports.splitlines()))

    def test_cors_options_authentication_and_isolation(self):
        origin='https://lovable.example.invalid'
        status,headers,_=self.call('OPTIONS',self.route(),headers={'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization'})
        self.assertEqual(status,204); self.assertEqual(headers['Access-Control-Allow-Origin'],origin)
        self.assertNotIn('Access-Control-Allow-Credentials',headers)
        self.assertEqual(self.call('GET',self.route())[0],401)
        self.assertEqual(self.call('GET',self.route(),token=self.tokens['alice'])[0],200)
        self.assertEqual(self.call('GET',self.route(B,BC),token=self.tokens['alice'])[0],403)
        self.assertEqual(self.call('GET',self.route(),token=self.tokens['bob'])[0],403)
        self.assertEqual(self.call('GET',self.route(),token=self.tokens['alice'],headers={'Origin':'https://evil.example.invalid'})[0],403)
        status,_,body=self.call('POST','/v1/sessions',dict(username='alice',password=self.stack.credentials['alice']))
        self.assertEqual(status,201)
        self.assertEqual(self.call('DELETE','/v1/session',token=body['access_token'])[0],204)
        self.assertEqual(self.call('GET','/v1/session',token=body['access_token'])[0],401)
        # Expiration is deliberately forced in private test state, not fabricated in API.
        import sqlite3,hashlib
        status,_,body=self.call('POST','/v1/sessions',dict(username='alice',password=self.stack.credentials['alice']))
        with sqlite3.connect(self.stack.config['session_db']) as db:
            db.execute('UPDATE sessions SET expires=0 WHERE digest=?',(hashlib.sha256(body['access_token'].encode()).hexdigest(),))
        self.assertEqual(self.call('GET','/v1/session',token=body['access_token'])[0],401)

    def test_forwarded_headers_cannot_create_trusted_transport(self):
        unsafe=subprocess.run([sys.executable,'-m','gunicorn','--check-config','-c',str(ROOT/'infra'/'gunicorn.conf.py'),'app:load_app()'],cwd=ROOT/'api',env=self.stack.env|{'CENTERWAY_UPSTREAM_ADDR':'0.0.0.0:8444'},capture_output=True)
        self.assertNotEqual(unsafe.returncode,0)
        forged={'Forwarded':'for=10.0.0.1;proto=http','X-Forwarded-Proto':'http','X-Forwarded-For':'198.51.100.1','X-Forwarded-SSL':'off'}
        self.assertEqual(self.call('GET','/health',headers=forged)[0],200)
        self.assertEqual(self.call('GET','/health',headers=forged,port=self.stack.api_port)[0],200)
        port=free_port(); config=self.stack.state/'plain-negative-test.py'
        config.write_text((ROOT/'infra'/'gunicorn.conf.py').read_text()+"\ncertfile=None\nkeyfile=None\n")
        log=open(self.stack.state/'plain-negative.log','w')
        process=subprocess.Popen([sys.executable,'-m','gunicorn','-c',str(config),'--bind',f'127.0.0.1:{port}','app:load_app()'],cwd=ROOT/'api',env=self.stack.env,stdout=log,stderr=log)
        try:
            self.stack.wait_port(port,process)
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            conn.request('GET','/health',headers={'X-Forwarded-Proto':'https','X-Forwarded-SSL':'on','Forwarded':'proto=https'})
            response=conn.getresponse(); response.read(); conn.close()
            self.assertEqual(response.status,400)
        finally: self.stack.stop(process); log.close()

    def test_https_idempotency_and_audit(self):
        request_id=str(uuid.uuid4())
        payload=dict(request_id=request_id,operation='append_value',arguments=dict(kind='source',id=str(uuid.uuid4()),expected_revision=0,
          reason='SYNTHETIC C01 HTTPS',data=dict(name='SYNTHETIC HTTPS source',locator='synthetic://https',method='synthetic manual')))
        def submit(_): return self.call('POST',self.route(kind='operations'),payload,token=self.tokens['alice'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(submit,range(2)))
        self.assertEqual([r[0] for r in results],[200,200]); self.assertEqual(results[0][2],results[1][2])
        self.assertEqual(results[0][2]['data']['actor'],'http_alice')
        import psycopg
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as conn:
            count=conn.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(request_id,)).fetchone()[0]
            self.assertEqual(count,1)

    def test_public_configuration_parses_without_activation(self):
        env=self.stack.env|{'API_HOST':'api.example.invalid','ACME_EMAIL':'operator@example.invalid'}
        result=subprocess.run([self.stack.caddy,'validate','--config',str(ROOT/'infra'/'Caddyfile'),'--adapter','caddyfile'],cwd=ROOT/'infra',env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        rejected=subprocess.run([sys.executable,str(ROOT/'infra'/'preflight.py'),'gateway'],env=env,capture_output=True)
        self.assertNotEqual(rejected.returncode,0) # reserved example host cannot be activated
        config=self.stack.config|{'origins':['https://ui.preflight-only.fixture']}
        # Syntactic fixture only: offline preflight does not query DNS or authorize a real origin.
        path=self.stack.state/'preflight-only.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
        command=[sys.executable,str(ROOT/'infra'/'preflight.py'),'api']
        api_env=self.stack.env|{'CENTERWAY_API_CONFIG':str(path)}
        self.assertEqual(subprocess.run(command,env=api_env,capture_output=True).returncode,0)
        key=self.stack.state/'pki'/'api.key'; key.chmod(0o644)
        try: self.assertNotEqual(subprocess.run(command,env=api_env,capture_output=True).returncode,0)
        finally: key.chmod(0o600)

    def test_secret_paths_and_logs(self):
        for path in ('/config.json','/credentials.json','/pki/ca.key','/debug','/metrics'):
            status,_,body=self.call('GET',path)
            self.assertEqual(status,404)
            self.assertFalse(body)
        logs=''.join(p.read_text() for p in self.stack.state.glob('*.log'))
        private=[*self.stack.credentials.values(),*self.tokens.values(),*[u['dsn'] for u in self.stack.config['users'].values()]]
        self.assertTrue(all(secret not in logs for secret in private),'Sensitive material found in local logs')

    def test_z_failures_are_closed_and_recoverable(self):
        self.stack.stop(self.stack.api)
        try:
            status,_,body=self.call('GET','/health')
            self.assertEqual(status,503); self.assertEqual(body,{'error':{'code':'gateway_unavailable'}})
        finally: self.stack.start_api()
        self.stack.stop(self.stack.proxy)
        try:
            with self.assertRaises(OSError): self.call('GET','/health')
        finally: self.stack.start_proxy()
        self.stack.stop(self.stack.proxy); self.stack.start_proxy(wrong_ca=True)
        try:
            self.assertEqual(self.call('POST','/v1/sessions',dict(username='alice',password=self.stack.credentials['alice']),token=self.tokens['alice'])[0],503)
        finally: self.stack.stop(self.stack.proxy); self.stack.start_proxy()
        self.stack.run('docker','stop',self.stack.container)
        try:
            self.assertEqual(self.call('GET',self.route(),token=self.tokens['alice'])[0],503)
            self.assertEqual(self.call('GET','/health')[2]['readiness'],'not_assessed')
        finally:
            self.stack.run('docker','start',self.stack.container)
        self.assertEqual(self.call('GET','/health')[0],200)
        self.test_secret_paths_and_logs()
