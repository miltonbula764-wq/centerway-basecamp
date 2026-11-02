"""Actual M68/T02 application + Chromium + local verified HTTPS/API/PG17.

Every write is a UI click; T01 is NEVER loaded or operated here. No fabricated API
responses, hosted services, screenshots/traces/storage-state or logged credentials.
"""
import base64
from datetime import datetime,timedelta,timezone
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from uuid import uuid4
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=15000)
import psycopg

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'infra'),str(ROOT/'cloud-demo')]
from runtime import PersistentDemo
from local_stack import free_port
from demo.provision import T,B,C,BC

class FrontendProxy(http.server.BaseHTTPRequestHandler):
    """TLS-only test edge forwarding bytes to the actual Vite application."""
    def log_message(self,*_):pass
    def do_GET(self):
        upstream=http.client.HTTPConnection('127.0.0.1',self.server.vite_port,timeout=60)
        try:
            headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','accept-encoding')}
            headers['Host']=f'127.0.0.1:{self.server.vite_port}'
            upstream.request('GET',self.path,headers=headers)
            response=upstream.getresponse();body=response.read()
            self.send_response(response.status)
            for key,value in response.getheaders():
                if key.lower() not in ('transfer-encoding','connection','content-length'):
                    self.send_header(key,value)
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        finally:upstream.close()

class ActualUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='centerway-t02-ui-')
        cls.stack=PersistentDemo(Path(cls.temp.name)/'state',os.environ['CENTERWAY_TEST_CADDY'])
        cls.vite=cls.server=cls.worker=cls.pw=cls.browser=None
        cls.log=None
        try:
            cls.stack.initialize();cls.stack.__enter__();cls.stack.stop(cls.stack.api)
            cls.vite_port=free_port()
            cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),FrontendProxy)
            cls.server.vite_port=cls.vite_port
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cls.stack.state/'pki/edge.crt',cls.stack.state/'pki/edge.key')
            cls.server.socket=tls.wrap_socket(cls.server.socket,server_side=True)
            cls.origin=f'https://localhost:{cls.server.server_port}'
            cls.api=f'https://localhost:{cls.stack.port}'
            cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
            cls.stack.config['origins']=[cls.origin]
            (cls.stack.state/'config.json').write_text(json.dumps(cls.stack.config));cls.stack.start_api()
            cls.log=open(Path(cls.temp.name)/'vite.log','w+')
            env=os.environ.copy();env['VITE_CENTERWAY_LOCAL_API']=cls.api
            cls.vite=subprocess.Popen([os.environ.get('CENTERWAY_TEST_BUN','bun'),'run','dev','--host','127.0.0.1','--port',str(cls.vite_port),'--strictPort'],cwd=ROOT/'lovable-ui',env=env,stdout=cls.log,stderr=cls.log,start_new_session=True)
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                if cls.vite.poll() is not None:raise RuntimeError('Actual frontend startup exited')
                try:
                    conn=http.client.HTTPConnection('127.0.0.1',cls.vite_port,timeout=2);conn.request('GET','/app');r=conn.getresponse();r.read();conn.close()
                    if r.status==200:break
                except (OSError,http.client.HTTPException):pass
                finally:
                    if 'conn' in locals():conn.close()
                time.sleep(.25)
            else:raise RuntimeError('Actual frontend startup timeout')
            # Verify both actual local TLS endpoints with the generated CA/hostname.
            for port in (cls.stack.port,cls.server.server_port):
                conn=http.client.HTTPSConnection('localhost',port,context=ssl.create_default_context(cafile=str(cls.stack.state/'pki/ca.crt')),timeout=30)
                conn.request('GET','/health' if port==cls.stack.port else '/app');r=conn.getresponse();r.read();conn.close()
                if r.status!=200:raise RuntimeError('Local TLS verification failed')
            cert=subprocess.run(['openssl','x509','-in',str(cls.stack.state/'pki/edge.crt'),'-pubkey','-noout'],check=True,capture_output=True).stdout
            der=subprocess.run(['openssl','pkey','-pubin','-outform','DER'],input=cert,check=True,capture_output=True).stdout
            pin=base64.b64encode(hashlib.sha256(der).digest()).decode()
            cls.pw=sync_playwright().start()
            launch={'args':['--ignore-certificate-errors-spki-list='+pin]}
            if os.environ.get('CENTERWAY_CHROMIUM_EXECUTABLE'):launch['executable_path']=os.environ['CENTERWAY_CHROMIUM_EXECUTABLE']
            cls.browser=cls.pw.chromium.launch(**launch)
            print('Actual UI local browser:',cls.browser.version,flush=True)
        except BaseException:
            if cls.log:
                cls.log.flush();cls.log.seek(0);print(cls.log.read()[-5000:],flush=True)
            cls.tearDownClass();raise

    @classmethod
    def tearDownClass(cls):
        if cls.browser:cls.browser.close()
        if cls.pw:cls.pw.stop()
        if cls.vite:
            try:os.killpg(cls.vite.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:cls.vite.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(cls.vite.pid,signal.SIGKILL);cls.vite.wait()
        if cls.server:cls.server.shutdown();cls.server.server_close()
        if cls.worker:cls.worker.join(timeout=5)
        cls.stack.close()
        manifest=cls.stack.state/'manifest.json'
        if manifest.exists():
            m=json.loads(manifest.read_text());subprocess.run(['docker','rm','-f',m['container']],capture_output=True)
            for volume in (m['volume'],m['volume']+'-tls'):subprocess.run(['docker','volume','rm',volume],capture_output=True)
        if cls.log:cls.log.close()
        cls.temp.cleanup()

    def setUp(self):
        mobile='mobile' in self._testMethodName
        self.context=self.browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1280,'height':900},is_mobile=mobile,has_touch=mobile)
        self.external=[];self.posts=[]
        def boundary(route):
            url=route.request.url
            if urlsplit(url).netloc in ('fonts.googleapis.com','fonts.gstatic.com'):
                route.abort()  # Existing cosmetic fonts; never contact the remote service.
            elif urlsplit(url).netloc not in (urlsplit(self.origin).netloc,urlsplit(self.api).netloc):
                self.external.append(urlsplit(url).netloc);route.abort()
            else:route.continue_()
        self.context.route('**/*',boundary)
        self.page=self.context.new_page();self.page.set_default_timeout(15000)
        self.page.on('request',lambda req:self.posts.append(req.post_data_json) if req.method=='POST' and urlsplit(req.url).path.endswith('/operations') else None)
        self.page.goto(self.origin+'/app')

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.external,[],'Application attempted non-local network access')

    def login(self,user='alice'):
        self.page.get_by_label('Utilizador',exact=True).fill(user)
        self.page.get_by_label('Palavra-passe',exact=True).fill(self.stack.credentials[user])
        self.page.get_by_role('button',name='Entrar',exact=True).click()
        expect(self.page.get_by_role('button',name='Terminar sessão',exact=True)).to_be_visible()
        expect(self.page.get_by_role('button',name='Atualizar dados',exact=True)).to_be_enabled()

    def editor(self):
        if self.page.viewport_size['width']<1024:self.page.get_by_role('button',name='Abrir navegação').click()
        self.page.get_by_role('link',name='Clientes',exact=True).first.click()
        self.page.locator(f'a[href="/app/clientes/{C}"]').first.click()
        self.page.get_by_role('button',name='Operar jornada F01–F06').click()
        self.dialog=self.page.get_by_role('dialog')
        expect(self.dialog.get_by_label('Ação manual',exact=True)).to_be_enabled()

    def action(self,op,kind=None):
        self.dialog.get_by_label('Ação manual',exact=True).select_option(op)
        if kind:self.dialog.get_by_label('Tipo de registo',exact=True).select_option(kind)

    def fill(self,values):
        for label,value in values.items():
            element=self.dialog.get_by_label(label,exact=True)
            if element.evaluate('(el)=>el.tagName')=='SELECT':element.select_option(str(value))
            else:element.fill(str(value))

    def send(self):
        before=len(self.posts)
        self.dialog.get_by_role('button',name='Pré-visualizar pedido',exact=True).click()
        confirm=self.dialog.get_by_role('button',name='Confirmar envio manual',exact=True)
        try:expect(confirm).to_be_visible()
        except AssertionError:
            raise AssertionError('Preview rejected: '+self.dialog.get_by_role('alert').inner_text()) from None
        expect(confirm).to_be_disabled();self.assertEqual(len(self.posts),before)
        self.dialog.get_by_role('checkbox',name='Confirmo este pedido sintético e o âmbito apresentado.').check()
        with self.page.expect_response(lambda r:r.request.method=='POST' and urlsplit(r.url).path.endswith('/operations')) as pending:
            confirm.click()
        response=pending.value;body=response.json()
        self.assertIn('data',body,'Actual API rejected request envelope')
        receipt=body['data']
        expect(self.dialog.get_by_role('status')).to_contain_text('Recibo '+receipt['status'])
        self.assertEqual(receipt['status'],'completed','Engine rejected an explicit synthetic test input')
        self.assertEqual(len(self.posts),before+1)
        return receipt

    def next(self):
        with self.page.expect_response(lambda r:r.request.method=='GET' and urlsplit(r.url).path.endswith('/manual-context')):
            self.dialog.get_by_role('button',name='Novo pedido após consultar recibo').click()
        expect(self.dialog.get_by_label('Ação manual',exact=True)).to_be_enabled()

    def exit_editor(self):
        self.dialog.get_by_role('button',name='Close',exact=True).click()
        expect(self.page.get_by_role('button',name='Atualizar dados',exact=True)).to_be_enabled()

    def test_01_entire_journey_by_actual_forms_without_t01(self):
        self.login();self.editor()
        self.action('append_value','source')
        self.fill({'Motivo do registo':'SYNTHETIC T02 explicit UI source','Nome da fonte':'SYNTHETIC T02 outcome source','Localizador da fonte':'synthetic://t02/ui/source','Método da fonte':'SYNTHETIC test total'})
        source=self.send()['result']['id'];self.next()
        now=datetime.now(timezone.utc)
        stamp=lambda sec:(now+timedelta(seconds=sec)).isoformat()
        self.action('append_value','contract')
        self.fill({'Motivo do registo':'SYNTHETIC T02 explicit contract','Objetivo':'SYNTHETIC T02 business total','Resultado esperado':'SYNTHETIC agreed total','Indicador de negócio':'SYNTHETIC outcome units','Unidade':'units','Método de medição':'SYNTHETIC test total','Sentido':'higher','Baseline':10,'Mínimo aceitável':15,'Alvo':20,'Início da baseline':stamp(-900),'Fim da baseline':stamp(-700),'Início da janela':stamp(-600),'Fim da janela':stamp(-500),'Fonte e versão':source+'|1','Referência da baseline':'synthetic://t02/ui/baseline'})
        contract=self.send()['result']['id'];self.next()
        self.action('append_value','evidence')
        self.fill({'Motivo do registo':'SYNTHETIC T02 declared outcome','Usar medição de contrato/versão':contract+'|1','Tipo de evidência':'outcome','Qualidade declarada':'verified','Valor observado':8,'Referência documental':'synthetic://t02/ui/outcome'})
        document=b'SYNTHETIC T02 explicit outcome value 8 units; no independent verification'
        self.dialog.get_by_label('Calcular SHA-256 de ficheiro local (não enviado)',exact=True).set_input_files({'name':'t02-outcome.txt','mimeType':'text/plain','buffer':document})
        expect(self.dialog.get_by_label('SHA-256 do documento',exact=True)).to_have_value(hashlib.sha256(document).hexdigest())
        self.send();self.next()
        self.action('detect');self.fill({'Contrato a avaliar':contract,'Períodos exigidos (2–120)':2})
        self.dialog.get_by_role('button',name='Usar instante atual — Instante de corte',exact=True).click()
        self.dialog.get_by_label('Selecionar revisão 1',exact=True).check()
        detection=self.send()['result'];self.assertEqual(detection['state'],'deterioracao_demonstrada');self.next()
        self.action('open_investigation');self.fill({'Deteção explícita':detection['id'],'Período da deteção':1,'Pergunta de investigação':'SYNTHETIC explicit prerequisite, causal impact unproven'})
        investigation=self.send()['result']['id'];self.next()
        self.action('append_investigation','factor')
        self.fill({'Investigação':investigation,'Motivo do registo':'SYNTHETIC operator hypothesis','Âmbito':'internal','Categoria':'SYNTHETIC T02 prerequisite','Hipótese não comprovada':'SYNTHETIC prerequisite may impede value; no causal claim','Requisito a verificar':'SYNTHETIC agreed prerequisite applies','Condição a testar':'SYNTHETIC prerequisite present','Protocolo de verificação':'SYNTHETIC manual fixture review, not independent proof','Instante da condição':stamp(-550),'Controlo':'saas','Parte responsável (vazio se unknown/none)':'SYNTHETIC team'})
        factor=self.send()['result']['id'];self.next()
        evidence=[]
        for purpose,assertion in [('requirement_applies','true'),('condition_met','false')]:
            self.action('append_investigation','evidence')
            self.fill({'Investigação':investigation,'Motivo do registo':'SYNTHETIC explicit documentary proposition','Fator e versão':factor+'|1','Proposição':purpose,'Suporte':'document','Afirmação declarada':assertion,'Fonte e versão':source+'|1','Referência documental':'synthetic://t02/ui/prerequisite','SHA-256 do documento':'b'*64})
            self.dialog.get_by_role('button',name='Usar instante atual — Instante da recolha',exact=True).click()
            evidence.append((self.send()['result']['id'],assertion));self.next()
        self.action('investigate');self.fill({'Investigação':investigation});self.dialog.get_by_role('button',name='Usar instante atual — Instante de corte',exact=True).click()
        report=self.send()['result'];self.assertEqual(report['result']['status'],'inconclusivo');self.next()
        self.action('intervene');self.fill({'Investigação':investigation,'Relatório persistido':report['id']})
        blocked=self.send()['result'];self.assertEqual(blocked['status'],'blocked');self.assertIsNone(blocked['execution_id']);self.next()
        self.exit_editor();self.page.get_by_role('button',name='Terminar sessão',exact=True).click()
        self.login('reviewer');self.editor()
        for eid,assertion in evidence:
            self.action('append_investigation','verification')
            self.fill({'Investigação':investigation,'Motivo do registo':'SYNTHETIC separate test principal; not human proof','Evidência e versão':eid+'|1','Veredicto':'confirmed','Afirmação verificada (null se unverifiable)':assertion,'Método de verificação':'SYNTHETIC scripted UI fixture; not human/independent verification','Explicação da revisão':'SYNTHETIC explicit test record only','Fonte e versão':source+'|1','Referência documental':'synthetic://t02/ui/test-review','SHA-256 do documento':'c'*64})
            self.dialog.get_by_role('button',name='Usar instante atual — Instante da revisão',exact=True).click()
            self.send();self.next()
        self.action('investigate');self.fill({'Investigação':investigation});self.dialog.get_by_role('button',name='Usar instante atual — Instante de corte',exact=True).click()
        report=self.send()['result'];self.assertEqual(report['result']['status'],'impedimento_demonstrado');self.next();self.exit_editor()
        self.page.get_by_role('button',name='Terminar sessão',exact=True).click();self.login();self.editor()
        self.action('intervene');self.fill({'Investigação':investigation,'Relatório persistido':report['id']})
        decision=self.send()['result'];self.assertEqual(decision['reason'],'no_authorized_eligible_action');self.assertIsNone(decision['execution_id']);self.next()
        anchor=datetime.fromisoformat(decision['recorded_at'])
        for revision,start,end in [(1,-4,-2),(2,2,4)]:
            self.action('append_value','contract')
            self.fill({'Copiar registo para nova revisão':contract+'|1','Motivo do registo':'SYNTHETIC short comparable UI test window','Início da janela':(anchor+timedelta(seconds=start)).isoformat(),'Fim da janela':(anchor+timedelta(seconds=end)).isoformat()})
            result=self.send()['result'];self.assertEqual(result['revision'],revision+1);self.next()
        self.action('plan_recovery');self.fill({'Decisão de intervenção':decision['id'],'Janela anterior':2,'Janela posterior':3,'Motivo do plano':'SYNTHETIC assess explicitly blocked intervention without invented outcomes'})
        plan=self.send()['result']['id'];self.next()
        self.action('evaluate_recovery');self.fill({'Plano de recuperação':plan});self.dialog.get_by_role('button',name='Usar instante atual — Instante de corte',exact=True).click()
        result=self.send()['result']['result'];self.assertEqual(result['status'],'resultado_inconclusivo');self.assertFalse(result['execution_succeeded']);self.assertEqual(result['causal_attribution'],'not_established')
        # Explicit prior authorization ONLY in this disposable T02 test, never T01.
        # The browser has no policy-grant endpoint or administrative credential.
        resource,catalog,policy=[str(uuid4()) for _ in range(3)]
        self.stack.sql(f"""BEGIN;
          INSERT INTO centerway.sandbox_flags VALUES('{T}','{C}','{resource}','isolated_synthetic',false,NULL);
          INSERT INTO centerway.intervention_catalog VALUES('{T}','{catalog}','SYNTHETIC T02 reversible flag',
            'SYNTHETIC T02 prerequisite','internal','saas','set_synthetic_flag',false,true,1,1);
          INSERT INTO centerway.intervention_policies VALUES('{T}','{C}','{policy}','{catalog}','{resource}','http_alice',
            clock_timestamp(),clock_timestamp()+interval '1 hour',1,1,interval '1 hour',interval '1 hour');
          COMMIT;""")
        self.next();self.action('intervene');self.fill({'Investigação':investigation})
        current_report=self.dialog.get_by_label('Relatório persistido',exact=True).locator('option').last.get_attribute('value')
        self.fill({'Relatório persistido':current_report})
        executed=self.send()['result'];self.assertEqual(executed['status'],'executed');self.next()
        # MVP-FIRST: positive recovery through actual forms, not only API fixtures.
        # Synthetic windows are time-scaled; this is not a calendar-scale pilot.
        anchor=datetime.fromisoformat(executed['recorded_at'])
        for revision,start,end in [(3,-4,-2),(4,2,4)]:
            self.action('append_value','contract')
            self.fill({'Copiar registo para nova revisão':contract+'|1','Motivo do registo':'SYNTHETIC MVP-FIRST comparable outcome window','Início da janela':(anchor+timedelta(seconds=start)).isoformat(),'Fim da janela':(anchor+timedelta(seconds=end)).isoformat()})
            self.assertEqual(self.send()['result']['revision'],revision+1);self.next()
        remaining=(anchor+timedelta(seconds=4)-datetime.now(timezone.utc)).total_seconds()
        if remaining>0:self.page.wait_for_timeout(remaining*1000+100)
        for revision,value in [(4,8),(5,15)]:
            self.action('append_value','evidence')
            self.fill({'Motivo do registo':'SYNTHETIC MVP-FIRST declared measurement; no causal proof','Usar medição de contrato/versão':contract+'|'+str(revision),'Tipo de evidência':'outcome','Qualidade declarada':'verified','Valor observado':value,'Referência documental':'synthetic://mvp-first/outcome/'+str(revision),'SHA-256 do documento':hashlib.sha256(f'SYNTHETIC {revision} {value}'.encode()).hexdigest()})
            self.send();self.next()
        self.action('plan_recovery')
        self.fill({'Decisão de intervenção':executed['id'],'Janela anterior':4,'Janela posterior':5,'Motivo do plano':'SYNTHETIC MVP-FIRST verify contracted minimum after authorized synthetic action'})
        positive_plan=self.send()['result']['id'];self.next()
        self.action('evaluate_recovery');self.fill({'Plano de recuperação':positive_plan})
        self.dialog.get_by_role('button',name='Usar instante atual — Instante de corte',exact=True).click()
        recovery=self.send()['result']['result']
        self.assertEqual(recovery['status'],'recuperacao_completa')
        self.assertTrue(recovery['execution_succeeded']);self.assertTrue(recovery['improvement_observed'])
        self.assertEqual(recovery['causal_attribution'],'not_established')
        self.assertEqual(recovery['independent_verification'],'not_established');self.next()
        self.action('undo');self.fill({'Execução a reverter':executed['execution_id']})
        undone=self.send()['result'];self.assertEqual(undone['undo_of'],executed['execution_id'])
        self.exit_editor()
        self.assertEqual(self.page.evaluate('localStorage.length+sessionStorage.length'),0)
        self.page.get_by_role('button',name='Terminar sessão',exact=True).click()
        expect(self.page.get_by_role('button',name='Entrar',exact=True)).to_be_visible()
        self.page.reload();expect(self.page.get_by_role('button',name='Entrar',exact=True)).to_be_visible()
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.intervention_executions').fetchone()[0],2)
            self.assertFalse(db.execute('SELECT value FROM centerway.sandbox_flags WHERE id=%s',(resource,)).fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.operation_receipts WHERE client_id=%s',(C,)).fetchone()[0],len(self.posts))

    def test_02_mobile_navigation_reader_and_reviewer_permissions(self):
        self.page.set_viewport_size({'width':390,'height':844});self.login('reader');self.editor()
        expect(self.dialog.get_by_role('button',name='Pré-visualizar pedido')).to_be_disabled()
        self.action('intervene');expect(self.dialog.get_by_role('button',name='Pré-visualizar pedido')).to_be_disabled()
        self.assertEqual(len(self.posts),0)
        self.exit_editor();self.page.get_by_role('button',name='Terminar sessão',exact=True).click()
        self.login('reviewer');self.editor();self.action('append_value','source')
        expect(self.dialog.get_by_role('button',name='Pré-visualizar pedido')).to_be_disabled()
        self.action('append_investigation','factor');expect(self.dialog.get_by_role('button',name='Pré-visualizar pedido')).to_be_enabled()
        self.action('intervene');expect(self.dialog.get_by_role('button',name='Pré-visualizar pedido')).to_be_disabled()
        self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'),True)
        self.assertEqual(self.context.cookies(),[])
        self.assertEqual(len(self.posts),0)

    def test_03_uncertain_response_requires_same_request_explicit_resend(self):
        self.login();self.editor();self.action('append_value','source')
        self.fill({'Motivo do registo':'SYNTHETIC actual commit with lost response','Nome da fonte':'SYNTHETIC lost response','Localizador da fonte':'synthetic://t02/response-loss','Método da fonte':'SYNTHETIC'})
        self.dialog.get_by_role('button',name='Pré-visualizar pedido').click()
        expect(self.dialog.get_by_role('button',name='Confirmar envio manual')).to_be_visible()
        self.dialog.get_by_role('checkbox',name='Confirmo este pedido sintético e o âmbito apresentado.').check()
        # CDP drops only the actual response AFTER the real server committed it.
        cdp=self.context.new_cdp_session(self.page)
        def lose_response(event):
            if event['request']['method']=='POST':
                cdp.send('Fetch.failRequest',{'requestId':event['requestId'],'errorReason':'Failed'})
                cdp.send('Fetch.disable')
            else:cdp.send('Fetch.continueResponse',{'requestId':event['requestId']})
        cdp.on('Fetch.requestPaused',lose_response)
        cdp.send('Fetch.enable',{'patterns':[{'urlPattern':'*/operations','requestStage':'Response'}]})
        self.dialog.get_by_role('button',name='Confirmar envio manual').click()
        retry=self.dialog.get_by_role('button',name='Reenviar exatamente o mesmo pedido')
        expect(retry).to_be_visible();self.assertEqual(len(self.posts),1)
        with self.page.expect_response(lambda r:r.request.method=='POST' and urlsplit(r.url).path.endswith('/operations')):
            retry.click()
        expect(self.dialog.get_by_role('status')).to_contain_text('Recibo completed')
        self.assertEqual(self.posts[0],self.posts[1])
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(self.posts[0]['request_id'],)).fetchone()[0],1)

    def test_04_mobile_write_persists_and_refresh_requires_new_login(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.login();self.editor();self.action('append_value','source')
        self.fill({'Motivo do registo':'SYNTHETIC mobile input','Nome da fonte':'SYNTHETIC mobile source','Localizador da fonte':'synthetic://t02/mobile','Método da fonte':'SYNTHETIC mobile'})
        receipt=self.send();self.assertEqual(receipt['result']['name'],'SYNTHETIC mobile source')
        self.exit_editor();self.page.reload()
        expect(self.page.get_by_role('button',name='Entrar',exact=True)).to_be_visible()
        self.login();self.editor()
        self.dialog.get_by_text('Contrato, revisões, fontes e evidências F01 (API)',exact=True).click()
        expect(self.dialog.locator('pre').filter(has_text='SYNTHETIC mobile source').first).to_be_visible()
        self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'),True)

    def test_05_server_expiration_unmounts_draft_and_does_not_post(self):
        import sqlite3
        self.login('reader');self.editor()
        with sqlite3.connect(self.stack.config['session_db']) as db:
            db.execute("UPDATE sessions SET expires=0 WHERE username='reader'")
        self.dialog.get_by_role('button',name='Atualizar jornada por GET',exact=True).click()
        expect(self.page.get_by_role('button',name='Entrar',exact=True)).to_be_visible()
        expect(self.page.get_by_role('dialog')).to_have_count(0)
        self.assertEqual(self.posts,[])
