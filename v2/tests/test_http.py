import http.cookiejar
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from centerway.store import Store
from centerway.server import make_server


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Store(Path(self.temp.name)/'db.sqlite3'),port=0)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        payload = json.dumps(body).encode() if body is not None else None
        req = Request(self.url+path,payload,{'Content-Type':'application/json',**(headers or {})})
        try:
            response = self.client.open(req)
        except HTTPError as response:
            return response.code,json.load(response),response.headers
        with response:
            return response.status,json.load(response),response.headers

    def login(self,user='demo',password='centerway-local'):
        return self.request('/api/login',{'user':user,'password':password})

    def test_session_cookie_permissions_logout_and_role_spoofing(self):
        self.assertEqual(401,self.request('/api/view?tenant=atlas&customer=customer-01')[0])
        self.assertEqual(401,self.login(password='bad')[0])
        code,_,headers = self.login('leitor')
        self.assertEqual(200,code)
        self.assertIn('HttpOnly',headers['Set-Cookie'])
        self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertEqual(200,self.request('/api/view?tenant=nimbus&customer=customer-01')[0])
        self.assertEqual(403,self.request('/api/view?tenant=atlas&customer=customer-01')[0])
        self.assertEqual(403,self.request('/api/advance',{'customer':'customer-01','tenant':'nimbus'})[0])
        self.assertEqual(400,self.request('/api/advance',{'customer':'customer-01','tenant':'nimbus','role':'operator'})[0])
        self.request('/api/logout',{})
        self.assertEqual(401,self.request('/api/view')[0])

    def test_full_cycle_through_http_and_foreign_case(self):
        self.login()
        _,data,_ = self.request('/api/advance',{'customer':'customer-01','tenant':'atlas'})
        body = {'customer':'customer-01','tenant':'atlas','case_id':data['case_id']}
        for _ in range(3):
            self.assertEqual(200,self.request('/api/advance',body)[0])
        self.assertEqual(404,self.request('/api/execute',{**body,'tenant':'nimbus'})[0])
        self.assertEqual(200,self.request('/api/execute',body)[0])
        self.assertTrue(self.request('/api/execute',body)[1]['reused'])
        code,result,_ = self.request('/api/verify',body)
        self.assertEqual(200,code)
        self.assertTrue(result['value_recovered'])

    def test_csrf_invalid_body_untrusted_evidence_and_traversal(self):
        self.assertEqual(403,self.request('/api/login',{'user':'demo','password':'centerway-local'},{'Origin':'https://evil.example'})[0])
        self.login()
        self.assertEqual(400,self.request('/api/advance',{'customer':'customer-01','tenant':'atlas','decision':{'action':'anything'}})[0])
        self.assertEqual(400,self.request('/api/advance',[])[0])
        self.assertEqual(400,self.request('/api/execute',{'customer':'customer-01','tenant':'atlas'})[0])
        self.assertEqual(404,self.request('/../../.env')[0])

    def test_customer_creation_observation_entry_registry_and_atomic_rejection(self):
        from centerway.synthetic import sample_rows
        self.login()
        body={'tenant':'atlas','customer':'http-new','name':'Cliente HTTP'}
        self.assertEqual(201,self.request('/api/customers',body)[0])
        self.assertEqual(409,self.request('/api/customers',body)[0])
        self.assertEqual(400,self.request('/api/advance',{'tenant':'atlas'})[0])
        rows=sample_rows()
        invalid=[rows[0],dict(rows[1],value=True)]
        self.assertEqual(400,self.request('/api/observations',{'tenant':'atlas','customer':'http-new','observations':invalid})[0])
        result=self.request('/api/observations',{'tenant':'atlas','customer':'http-new','observations':rows})
        self.assertEqual(200,result[0])
        self.assertEqual(14,result[1]['inserted'])
        result=self.request('/api/observations',{'tenant':'atlas','customer':'http-new','observations':rows[::-1]})
        self.assertTrue(result[1]['reused'])
        case_id=self.request('/api/advance',{'tenant':'atlas','customer':'http-new'})[1]['case_id']
        for _ in range(3):
            self.assertEqual(200,self.request('/api/advance',{'tenant':'atlas','customer':'http-new','case_id':case_id})[0])
        self.assertEqual(404,self.request('/api/execute',{'tenant':'atlas','customer':'customer-01','case_id':case_id})[0])
        self.assertEqual(200,self.request('/api/execute',{'tenant':'atlas','customer':'http-new','case_id':case_id})[0])
        view=self.request('/api/view?tenant=atlas&customer=http-new')[1]
        self.assertEqual('http-new',view['environment']['customer'])
        self.assertEqual(14,len(view['case']['observation']['rows']))
        self.assertTrue(any(r['customer']=='http-new' for r in self.request('/api/view')[1]['registry']))
        self.request('/api/logout',{})
        self.login('leitor')
        self.assertEqual(403,self.request('/api/observations',{'tenant':'atlas','customer':'http-new','observations':rows})[0])
        registry=self.request('/api/view')[1]['registry']
        self.assertTrue(all(r['tenant']=='nimbus' for r in registry))
        self.assertEqual(403,self.request('/api/customers',{'tenant':'nimbus','customer':'bad','name':'Sem permissão'})[0])
