import hashlib
import http.cookiejar
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPSHandler,HTTPCookieProcessor
from jsonschema import Draft202012Validator

from centerway.core import Core,Problem
from centerway import preview,production
from centerway.production import ProductionPolicy,BUSINESS_TABLES
from centerway.runtime import policy_for
from centerway.store import Store
from centerway.ops import check,backup


def manifest(path,rows=None):
    rows=rows or [
        {'user':'manager','memberships':[{'tenant':'tenant-a','role':'operator'}]},
        {'user':'auditor','memberships':[{'tenant':'tenant-a','role':'viewer'}]},
        {'user':'outsider','memberships':[{'tenant':'tenant-b','role':'operator'}]},
    ]
    path.write_text(json.dumps({'accounts':rows}));path.chmod(0o600)
    return path


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certs=tempfile.TemporaryDirectory();cls.cert=Path(cls.certs.name)/'cert.pem';cls.key=Path(cls.certs.name)/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.certs.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.path=self.root/'production.sqlite3';self.credentials=self.root/'production-secrets.json'
        self.config=manifest(self.root/'accounts.json');self.port=port();self.origin=f'https://127.0.0.1:{self.port}'
        production.provision(self.path,self.credentials,self.origin,self.config)
        self.passwords=json.loads(self.credentials.read_text())['accounts'];self.store=Store.open_existing(self.path)
        self.policy=ProductionPolicy(self.store);self.server=None
        self.client=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(self.cert))),HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        if self.server: self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()

    def start(self):
        from centerway.server import make_server
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,self.key)
        self.server=make_server(self.store,port=self.port,preview=self.policy,tls_context=context)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def call(self,path,body=None,headers=None):
        request=Request(self.origin+path,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json','Origin':self.origin,**(headers or {})})
        try: response=self.client.open(request)
        except HTTPError as error: response=error
        with response:
            raw=response.read();return response.status,json.loads(raw) if raw else None,response.headers

    def login(self,user='manager',password=None):
        return self.call('/api/login',{'user':user,'password':password if password is not None else self.passwords[user]})

    def test_permanent_empty_database_no_demo_accounts_or_lease_and_contract(self):
        self.assertFalse(self.policy.expired());self.assertIsNone(self.policy.expires)
        self.assertEqual('production',check(self.path,self.origin,'production')['mode'])
        self.assertIsNone(check(self.path,self.origin,'production')['expires'])
        with self.store.transaction() as db:
            for table in BUSINESS_TABLES: self.assertEqual(0,db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='preview_metadata'").fetchone())
            self.assertNotIn('expires',{row['name'] for row in db.execute('PRAGMA table_info(production_metadata)')})
        self.start();self.assertEqual(401,self.call('/api/view')[0])
        status,_,headers=self.login();self.assertEqual(200,status)
        for flag in ('__Host-cw_production_session=','Secure','HttpOnly','SameSite=Strict','Max-Age=3600'): self.assertIn(flag,headers['Set-Cookie'])
        view=self.call('/api/view')[1]
        self.assertEqual('production',view['environment_type']);self.assertEqual('disabled',view['decision_mode']);self.assertEqual([],view['registry'])
        self.assertTrue(all(value==0 for value in view['counts'].values()))
        spec=json.loads((Path(__file__).resolve().parents[1]/'contracts/openapi.json').read_text())
        Draft202012Validator({'$ref':'#/components/schemas/View','components':spec['components']}).validate(view)
        for path in ('/','/app.js','/style.css'): self.assertEqual(404,self.call(path)[0])
        self.assertEqual(200,self.call('/api/logout',{})[0]);self.assertEqual(401,self.call('/api/view')[0])

    def test_all_business_endpoints_blocked_without_invoking_core_or_writing(self):
        self.start();self.login()
        bodies={
            '/api/customers':{'tenant':'tenant-a','customer':'new','name':'Never simulated'},
            '/api/observations':{'tenant':'tenant-a','customer':'new','observations':[]},
            '/api/advance':{'tenant':'tenant-a','customer':'new'},
            '/api/execute':{'tenant':'tenant-a','customer':'new','case_id':'unknown'},
            '/api/verify':{'tenant':'tenant-a','customer':'new','case_id':'unknown'},
            '/api/simulate-usage':{'tenant':'tenant-a','customer':'new','case_id':'unknown'},
        }
        for path,body in bodies.items():
            status,result,_=self.call(path,body)
            self.assertEqual(503,status);self.assertEqual('unavailable',result['code'])
            self.assertNotIn('reused',result)
        self.assertEqual(503,self.call('/api/view?tenant=tenant-a&customer=new')[0])
        self.assertEqual(403,self.call('/api/view?tenant=tenant-b')[0])
        self.assertEqual(403,self.call('/api/advance',{'tenant':'tenant-b','customer':'new'})[0])
        self.call('/api/logout',{});self.login('auditor')
        self.assertEqual(403,self.call('/api/advance',{'tenant':'tenant-a','customer':'new'})[0])
        # Storage also blocks accidental direct invocation of the sandbox Core.
        with self.assertRaises(Problem): Core(self.store).create_customer('manager','tenant-a','new','Never simulated')
        with self.assertRaises(sqlite3.IntegrityError),self.store.transaction() as db:
            db.execute("INSERT INTO environments VALUES ('tenant-a','new','Never simulated','{}',0)")
        with self.store.transaction() as db:
            for table in BUSINESS_TABLES: self.assertEqual(0,db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])

    def test_mode_mismatch_public_credentials_and_demo_cookie_cannot_cross(self):
        demo_path=self.root/'demo.sqlite3';demo_secrets=self.root/'demo-secrets.json'
        preview.provision(demo_path,demo_secrets,self.origin)
        original=hashlib.sha256(demo_path.read_bytes()).hexdigest()
        with self.assertRaises((ValueError,sqlite3.Error)): ProductionPolicy(Store.open_existing(demo_path))
        self.assertEqual(original,hashlib.sha256(demo_path.read_bytes()).hexdigest())
        with self.assertRaises(ValueError): preview.PreviewPolicy(self.store)
        with self.assertRaises(ValueError): Store(self.path)
        with self.assertRaises(ValueError): production.provision(demo_path,self.root/'no-secrets.json',self.origin,self.config)
        with self.assertRaises(ValueError): policy_for('invalid',self.store)
        self.start()
        for user in ('demo','atlas','leitor','founder'):
            self.assertEqual(401,self.login(user,'centerway-local')[0])
        self.assertEqual(401,self.login('manager','centerway-local')[0])
        _,_,headers=self.login()
        token=headers['Set-Cookie'].split(';',1)[0].split('=',1)[1]
        self.assertEqual(401,self.call('/api/view',headers={'Cookie':'__Host-cw_session='+token})[0])
        with Store.open_existing(demo_path).transaction() as db:
            db.execute("INSERT INTO sessions VALUES ('demo-test-token','founder','2099-01-01T00:00:00+00:00')")
        self.assertEqual(401,self.call('/api/view',headers={'Cookie':'__Host-cw_production_session=demo-test-token'})[0])
        # Unchanged demo lease and capability remain explicitly sandbox-only.
        demo_policy=preview.PreviewPolicy(Store.open_existing(demo_path))
        self.assertIsNotNone(demo_policy.expires)
        with self.assertRaises(ValueError): preview.provision(self.root/'too-long.sqlite3',self.root/'too-long.json',self.origin,25)

    def test_permission_changes_removal_and_password_rotation_revoke_sessions(self):
        self.start();self.login();old=self.passwords['manager']
        rotated=self.root/'rotated.json';production.rotate_password(self.path,'manager',rotated)
        self.assertEqual(401,self.call('/api/view')[0]);self.assertEqual(401,self.login('manager',old)[0])
        new=json.loads(rotated.read_text())['accounts']['manager'];self.assertEqual(200,self.login('manager',new)[0])
        changed=manifest(self.root/'changed.json',[
            {'user':'manager','memberships':[{'tenant':'tenant-a','role':'viewer'}]},
            {'user':'outsider','memberships':[{'tenant':'tenant-b','role':'operator'}]},
            {'user':'new-user','memberships':[{'tenant':'tenant-b','role':'viewer'}]},
        ])
        added=self.root/'new-credentials.json';production.apply_accounts(self.path,changed,added)
        self.assertEqual(401,self.call('/api/view')[0]);self.assertEqual(200,self.login('manager',new)[0])
        self.assertEqual([{'tenant':'tenant-a','role':'viewer'}],self.call('/api/view')[1]['memberships'])
        self.assertEqual(403,self.call('/api/advance',{'tenant':'tenant-a','customer':'x'})[0])
        self.assertEqual({'new-user'},set(json.loads(added.read_text())['accounts']))
        with self.store.transaction() as db:
            self.assertFalse(db.execute("SELECT 1 FROM users WHERE id='auditor'").fetchone())
            self.assertEqual(3,db.execute('SELECT count(*) FROM production_auth_audit').fetchone()[0])
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM production_auth_audit')

    def test_expired_sessions_remain_expired_even_without_global_lease(self):
        self.start();self.login()
        with self.store.transaction() as db: db.execute("UPDATE sessions SET expires='2000-01-01T00:00:00+00:00'")
        self.assertEqual(401,self.call('/api/view')[0]);self.assertEqual(200,self.login()[0])
        self.assertFalse(self.policy.expired())

    def test_missing_guard_or_contaminated_data_fails_closed_without_repair(self):
        self.start();self.login()
        with self.store.transaction() as db: db.execute('DROP TRIGGER production_block_environments_INSERT')
        self.assertEqual(503,self.call('/api/view')[0])
        with self.assertRaises(ValueError): ProductionPolicy(self.store)
        with self.store.transaction() as db:
            db.execute("INSERT INTO environments VALUES ('tenant-a','fake','fake','{}',0)")
            db.execute(production.guards()['production_block_environments_INSERT'])
        with self.assertRaises(ValueError): ProductionPolicy(self.store)
        self.assertEqual(503,self.call('/api/view')[0])
        with self.store.transaction() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM environments').fetchone()[0])

    def test_invalid_config_and_secret_write_failure_leave_no_authorized_changes(self):
        unsafe=manifest(self.root/'unsafe.json',[{'user':'demo','memberships':[{'tenant':'tenant-a','role':'operator'}]}])
        with self.assertRaises(ValueError): production.apply_accounts(self.path,unsafe,self.root/'bad-output.json')
        before=self.path.read_bytes()
        with patch('centerway.production.secret_output',side_effect=OSError('test write failure')):
            with self.assertRaises(OSError): production.rotate_password(self.path,'manager',self.root/'failed.json')
        self.assertEqual(before,self.path.read_bytes());self.assertFalse((self.root/'failed.json').exists())
        self.assertEqual(0o600,stat.S_IMODE(self.credentials.stat().st_mode))
        self.assertEqual('verified',backup(self.path,self.root/'production-backup.sqlite3')['status'])

    def test_unsafe_account_manifests_and_public_hash_are_refused(self):
        original=self.path.read_bytes()
        invalid=[
            {'accounts':[]},
            {'accounts':[{'user':'owner','password':'public','memberships':[{'tenant':'tenant-a','role':'operator'}]}]},
            {'accounts':[{'user':'owner','memberships':[{'tenant':'atlas','role':'operator'}]}]},
            {'accounts':[{'user':'owner','memberships':[{'tenant':'tenant-a','role':'admin'}]}]},
            {'accounts':[{'user':'owner','memberships':[{'tenant':'tenant-a','role':'viewer'}]}]},
            {'accounts':[{'user':'owner','memberships':[{'tenant':'tenant-a','role':'operator'},{'tenant':'tenant-a','role':'viewer'}]}]},
        ]
        invalid.append({'accounts':invalid[2]['accounts']*2})
        for payload in invalid:
            self.config.write_text(json.dumps(payload))
            with self.assertRaises(ValueError): production.apply_accounts(self.path,self.config,self.root/'refused.json')
            self.assertEqual(original,self.path.read_bytes());self.assertFalse((self.root/'refused.json').exists())
        manifest(self.config);self.config.chmod(0o644)
        with self.assertRaises(ValueError): production.apply_accounts(self.path,self.config,self.root/'refused.json')
        self.assertEqual(original,self.path.read_bytes())
        # Even a correctly formatted hash of the public lab password is forbidden.
        with self.store.transaction() as db:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(production.password_hash('centerway-local'),'manager'))
        with self.assertRaises(ValueError): ProductionPolicy(self.store)

    def test_runtime_requires_explicit_mode_and_never_creates_missing_state(self):
        missing=self.root/'missing.sqlite3'
        result=subprocess.run([sys.executable,'-m','centerway.runtime','serve','--mode','production','--db',str(missing),'--certfile',str(self.cert),'--keyfile',str(self.key)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(1,result.returncode);self.assertFalse(missing.exists());self.assertIn('configuration_refused',result.stderr)
        result=subprocess.run([sys.executable,'-m','centerway.runtime','serve','--db',str(self.path),'--certfile',str(self.cert),'--keyfile',str(self.key)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(2,result.returncode)
