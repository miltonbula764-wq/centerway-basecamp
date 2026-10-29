"""Real persistent PostgreSQL, real TLS, unchanged API/engines. Synthetic fixtures only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import PersistentDemo, ROOT
from scenario import Scenario
from demo.provision import T,B,C,C2


class PersistentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='centerway-c03-tests-')
        cls.state = Path(cls.temp.name)/'state'
        cls.caddy = os.environ['CENTERWAY_TEST_CADDY']
        cls.demo = PersistentDemo(cls.state,cls.caddy)
        try:
            cls.demo.initialize()
            cls.demo.__enter__()
            cls.scenario = Scenario(cls.demo)
            cls.result = cls.scenario.run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.demo.close()
        if (cls.state/'manifest.json').exists():
            manifest = json.loads((cls.state/'manifest.json').read_text())
            subprocess.run(['docker','rm','-f',manifest['container']],capture_output=True)
            for volume in (manifest['volume'],manifest['volume']+'-tls'):
                subprocess.run(['docker','volume','rm',volume],capture_output=True)
        cls.temp.cleanup()

    def test_complete_synthetic_https_journey(self):
        result = self.result
        self.assertTrue(result['synthetic_only'])
        self.assertEqual(result['missing_status'],'resultado_inconclusivo')
        self.assertEqual(result['recovery_result']['status'],'recuperacao_completa')
        self.assertEqual(result['recovery_result']['causal_attribution'],'not_established')
        self.assertEqual(result['recovery_result']['independent_verification'],'not_established')
        self.assertTrue(result['recovery_result']['execution_succeeded'])
        self.assertTrue(result['recovery_result']['improvement_observed'])
        status, body = self.scenario.request('GET',f'/v1/tenants/{T}/clients/{C}/journey')
        self.assertEqual(status,200)
        detection = next(d for d in body['data']['detections'] if d['id'] == result['detection_id'])
        self.assertEqual(detection['result']['state'],'deterioracao_demonstrada')
        report = next(i for i in body['data']['investigations'] if i['id'] == result['investigation_id'])
        self.assertEqual(report['result']['independent_verification'],'not_established')
        self.assertEqual(report['result']['status'],'impedimento_demonstrado')
        self.assertEqual(len(body['data']['executions']),1)

    def test_permissions_clients_sessions_and_individual_principals(self):
        scenario = Scenario(self.demo)
        route=f'/v1/tenants/{T}/clients'
        self.assertEqual(scenario.request('GET',route)[0],401)
        scenario.login('reader'); scenario.login('bob')
        self.assertEqual(scenario.request('GET',route,user='reader')[1]['data'],[{'client_id':C,'display_name':'SYNTHETIC client A'}])
        self.assertEqual(scenario.request('GET',route,user='bob')[0],403)
        self.assertEqual(scenario.request('GET',f'/v1/tenants/{B}/clients',user='reader')[0],403)
        self.assertEqual(scenario.request('GET',f'/v1/tenants/{T}/clients/{C2}/journey',user='reader')[0],403)
        self.assertEqual(scenario.request('POST',f'/v1/tenants/{T}/clients/{C}/operations',self.result['intervention_request'],user='reader')[0],403)
        self.assertEqual(scenario.request('GET','/v1/session',user='reader')[1]['principal'],'http_reader')
        self.assertEqual(scenario.request('DELETE','/v1/session',user='reader')[0],204)
        self.assertEqual(scenario.request('GET',route,user='reader')[0],401)
        import psycopg
        with psycopg.connect(self.demo.config['users']['bob']['dsn']) as db:
            self.assertEqual(db.execute('SELECT session_user::text').fetchone()[0],'http_bob')
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.recovery_runs WHERE tenant_id=%s',(T,)).fetchone()[0],0)

    def test_restart_persistence_idempotency_and_database_failure(self):
        scenario=self.scenario
        token=scenario.tokens['alice']
        route=f'/v1/tenants/{T}/clients/{C}/journey'
        before=scenario.request('GET',route)[1]['data']
        # Stop both servers and PostgreSQL; reconstruct server objects from disk.
        self.demo.close()
        self.demo.run('docker','stop',self.demo.container)
        with self.assertRaises(OSError):
            with socket.create_connection(('127.0.0.1',self.demo.port),timeout=1): pass
        self.__class__.demo = PersistentDemo(self.state,self.caddy)
        self.demo.__enter__()
        scenario.demo = self.demo
        self.assertEqual(scenario.request('GET',route)[1]['data'],before)
        self.assertEqual(scenario.tokens['alice'],token)  # the same opaque session survived restart
        status, body=scenario.request('POST',f'/v1/tenants/{T}/clients/{C}/operations',self.result['intervention_request'])
        self.assertEqual(status,200)
        self.assertEqual(body['data']['result']['id'],self.result['decision_id'])
        self.assertEqual(len(scenario.request('GET',route)[1]['data']['executions']),1)
        import psycopg
        with psycopg.connect(self.demo.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(self.result['intervention_request']['request_id'],)).fetchone()[0],1)
        self.demo.run('docker','stop',self.demo.container)
        try:
            self.assertEqual(scenario.request('GET',f'/v1/tenants/{T}/clients')[0],503)
            self.assertEqual(scenario.request('GET','/health')[0],200)  # liveness only
        finally:
            self.demo.run('docker','start',self.demo.container); self.demo.ready_database()
        self.assertEqual(scenario.request('GET',route)[0],200)
        self.demo.stop(self.demo.api)
        try:
            self.assertEqual(scenario.request('GET',route)[0],503)
        finally:
            self.demo.start_api()

    def test_secrets_private_storage_and_no_automatic_reinitialization(self):
        for name in ('credentials.json','config.json','postgres.env','manifest.json','pki/ca.key','pki/api.key','pki/db.key'):
            self.assertEqual((self.state/name).stat().st_mode & 0o077,0,name)
        ports=self.demo.run('docker','port',self.demo.container)
        self.assertTrue(all('127.0.0.1:' in line for line in ports.splitlines()))
        with self.assertRaises(ValueError):
            PersistentDemo(self.state,self.caddy).initialize()
        with self.assertRaises(ValueError):
            Scenario(self.demo).run()
        path=self.state/'manifest.json'; original=path.read_text()
        try:
            data=json.loads(original); data['migrations']['sql/001_foundation.sql']='drift'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): PersistentDemo(self.state,self.caddy).read_manifest()
        finally: path.write_text(original)
        with self.assertRaises(ValueError):
            PersistentDemo(ROOT/'cloud-demo'/'unsafe-state',self.caddy)
        config_path=self.state/'config.json'; original_config=config_path.read_text()
        try:
            changed=json.loads(original_config); changed['demo']=True
            config_path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): PersistentDemo(self.state,self.caddy).read_manifest()
        finally: config_path.write_text(original_config)
        logs=''.join(p.read_text() for p in self.state.glob('*.log'))
        for secret in list(self.demo.credentials.values())+list(self.scenario.tokens.values()):
            self.assertNotIn(secret,logs)
        self.assertNotIn('password=',logs)
        for name in ('credentials.json','config.json','postgres.env','pki/ca.key'):
            self.assertEqual(self.scenario.request('GET','/'+name)[0],404)
        # Validate future public hostname template without starting it or contacting a CA.
        env=self.demo.env|{'API_HOST':'api.getcenterway.com','ACME_EMAIL':'operator@example.invalid'}
        result=subprocess.run([self.caddy,'validate','--config',str(ROOT/'infra'/'Caddyfile'),'--adapter','caddyfile'],cwd=ROOT/'infra',env=env,capture_output=True)
        self.assertEqual(result.returncode,0)


if __name__ == '__main__': unittest.main()
