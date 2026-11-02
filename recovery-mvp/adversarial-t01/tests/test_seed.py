"""Real PG17/TLS/authenticated API. Never operate the T01 journey beyond F01."""
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'api'),str(ROOT/'managed'),str(ROOT/'adversarial-t01')]
from app import create_app, Database
from demo.provision import provision,T,B,C,BC
from seed import prepare,apply,fixture,check_target,load_initial,private_read,private_write,bootstrap,check_activation,SPECS


class T01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=Path(os.environ['CW_HTTP_STATE'])
        cls.config,cls.old_credentials=provision(os.environ['CW_HTTP_CONTAINER'],os.environ['CW_HTTP_PORT'],cls.state)
        # Owner password is used privately; never passed in argv or emitted.
        inspected=json.loads(subprocess.check_output(['docker','inspect',os.environ['CW_HTTP_CONTAINER']]))[0]
        password=next(x.partition('=')[2] for x in inspected['Config']['Env'] if x.startswith('POSTGRES_PASSWORD='))
        cls.owner=dict(synthetic_only=True,dsn=make_conninfo(host='127.0.0.1',port=os.environ['CW_HTTP_PORT'],dbname='postgres',user='postgres',password=password,sslmode='verify-full',sslrootcert=str(cls.state/'ca.pem')))
        with psycopg.connect(cls.owner['dsn'],autocommit=True) as db:
            db.execute((ROOT/'managed/sql/001_sessions.sql').read_text(),prepare=False)
            password=secrets.token_urlsafe(32)
            db.execute(sql.SQL('CREATE ROLE cw_sessions_runtime LOGIN PASSWORD {} IN ROLE cw_session_store').format(sql.Literal(password)))
        cls.config.update(demo=False,synthetic_only=True,session_store='postgres',session_postgres=dict(principal='cw_sessions_runtime',dsn=make_conninfo(cls.owner['dsn'],user='cw_sessions_runtime',password=password)),origins=['https://frontend.example.invalid'])
        for user in cls.config['users'].values():
            user['dsn']=make_conninfo(user['dsn'],sslmode='verify-full',sslrootcert=str(cls.state/'ca.pem'))
        # Existing demonstration receipt must survive addition of T01.
        Database(False).call(cls.config['users']['alice'],'operate',(T,C,str(uuid4()),'append_value',dict(kind='source',id=str(uuid4()),expected_revision=0,reason='Existing A demo receipt',data=dict(name='Existing A',locator='synthetic://existing-a',method='existing'))))
        cls.before=cls.other_tenants()
        cls.output=cls.state/'t01-private'
        cls.bundle=prepare(cls.owner,cls.config,cls.output)
        cls.data,_=fixture()
        # Simulate an interruption after committed owner bootstrap, before F01 data.
        with psycopg.connect(cls.owner['dsn']) as db:
            bootstrap(db,cls.bundle,cls.data)
            if db.execute('SELECT count(*) FROM centerway.evidence_versions WHERE tenant_id=%s',(cls.data['tenant_id'],)).fetchone()[0] != 0:
                raise AssertionError('bootstrap ran business engines or loaded observations')
        apply(cls.owner,cls.bundle)
        cls.runtime=private_read(cls.output/'runtime-config.json')
        cls.credentials=private_read(cls.output/'credentials.json')

    @classmethod
    def other_tenants(cls):
        with psycopg.connect(cls.owner['dsn']) as db:
            tables=db.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='centerway' AND c.relkind='r'").fetchall()
            result={}
            for (table,) in tables:
                rows=db.execute(sql.SQL('SELECT to_jsonb(t) FROM centerway.{} t WHERE tenant_id IN (%s,%s)').format(sql.Identifier(table)),(T,B)).fetchall()
                result[table]=sorted([json.dumps(r[0],sort_keys=True) for r in rows])
            return result

    def setUp(self):
        self.app=create_app(self.runtime)
        self.route=f"/v1/tenants/{self.data['tenant_id']}/clients/{self.data['client_id']}"

    def http(self,method,path,data=None,token=None):
        headers={'Origin':self.config['origins'][0]}
        if token: headers['Authorization']='Bearer '+token
        return self.app.test_client().open(path,method=method,json=data,headers=headers,base_url='https://localhost')

    def login(self,username):
        credentials=self.credentials if username.startswith('t01_') else self.old_credentials
        response=self.http('POST','/v1/sessions',dict(username=username,password=credentials[username]))
        self.assertEqual(response.status_code,201)
        return response.get_json()['access_token']

    def count(self,table):
        with psycopg.connect(self.owner['dsn']) as db:
            return db.execute(sql.SQL('SELECT count(*) FROM centerway.{} WHERE tenant_id=%s').format(sql.Identifier(table)),(self.data['tenant_id'],)).fetchone()[0]

    def test_01_initial_data_only_no_anticipation(self):
        response=self.http('GET',self.route+'/journey',token=self.login('t01_operator'))
        self.assertEqual(response.status_code,200)
        journey=response.get_json()['data']
        self.assertEqual(len(journey['contracts']),9)
        self.assertEqual(len(journey['evidence_history']),8)
        self.assertEqual(len(journey['sources']),7)
        for field in ('detections','investigations','decisions','executions','recovery_plans','operations'):
            self.assertEqual(journey[field],[],field)
        self.assertEqual(journey['work_items'][0]['next'],'detect')
        self.assertEqual(self.count('discovery_inputs'),2)
        self.assertEqual(self.count('intervention_policies'),0)
        for table in ('discoveries','investigation_runs','investigation_verification_versions','recovery_runs'):
            self.assertEqual(self.count(table),0)
        self.assertNotIn('s9',json.dumps(journey,ensure_ascii=False).lower())

    def test_02_repeat_concurrent_apply_preserves_a_b_and_audit(self):
        before=self.count('audit_log')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _:apply(self.owner,self.bundle),range(2)))
        self.assertEqual(self.count('audit_log'),before)
        self.assertEqual(self.other_tenants(),self.before)
        for user in self.config['users']:
            self.assertEqual(self.runtime['users'][user],self.config['users'][user])
        for key in set(self.config)-{'users'}:
            self.assertEqual(self.runtime[key],self.config[key])

    def test_03_http_and_database_isolation_both_directions(self):
        for username in ('alice','bob'):
            token=self.login(username)
            self.assertEqual(self.http('GET',self.route+'/journey',token=token).status_code,403)
            self.assertEqual(self.http('GET',f"/v1/tenants/{self.data['tenant_id']}/clients",token=token).status_code,403)
            self.assertIsNone(Database(False).call(self.runtime['users'][username],'journey',(self.data['tenant_id'],self.data['client_id'])))
            with psycopg.connect(self.runtime['users'][username]['dsn']) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM centerway.audit_log WHERE tenant_id=%s',(self.data['tenant_id'],)).fetchone()[0],0)
        for username in SPECS:
            token=self.login(username)
            directory=self.http('GET',f"/v1/tenants/{self.data['tenant_id']}/clients",token=token)
            self.assertEqual(directory.get_json()['data'],[dict(client_id=self.data['client_id'],display_name='Meridian Distribuição')])
            for tenant,client in ((T,C),(B,BC)):
                self.assertEqual(self.http('GET',f'/v1/tenants/{tenant}/clients/{client}/journey',token=token).status_code,403)
                self.assertIsNone(Database(False).call(self.runtime['users'][username],'journey',(tenant,client)))
        self.assertEqual(self.http('GET',self.route+'/journey').status_code,401)

    def test_04_permissions_and_no_self_authorization(self):
        token=self.login('t01_reader')
        request=dict(request_id=str(uuid4()),operation='append_value',arguments=dict(kind='source',id=str(uuid4()),expected_revision=0,reason='denied',data=dict(name='denied',locator='synthetic://denied',method='denied')))
        before=self.count('audit_log')
        self.assertEqual(self.http('POST',self.route+'/operations',request,token).status_code,403)
        self.assertEqual(self.count('audit_log'),before)
        for username in SPECS:
            with psycopg.connect(self.runtime['users'][username]['dsn']) as db:
                row=db.execute("SELECT session_user::text,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=session_user").fetchone()
                self.assertEqual(row,(SPECS[username][0],False,False,False,False,False))
                self.assertFalse(db.execute("SELECT has_table_privilege(session_user,'centerway.intervention_policies','INSERT')").fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute('INSERT INTO centerway.intervention_policies DEFAULT VALUES')
        self.assertEqual(self.runtime['users']['t01_reader']['operations'],[])
        self.assertEqual(self.runtime['users']['t01_reviewer']['operations'],['append_investigation','investigate'])

    def test_05_provenance_quality_weeks_and_actual_file_hashes(self):
        with psycopg.connect(self.runtime['users']['t01_operator']['dsn']) as db:
            evidence=db.execute('SELECT to_jsonb(e) FROM centerway.evidence_versions e WHERE tenant_id=%s ORDER BY contract_revision',(self.data['tenant_id'],)).fetchall()
            for i,(e,) in enumerate(evidence,1):
                self.assertEqual(e['observed_value'],[39,35,29,30,33,37,36,34][i-1])
                self.assertEqual(e['quality'],'partial' if i==7 else 'verified')
                self.assertEqual(e['actor'],'cw_t01_operator')
                self.assertEqual(e['content_sha256'],hashlib.sha256((ROOT/'adversarial-t01/documents'/f's{i}.json').read_bytes()).hexdigest())
                self.assertEqual(e['revision'],1)
                self.assertEqual(e['unit'],'horas')
            contracts=db.execute('SELECT baseline,minimum_acceptable,target,direction::text FROM centerway.contract_versions WHERE tenant_id=%s',(self.data['tenant_id'],)).fetchall()
            self.assertEqual(contracts,[(40,24,24,'lower')]*9)
            entities={r[0] for r in db.execute('SELECT DISTINCT entity FROM centerway.audit_log WHERE tenant_id=%s',(self.data['tenant_id'],))}
            self.assertTrue({'companies','clients','memberships','source_versions','contract_versions','evidence_versions','discovery_inputs','discovery_rules','sandbox_flags','intervention_catalog'} <= entities)
            for item in self.data['discovery_inputs']:
                self.assertNotIn('verification',item)
                self.assertIn('não comprovado',item['factor']['hypothesis'])
                self.assertIn('não',item['factor']['condition'])
                self.assertEqual([e['purpose'] for e in item['evidence']],['condition_met'])
                self.assertFalse(item['evidence'][0]['assertion'])

    def test_06_incompatible_csv_and_missing_timestamp_not_coerced(self):
        evidence=next(r for r in self.data['records'] if r['kind']=='evidence' and r['data']['contract_revision']==7)
        row=copy.deepcopy(evidence['data']); row.update(observed_value=22,measurement_method='média aritmética; inclui P1')
        with psycopg.connect(self.runtime['users']['t01_operator']['dsn']) as db:
            with self.assertRaises(psycopg.errors.CheckViolation):
                db.execute('SELECT centerway.append_version(%s,%s,%s,%s,%s,%s,%s)',(self.data['tenant_id'],self.data['client_id'],'evidence',str(uuid4()),0,'incompatible test rolled back',Jsonb(row)))
        self.assertEqual(self.count('evidence_versions'),8)
        with psycopg.connect(self.owner['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.evidence_versions WHERE tenant_id=%s AND observed_value=0',(self.data['tenant_id'],)).fetchone()[0],0)

    def test_07_bundle_files_guards_and_future_quarantine(self):
        for name in ('bundle.json','runtime-config.json','credentials.json'):
            self.assertEqual((self.output/name).stat().st_mode & 0o777,0o600)
        self.assertEqual(self.output.stat().st_mode & 0o777,0o700)
        with self.assertRaises(ValueError): prepare(self.owner,self.config,self.output)
        bad=copy.deepcopy(self.bundle); bad['fixture_sha256']='0'*64
        with self.assertRaises(ValueError): apply(self.owner,bad)
        remote=copy.deepcopy(self.bundle); remote['target']['host']='demo.example.invalid'
        remote_dsn=make_conninfo(self.owner['dsn'],host='demo.example.invalid')
        with self.assertRaises(ValueError): check_target(remote_dsn,remote)
        with self.assertRaises(ValueError): check_target(remote_dsn,remote,True,'wrong')
        # Pure guard, no DNS or connection. Explicit activation is a future operator action.
        check_target(remote_dsn,remote,True,self.data['tenant_id'])
        with self.assertRaises(ValueError): check_target(self.owner['dsn'],remote,True,self.data['tenant_id'])
        future=json.loads((ROOT/'adversarial-t01/future/s9.json').read_text())
        self.assertEqual(future['reveal'],'MANUAL_ONLY_AFTER_INITIAL_TEST')
        self.assertEqual(future['reports'][0]['hours'],23)
        self.assertFalse(future['reports'][1]['compatible'])
        self.assertNotIn('s9',json.dumps(self.data).lower())

    def test_08_collision_and_runtime_scope_drift_fail_closed(self):
        changed=copy.deepcopy(self.bundle); changed['users']['t01_reader']['clients']={T:[C]}
        with self.assertRaises(ValueError): apply(self.owner,changed)
        before=self.count('audit_log')
        bad=copy.deepcopy(self.data)
        bad['records'][0]['data']['name']='different immutable source'
        with psycopg.connect(self.runtime['users']['t01_operator']['dsn']) as db:
            with self.assertRaises(ValueError): load_initial(db,bad)
            db.rollback()
        self.assertEqual(self.count('audit_log'),before)
        check_activation(self.config,self.bundle,self.runtime)
        previous=copy.deepcopy(self.config); previous['session_ttl']=901
        with self.assertRaises(ValueError): check_activation(previous,self.bundle,self.runtime)
        candidate=copy.deepcopy(self.runtime); candidate['users']['alice']['operations']=[]
        with self.assertRaises(ValueError): check_activation(self.config,self.bundle,candidate)
        # A role drift must not be silently repaired by re-applying the seed.
        with psycopg.connect(self.owner['dsn'],autocommit=True) as db:
            db.execute('ALTER ROLE cw_t01_reader NOLOGIN')
            try:
                with self.assertRaises(ValueError): apply(self.owner,self.bundle)
            finally: db.execute('ALTER ROLE cw_t01_reader LOGIN')

    def test_09_interrupted_data_transaction_can_resume(self):
        before=self.count('audit_log')
        # Simulate failure after an append inside the same F01 seed transaction.
        with self.assertRaises(RuntimeError):
            with psycopg.connect(self.runtime['users']['t01_operator']['dsn']) as db:
                db.execute('SELECT centerway.append_version(%s,%s,%s,%s,0,%s,%s)',(self.data['tenant_id'],self.data['client_id'],'source',str(uuid4()),'transaction rollback test',Jsonb(dict(name='Rollback',locator='synthetic://rollback',method='test'))))
                raise RuntimeError('interrupted')
        apply(self.owner,self.bundle)
        self.assertEqual(self.count('audit_log'),before)
        self.assertEqual(self.other_tenants(),self.before)

    def test_10_session_logout_and_initial_business_authorization(self):
        token=self.login('t01_operator')
        session=self.http('GET','/v1/session',token=token).get_json()
        self.assertEqual(session['clients'],{self.data['tenant_id']:[self.data['client_id']]})
        self.assertEqual(session['principal'],'cw_t01_operator')
        self.assertEqual(self.http('DELETE','/v1/session',token=token).status_code,204)
        self.assertEqual(self.http('GET',self.route+'/journey',token=token).status_code,401)
        self.assertEqual(self.count('intervention_policies'),0)
        self.assertEqual(self.count('intervention_executions'),0)
        self.assertEqual(self.count('detection_runs'),0)

    def test_11_operator_cli_is_idempotent_and_redacts_output(self):
        owner_path=self.state/'owner-cli.json'
        private_write(owner_path,self.owner)
        before=self.count('audit_log')
        result=subprocess.run([sys.executable,str(ROOT/'adversarial-t01/seed.py'),'apply',
            '--owner-config',str(owner_path),'--bundle',str(self.output/'bundle.json')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,'CLI failed; inspect private state')
        sensitive=list(self.credentials.values())+[self.owner['dsn']]+[u['dsn'] for u in self.bundle['users'].values()]
        self.assertFalse(any(secret in result.stdout+result.stderr for secret in sensitive),'secret appeared in CLI output')
        self.assertIn('no detection, investigation, intervention or recovery executed',result.stdout)
        self.assertEqual(self.count('audit_log'),before)
