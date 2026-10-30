"""Real Chromium + pinned Lovable source + real local HTTPS API/PostgreSQL.

Not a hosted Lovable test. All data are SYNTHETIC; the local test certificate
is trusted by its explicit SPKI only. No global TLS/CORS bypass or route mocks.
"""
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'infra'))
sys.path.insert(0, str(ROOT / 'cloud-demo'))
from runtime import PersistentDemo
from demo.provision import T, B, C, BC
from scenario import Scenario, uid


class BrowserScenario(Scenario):
    """Reuse C03's synthetic inputs; every login/read/operation uses browser fetch."""
    def __init__(self, demo, page):
        super().__init__(demo)
        self.page = page

    def login(self, user):
        self.page.evaluate('''async cfg => {
          const {HttpTransport}=await import('/http-transport.js');
          window.scenarioTransports ??= {};
          const t=new HttpTransport({baseUrl:cfg.api,allowLocalhost:true,fetch:fetch.bind(window)});
          await t.createSession({username:cfg.user,password:cfg.password});
          await t.getSession();
          window.scenarioTransports[cfg.user]=t;
        }''', dict(api=f'https://localhost:{self.demo.port}', user=user, password=self.demo.credentials[user]))

    def command(self, operation, arguments, user='alice', key=None):
        payload = dict(request_id=key or uid(), operation=operation, arguments=arguments)
        receipt = self.page.evaluate('''async cfg =>
          window.scenarioTransports[cfg.user].operate(cfg.tenant,cfg.client,cfg.payload)
        ''', dict(user=user, tenant=T, client=C, payload=payload))
        if receipt['status'] != 'completed':
            raise RuntimeError('Browser synthetic operation did not complete')
        return receipt['result'], payload

    def request(self, method, path, data=None, user='alice'):
        if method != 'GET' or path != f'/v1/tenants/{T}/clients/{C}/journey':
            raise RuntimeError('Unexpected synthetic scenario route')
        journey = self.page.evaluate('''async cfg =>
          window.scenarioTransports[cfg.user].getJourney(cfg.tenant,cfg.client)
        ''', dict(user=user, tenant=T, client=C))
        return 200, dict(data=journey)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/':
            body = b'<!doctype html><title>CENTERWAY SYNTHETIC transport test</title>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


class ChromiumCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='centerway-chromium-')
        cls.stack = PersistentDemo(Path(cls.temp.name) / 'state', os.environ['CENTERWAY_TEST_CADDY'])
        cls.servers = []
        cls.pw = cls.browser = None
        try:
            cls.stack.initialize()
            cls.stack.__enter__()
            cls.stack.stop(cls.stack.api)
            # Two actual HTTPS origins; only the first is authorized by the API.
            for _ in range(2):
                handler = functools.partial(QuietHandler, directory=os.environ['CENTERWAY_TEST_JS'])
                server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(cls.stack.state / 'pki/edge.crt', cls.stack.state / 'pki/edge.key')
                server.socket = context.wrap_socket(server.socket, server_side=True)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                cls.servers.append((server, worker))
            cls.origins = [f'https://localhost:{s.server_port}' for s, _ in cls.servers]
            cls.stack.config['origins'] = [cls.origins[0]]
            (cls.stack.state / 'config.json').write_text(json.dumps(cls.stack.config))
            cls.stack.start_api()
            # Independently verify CA chain and hostname before the browser test.
            import urllib.request
            trust = ssl.create_default_context(cafile=str(cls.stack.state / 'pki/ca.crt'))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=trust))
            with opener.open(f'https://localhost:{cls.stack.port}/health', timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError('Verified TLS health failed')
            cert = subprocess.run(['openssl', 'x509', '-in', str(cls.stack.state / 'pki/edge.crt'), '-pubkey', '-noout'], check=True, capture_output=True).stdout
            der = subprocess.run(['openssl', 'pkey', '-pubin', '-outform', 'DER'], input=cert, check=True, capture_output=True).stdout
            import hashlib
            pin = base64.b64encode(hashlib.sha256(der).digest()).decode()
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch(args=['--ignore-certificate-errors-spki-list=' + pin])
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.browser:
            cls.browser.close()
        if cls.pw:
            cls.pw.stop()
        for server, worker in cls.servers:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
        cls.stack.close()
        manifest = cls.stack.state / 'manifest.json'
        if manifest.exists():
            m = json.loads(manifest.read_text())
            subprocess.run(['docker', 'rm', '-f', m['container']], capture_output=True)
            for volume in (m['volume'], m['volume'] + '-tls'):
                subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.on('requestfailed', lambda req: print('Browser network failure:',
            req.method, urlsplit(req.url).path, req.failure, flush=True))
        self.page.on('response', lambda res: print('Browser HTTP error:',
            res.status, urlsplit(res.url).path, flush=True) if res.status >= 500 else None)
        self.page.goto(self.origins[0])

    def tearDown(self):
        self.context.close()

    def boot(self, user='alice'):
        # Credentials remain in memory; no tracing, request logging, screenshots,
        # HAR, storage state or page export is enabled in this suite.
        self.page.evaluate('''async cfg => {
          const {HttpTransport} = await import('/http-transport.js');
          const {SessionController} = await import('/session-controller.js');
          window.transport = new HttpTransport({baseUrl:cfg.api,allowLocalhost:true,fetch:fetch.bind(window)});
          window.controller = new SessionController(window.transport);
          await window.controller.login(cfg.user,cfg.password);
        }''', dict(api=f'https://localhost:{self.stack.port}', user=user, password=self.stack.credentials[user]))

    def test_01_login_directory_journey_logout_and_no_persistence(self):
        self.boot()
        result = self.page.evaluate('''async ids => {
          const c=window.controller;
          await c.selectTenant(ids.tenant);
          const progress=await c.selectClient(ids.client);
          const result={principal:c.state.session.principal,name:c.state.view.displayName,
            contracts:progress.contracts,causal:progress.causalAttribution,
            directory:c.state.directory.length};
          const logout=c.logout();
          result.immediate=c.state.status;
          await logout;
          result.final=c.state.status; result.hasSession=window.transport.hasSession;
          result.local=localStorage.length; result.session=sessionStorage.length;
          return result;
        }''', dict(tenant=T, client=C))
        self.assertEqual(result, dict(principal='http_alice', name='SYNTHETIC client A', contracts=1,
            causal='not_established', directory=1, immediate='logged_out', final='logged_out',
            hasSession=False, local=0, session=0))
        self.assertEqual(self.context.cookies(), [])

    def test_02_cross_tenant_and_reader_operation_are_forbidden(self):
        for user, tenant in [('bob', T), ('alice', B)]:
            self.boot(user)
            result = self.page.evaluate('''async tenant => {
              try { await window.transport.listClients(tenant); return 'unexpected_success'; }
              catch(e) { return {kind:e.kind,status:e.status}; }
            }''', tenant)
            self.assertEqual(result, dict(kind='http', status=403))
        self.boot('reader')
        result = self.page.evaluate('''async ids => {
          try { await window.transport.operate(ids.tenant,ids.client,{
            request_id:crypto.randomUUID(),operation:'intervene',arguments:{
              investigation_id:crypto.randomUUID(),report_id:crypto.randomUUID()}}); return 'unexpected_success'; }
          catch(e) { return {kind:e.kind,status:e.status}; }
        }''', dict(tenant=T, client=C))
        self.assertEqual(result, dict(kind='http', status=403))

    def test_03_actual_operation_replay_and_conflict(self):
        self.boot()
        result = self.page.evaluate('''async ids => {
          const t=window.transport;
          const req={request_id:crypto.randomUUID(),operation:'append_value',arguments:{
            kind:'source',id:crypto.randomUUID(),expected_revision:0,reason:'SYNTHETIC Chromium',
            data:{name:'SYNTHETIC Chromium source',locator:'synthetic://chromium',method:'SYNTHETIC manual'}}};
          const first=await t.operate(ids.tenant,ids.client,req);
          const replay=await t.operate(ids.tenant,ids.client,req);
          const requestId=req.request_id;
          req.arguments.reason='SYNTHETIC conflicting body';
          let conflict=null;
          try {await t.operate(ids.tenant,ids.client,req);} catch(e) {conflict=e.status;}
          return {status:first.status,equal:JSON.stringify(first)===JSON.stringify(replay),conflict,requestId};
        }''', dict(tenant=T, client=C))
        self.assertEqual((result['status'], result['equal'], result['conflict']), ('completed', True, 409))
        import psycopg
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            count = db.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s", (result['requestId'],)).fetchone()[0]
            self.assertEqual(count, 1)

    def test_04_browser_rejects_unapproved_cors_origin(self):
        self.page.goto(self.origins[1])
        result = self.page.evaluate('''async api => {
          const {HttpTransport}=await import('/http-transport.js');
          const t=new HttpTransport({baseUrl:api,allowLocalhost:true,fetch:fetch.bind(window)});
          try {await t.createSession({username:'SYNTHETIC',password:'SYNTHETIC'});return 'unexpected_success';}
          catch(e) {return {kind:e.kind,status:e.status};}
        }''', f'https://localhost:{self.stack.port}')
        self.assertEqual(result, dict(kind='network', status=None))

    def test_05_server_expiry_clears_controller_and_transport(self):
        self.boot('reader')
        with sqlite3.connect(self.stack.config['session_db']) as db:
            db.execute("UPDATE sessions SET expires=0 WHERE username='reader'")
        result = self.page.evaluate('''async tenant => {
          let status=null;
          try {await window.controller.selectTenant(tenant);}catch(e){status=e.status;}
          return {status,state:window.controller.state.status,session:window.controller.state.session,
            hasSession:window.transport.hasSession};
        }''', T)
        self.assertEqual(result, dict(status=401, state='expired', session=None, hasSession=False))

    def test_99_database_failure_is_readable_and_gateway_failure_is_opaque(self):
        # Docker stop/start changes the runner's veth interfaces. Chromium reports
        # ERR_NETWORK_CHANGED asynchronously after those changes, even for loopback.
        # Keep destructive network lifecycle last, after the uninterrupted journey.
        self.boot()
        self.stack.run('docker', 'stop', self.stack.container)
        try:
            result = self.page.evaluate('''async tenant => {
              try {await window.transport.listClients(tenant);return 'unexpected_success';}
              catch(e){return {kind:e.kind,status:e.status};}
            }''', T)
            self.assertEqual(result, dict(kind='http', status=503))
        finally:
            self.stack.run('docker', 'start', self.stack.container)
            self.stack.ready_database()
        self.stack.stop(self.stack.api)
        try:
            result = self.page.evaluate('''async tenant => {
              try {await window.transport.listClients(tenant);return 'unexpected_success';}
              catch(e){return {kind:e.kind,status:e.status};}
            }''', T)
            self.assertEqual(result, dict(kind='network', status=None))
        finally:
            self.stack.start_api()
        # Recovery is eventual after a deliberate outage. Only this read is polled;
        # no mutation, login, intervention or request_id is ever retried here.
        deadline = time.monotonic() + 10
        while True:
            result = self.page.evaluate('''async t=>{
              try{return {count:(await window.transport.listClients(t)).data.length};}
              catch(e){return {kind:e.kind,status:e.status};}
            }''', T)
            if result == dict(count=1):
                break
            if time.monotonic() >= deadline:
                self.fail('Read did not recover after deliberate outage: ' + str(result))
            time.sleep(.1)

    def test_07_full_synthetic_value_journey_through_browser_transport(self):
        scenario = BrowserScenario(self.stack, self.page)
        result = scenario.run()
        self.assertTrue(result['synthetic_only'])
        self.assertEqual(result['missing_status'], 'resultado_inconclusivo')
        self.assertEqual(result['recovery_result']['status'], 'recuperacao_completa')
        self.assertEqual(result['recovery_result']['causal_attribution'], 'not_established')
        self.assertEqual(result['recovery_result']['independent_verification'], 'not_established')
        req = result['intervention_request']
        # Explicit same-key resend; it must reuse the execution, never repeat it.
        replay, _ = scenario.command(req['operation'], req['arguments'], key=req['request_id'])
        self.assertEqual(replay['id'], result['decision_id'])
        import psycopg
        with psycopg.connect(self.stack.config['users']['alice']['dsn']) as db:
            count = db.execute('SELECT count(*) FROM centerway.intervention_executions WHERE decision_id=%s', (result['decision_id'],)).fetchone()[0]
            self.assertEqual(count, 1)

    def test_08_invalid_login_keeps_actual_http_401(self):
        result = self.page.evaluate('''async api => {
          const {HttpTransport}=await import('/http-transport.js');
          const t=new HttpTransport({baseUrl:api,allowLocalhost:true,fetch:fetch.bind(window)});
          try {await t.createSession({username:'SYNTHETIC',password:'SYNTHETIC'});return 'unexpected_success';}
          catch(e) {return {kind:e.kind,status:e.status,code:e.code,hasSession:t.hasSession};}
        }''', f'https://localhost:{self.stack.port}')
        self.assertEqual(result, dict(kind='http', status=401, code='invalid_credentials', hasSession=False))
