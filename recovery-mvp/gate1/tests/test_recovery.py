import copy
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg.conninfo import make_conninfo

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'gate1'),str(ROOT/'api'),str(ROOT/'cloud-demo'),str(ROOT/'infra')]
import recovery as g2
from demo.provision import provision,T,B,C,BC
from app import create_app
from scenario import Scenario,setup_policy

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); cls.state=Path(cls.temp.name)
        cls.container='cw-g2-source-'+secrets.token_hex(8)
        cls.password=secrets.token_urlsafe(24)
        env=os.environ.copy();env['POSTGRES_PASSWORD']=cls.password
        subprocess.run(['docker','run','-d','--name',cls.container,'-e','POSTGRES_PASSWORD','-p','127.0.0.1::5432',g2.IMAGE],env=env,check=True,stdout=subprocess.DEVNULL)
        cls.addClassCleanup(cls.cleanup)
        import time
        for _ in range(60):
            r=subprocess.run(['docker','exec',cls.container,'sh','-c','test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres'],capture_output=True)
            if r.returncode==0: break
            time.sleep(.3)
        for migration in sorted((ROOT/'sql').glob('*.sql')):
            g2.command(['docker','exec','-i',cls.container,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres'],migration.read_bytes())
        g2.command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(cls.state/'key.pem'),'-out',str(cls.state/'ca.pem')])
        for local,remote in [('key.pem','server.key'),('ca.pem','server.crt')]:
            g2.command(['docker','cp',str(cls.state/local),cls.container+':/var/lib/postgresql/'+remote])
        g2.command(['docker','exec','-u','root',cls.container,'sh','-c','chown postgres:postgres /var/lib/postgresql/server.* && chmod 600 /var/lib/postgresql/server.*'])
        for setting in ["ssl=on","ssl_cert_file='/var/lib/postgresql/server.crt'","ssl_key_file='/var/lib/postgresql/server.key'"]:
            g2.command(['docker','exec',cls.container,'psql','-U','postgres','-c','ALTER SYSTEM SET '+setting])
        g2.command(['docker','restart',cls.container])
        for _ in range(60):
            r=subprocess.run(['docker','exec',cls.container,'sh','-c','test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres'],capture_output=True)
            if r.returncode==0: break
            time.sleep(.3)
        port=g2.command(['docker','port',cls.container,'5432/tcp']).decode().strip().rsplit(':',1)[1]
        cls.dsn=make_conninfo(host='127.0.0.1',port=port,dbname='postgres',user='postgres',password=cls.password,sslmode='verify-full',sslrootcert=str(cls.state/'ca.pem'))
        config,credentials=provision(cls.container,port,cls.state)
        with psycopg.connect(cls.dsn) as db:
            db.execute((ROOT/'managed/sql/001_sessions.sql').read_text(),prepare=False)
            db.execute("INSERT INTO cw_sessions.sessions VALUES (%s,'synthetic-user',%s,4102444800)",('a'*64,'b'*64))
        def apply(statement):
            with psycopg.connect(cls.dsn) as db: db.execute(statement,prepare=False)
        setup_policy(SimpleNamespace(sql=apply))
        app=create_app(config)
        class LocalScenario(Scenario):
            def __init__(self): self.demo=SimpleNamespace(credentials=credentials,state=cls.state);self.tokens={}
            def request(self,method,path,data=None,user='alice'):
                h={'Origin':'http://localhost:5173'}
                if user in self.tokens:h['Authorization']='Bearer '+self.tokens[user]
                r=app.test_client().open(path,method=method,json=data,headers=h,base_url='http://localhost')
                return r.status_code,r.get_json(silent=True)
        cls.scenario=LocalScenario(); cls.scenario.run()
        cls.key=cls.state/'identity'
        g2.command(['age-keygen','-o',str(cls.key)]);cls.key.chmod(0o600)
        cls.recipient=g2.command(['age-keygen','-y',str(cls.key)]).decode().strip()
        cls.archive=cls.state/'bundle'
        g2.export(cls.dsn,cls.archive,cls.recipient)

    @classmethod
    def cleanup(cls):
        subprocess.run(['docker','rm','-fv',cls.container],capture_output=True)
        cls.temp.cleanup()

    def test_01_actual_pg17_tls_export_restore_and_replay(self):
        with psycopg.connect(self.dsn) as db: before=g2.inventory(db)
        result=g2.restore(self.archive,self.key)
        self.assertEqual(result['status'],'isolated_restore_verified')
        self.assertFalse(result['runtime_ready'])
        self.assertEqual(g2.restore(self.archive,self.key),result)
        with psycopg.connect(self.dsn) as db: self.assertEqual(g2.inventory(db),before)
        self.assertGreater(before['centerway.operation_receipts']['rows'],0)
        self.assertEqual(before['cw_sessions.sessions']['rows'],1)

    def test_02_confidentiality_and_existing_destination(self):
        for file in self.archive.iterdir():
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            for marker in [b'PGDMP',b'SYNTHETIC',self.password.encode(),b'synthetic-user']:
                self.assertNotIn(marker,file.read_bytes())
        with self.assertRaises(g2.RecoveryError):g2.export(self.dsn,self.archive,self.recipient)

    def test_03_corruption_and_wrong_key_before_restore(self):
        target=self.state/'corrupt';shutil.copytree(self.archive,target)
        try:
            p=target/'database.age';p.write_bytes(p.read_bytes()[:-8]+b'changed!')
            checks=json.loads((target/'checksums.json').read_text());checks['database.age']=g2.digest(p.read_bytes())
            (target/'checksums.json').write_bytes(g2.encode(checks))
            with patch.object(g2.sp,'Popen',wraps=g2.sp.Popen) as process:
                with self.assertRaises(Exception):g2.restore(target,self.key)
                self.assertFalse(any(c.args[0][0]=='docker' for c in process.call_args_list))
            wrong=self.state/'wrong';g2.command(['age-keygen','-o',str(wrong)]);wrong.chmod(0o600)
            with self.assertRaises(Exception):g2.restore(self.archive,wrong)
        finally:shutil.rmtree(target)

    def test_04_tls_network_and_configuration_fail_closed(self):
        for options in [dict(sslmode='require'),dict(host='ep-test-pooler.aws.neon.tech'),dict(sslrootcert='/absent'),dict(port='1')]:
            dest=self.state/('failure-'+secrets.token_hex(3))
            with self.assertRaises(Exception):g2.export(make_conninfo(self.dsn,**options),dest,self.recipient)
            self.assertFalse(dest.exists())

    def test_05_dump_and_age_exit_statuses_and_timeout(self):
        real=g2.sp.Popen
        for stage in ['pg_dump','age','timeout']:
            dest=self.state/('failure-'+stage)
            def replacement(args,**kwargs):
                if (stage=='pg_dump' and args[0]=='pg_dump' and '--version' not in args) or (stage=='age' and args[0]=='age'):
                    args=[sys.executable,'-c','import sys;sys.stderr.write("SECRET-MUST-NOT-LOG");sys.exit(7)']
                if stage=='timeout' and args[0]=='pg_dump' and '--version' not in args:
                    args=[sys.executable,'-c','import time;time.sleep(10)']
                return real(args,**kwargs)
            with patch.object(g2.sp,'Popen',side_effect=replacement),patch.object(g2,'TIMEOUT',.5 if stage=='timeout' else 180):
                with self.assertRaises(Exception):g2.export(self.dsn,dest,self.recipient)
            self.assertFalse(dest.exists())

    def test_06_private_paths_limits_and_lost_destination(self):
        key=self.state/'public-key';key.write_bytes(self.key.read_bytes());key.chmod(0o644)
        with self.assertRaises(Exception):g2.restore(self.archive,key)
        with self.assertRaises(Exception):g2.export(self.dsn,self.state/'missing'/'bundle',self.recipient)
        with patch.object(g2,'LIMIT',100):
            with self.assertRaises(Exception):g2.export(self.dsn,self.state/'tiny',self.recipient)
        self.assertFalse((self.state/'tiny').exists())

    def test_07_dynamic_snapshot_includes_new_sessions(self):
        with psycopg.connect(self.dsn) as db:
            db.execute("INSERT INTO cw_sessions.sessions VALUES (%s,'late-synthetic',%s,4102444800)",('c'*64,'d'*64))
        target=self.state/'later';g2.export(self.dsn,target,self.recipient)
        manifest=json.loads(g2.command(['age','-d','-i',str(self.key),str(target/'manifest.age')]))
        self.assertEqual(manifest['tables']['cw_sessions.sessions']['rows'],2)
        self.assertEqual(g2.restore(target,self.key)['status'],'isolated_restore_verified')

    def test_08_loss_during_publish_and_symlink(self):
        target=self.state/'lost-publish'
        with patch.object(g2.os,'rename',side_effect=OSError('synthetic destination lost')):
            with self.assertRaises(Exception):g2.export(self.dsn,target,self.recipient)
        self.assertFalse(target.exists())
        link=self.state/'link';link.symlink_to(self.key)
        with self.assertRaises(Exception):g2.restore(self.archive,link)

    def test_09_baseline_mismatch_is_not_success(self):
        target=self.state/'mismatch';shutil.copytree(self.archive,target)
        m=json.loads(g2.command(['age','-d','-i',str(self.key),str(target/'manifest.age')]))
        m['tables']['centerway.operation_receipts']['rows']+=1
        (target/'manifest.age').write_bytes(g2.command(['age','-r',self.recipient],g2.encode(m)))
        checks={p.name:g2.digest(p.read_bytes()) for p in [target/'database.age',target/'manifest.age']}
        (target/'checksums.json').write_bytes(g2.encode(checks))
        with self.assertRaises(Exception):g2.restore(target,self.key)
        remaining=g2.command(['docker','ps','-aq','--filter','name=cw-g2-restore-'])
        self.assertEqual(remaining.strip(),b'')

    def test_10_snapshot_excludes_write_after_baseline(self):
        real=g2.sp.Popen
        with psycopg.connect(self.dsn) as db:
            before=db.execute('SELECT count(*) FROM cw_sessions.sessions').fetchone()[0]
        def concurrent_write(args,**kwargs):
            if args[0]=='pg_dump' and '--version' not in args:
                with psycopg.connect(self.dsn) as db:
                    db.execute("INSERT INTO cw_sessions.sessions VALUES (%s,'concurrent-synthetic',%s,4102444800)",('e'*64,'f'*64))
            return real(args,**kwargs)
        target=self.state/'snapshot'
        with patch.object(g2.sp,'Popen',side_effect=concurrent_write):g2.export(self.dsn,target,self.recipient)
        m=json.loads(g2.command(['age','-d','-i',str(self.key),str(target/'manifest.age')]))
        self.assertEqual(m['tables']['cw_sessions.sessions']['rows'],before)
        self.assertEqual(g2.restore(target,self.key)['status'],'isolated_restore_verified')

if __name__=='__main__':unittest.main()
