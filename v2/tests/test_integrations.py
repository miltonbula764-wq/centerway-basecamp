"""Integration metadata only; discarded SQLite files and no external connections."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from centerway.core import Problem
from centerway.integration_contract import load, validate
from centerway.integrations import IntegrationRepository, install, GUARDS
from centerway.production import ProductionPolicy, BUSINESS_TABLES
from centerway.store import Store

EXAMPLES=Path(__file__).resolve().parents[1]/'examples/integrations'


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.path=self.root/'sandbox.sqlite3';self.store=Store(self.path,seed_demo=False,seed_accounts=False)
        with self.store.transaction() as db:
            for user in ('owner','scoped','reader'):
                db.execute('INSERT INTO users VALUES (?,?)',(user,'not-a-login-fixture'))
            db.executemany('INSERT INTO memberships VALUES (?,?,?)',[
                ('owner','collaboration','operator'),('owner','billing','operator'),('owner','support','operator'),
                ('scoped','collaboration','operator'),('reader','collaboration','viewer')])
        install(self.store);self.repo=IntegrationRepository(self.store)
        self.config=load(EXAMPLES/'collaboration.json')

    def tearDown(self): self.temp.cleanup()

    def test_three_saas_declarations_are_stored_and_read_without_core_changes(self):
        for path in sorted(EXAMPLES.glob('*.json')):
            doc=load(path);tenant=doc['tenant']
            saved=self.repo.append('owner',tenant,doc,0)
            self.assertEqual(1,saved['version']);self.assertEqual(doc,saved['config'])
            self.assertEqual(saved,IntegrationRepository(Store.open_existing(self.path)).get('owner',tenant))
            self.assertEqual(doc['provenance'],self.repo.get('owner',tenant)['config']['provenance'])
        with self.store.transaction() as db:
            for table in BUSINESS_TABLES: self.assertEqual(0,db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
        self.assertEqual(1,len(self.repo.history('owner','collaboration')))
        self.assertEqual(1,len(self.repo.history('owner','billing')))

    def test_missing_information_is_not_inferred_and_missing_value_verification_stays_empty(self):
        doc=deepcopy(self.config)
        for key in ('value_goals','metrics','events','evidence','capabilities'): doc[key]=[]
        self.assertEqual(doc,validate(doc))
        self.repo.append('owner','collaboration',doc,0)
        self.assertEqual([],self.repo.get('owner','collaboration')['config']['capabilities'])
        doc=deepcopy(self.config);verification=doc['capabilities'][0]['verification']
        verification['value']=[];verification['value_goal_refs']=[]
        self.repo.append('owner','collaboration',doc,1)
        self.assertEqual([],self.repo.get('owner','collaboration')['config']['capabilities'][0]['verification']['value'])

    def test_version_pinning_provenance_hashes_conflicts_and_detached_reads(self):
        first=self.repo.append('owner','collaboration',self.config,0)
        changed=deepcopy(self.config);changed['product']['description']='Explicit revised supplier declaration.'
        changed['provenance']['source_ref']='manual:revision-two'
        second=self.repo.append('scoped','collaboration',changed,1)
        self.assertEqual(first['record_hash'],second['parent_hash']);self.assertNotEqual(first['content_hash'],second['content_hash'])
        self.assertEqual('scoped',second['actor']);self.assertEqual(2,second['version'])
        self.assertEqual(first,self.repo.get('owner','collaboration',1))
        with self.assertRaises(Problem) as error: self.repo.append('owner','collaboration',self.config,1)
        self.assertEqual(409,error.exception.status)
        second['config']['product']['name']='Mutated local result'
        self.assertEqual(changed,self.repo.get('owner','collaboration')['config'])
        history=self.repo.history('owner','collaboration')
        self.assertEqual(2,len(history))
        self.assertEqual('manual:revision-two',history[1]['provenance']['source_ref'])
        with self.assertRaises(Problem) as error: self.repo.get('owner','collaboration',3)
        self.assertEqual(404,error.exception.status)
        with self.assertRaises(ValueError): self.repo.get('owner','collaboration',True)

    def test_memberships_apply_to_reads_writes_history_and_are_rechecked(self):
        self.repo.append('owner','collaboration',self.config,0)
        self.assertEqual(1,self.repo.get('reader','collaboration')['version'])
        for call in (
            lambda:self.repo.append('reader','collaboration',self.config,1),
            lambda:self.repo.get('scoped','billing'),
            lambda:self.repo.history('scoped','billing'),
            lambda:self.repo.append('scoped','billing',load(EXAMPLES/'billing.json'),0),
            lambda:self.repo.get('unknown','collaboration'),
            lambda:self.repo.append('owner','collaboration',load(EXAMPLES/'billing.json'),1),
        ):
            with self.assertRaises(Problem) as error: call()
            self.assertEqual(403,error.exception.status)
        with self.store.transaction() as db:
            db.execute("UPDATE memberships SET role='viewer' WHERE user_id='scoped'")
        with self.assertRaises(Problem): self.repo.append('scoped','collaboration',self.config,1)
        with self.store.transaction() as db: db.execute("DELETE FROM memberships WHERE user_id='scoped'")
        with self.assertRaises(Problem): self.repo.get('scoped','collaboration',1)

    def test_cross_saas_references_and_undeclared_evidence_are_rejected_atomically(self):
        self.repo.append('owner','billing',load(EXAMPLES/'billing.json'),0)
        for mutation in (
            lambda d:d['metrics'][0].update(event_refs=['invoice-delivered']),
            lambda d:d['value_goals'][0].update(metric_refs=['delivered-invoices']),
            lambda d:d['capabilities'][0]['conditions'][0].update(evidence_ref='billing:operation-state'),
            lambda d:d['evidence'][0].update(availability='unavailable'),
            lambda d:d['capabilities'][0]['conditions'][0].update(field='unknown'),
            lambda d:d['capabilities'][0]['verification']['value'][0].update(evidence_ref='operation-state',field='paused'),
        ):
            doc=deepcopy(self.config);mutation(doc)
            with self.assertRaises(ValueError): self.repo.append('owner','collaboration',doc,0)
            self.assertEqual([],self.repo.history('owner','collaboration'))
        # Identical local evidence IDs in different tenants never share records.
        self.repo.append('owner','collaboration',self.config,0)
        self.assertEqual('collaboration',self.repo.get('owner','collaboration')['config']['tenant'])
        self.assertEqual('billing',self.repo.get('owner','billing')['config']['tenant'])

    def test_validation_rejects_extra_fields_permissions_types_duplicates_and_limits(self):
        mutations=[
            lambda d:d.update(schema_version=True),
            lambda d:d.update(tenant='../../other'),
            lambda d:d.update(credentials={'password':'must-not-be-stored'}),
            lambda d:d['metrics'].append(deepcopy(d['metrics'][0])),
            lambda d:d['capabilities'][0]['permissions'].update(required_role='viewer'),
            lambda d:d['capabilities'][0]['permissions'].update(requires_human_approval=1),
            lambda d:d['capabilities'][0]['conditions'][0].update(value=1),
            lambda d:d['capabilities'][0]['conditions'][0].update(operator='eval'),
            lambda d:d['capabilities'][0]['conditions'][0].update(operator='lt'),
            lambda d:d['events'][0]['fields'][0].update(required=False),
            lambda d:d['provenance'].update(recorded_at='2026-10-25T00:00:00'),
            lambda d:d['product'].update(description='x'*65537),
            lambda d:d['value_goals'][0].update(metric_refs=[],evidence_refs=[]),
        ]
        before=self.path.read_bytes()
        for mutation in mutations:
            doc=deepcopy(self.config);mutation(doc)
            with self.assertRaises(ValueError): self.repo.append('owner','collaboration',doc,0)
            self.assertEqual(before,self.path.read_bytes())
        bad=self.root/'bad.json';bad.write_text('{"tenant":"collaboration","tenant":"billing"}')
        with self.assertRaises(ValueError): load(bad)
        bad.write_text('{"value":NaN}')
        with self.assertRaises(ValueError): load(bad)

    def test_generic_numeric_timestamp_and_exists_conditions_without_evaluation(self):
        doc=deepcopy(self.config);source=doc['evidence'][0]
        source['fields'] += [{'name':'count','type':'integer','required':True},{'name':'when','type':'timestamp','required':True}]
        conditions=doc['capabilities'][0]['conditions']
        conditions[:]=[
            {'evidence_ref':'operation-state','field':'count','operator':'gte','value':2},
            {'evidence_ref':'operation-state','field':'when','operator':'gt','value':'2026-01-01T00:00:00Z'},
            {'evidence_ref':'operation-state','field':'paused','operator':'exists'},
        ]
        self.assertEqual(doc,validate(doc))
        for value in (True,2.5,float('inf'),10**400):
            invalid=deepcopy(doc);invalid['capabilities'][0]['conditions'][0]['value']=value
            with self.assertRaises(ValueError): validate(invalid)
        self.repo.append('owner','collaboration',doc,0)
        self.assertEqual(doc,self.repo.get('owner','collaboration')['config'])

    def test_concurrent_append_has_one_winner_and_no_overwritten_version(self):
        def append_once(_):
            try: return self.repo.append('owner','collaboration',self.config,0)['version']
            except Problem as error: return error.status
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(append_once,range(2)))
        self.assertEqual([1,409],sorted(outcomes))
        self.assertEqual(1,len(self.repo.history('owner','collaboration')))

    def test_storage_is_append_only_and_tamper_is_detected_without_repair(self):
        self.repo.append('owner','collaboration',self.config,0)
        with self.store.transaction() as db:
            for sql in ('DELETE FROM integration_versions','UPDATE integration_versions SET actor=\'forged\''):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)
            db.execute('DROP TRIGGER integration_immutable_integration_versions_UPDATE')
        with self.assertRaises(ValueError): self.repo.get('owner','collaboration')
        with self.store.transaction() as db:
            db.execute("UPDATE integration_versions SET actor='forged'")
            db.execute(GUARDS['integration_immutable_integration_versions_UPDATE'])
        with self.assertRaises(ValueError): self.repo.get('owner','collaboration')
        with self.store.transaction() as db:
            self.assertEqual('forged',db.execute('SELECT actor FROM integration_versions').fetchone()[0])

    def test_setup_is_explicit_and_cli_does_not_create_missing_runtime(self):
        untouched=self.root/'unconfigured.sqlite3';store=Store(untouched,seed_demo=False)
        before=hashlib.sha256(untouched.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): IntegrationRepository(Store.open_existing(untouched))
        self.assertEqual(before,hashlib.sha256(untouched.read_bytes()).hexdigest())
        with self.assertRaises(ValueError): install(self.store)
        result=subprocess.run([sys.executable,'-m','centerway.integrations','init','--db',str(self.root/'missing.sqlite3')],cwd=EXAMPLES.parents[1],capture_output=True,text=True)
        self.assertEqual(1,result.returncode);self.assertFalse((self.root/'missing.sqlite3').exists())
        for command in (
            ['validate','--file',str(EXAMPLES/'collaboration.json')],
            ['append','--db',str(self.path),'--user','owner','--tenant','collaboration','--file',str(EXAMPLES/'collaboration.json'),'--expected-version','0'],
            ['get','--db',str(self.path),'--user','owner','--tenant','collaboration','--version','1'],
            ['history','--db',str(self.path),'--user','owner','--tenant','collaboration'],
        ):
            run=subprocess.run([sys.executable,'-m','centerway.integrations',*command],cwd=EXAMPLES.parents[1],capture_output=True,text=True)
            self.assertEqual(0,run.returncode,run.stderr);json.loads(run.stdout)

    def test_production_configuration_cannot_enable_business_or_import_synthetic_examples(self):
        from centerway.production import provision
        accounts=self.root/'accounts.json'
        accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
        path=self.root/'production.sqlite3'
        provision(path,self.root/'secrets.json','https://app.example.invalid',accounts)
        store=Store.open_existing(path);install(store);repo=IntegrationRepository(store)
        with self.assertRaises(Problem) as error: repo.append('owner','collaboration',self.config,0)
        self.assertEqual(403,error.exception.status)
        declared=deepcopy(self.config);declared['data_classification']='declared'
        declared['provenance']['source_ref']='test:unverified-supplier-declaration'
        repo.append('owner','collaboration',declared,0)
        self.assertEqual(1,repo.get('owner','collaboration')['version'])
        policy=ProductionPolicy(store)
        with self.assertRaises(Problem) as error: policy.block_operation(store,'owner','collaboration')
        self.assertEqual(503,error.exception.status)
        with store.transaction() as db:
            for table in BUSINESS_TABLES: self.assertEqual(0,db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
            with self.assertRaises(sqlite3.IntegrityError): db.execute("INSERT INTO environments VALUES ('collaboration','client','Blocked','{}',0)")

    def test_private_demo_expiry_applies_to_an_existing_repository(self):
        from centerway.preview import provision
        path=self.root/'demo.sqlite3';provision(path,self.root/'demo-secrets.json','https://demo.example.invalid')
        store=Store.open_existing(path);install(store);repo=IntegrationRepository(store)
        doc=deepcopy(self.config);doc['tenant']='atlas'
        repo.append('founder','atlas',doc,0)
        with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
        with self.assertRaises(ValueError): repo.get('founder','atlas')
        with self.assertRaises(ValueError): repo.append('founder','atlas',doc,1)
        with store.transaction() as db: db.execute('DROP TABLE preview_metadata')
        with self.assertRaises(ValueError): IntegrationRepository(store)
