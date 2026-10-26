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
                from centerway.integration_contract import load
                from centerway.integrations import install as install_integrations,IntegrationRepository
                from centerway.evidence import install as install_evidence
                production_store=Store.open_existing(path);install_integrations(production_store)
                saas_configuration=load(cwd/'examples/integrations/collaboration.json')
                saas_configuration['tenant']='company-a';saas_configuration['data_classification']='declared'
                IntegrationRepository(production_store).append('owner','company-a',saas_configuration,0)
                install_evidence(production_store)
                # M15: identified source claims through the actual Caddy -> HTTPS Python path.
                from centerway.webhooks import install as install_webhooks,signed_bytes,PATH
                import secrets,hmac,hashlib
                install_webhooks(production_store)
                webhook_secret=secrets.token_bytes(32);webhook_key=root/'source.key'
                webhook_key.write_text(webhook_secret.hex());webhook_key.chmod(0o600)
                snapshot=IntegrationRepository(production_store).get('owner','company-a')
                webhook_config=root/'webhooks.json'
                webhook_config.write_text(json.dumps({'schema_version':1,'mode':'production','sources':[{
                    'id':'proxy-test-source','tenant':'company-a','config_version':1,'config_hash':snapshot['content_hash'],
                    'mapping_version':1,'classification':'declared','customers':{'proxy-external':'webhook-c'},
                    'routes':{'paused':{'kind':'evidence','definition_id':'operation-state','source_ref':saas_configuration['evidence'][0]['source_ref'],'fields':{'paused':'data.flag'}}},
                    'keys':[{'id':'key-1','secret_file':str(webhook_key),'not_before':int(time.time())-10,'expires_at':int(time.time())+3600}]}]}))
                webhook_config.chmod(0o600)
                # M16: a locally authorized analysis pilot, no operational production unlock.
                from centerway import detection,investigation,ai_proposals,controlled_execution,recovery,orchestration,pilot
                for module in (detection,investigation,ai_proposals,controlled_execution,recovery,orchestration,pilot): module.install(production_store)
                pilot.authorize(production_store,'owner','company-a',True,False,'Explicit local proxy TEST pilot authorization.',0)

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
                    return subprocess.Popen([sys.executable,'-u','-m','centerway.runtime','serve','--mode','production' if production else 'demo','--db',str(path),'--certfile',str(cert),'--keyfile',str(key),'--port',str(backend_port),*(['--webhook-config',str(webhook_config)] if production else [])],cwd=cwd,stdout=output,stderr=output)
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
                if production:
                    raw=json.dumps({'mapping_version':1,'config_version':1,'customer_id':'proxy-external','event_type':'paused',
                        'event_id':'proxy-test-claim-1','occurred_at':'2026-01-01T00:00:00Z','period':None,'data':{'flag':True}},indent=2).encode()
                    stamp=str(int(time.time()));nonce=secrets.token_hex(16)
                    signature='v1='+hmac.new(webhook_secret,signed_bytes('proxy-test-source','key-1',stamp,nonce,raw),hashlib.sha256).hexdigest()
                    machine=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))))
                    signed_headers={'Content-Type':'application/json','X-CW-Source':'proxy-test-source','X-CW-Key-Id':'key-1',
                                    'X-CW-Timestamp':stamp,'X-CW-Nonce':nonce,'X-CW-Signature':signature}
                    def send_claim(headers=signed_headers):
                        try: response=machine.open(Request(origin+PATH,raw,headers),timeout=5)
                        except HTTPError as error: response=error
                        with response: return response.status,json.loads(response.read())
                    receipt=send_claim();self.assertEqual(200,receipt[0]);self.assertEqual('source_claim',receipt[1]['claim_classification'])
                    self.assertEqual(receipt,send_claim())
                    self.assertEqual(401,send_claim({**signed_headers,'X-CW-Signature':'v1='+'0'*64})[0])
                    with production_store.transaction() as db:
                        self.assertEqual(1,db.execute('SELECT count(*) FROM webhook_receipts').fetchone()[0])
                        self.assertEqual('webhook:proxy-test-source',db.execute('SELECT actor FROM evidence_items').fetchone()[0])
                status,_,headers=call('/api/login',{'user':'owner' if production else 'founder','password':passwords['owner' if production else 'founder']})
                self.assertEqual(200,status)
                session_tokens=[headers['Set-Cookie'].split(';',1)[0].split('=',1)[1]]
                cookie='__Host-cw_production_session=' if production else '__Host-cw_session='
                for flag in (cookie,'Secure','HttpOnly','SameSite=Strict'): self.assertIn(flag,headers['Set-Cookie'])
                if production:
                    view=json.loads(call('/api/view')[1])
                    self.assertEqual('production',view['environment_type']);self.assertEqual('disabled',view['decision_mode'])
                    self.assertEqual([],view['registry'])
                    self.assertEqual(200,call('/api/pilot/context?tenant=company-a')[0])
                    customer={'tenant':'company-a','customer':'pilot-test-client','name':'Explicit proxy TEST client','context':'Synthetic protocol check, no real results.','expected_version':0}
                    self.assertEqual(200,call('/api/pilot/customers/append',customer)[0])
                    process={'tenant':'company-a','customer':'pilot-test-client','case_id':'pilot-case','request_id':'proxy-test-process','as_of':'2026-01-01T00:00:00Z'}
                    status,result,_=call('/api/pilot/process',process);self.assertEqual(200,status)
                    self.assertEqual('awaiting_data',json.loads(result)['checkpoint']['payload']['state'])
                    self.assertFalse(json.loads(result)['real_recovery_demonstrated'])
                    self.assertEqual(200,call('/api/pilot/analysis?tenant=company-a&customer=pilot-test-client&case_id=pilot-case')[0])

                    evidence_body={'tenant':'company-a','customer':'c','config_version':1,'records':[{
                        'external_id':'proxy-evidence-1','kind':'evidence','definition_id':'operation-state',
                        'source_ref':saas_configuration['evidence'][0]['source_ref'],'occurred_at':'2026-01-01T00:00:00Z',
                        'period':None,'payload':{'paused':True}}]}
                    self.assertEqual(200,call('/api/evidence',evidence_body)[0])
                    evidence_route='/api/evidence/view?tenant=company-a&customer=c&config_version=1'
                    evidence_before=json.loads(call(evidence_route)[1])
                    self.assertEqual('inactive',evidence_before['operational_state'])
                    self.assertEqual(1,len(evidence_before['records']))
                    self.assertEqual(503,call('/api/execute',{'tenant':'company-a','customer':'c','case_id':'c'})[0])
                    backend.terminate();backend.wait(timeout=15);self.assertEqual(0,backend.returncode)
                    backend=start_backend();ready('/api/view')
                    self.assertEqual(view,json.loads(call('/api/view')[1]))
                    self.assertEqual(evidence_before,json.loads(call(evidence_route)[1]))
                    self.assertTrue(json.loads(call('/api/evidence',evidence_body)[1])['reused'])
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
                for secret in [*passwords.values(),*session_tokens,'query-secret-marker',*([webhook_secret.hex(),signature,nonce] if production else [])]:
                    self.assertTrue(secret not in log.read_text(),'Proxy log leaked a test secret')
                with Store.open_existing(path).transaction() as db:
                    if production:
                        self.assertEqual(0,db.execute('SELECT count(*) FROM history').fetchone()[0])
                    else:
                        self.assertEqual(1,db.execute("SELECT count(*) FROM history WHERE stage='C05' AND case_id=?",(body['case_id'],)).fetchone()[0])
            finally:
                for process in (proxy,backend):
                    if process and process.poll() is None: process.terminate();process.wait(timeout=15)
