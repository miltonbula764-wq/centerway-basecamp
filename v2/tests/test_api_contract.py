"""Validate real HTTP payloads against the committed OpenAPI 3.1 schemas."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request,build_opener,HTTPCookieProcessor
from urllib.error import HTTPError
from unittest.mock import patch
import http.cookiejar
from jsonschema import Draft202012Validator,FormatChecker
from centerway.core import Core
from centerway.store import Store
from centerway.server import make_server
from centerway.http_contract import API_METHODS,API_VERSION,ERROR_CODES
from centerway.synthetic import sample_rows

SPEC=json.loads((Path(__file__).resolve().parents[1]/'contracts/openapi.json').read_text())


def validator(schema):
    return Draft202012Validator({**schema,'components':SPEC['components']},format_checker=FormatChecker())


def resolve(node):
    if '$ref' not in node:
        return node
    value=SPEC
    for part in node['$ref'][2:].split('/'):
        value=value[part]
    return value


class SchemaTests(unittest.TestCase):
    def test_inventory_schemas_refs_and_examples(self):
        self.assertEqual(API_VERSION,SPEC['info']['version'])
        self.assertEqual(set(API_METHODS),set(SPEC['paths']))
        ids=[]
        for path,method in API_METHODS.items():
            self.assertEqual({method.lower(),'options'},set(SPEC['paths'][path]))
            ids.extend(op['operationId'] for op in SPEC['paths'][path].values())
        self.assertEqual(len(ids),len(set(ids)))
        def walk(value):
            if isinstance(value,dict):
                if '$ref' in value:
                    self.assertTrue(value['$ref'].startswith('#/'))
                    resolve(value)
                for child in value.values(): walk(child)
            elif isinstance(value,list):
                for child in value: walk(child)
        walk(SPEC)
        for schema in SPEC['components']['schemas'].values():
            Draft202012Validator.check_schema(schema)
            for example in schema.get('examples',[]):
                validator(schema).validate(example)
        self.assertEqual(set(ERROR_CODES.values()),set(SPEC['components']['schemas']['Error']['properties']['code']['enum']))


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'api.sqlite3',seed_demo=False)
        self.server=make_server(self.store,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def call(self,path,body=None,method=None,headers=None,raw=None):
        method=method or ('POST' if body is not None or raw is not None else 'GET')
        payload=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        req=Request(self.origin+path,payload,{'Content-Type':'application/json',**(headers or {})},method=method)
        try:
            response=self.client.open(req)
        except HTTPError as error:
            response=error
        with response:
            data=response.read()
            result=json.loads(data) if data else None
            self.assertEqual(API_VERSION,response.headers['X-Centerway-API-Version'])
            route=path.split('?')[0]
            operation=SPEC['paths'].get(route,{}).get(method.lower())
            if response.status>=400:
                validator({'$ref':'#/components/schemas/Error'}).validate(result) if result else None
                if result:
                    self.assertEqual(ERROR_CODES[response.status],result['code'])
            if operation and str(response.status) in operation['responses']:
                schema=resolve(operation['responses'][str(response.status)]).get('content',{}).get('application/json',{}).get('schema')
                if schema:
                    validator(schema).validate(result)
            if operation and body is not None and response.status<400 and 'requestBody' in operation:
                validator(operation['requestBody']['content']['application/json']['schema']).validate(body)
            return response.status,result,response.headers

    def login(self,user='demo'):
        self.assertEqual(200,self.call('/api/login',{'user':user,'password':'centerway-local'})[0])

    def create(self,tenant='atlas',customer='contract-client',scenario='blocked'):
        body={'tenant':tenant,'customer':customer,'name':'Cliente fictício do contrato','scenario':scenario}
        self.assertEqual(201,self.call('/api/customers',body)[0])
        return {'tenant':tenant,'customer':customer}

    def prepare(self,scope):
        self.assertEqual(200,self.call('/api/observations',{**scope,'observations':sample_rows()})[0])
        _,result,_=self.call('/api/advance',scope)
        body={**scope,'case_id':result['case_id']}
        for _ in range(3):
            self.assertEqual(200,self.call('/api/advance',body)[0])
            self.read(scope)
        return body

    def read(self,scope,case_id=None):
        query=f"tenant={scope['tenant']}&customer={scope['customer']}"+(f'&case_id={case_id}' if case_id else '')
        status,result,_=self.call('/api/view?'+query)
        self.assertEqual(200,status)
        return result

    def test_all_atlas_payloads_historical_reads_and_idempotent_execution(self):
        self.assertEqual(401,self.call('/api/view')[0])
        self.login()
        self.call('/api/view')
        scope=self.create()
        self.assertIsNone(self.read(scope)['case'])
        self.call('/api/view?tenant=atlas')
        body=self.prepare(scope)
        self.assertEqual(False,self.call('/api/execute',body)[1]['reused'])
        self.assertEqual(True,self.call('/api/execute',body)[1]['reused'])
        self.assertTrue(self.call('/api/verify',body)[1]['value_recovered'])
        old=self.read(scope)['case']
        self.assertEqual(200,self.call('/api/advance',scope)[0])
        self.assertEqual(old,self.read(scope,body['case_id'])['case'])
        self.assertEqual(409,self.call('/api/verify',body)[0])
        self.assertEqual(200,self.call('/api/logout',{})[0])
        self.assertEqual(401,self.call('/api/view')[0])

    def test_nimbus_operational_value_and_simulated_usage_payloads(self):
        self.login()
        scope=self.create('nimbus')
        body=self.prepare(scope)
        self.call('/api/execute',body)
        result=self.call('/api/verify',body)[1]
        self.assertTrue(result['operational_recovered']);self.assertFalse(result['value_recovered'])
        self.assertFalse(self.call('/api/simulate-usage',body)[1]['reused'])
        self.assertTrue(self.call('/api/simulate-usage',body)[1]['reused'])
        self.assertTrue(self.call('/api/verify',body)[1]['value_recovered'])
        self.read(scope)

    def test_insufficient_healthy_unknown_cause_and_stale_snapshots_match_schema(self):
        self.login()
        for customer in ('insufficient','healthy','unknown','stale'):
            scope=self.create(customer=customer,scenario='operational' if customer=='unknown' else 'blocked')
            rows=[] if customer=='insufficient' else sample_rows(recent=10 if customer=='healthy' else 2,days=3 if customer=='stale' else 14)
            if rows: self.call('/api/observations',{**scope,'observations':rows})
            body={**scope,'case_id':self.call('/api/advance',scope)[1]['case_id']}
            if customer=='stale':
                self.call('/api/observations',{**scope,'observations':sample_rows()})
                self.assertEqual('stale_evidence',self.read(scope)['case']['stage'])
            else:
                self.call('/api/advance',body)
                if customer=='unknown':
                    self.call('/api/advance',body);self.call('/api/advance',body)
                    self.assertIsNone(self.read(scope)['case']['decision']['action'])
                else:
                    self.read(scope)

    def test_invalid_requests_are_json_and_cannot_hide_or_change_scope(self):
        self.login()
        for query in ('tenant=','tenant=atlas&tenant=nimbus','tenant=atlas&typo=one','customer=one','case_id=one','tenant'):
            self.assertEqual(400,self.call('/api/view?'+query)[0])
        for raw in (b'{"tenant":"atlas","tenant":"nimbus","customer":"one"}',b'{"x":NaN}',b'{"x":Infinity}',b'not-json',b'[]',b'\xff'):
            self.assertEqual(400,self.call('/api/advance',raw=raw)[0])
        self.assertEqual(400,self.call('/api/login',{'user':'demo','password':'centerway-local','role':'operator'})[0])
        self.assertEqual(400,self.call('/api/logout',{'tenant':'atlas'})[0])
        self.assertEqual(400,self.call('/api/advance',{'tenant':'atlas','customer':'one','case_id':''})[0])
        self.assertEqual(415,self.call('/api/advance',raw=b'{}',headers={'Content-Type':'text/plain'})[0])
        self.assertEqual(413,self.call('/api/advance',raw=b' '*65537)[0])
        self.assertEqual(404,self.call('/api/missing',{})[0])
        self.assertEqual(400,self.call('/api/logout?ignored=one',{})[0])
        for method,path in (('GET','/api/login'),('POST','/api/view'),('PUT','/api/advance'),('DELETE','/api/customers')):
            status,_,headers=self.call(path,method=method)
            self.assertEqual(405,status);self.assertIn(API_METHODS[path],headers['Allow'])

    def test_errors_do_not_leak_exceptions_and_failed_write_rolls_back(self):
        self.login();scope=self.create();body=self.prepare(scope)
        before=self.read(scope)
        with patch.object(Core,'audit',side_effect=RuntimeError('secret-marker')),patch('sys.stderr',new_callable=io.StringIO) as logs:
            self.assertEqual(500,self.call('/api/execute',body)[0])
            self.assertNotIn('secret-marker',logs.getvalue())
        self.assertEqual(before,self.read(scope))
        with patch('sys.stderr',new_callable=io.StringIO) as logs:
            self.assertEqual(400,self.call('/api/login?password=secret-marker',{'user':'demo','password':'unused'})[0])
            self.assertNotIn('secret-marker',logs.getvalue())
        with patch.object(Core,'view',side_effect=RuntimeError('secret-marker')),patch('sys.stderr',new_callable=io.StringIO) as logs:
            status,data,_=self.call('/api/view')
            self.assertEqual(500,status);self.assertNotIn('secret-marker',json.dumps(data)+logs.getvalue())
