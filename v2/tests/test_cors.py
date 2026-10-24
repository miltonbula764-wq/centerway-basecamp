"""CORS is opt-in transport, never a substitute for authentication/tenant checks."""
import http.cookiejar
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from centerway.preview import provision,PreviewPolicy
from centerway.server import make_server
from centerway.store import Store


class HttpsFixture:
    enabled=True

    @classmethod
    def setUpClass(cls):
        cls.cert_temp=tempfile.TemporaryDirectory()
        cls.cert=Path(cls.cert_temp.name)/'cert.pem';cls.key=Path(cls.cert_temp.name)/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.cert_temp.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.origin=f'https://127.0.0.1:{port}'
        self.frontend='https://127.0.0.1:9444'
        self.credentials=Path(self.temp.name)/'credentials.json'
        self.path=Path(self.temp.name)/'db.sqlite3'
        provision(self.path,self.credentials,self.origin)
        self.passwords=json.loads(self.credentials.read_text())['accounts']
        self.store=Store(self.path,seed_demo=False)
        self.policy=PreviewPolicy(self.store)
        self.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=port,preview=self.policy,tls_context=self.context,frontend_origins=[self.frontend] if self.enabled else [])
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(self.cert))),HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def call(self,path,body=None,method=None,origin=None,headers=None):
        request=Request(self.origin+path,json.dumps(body).encode() if body is not None else None,
            {'Content-Type':'application/json','Origin':origin or self.frontend,**(headers or {})},method=method)
        try: response=self.client.open(request)
        except HTTPError as error: response=error
        with response:
            payload=response.read()
            return response.status,json.loads(payload) if payload else None,response.headers

    def preflight(self,method='POST',headers='content-type',origin=None):
        return self.call('/api/login',method='OPTIONS',origin=origin,headers={'Access-Control-Request-Method':method,'Access-Control-Request-Headers':headers})


class CorsTests(HttpsFixture,unittest.TestCase):
    def test_preflight_and_real_credentials_require_auth_and_keep_isolation(self):
        status,body,headers=self.preflight()
        self.assertEqual(204,status);self.assertIsNone(body)
        self.assertIsNone(headers.get('Content-Length'))
        self.assertEqual(self.frontend,headers['Access-Control-Allow-Origin'])
        self.assertEqual('true',headers['Access-Control-Allow-Credentials'])
        self.assertEqual('POST',headers['Access-Control-Allow-Methods'])
        self.assertEqual('Origin',headers['Vary'])
        status,body,headers=self.call('/api/view')
        self.assertEqual(401,status);self.assertEqual('unauthenticated',body['code'])
        self.assertEqual(self.frontend,headers['Access-Control-Allow-Origin'])
        status,_,headers=self.call('/api/login',{'user':'atlas-private','password':self.passwords['atlas-private']})
        self.assertEqual(200,status);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertIn('Secure',headers['Set-Cookie'])
        status,body,_=self.call('/api/view')
        self.assertEqual(200,status);self.assertEqual(75,len(body['registry']))
        self.assertTrue(all(row['tenant']=='atlas' for row in body['registry']))
        status,body,headers=self.call('/api/view?tenant=nimbus&customer=client-007')
        self.assertEqual(403,status);self.assertEqual('forbidden',body['code'])
        self.assertEqual(self.frontend,headers['Access-Control-Allow-Origin'])
        self.assertEqual(200,self.call('/api/logout',{})[0])
        self.assertEqual(401,self.call('/api/view')[0])

    def test_unknown_origins_methods_headers_and_cross_site_are_denied(self):
        for origin in ('https://evil.example','null',self.frontend+'.evil.example'):
            status,_,headers=self.preflight(origin=origin)
            self.assertEqual(403,status);self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
        self.assertEqual(405,self.preflight(method='DELETE')[0])
        self.assertEqual(400,self.preflight(headers='content-type, authorization')[0])
        self.assertEqual(400,self.preflight(headers='x-forged-role')[0])
        status,body,_=self.call('/api/login',{'user':'founder','password':self.passwords['founder']},headers={'Sec-Fetch-Site':'cross-site'})
        self.assertEqual(403,status);self.assertEqual('forbidden',body['code'])
        self.assertEqual(421,self.call('/api/view',headers={'Host':'evil.example','X-Forwarded-Host':self.policy.authority})[0])

    def test_configuration_cannot_enable_cors_for_public_lab_or_wildcards(self):
        lab=Store(Path(self.temp.name)/'lab.sqlite3')
        with self.assertRaises(ValueError):
            make_server(lab,port=0,frontend_origins=[self.frontend])
        for origin in ('*','https://*.example.com','http://example.com','https://example.com/path','https://user:pass@example.com'):
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                make_server(self.store,port=0,preview=self.policy,tls_context=self.context,frontend_origins=[origin])

    def test_rate_limit_is_readable_without_exposing_session_or_password(self):
        for _ in range(10):
            self.assertEqual(401,self.call('/api/login',{'user':'founder','password':'wrong'})[0])
        status,body,headers=self.call('/api/login',{'user':'founder','password':self.passwords['founder']})
        self.assertEqual(429,status);self.assertEqual('rate_limited',body['code'])
        self.assertEqual('60',headers['Retry-After'])
        self.assertIn('Retry-After',headers['Access-Control-Expose-Headers'])
        self.assertIsNone(headers.get('Set-Cookie'))
        self.assertNotIn(self.passwords['founder'],json.dumps(body))


class CorsDefaultTests(HttpsFixture,unittest.TestCase):
    enabled=False

    def test_cross_origin_remains_disabled_by_default(self):
        status,_,headers=self.preflight()
        self.assertEqual(403,status);self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
        self.assertEqual(403,self.call('/api/view')[0])
        status,_,_=self.call('/api/login',{'user':'founder','password':self.passwords['founder']},origin=self.origin)
        self.assertEqual(200,status)
