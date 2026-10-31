"""Read-only T02 extension under actual T01 PostgreSQL identities; no T01 engine runs."""
import copy
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'api'),str(ROOT/'adversarial-t01/tests')]
from app import create_app,Database,APIError
from demo.provision import T,B,C,BC
fixture_tests=importlib.import_module('test_seed')

class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_tests.T01Tests.setUpClass()
        cls.fixture=fixture_tests.T01Tests
        cls.config=cls.fixture.runtime
        cls.tenant=cls.fixture.data['tenant_id'];cls.client=cls.fixture.data['client_id']
        cls.path=f'/v1/tenants/{cls.tenant}/clients/{cls.client}/manual-context'

    def setUp(self):
        self.app=create_app(self.config)

    def http(self,method,path,username=None,data=None):
        headers={'Origin':self.config['origins'][0]}
        if username:
            credentials=self.fixture.credentials if username.startswith('t01_') else self.fixture.old_credentials
            login=self.app.test_client().post('/v1/sessions',json=dict(username=username,password=credentials[username]),headers=headers,base_url='https://localhost')
            self.assertEqual(login.status_code,201)
            headers['Authorization']='Bearer '+login.get_json()['access_token']
        return self.app.test_client().open(path,method=method,json=data,headers=headers,base_url='https://localhost')

    def test_01_auth_scope_real_principal_and_no_secrets(self):
        self.assertEqual(self.http('GET',self.path).status_code,401)
        for user in ('t01_reader','t01_reviewer','t01_operator'):
            r=self.http('GET',self.path,user);self.assertEqual(r.status_code,200)
            value=r.get_json()['data']
            self.assertEqual(value['principal'],self.config['users'][user]['principal'])
            self.assertEqual(value['tenant_id'],self.tenant)
            self.assertEqual(value['client_id'],self.client)
            self.assertEqual(value['policies'],[])
            self.assertEqual(len(value['catalog']),1)
            self.assertEqual(value['factors'],[])
            self.assertFalse(any(u['dsn'] in r.get_data(as_text=True) for u in self.config['users'].values()),'credential leak')

    def test_02_cross_tenant_and_client_denied_http_and_pg(self):
        for user in ('alice','bob'):
            self.assertEqual(self.http('GET',self.path,user).status_code,403)
            with self.assertRaises(APIError) as e:
                Database(False).call(self.config['users'][user],'manual_context',(self.tenant,self.client))
            self.assertEqual(e.exception.status,403)
        for tenant,client in ((T,C),(B,BC)):
            self.assertEqual(self.http('GET',f'/v1/tenants/{tenant}/clients/{client}/manual-context','t01_reader').status_code,403)
        self.assertEqual(self.http('GET',f'/v1/tenants/{self.tenant}/clients/{uuid4()}/manual-context','t01_reader').status_code,403)
        self.assertEqual(self.http('GET',self.path+'?limit=100','t01_reader').status_code,422)
        self.assertEqual(self.http('POST',self.path,'t01_operator',{}).status_code,405)

    def test_03_preflight_and_read_does_not_operate_t01(self):
        with psycopg.connect(self.fixture.owner['dsn']) as db:
            before=db.execute('SELECT count(*) FROM centerway.audit_log WHERE tenant_id=%s',(self.tenant,)).fetchone()[0]
        r=self.app.test_client().options(self.path,headers={'Origin':self.config['origins'][0],'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization'},base_url='https://localhost')
        self.assertEqual(r.status_code,204)
        self.assertEqual(r.headers['Access-Control-Allow-Origin'],self.config['origins'][0])
        for _ in range(2):self.assertEqual(self.http('GET',self.path,'t01_reader').status_code,200)
        with psycopg.connect(self.fixture.owner['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.audit_log WHERE tenant_id=%s',(self.tenant,)).fetchone()[0],before)
            for table in ('detection_runs','investigations','intervention_decisions','intervention_executions','recovery_runs','operation_receipts'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM centerway.{table} WHERE tenant_id=%s',(self.tenant,)).fetchone()[0],0)

    def test_04_forged_scope_and_write_permissions_are_server_enforced(self):
        r=self.http('POST',f'/v1/tenants/{self.tenant}/clients/{self.client}/operations','t01_reader',dict(request_id=str(uuid4()),operation='detect',arguments=dict(contract_id=self.fixture.data['contract_id'],revisions=[2],as_of='2026-10-27T00:00:00Z',required_periods=2)))
        self.assertEqual(r.status_code,403)
        r=self.http('POST',f'/v1/tenants/{self.tenant}/clients/{self.client}/operations','t01_reviewer',dict(request_id=str(uuid4()),operation='intervene',arguments=dict(investigation_id=str(uuid4()),report_id=str(uuid4()))))
        self.assertEqual(r.status_code,403)
        # Deliberately forged HTTP scope still cannot cross the DB tenant boundary.
        config=copy.deepcopy(self.config);config['users']['bob']['clients'][self.tenant]=[self.client]
        self.app=create_app(config)
        self.assertEqual(self.http('GET',self.path,'bob').status_code,403)

    def test_05_bounded_audit_and_policy_principal_filter(self):
        # Separate local A/client test; T01 stays at its prepared initial stage.
        with psycopg.connect(self.config['users']['alice']['dsn']) as db:
            for _ in range(101):
                db.execute('SELECT centerway.append_version(%s,%s,\'source\',%s,0,%s,%s)',(T,C,str(uuid4()),'SYNTHETIC T02 context bound',Jsonb(dict(name='SYNTHETIC T02',locator='synthetic://t02/bounded',method='explicit test input'))))
        catalog,resource,p1,p2=[str(uuid4()) for _ in range(4)]
        with psycopg.connect(self.fixture.owner['dsn']) as db:
            db.execute("INSERT INTO centerway.intervention_catalog VALUES(%s,%s,'SYNTHETIC T02 bound test','T02','internal','saas','set_synthetic_flag',false,true,1,1)",(T,catalog))
            db.execute("INSERT INTO centerway.sandbox_flags VALUES(%s,%s,%s,'isolated_synthetic',false,NULL)",(T,C,resource))
            for ident,principal in [(p1,'http_alice'),(p2,'http_reader')]:
                db.execute("INSERT INTO centerway.intervention_policies VALUES(%s,%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()+interval '1 day',1,1,interval '1 hour',interval '1 hour')",(T,C,ident,catalog,resource,principal))
        with psycopg.connect(self.fixture.owner['dsn']) as db:
            db.execute("INSERT INTO centerway.intervention_revocations VALUES(%s,%s,%s,'SYNTHETIC T02 explicit test revocation')",(T,C,p2))
        result=Database(False).call(self.config['users']['alice'],'manual_context',(T,C))
        self.assertEqual([p['id'] for p in result['policies']],[p1])
        self.assertFalse(any(a['entity']=='intervention_policies' and a['snapshot']['principal']!='http_alice' for a in result['audit']))
        reader=Database(False).call(self.config['users']['reader'],'manual_context',(T,C))
        self.assertEqual([p['id'] for p in reader['policies']],[p2])
        self.assertEqual([p['policy_id'] for p in reader['revocations']],[p2])
        self.assertEqual(result['revocations'],[])
        self.assertFalse(any(a['entity']=='intervention_revocations' and a['snapshot']['policy_id']==p2 for a in result['audit']))
        self.assertEqual(Database(False).call(self.config['users']['reviewer'],'manual_context',(T,C))['policies'],[])
        self.assertEqual(len(result['audit']),100)
        self.assertTrue(result['truncated']['audit'])
        self.assertTrue(all(x['snapshot']['client_id']==C for x in result['audit']))
        self.assertEqual(result['limit_per_collection'],100)

    def test_06_audit_error_receipts_hide_sql_messages_without_changing_history(self):
        request_id=str(uuid4())
        payload=dict(request_id=request_id,operation='append_value',arguments=dict(kind='source',id=str(uuid4()),expected_revision=0,reason='SYNTHETIC T02 actual rejected input',data={}))
        response=self.http('POST',f'/v1/tenants/{T}/clients/{C}/operations','alice',payload)
        self.assertEqual(response.status_code,422)
        value=self.http('GET',f'/v1/tenants/{T}/clients/{C}/manual-context','alice').get_json()['data']
        event=next(e for e in value['audit'] if e['entity']=='operation_receipts' and e['snapshot']['request_id']==request_id)
        self.assertEqual(set(event['snapshot']['result']),{'code','sqlstate'})
        self.assertEqual(event['snapshot']['result']['code'],'engine_rejected')
        with psycopg.connect(self.fixture.owner['dsn']) as db:
            stored=db.execute("SELECT snapshot->'result' FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(request_id,)).fetchone()[0]
            self.assertIn('message',stored)  # Sanitized transport does not rewrite audit.
