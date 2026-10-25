"""Real Caddy → verified TLS Python on loopback; no product frontend or hosting."""
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from centerway.preview import provision
from centerway.store import Store

CADDY=os.environ.get('CADDY_BIN') or shutil.which('caddy')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def certificate(cert,key,name='localhost'):
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(key),'-out',str(cert),'-subj',f'/CN={name}','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)


@unittest.skipUnless(CADDY,'Set CADDY_BIN for real reverse-proxy verification')
class InfraProxyTests(unittest.TestCase):
    def test_same_origin_cookie_cycle_restart_and_fail_closed_upstream(self):
        self.proxy_cycle()

    def test_production_auth_restart_and_disabled_operations_through_caddy(self):
        self.proxy_cycle(production=True)

    def proxy_cycle(self,production=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cwd=Path(__file__).resolve().parents[1]
            cert,key=root/'cert.pem',root/'key.pem';certificate(cert,key)
            edge_port,backend_port=free_port(),free_port()
            while backend_port==edge_port: backend_port=free_port()
            origin=f'https://127.0.0.1:{edge_port}'
            path,credentials=root/'state.sqlite3',root/'credentials.json'
            if production:
                from centerway.production import provision as provision_production
                accounts=root/'accounts.json'
                accounts.write_text(json.dumps({'accounts':[
                    {'user':'owner','memberships':[{'tenant':'company-a','role':'operator'}]},
                    {'user':'auditor','memberships':[{'tenant':'company-b','role':'viewer'}]}]}))
                accounts.chmod(0o600)
                provision_production(path,credentials,origin,accounts)
            else:
                provision(path,credentials,origin)
            passwords=json.loads(credentials.read_text())['accounts']
            frontend=root/'frontend';frontend.mkdir()
            (frontend/'index.html').write_text('LOCAL ROUTING FIXTURE; NO PRODUCT FRONTEND')
            (frontend/'.env').write_text('must-not-be-served')
            (frontend/'backup.sqlite3').write_text('must-not-be-served')
            configuration=(cwd/'infra/Caddyfile').read_text().replace('admin off','admin off\n\tauto_https off\n\tdefault_bind 127.0.0.1')
            configuration=configuration.replace('https://{$CENTERWAY_PUBLIC_HOST} {',f'https://{{$CENTERWAY_PUBLIC_HOST}} {{\n\ttls {cert} {key}')
            config=root/'Caddyfile';config.write_text(configuration)
            environment=os.environ.copy();environment.update(CENTERWAY_PUBLIC_HOST=f'127.0.0.1:{edge_port}',CENTERWAY_BACKEND_ADDR=f'127.0.0.1:{backend_port}',CENTERWAY_BACKEND_CA=str(cert),CENTERWAY_FRONTEND_ROOT=str(frontend))
            log=root/'caddy.log';backend_log=root/'backend.log';backend=proxy=None
            client=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))),HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def call(route,body=None,headers=None):
                req=Request(origin+route,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json','Origin':origin,**(headers or {})})
                try: response=client.open(req,timeout=4)
                except HTTPError as error: response=error
                with response: return response.status,response.read(),response.headers
            def ready(route='/'):
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    try:
                        if call(route)[0] in (200,401): return
                    except (URLError,OSError): pass
                    time.sleep(.05)
                diagnostic=log.read_text() if log.exists() else ''
                diagnostic+=backend_log.read_text() if backend_log.exists() else ''
                for password in passwords.values(): diagnostic=diagnostic.replace(password,'<redacted>')
                self.fail('Local proxy/backend startup failed: '+diagnostic[-3500:])
            def start_backend():
                with backend_log.open('ab') as output:
                    return subprocess.Popen([sys.executable,'-u','-m','centerway.runtime','serve','--mode','production' if production else 'demo','--db',str(path),'--certfile',str(cert),'--keyfile',str(key),'--port',str(backend_port)],cwd=cwd,stdout=output,stderr=output)
            def start_proxy():
                with log.open('ab') as output:
                    return subprocess.Popen([CADDY,'run','--config',str(config),'--adapter','caddyfile'],env=environment,stdout=output,stderr=output)
            try:
                validated=subprocess.run([CADDY,'validate','--config',str(config),'--adapter','caddyfile'],env=environment,capture_output=True,text=True)
                self.assertEqual(0,validated.returncode,validated.stderr)
                backend=start_backend();proxy=start_proxy();ready('/api/view')
                self.assertIn(b'LOCAL ROUTING FIXTURE',call('/app/route')[1])
                for private in ('/.env','/backup.sqlite3','/private/key.pem','/assets/.git/config'):
                    self.assertEqual(404,call(private)[0])
                status,payload,_=call('/api/missing')
                self.assertEqual(404,status);self.assertEqual('not_found',json.loads(payload)['code'])
                self.assertEqual(401,call('/api/view')[0])
                status,_,headers=call('/api/login',{'user':'owner' if production else 'founder','password':passwords['owner' if production else 'founder']})
                self.assertEqual(200,status)
                session_tokens=[headers['Set-Cookie'].split(';',1)[0].split('=',1)[1]]
                cookie='__Host-cw_production_session=' if production else '__Host-cw_session='
                for flag in (cookie,'Secure','HttpOnly','SameSite=Strict'): self.assertIn(flag,headers['Set-Cookie'])
                if production:
                    view=json.loads(call('/api/view')[1])
                    self.assertEqual('production',view['environment_type']);self.assertEqual('disabled',view['decision_mode'])
                    self.assertEqual([],view['registry'])
                    self.assertEqual(503,call('/api/execute',{'tenant':'company-a','customer':'c','case_id':'c'})[0])
                    backend.terminate();backend.wait(timeout=15);self.assertEqual(0,backend.returncode)
                    backend=start_backend();ready('/api/view')
                    self.assertEqual(view,json.loads(call('/api/view')[1]))
                    with Store.open_existing(path).transaction() as db:
                        self.assertEqual(0,db.execute('SELECT count(*) FROM executions').fetchone()[0])
                        self.assertNotIn('expires_at',[r['name'] for r in db.execute('PRAGMA table_info(production_metadata)')])
                else:
                    self.assertEqual(150,len(json.loads(call('/api/view')[1])['registry']))
                    scope={'tenant':'atlas','customer':'client-007'}
                    body={**scope,'case_id':json.loads(call('/api/view?tenant=atlas&customer=client-007')[1])['case']['id']}
                    self.assertFalse(json.loads(call('/api/execute',body)[1])['reused'])
                    self.assertTrue(json.loads(call('/api/verify',body)[1])['value_recovered'])
                    before=json.loads(call('/api/view?tenant=atlas&customer=client-007')[1])
                    backend.terminate();backend.wait(timeout=15);self.assertEqual(0,backend.returncode)
                    backend=start_backend();ready('/api/view')
                    self.assertEqual(before,json.loads(call('/api/view?tenant=atlas&customer=client-007')[1]))
                    self.assertTrue(json.loads(call('/api/execute',body)[1])['reused'])
                self.assertEqual(403,call('/api/logout',{},headers={'Origin':'https://evil.example'})[0])
                self.assertEqual(200,call('/api/logout',{})[0]);self.assertEqual(401,call('/api/view')[0])
                reader='auditor' if production else 'reader-private'
                reader_status,_,reader_headers=call('/api/login',{'user':reader,'password':passwords[reader]})
                self.assertEqual(200,reader_status)
                session_tokens.append(reader_headers['Set-Cookie'].split(';',1)[0].split('=',1)[1])
                if production:
                    self.assertEqual(403,call('/api/view?tenant=company-a')[0])
                    self.assertEqual(403,call('/api/advance',{'tenant':'company-b','customer':'c'})[0])
                else:
                    self.assertEqual(75,len(json.loads(call('/api/view')[1])['registry']))
                    self.assertEqual(403,call('/api/view?tenant=atlas&customer=client-007')[0])
                    self.assertEqual(403,call('/api/advance',{'tenant':'nimbus','customer':'client-007'})[0])
                backend.terminate();backend.wait(timeout=15)
                self.assertEqual(502,call('/api/view')[0])
                backend=start_backend();ready('/api/view')
                proxy.terminate();proxy.wait(timeout=10)
                other_cert,other_key=root/'other.pem',root/'other.key';certificate(other_cert,other_key,'other')
                environment['CENTERWAY_BACKEND_CA']=str(other_cert)
                proxy=start_proxy();ready('/')
                self.assertEqual(502,call('/api/view')[0])
                self.assertEqual(502,call('/api/view?password=query-secret-marker')[0])
                for secret in [*passwords.values(),*session_tokens,'query-secret-marker']:
                    self.assertTrue(secret not in log.read_text(),'Proxy log leaked a test secret')
                with Store.open_existing(path).transaction() as db:
                    if production:
                        self.assertEqual(0,db.execute('SELECT count(*) FROM history').fetchone()[0])
                    else:
                        self.assertEqual(1,db.execute("SELECT count(*) FROM history WHERE stage='C05' AND case_id=?",(body['case_id'],)).fetchone()[0])
            finally:
                for process in (proxy,backend):
                    if process and process.poll() is None: process.terminate();process.wait(timeout=15)
