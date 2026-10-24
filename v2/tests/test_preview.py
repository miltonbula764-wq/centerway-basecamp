"""Verified TLS locally using an explicitly trusted disposable test certificate."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import stat
import subprocess
import tempfile
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from unittest.mock import patch
from datetime import datetime,timedelta,timezone

from centerway.preview import provision,PreviewPolicy,canonical_origin,LoginLimiter
from centerway.server import make_server
from centerway.store import Store


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cert_temp=tempfile.TemporaryDirectory()
        cls.cert=Path(cls.cert_temp.name)/'test-cert.pem'
        cls.key=Path(cls.cert_temp.name)/'test-key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2',
                        '-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=localhost',
                        '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.cert_temp.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'preview.sqlite3'
        self.credentials=Path(self.temp.name)/'credentials.json'
        with socket.socket() as port_socket:
            port_socket.bind(('127.0.0.1',0))
            port=port_socket.getsockname()[1]
        self.origin=f'https://127.0.0.1:{port}'
        provision(self.path,self.credentials,self.origin)
        self.passwords=json.loads(self.credentials.read_text())['accounts']
        self.store=Store(self.path,seed_demo=False)
        self.policy=PreviewPolicy(self.store)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=port,preview=self.policy,tls_context=context)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        # Certificate validation remains enabled: trust only our explicit test CA.
        self.client=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(self.cert))),
                                 HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        payload=json.dumps(body).encode() if body is not None else None
        request_headers={'Content-Type':'application/json','Origin':self.origin,**(headers or {})}
        req=Request(self.origin+path,payload,request_headers)
        try:
            response=self.client.open(req)
        except HTTPError as response:
            return response.code,response.read(),response.headers
        with response:
            return response.status,response.read(),response.headers

    def login(self,user='founder'):
        return self.request('/api/login',{'user':user,'password':self.passwords[user]})

    def test_private_login_no_public_accounts_passwords_or_data_and_secure_cookie(self):
        status,html,headers=self.request('/')
        self.assertEqual(200,status)
        self.assertNotIn(b'centerway-local',html)
        self.assertNotIn(b'value="demo"',html)
        self.assertNotIn(b'value="leitor"',html)
        self.assertNotIn(b'value="atlas"',html)
        self.assertNotIn(b'Cliente sint',html)
        self.assertNotIn(b'value="'+self.passwords['founder'].encode()+b'"',html)
        self.assertIn(b'autocomplete="username"',html)
        self.assertIn('max-age=',headers['Strict-Transport-Security'])
        self.assertEqual('no-store',headers['Cache-Control'])
        self.assertEqual('DENY',headers['X-Frame-Options'])
        self.assertEqual(401,self.request('/api/view')[0])
        for user in ('demo','atlas','leitor'):
            self.assertEqual(401,self.request('/api/login',{'user':user,'password':'centerway-local'})[0])
        status,_,headers=self.login()
        self.assertEqual(200,status)
        cookie=headers['Set-Cookie']
        self.assertTrue(cookie.startswith('__Host-cw_session='))
        for flag in ('Secure','HttpOnly','SameSite=Strict','Path=/','Max-Age=3600'):
            self.assertIn(flag,cookie)
        status,payload,_=self.request('/api/view')
        self.assertEqual(150,len(json.loads(payload)['registry']))
        self.assertEqual(200,self.request('/api/logout',{})[0])
        self.assertEqual(401,self.request('/api/view')[0])
        self.assertEqual(0o600,stat.S_IMODE(self.credentials.stat().st_mode))
        self.assertEqual(0o600,stat.S_IMODE(self.path.stat().st_mode))

    def test_isolation_and_permissions_over_verified_https(self):
        self.login('atlas-private')
        registry=json.loads(self.request('/api/view')[1])['registry']
        self.assertEqual(75,len(registry))
        self.assertTrue(all(row['tenant']=='atlas' for row in registry))
        self.assertEqual(403,self.request('/api/view?tenant=nimbus&customer=client-007')[0])
        view=json.loads(self.request('/api/view?tenant=atlas&customer=client-007')[1])
        body={'tenant':'atlas','customer':'client-008','case_id':view['case']['id']}
        self.assertEqual(404,self.request('/api/execute',body)[0])
        body['customer']='client-007'
        self.assertEqual(200,self.request('/api/execute',body)[0])
        result=json.loads(self.request('/api/verify',body)[1])
        self.assertTrue(result['value_recovered'])
        self.assertEqual('sandbox',result['scope'])
        self.request('/api/logout',{})
        self.login('reader-private')
        self.assertEqual(75,len(json.loads(self.request('/api/view')[1])['registry']))
        self.assertEqual(403,self.request('/api/advance',{'tenant':'nimbus','customer':'client-007'})[0])

    def test_origin_host_forwarded_headers_expiry_and_path_guards(self):
        self.assertEqual(403,self.request('/api/login',{'user':'founder','password':'bad'},{'Origin':'https://evil.example'})[0])
        self.assertEqual(403,self.request('/api/login',{'user':'founder','password':'bad'},{'Origin':''})[0])
        self.assertEqual(421,self.request('/',headers={'Host':'evil.example','X-Forwarded-Host':self.policy.authority})[0])
        self.assertEqual(404,self.request('/../../credentials.json')[0])
        self.assertEqual(404,self.request('/data/preview.sqlite3')[0])
        self.login()
        with self.store.transaction() as db:
            db.execute('UPDATE sessions SET expires=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),))
        self.assertEqual(401,self.request('/api/view')[0])
        self.policy.expires=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.assertEqual(503,self.request('/api/view')[0])
        self.assertEqual(503,self.request('/')[0])

    def test_login_throttle_over_https(self):
        for _ in range(10):
            self.assertEqual(401,self.request('/api/login',{'user':'founder','password':'wrong'})[0])
        self.assertEqual(429,self.login()[0])
        limiter=LoginLimiter()
        with patch('centerway.preview.time.monotonic',return_value=1):
            self.assertTrue(all(limiter.allow('one','founder') for _ in range(10)))
            self.assertFalse(limiter.allow('two','founder'))
        with patch('centerway.preview.time.monotonic',return_value=62):
            self.assertTrue(limiter.allow('one','founder'))

    def test_fail_closed_without_tls_private_metadata_or_credentials(self):
        template=Path(self.temp.name)/'changed-template'
        template.mkdir()
        (template/'index.html').write_text('<h1>centerway-local</h1>')
        with patch('centerway.server.STATIC',template):
            status,payload,_=self.request('/')
            self.assertEqual(503,status)
            self.assertNotIn(b'centerway-local',payload)
        cli=subprocess.run([sys.executable,'-m','centerway.preview','serve','--db',str(self.path),
                            '--certfile',str(self.path.parent/'missing-cert.pem'),
                            '--keyfile',str(self.path.parent/'missing-key.pem')],
                           cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=5)
        self.assertEqual(1,cli.returncode)
        self.assertIn('Arranque recusado',cli.stderr)
        self.assertNotIn('Servidor HTTPS privado iniciado',cli.stdout)
        with self.assertRaises(ValueError):
            make_server(self.store,preview=self.policy)
        with self.assertRaises(ValueError):
            make_server(self.store)
        lab=Store(Path(self.temp.name)/'lab.sqlite3')
        with self.assertRaises(ValueError):
            make_server(lab,host='0.0.0.0')
        with self.assertRaises(ValueError):
            PreviewPolicy(lab)
        with self.assertRaises(ValueError):
            provision(self.path,self.credentials,self.origin)
        with self.assertRaises(ValueError):
            canonical_origin('http://example.com')
        with self.assertRaises(ValueError):
            canonical_origin('https://example.com/path')
        with self.store.transaction() as db:
            salt='test-public-password'
            digest=hashlib.scrypt(b'centerway-local',salt=salt.encode(),n=16384,r=8,p=1).hex()
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(salt+':'+digest,'founder'))
        with self.assertRaises(ValueError):
            PreviewPolicy(self.store)
