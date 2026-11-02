"""Synthetic signup is disabled by default and invite-gated when explicitly enabled."""
import os
import unittest
from unittest.mock import patch
from app import create_app, password_hash

T='a1000000-0000-0000-0000-000000000001'
C='a2000000-0000-0000-0000-000000000001'

class FakeSessions:
    def __init__(self):
        self.users={}
        self.sessions={}
    def get_test_user(self,username):
        return self.users.get(username)
    def register_test_user(self,username,encoded):
        if self.users: return False
        self.users[username]=encoded
        return True
    def put(self,digest,username,version,expiry):
        self.sessions[digest]=(username,version,expiry)
    def get(self,digest):
        return self.sessions.get(digest)
    def delete(self,digest):
        self.sessions.pop(digest,None)

class FakeDatabase:
    def __init__(self,_):pass
    def call(self,user,kind,params=()):
        if kind=='identity':return 'http_alice'
        if kind=='clients':return [{'client_id':C,'display_name':'SYNTHETIC client A'}]
        raise AssertionError(kind)

class TestSignup(unittest.TestCase):
    def config(self):
        return {'demo':True,'synthetic_only':True,'session_store':'postgres',
          'origins':['https://value-recovery-radar.lovable.app'],
          'users':{'alice':{'principal':'http_alice','dsn':'host=localhost',
           'clients':{T:[C]},'operations':['append_value'],
           'company_tenants':[],'password_hash':password_hash('old-pass-12345')}}}
    def test_invitation_signup_login_and_one_account(self):
        sessions=FakeSessions()
        with patch.dict(os.environ,{'CENTERWAY_TEST_SIGNUP_KEY':'a'*40}):
            with patch('app.session_store',return_value=sessions),patch('app.Database',FakeDatabase):
                client=create_app(self.config()).test_client()
                payload={'username':'tester','password':'new-private-pass-123','invite_code':'a'*40}
                self.assertEqual(client.post('/v1/test-signup',json={**payload,'invite_code':'wrong'}).status_code,403)
                self.assertEqual(client.post('/v1/test-signup',json=payload).status_code,201)
                self.assertEqual(client.post('/v1/test-signup',json=payload).status_code,409)
                self.assertEqual(client.post('/v1/sessions',json={'username':'tester','password':'bad'}).status_code,401)
                login=client.post('/v1/sessions',json={'username':'tester','password':payload['password']})
                self.assertEqual(login.status_code,201)
                token=login.json['access_token']
                self.assertEqual(client.get('/v1/session',headers={'Authorization':'Bearer '+token}).status_code,200)
    def test_disabled_for_other_environments(self):
        with patch.dict(os.environ,{'CENTERWAY_TEST_SIGNUP_KEY':'a'*40}):
            with patch('app.session_store',return_value=FakeSessions()),patch('app.Database',FakeDatabase):
                cfg=self.config();cfg['synthetic_only']=False
                client=create_app(cfg).test_client()
                self.assertEqual(client.post('/v1/test-signup',json={}).status_code,404)

if __name__=='__main__': unittest.main()
