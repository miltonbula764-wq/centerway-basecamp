"""Real PostgreSQL logins/TLS; synthetic F01–F06 logical recovery, no SQL mocks."""
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace

import psycopg
from psycopg.conninfo import make_conninfo

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'api'),str(ROOT/'managed'),str(ROOT/'cloud-demo'),str(ROOT/'infra')]
from app import create_app,Database,APIError
from demo.provision import provision,T,B,C,BC
from session_store import PostgresSessions
from render_app import RenderEdge
from backup import backup,restore
from scenario import Scenario,setup_policy


def stable_journey(value):
    # SQL deliberately has no ORDER BY on work_items; preserve every value and
    # multiplicity, normalizing only that unordered operational projection.
    value=copy.deepcopy(value)
    value['work_items']=sorted(value.get('work_items',[]),key=lambda x:json.dumps(x,sort_keys=True))
    return value


class ManagedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=Path(os.environ['CW_HTTP_STATE'])
        cls.config,cls.credentials=provision(os.environ['CW_HTTP_CONTAINER'],os.environ['CW_HTTP_PORT'],cls.state)
        cls.owner=make_conninfo(host='127.0.0.1',port=os.environ['CW_HTTP_PORT'],dbname='postgres',user='postgres',sslmode='verify-full',sslrootcert=str(cls.state/'ca.pem'))
        # Existing Docker demo creates a random owner password: read from container
        # environment privately, not from output or repository configuration.
        inspected=json.loads(subprocess.check_output(['docker','inspect',os.environ['CW_HTTP_CONTAINER']]))[0]
        password=next(x.partition('=')[2] for x in inspected['Config']['Env'] if x.startswith('POSTGRES_PASSWORD='))
        cls.owner=make_conninfo(cls.owner,password=password)
        with psycopg.connect(cls.owner,autocommit=True) as db:
            db.execute((ROOT/'managed/sql/001_sessions.sql').read_text(),prepare=False)
            password=secrets.token_urlsafe(32)
            from psycopg import sql
            db.execute(sql.SQL('CREATE ROLE cw_sessions_runtime LOGIN PASSWORD {} IN ROLE cw_session_store').format(sql.Literal(password)))
        cls.config.update(demo=False,session_store='postgres',session_postgres=dict(principal='cw_sessions_runtime',dsn=make_conninfo(cls.owner,user='cw_sessions_runtime',password=password)),origins=['https://frontend.example.invalid'])
        for user in cls.config['users'].values():
            user['dsn']=make_conninfo(user['dsn'],sslmode='verify-full',sslrootcert=str(cls.state/'ca.pem'))
        cls.app=create_app(cls.config)

    def http(self,method,path,data=None,token=None,app=None,headers=None):
        h={'Origin':'https://frontend.example.invalid'}
        if token: h['Authorization']='Bearer '+token
        h.update(headers or {})
        r=(app or self.app).test_client().open(path,method=method,json=data,headers=h,base_url='https://localhost')
        return r.status_code,r.get_json(silent=True)

    def login(self,user='alice',app=None):
        status,body=self.http('POST','/v1/sessions',dict(username=user,password=self.credentials[user]),app=app)
        self.assertEqual(status,201,body)
        return body['access_token']

    def setUp(self):
        # Each app has an independent in-memory limiter, as after a process restart.
        self.app=create_app(self.config)

    def test_01_persistent_digest_and_logout_across_instances(self):
        token=self.login()
        with psycopg.connect(self.owner) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM cw_sessions.sessions WHERE digest=%s',(token,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM cw_sessions.sessions WHERE digest=%s',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()[0],1)
        other=create_app(self.config)
        self.assertEqual(self.http('GET','/v1/session',token=token,app=other)[0],200)
        self.assertEqual(self.http('DELETE','/v1/session',token=token,app=other)[0],204)
        self.assertEqual(self.http('GET','/v1/session',token=token)[0],401)

    def test_02_expiration_and_config_revocation(self):
        token=self.login()
        with psycopg.connect(self.owner) as db:
            db.execute('UPDATE cw_sessions.sessions SET expires=1 WHERE digest=%s',(hashlib.sha256(token.encode()).hexdigest(),))
        self.assertEqual(self.http('GET','/v1/session',token=token)[0],401)
        token=self.login()
        config=copy.deepcopy(self.config); config['users']['alice']['operations']=[]
        self.assertEqual(self.http('GET','/v1/session',token=token,app=create_app(config))[0],401)

    def test_03_scopes_and_database_rls(self):
        token=self.login()
        route=lambda t,c:f'/v1/tenants/{t}/clients/{c}/journey'
        self.assertEqual(self.http('GET',route(T,C),token=token)[0],200)
        self.assertEqual(self.http('GET',route(B,BC),token=token)[0],403)
        # Bypass HTTP scopes deliberately; PostgreSQL itself must still reject visibility.
        result=Database(False).call(self.config['users']['alice'],'journey',(B,BC))
        self.assertIsNone(result)
        self.assertEqual(self.http('POST',f'/v1/tenants/{T}/clients/{C}/operations',{'request_id':'invalid'},token=self.login('reader'))[0],422)

    def test_04_concurrent_session_cap(self):
        store=PostgresSessions(self.config['session_postgres'])
        def put(i): store.put(hashlib.sha256(f'parallel-{i}'.encode()).hexdigest(),'parallel','a'*64,time.time()+900+i)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(put,range(24)))
        with psycopg.connect(self.owner) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM cw_sessions.sessions WHERE username='parallel'").fetchone()[0],10)

    def test_05_least_privilege_and_tls(self):
        with psycopg.connect(self.config['session_postgres']['dsn']) as db:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege): db.execute('SELECT * FROM centerway.clients')
        with psycopg.connect(self.config['users']['alice']['dsn']) as db:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege): db.execute('SELECT * FROM cw_sessions.sessions')
        with self.assertRaises(ValueError): PostgresSessions(dict(dsn=self.owner,principal='postgres'))
        config=copy.deepcopy(self.config['session_postgres']); config['dsn']=make_conninfo(config['dsn'],sslmode='require')
        with self.assertRaises(ValueError): PostgresSessions(config)
        with self.assertRaises(psycopg.OperationalError):
            with psycopg.connect(make_conninfo(self.owner,sslrootcert='/nonexistent-ca'),connect_timeout=2): pass

    def test_06_session_failure_closed_and_recovery(self):
        token=self.login()
        with psycopg.connect(self.owner,autocommit=True) as db:
            db.execute('ALTER ROLE cw_sessions_runtime NOLOGIN')
            try:
                status,body=self.http('GET','/v1/session',token=token)
                self.assertEqual(status,503); self.assertEqual(body,{'error':{'code':'session_store_unavailable'}})
            finally: db.execute('ALTER ROLE cw_sessions_runtime LOGIN')
        self.assertEqual(self.http('GET','/v1/session',token=token)[0],200)

    def test_07_render_boundary_ignores_spoofed_headers(self):
        app=create_app(self.config); app.wsgi_app=RenderEdge(app.wsgi_app,'centerway-test.onrender.com')
        c=app.test_client()
        headers={'Forwarded':'proto=http;host=evil.invalid','X-Forwarded-Proto':'http','X-Forwarded-Host':'evil.invalid','X-Forwarded-For':'1.2.3.4'}
        r=c.post('/v1/sessions',json=dict(username='alice',password=self.credentials['alice']),headers=headers,base_url='http://centerway-test.onrender.com')
        self.assertEqual(r.status_code,201)
        self.assertEqual(c.get('/v1/session',base_url='https://evil.invalid').status_code,400)
        plain=create_app(self.config).test_client()
        self.assertEqual(plain.get('/health',headers={'X-Forwarded-Proto':'https'},base_url='http://localhost').status_code,400)
        self.assertEqual(c.get('/health',base_url='http://localhost').get_json()['readiness'],'not_assessed')
        with self.assertRaises(ValueError): RenderEdge(app,'evil.invalid')

    def test_08_logical_encrypted_recovery_and_intervention_replay(self):
        owner=self.owner
        def sql_apply(statement):
            with psycopg.connect(owner) as db: db.execute(statement,prepare=False)
        setup_policy(SimpleNamespace(sql=sql_apply))
        demo=SimpleNamespace(state=self.state,credentials=self.credentials)
        # Reuse the exact existing synthetic F01–F06 scenario, with real DB/API.
        test=self
        class ManagedScenario(Scenario):
            def __init__(self): self.demo=demo; self.tokens={}
            def request(self,method,path,data=None,user='alice'):
                return test.http(method,path,data,self.tokens.get(user))
        scenario=ManagedScenario(); result=scenario.run()
        self.assertEqual(result['recovery_result']['status'],'recuperacao_completa')
        route=f'/v1/tenants/{T}/clients/{C}/journey'
        before=self.http('GET',route,token=scenario.tokens['alice'])[1]['data']
        key=self.state/'backup.key'
        subprocess.run(['age-keygen','-o',str(key)],check=True,capture_output=True)
        key.chmod(0o600)
        recipient=subprocess.check_output(['age-keygen','-y',str(key)],text=True).strip()
        archive=self.state/'logical.age'; backup(owner,archive,recipient)
        self.assertNotIn(b'SYNTHETIC',archive.read_bytes())
        with self.assertRaises(ValueError): restore(owner,archive,key)
        wrong=self.state/'wrong.key'
        subprocess.run(['age-keygen','-o',str(wrong)],check=True,capture_output=True); wrong.chmod(0o600)
        with psycopg.connect(owner,autocommit=True) as db: db.execute('CREATE DATABASE cw_restored')
        target=make_conninfo(owner,dbname='cw_restored')
        corrupt=self.state/'corrupt.age'; corrupt.write_bytes(archive.read_bytes()[:-20]+b'changed'); corrupt.chmod(0o600)
        with self.assertRaises(Exception): restore(target,corrupt,key)
        with self.assertRaises(Exception): restore(target,archive,wrong)
        restore(target,archive,key)
        with self.assertRaises(ValueError): restore(target,archive,key)
        config=copy.deepcopy(self.config)
        for user in config['users'].values(): user['dsn']=make_conninfo(user['dsn'],dbname='cw_restored')
        config['session_postgres']['dsn']=make_conninfo(config['session_postgres']['dsn'],dbname='cw_restored')
        restored=create_app(config)
        self.assertEqual(self.http('GET',route,token=scenario.tokens['alice'],app=restored)[0],401)
        token=self.login(app=restored)
        self.assertEqual(stable_journey(self.http('GET',route,token=token,app=restored)[1]['data']),stable_journey(before))
        status,_=self.http('POST',f'/v1/tenants/{T}/clients/{C}/operations',result['intervention_request'],token,app=restored)
        self.assertEqual(status,200)
        after=self.http('GET',route,token=token,app=restored)[1]['data']
        self.assertEqual(stable_journey(after),stable_journey(before))
        self.assertIsNone(Database(False).call(config['users']['bob'],'journey',(T,C)))

    def test_09_actual_render_gunicorn_command(self):
        env=os.environ.copy()
        env.update(RENDER='true',RENDER_SERVICE_ID='srv-test',RENDER_EXTERNAL_HOSTNAME='centerway-test.onrender.com',CENTERWAY_MANAGED_CONFIG=json.dumps(self.config))
        config=json.loads(env['CENTERWAY_MANAGED_CONFIG']); config['synthetic_only']=True
        env['CENTERWAY_MANAGED_CONFIG']=json.dumps(config)
        result=subprocess.run([str(Path(sys.executable).with_name('gunicorn')),'--chdir','recovery-mvp/managed','-c','gunicorn.conf.py','--check-config','render_app:load_render_app()'],cwd=ROOT.parent,env=env,capture_output=True)
        self.assertEqual(result.returncode,0,'Exact Render startup/configuration command rejected')
