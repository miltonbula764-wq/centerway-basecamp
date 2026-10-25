"""C05 uses only a labelled local TEST adapter and C04 fixture. No real SaaS/AI."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
import secrets
import threading
import unittest
from unittest.mock import patch

from centerway.controlled_execution import ExecutionRepository,install,GUARDS
from centerway.core import Problem
from centerway.evidence import EvidenceRepository
from centerway.execution_adapter import ExecutionAdapter,ExecutionReceipt
from centerway.integrations import canonical,IntegrationRepository
from centerway.store import Store,now
import test_ai_proposals as fixtures
from test_ai_proposals import FixtureAdapter,fixture


class PersistentTestAdapter(ExecutionAdapter):
    """TEST ONLY. Separate SQLite fake service; atomic revision and key+effect.

    Generic field transitions are explicit TEST inputs, never a runtime connector.
    """
    def __init__(self,path,tenant='collaboration',capability='reopen-delivery-queue',field='paused'):
        self.path=path;self.tenant=tenant;self.capability=capability;self.field=field
        self.calls=0;self.observations=0;self.on_observe=None;self.on_apply=None;self.failure=None
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS state(tenant,customer,revision INTEGER,value INTEGER,PRIMARY KEY(tenant,customer))')
            db.execute('CREATE TABLE IF NOT EXISTS effects(key TEXT PRIMARY KEY,tenant,customer,before_revision,after_revision)')
            db.execute('INSERT OR IGNORE INTO state VALUES (?,?,1,1)',(tenant,'fictional-account'))
    def descriptor(self):
        return {'kind':'test_adapter','adapter_id':'explicit-sqlite-test','version':'v1','tenant':self.tenant,'capability_id':self.capability,'idempotent':True,'atomic_conditions':True}
    def observe(self,binding):
        self.observations+=1
        if self.on_observe: self.on_observe(binding)
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT revision,value FROM state WHERE tenant=? AND customer=?',(binding['tenant'],binding['customer'])).fetchone()
        return {'tenant':binding['tenant'],'customer':binding['customer'],'capability_id':self.capability,'revision':str(row[0]),'observed_at':now(),
                'facts':[{'evidence_ref':'operation-state','field':self.field,'value':bool(row[1])}]}
    def change(self,value=True):
        with sqlite3.connect(self.path) as db: db.execute('UPDATE state SET revision=revision+1,value=? WHERE tenant=?',(int(value),self.tenant))
    def apply(self,key,binding,snapshot):
        self.calls+=1
        if self.on_apply: self.on_apply(binding)
        if self.failure=='before': return ExecutionReceipt('failed_no_effect','test-no-effect',snapshot['revision'],None)
        if self.failure=='crash-before': raise KeyboardInterrupt
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT before_revision,after_revision FROM effects WHERE key=?',(key,)).fetchone()
            if prior: return ExecutionReceipt('test_applied','test-receipt',*prior)
            row=db.execute('SELECT revision,value FROM state WHERE tenant=? AND customer=?',(binding['tenant'],binding['customer'])).fetchone()
            if str(row[0])!=snapshot['revision'] or not row[1]: return ExecutionReceipt('failed_no_effect','test-fenced',snapshot['revision'],None)
            db.execute('UPDATE state SET value=0,revision=revision+1 WHERE tenant=? AND customer=?',(binding['tenant'],binding['customer']))
            db.execute('INSERT INTO effects VALUES (?,?,?,?,?)',(key,binding['tenant'],binding['customer'],str(row[0]),str(row[0]+1)))
        if self.failure=='after': raise TimeoutError('do-not-store-provider-secret')
        if self.failure=='crash-after': raise KeyboardInterrupt
        if self.failure=='invalid': return {'status':'success','recovered':True,'secret':'do-not-store-provider-secret'}
        return ExecutionReceipt('test_applied','test-receipt',str(row[0]),str(row[0]+1))
    def effects(self):
        with sqlite3.connect(self.path) as db: return db.execute('SELECT count(*) FROM effects').fetchone()[0]


class ExecutionTests(unittest.TestCase):
    setUpBase=fixtures.ProposalTests.setUp
    tearDown=fixtures.ProposalTests.tearDown
    def setUp(self):
        self.setUpBase();self.repo.propose('demo','collaboration','fictional-account',self.parents['collaboration']['id'],1,'proposal',FixtureAdapter())
        install(self.store);self.engine=ExecutionRepository(self.store);self.adapter=PersistentTestAdapter(self.root/'fake-service.sqlite3')
        self.session_token=secrets.token_urlsafe(32)
        with self.store.transaction() as db: db.execute('INSERT INTO sessions VALUES (?,?,?)',(self.session_token,'demo',(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
    def prepare(self,user='demo',execution='exec-1',request='proposal',adapter=None):
        return self.engine.prepare(user,'collaboration','fictional-account',request,execution,adapter or self.adapter)
    def approve(self,user='demo',execution='exec-1',**kwargs):
        intent=self.engine.get('demo','collaboration','fictional-account',execution)['intent']
        return self.engine.approve(user,'collaboration','fictional-account',execution,intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter,**kwargs)
    def execute(self,user='demo',execution='exec-1',adapter=None):
        return self.engine.execute(user,'collaboration','fictional-account',execution,adapter or self.adapter)
    def get(self,user='demo',execution='exec-1'):
        return self.engine.get(user,'collaboration','fictional-account',execution)
    def ready(self): self.prepare();self.approve()

    def test_approval_requires_current_session_and_revocation_blocks_dispatch(self):
        intent=self.prepare()
        for token in (None,'forged-test-session-token'):
            with self.assertRaises(Problem): self.engine.approve('demo','collaboration','fictional-account','exec-1',intent['record_hash'],human_confirmed=True,session_token=token,adapter=self.adapter)
        self.approve()
        self.assertNotIn(self.session_token,canonical(self.get()))
        with self.store.transaction() as db: db.execute('DELETE FROM sessions WHERE user_id=?',('demo',))
        with self.assertRaises(Problem): self.execute(user='atlas')
        self.assertEqual(0,self.adapter.calls)

    def test_three_saas_use_same_contract_with_independent_test_effects(self):
        for tenant in ('collaboration','billing','support'):
            capability=fixture(tenant,'config','c04')['capabilities'][0]['id']
            adapter=PersistentTestAdapter(self.root/'three-saas.sqlite3',tenant,capability)
            if tenant!='collaboration': self.repo.propose('demo',tenant,'fictional-account',self.parents[tenant]['id'],1,'proposal',FixtureAdapter())
            intent=self.engine.prepare('demo',tenant,'fictional-account','proposal','shared-execution-id',adapter)
            self.engine.approve('demo',tenant,'fictional-account','shared-execution-id',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=adapter)
            result=self.engine.execute('demo',tenant,'fictional-account','shared-execution-id',adapter)
            self.assertEqual('test_applied',result['state'])
            self.assertEqual(tenant,result['intent']['tenant'])
        with sqlite3.connect(self.root/'three-saas.sqlite3') as db:
            self.assertEqual(3,db.execute('SELECT count(*) FROM effects').fetchone()[0])
            self.assertEqual(3,db.execute('SELECT count(DISTINCT key) FROM effects').fetchone()[0])

    def test_customers_with_external_ids_remain_isolated_with_independent_effect_keys(self):
        customer='Account / 002'
        parent=fixtures.ProposalTests.new_subject(self,customer)
        self.repo.propose('demo','collaboration',customer,parent['id'],1,'proposal',FixtureAdapter())
        # New evidence for another customer does not stale the first customer.
        self.ready();first=self.execute()
        with sqlite3.connect(self.adapter.path) as db: db.execute('INSERT INTO state VALUES (?,?,1,1)',('collaboration',customer))
        intent=self.engine.prepare('demo','collaboration',customer,'proposal','exec-1',self.adapter)
        self.engine.approve('demo','collaboration',customer,'exec-1',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter)
        result=self.engine.execute('demo','collaboration',customer,'exec-1',self.adapter)
        self.assertEqual('test_applied',result['state']);self.assertEqual(2,self.adapter.effects())
        self.assertNotEqual(first['attempts']['payload']['execution_key'],result['attempts']['payload']['execution_key'])

    def test_backup_preserves_approval_attempt_receipt_and_no_automatic_setup(self):
        from centerway.ops import backup
        self.ready();self.execute()
        self.assertEqual('verified',backup(self.path,self.root/'backup.sqlite3')['status'])
        replica=ExecutionRepository(Store.open_existing(self.root/'backup.sqlite3'))
        self.assertEqual(self.get(),replica.get('demo','collaboration','fictional-account','exec-1'))
        replica.execute('demo','collaboration','fictional-account','exec-1',self.adapter)
        self.assertEqual(1,self.adapter.calls)

    def test_full_explicit_flow_changes_only_persistent_test_service_and_exposes_c06_receipt(self):
        tables=('environments','observations','cases','executions','history','evidence_items','detection_runs','investigation_versions','c04_requests','c04_results')
        with self.store.transaction() as db: before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        intent=self.prepare();self.assertEqual('awaiting_human_approval',self.get()['state'])
        self.assertEqual(0,self.adapter.effects())
        with self.assertRaises(Problem): self.execute()
        self.approve();self.assertEqual('approved_test_only',self.get()['state'])
        result=self.execute();self.assertEqual('test_applied',result['state']);self.assertEqual(1,self.adapter.effects())
        self.assertEqual('test_adapter',result['attempts']['payload']['adapter']['kind'])
        self.assertEqual(intent['record_hash'],result['approvals']['payload']['intent_hash'])
        self.assertIsNone(result['results']['payload']['operational_recovered']);self.assertIsNone(result['results']['payload']['value_recovered'])
        self.assertEqual('not_performed',result['verification_status']);self.assertEqual('blocked',result['external_execution'])
        with self.store.transaction() as db: self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})
        reopened=ExecutionRepository(Store.open_existing(self.path));self.assertEqual(result,reopened.get('demo','collaboration','fictional-account','exec-1'))

    def test_no_implicit_approval_wrong_hash_flag_or_invented_actor(self):
        intent=self.prepare()
        for actor,hash_,flag in [('demo',intent['record_hash'],False),('demo','0'*64,True),('leitor',intent['record_hash'],True),('unknown',intent['record_hash'],True)]:
            with self.assertRaises(Problem): self.engine.approve(actor,'collaboration','fictional-account','exec-1',hash_,human_confirmed=flag,session_token=self.session_token,adapter=self.adapter)
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls);self.assertEqual('awaiting_human_approval',self.get()['state'])

    def test_same_execution_and_alternate_ids_never_dispatch_twice(self):
        first=self.prepare();self.assertEqual(first,self.prepare())
        with self.assertRaises(Problem): self.prepare(execution='other-id')
        self.repo.propose('demo','collaboration','fictional-account',self.parents['collaboration']['id'],1,'second-proposal',FixtureAdapter())
        with self.assertRaises(Problem): self.prepare(execution='other-id',request='second-proposal')
        approval=self.approve();self.assertEqual(approval,self.approve())
        self.execute();self.execute(user='atlas');self.execute();self.assertEqual(1,self.adapter.calls);self.assertEqual(1,self.adapter.effects())

    def test_concurrent_dispatch_is_reserved_before_io_and_no_core_lock_is_held(self):
        self.ready();started=threading.Event();release=threading.Event()
        def wait(_): started.set();self.assertTrue(release.wait(5))
        self.adapter.on_apply=wait
        with ThreadPoolExecutor(max_workers=1) as pool:
            task=pool.submit(self.execute);self.assertTrue(started.wait(5))
            try:
                pending=self.execute();self.assertEqual('uncertain_pending',pending['state']);self.assertEqual(1,self.adapter.calls)
                with self.store.transaction() as db: self.assertEqual(1,db.execute('SELECT count(*) FROM c05_attempts').fetchone()[0])
            finally: release.set()
            self.assertEqual('test_applied',task.result(timeout=10)['state'])
        self.assertEqual(1,self.adapter.effects())

    def test_timeout_after_effect_invalid_receipt_and_crash_never_retry_or_claim_recovery(self):
        for failure in ('after','invalid','crash-after','crash-before','before'):
            with self.subTest(failure=failure):
                # Fresh complete lab per outcome, including an independent fake service.
                self.tearDown();self.setUp();self.ready();self.adapter.failure=failure
                if failure.startswith('crash'):
                    with self.assertRaises(KeyboardInterrupt): self.execute()
                else: self.execute()
                view=self.execute();expected='uncertain_pending' if failure.startswith('crash') else 'failed_no_effect' if failure=='before' else 'uncertain'
                self.assertEqual(expected,view['state']);self.assertEqual(1,self.adapter.calls)
                self.assertEqual(0 if failure in ('crash-before','before') else 1,self.adapter.effects())
                self.assertNotIn('do-not-store-provider-secret',canonical(view))

    def test_past_condition_and_changed_revision_need_new_review_even_when_still_true(self):
        self.prepare();self.adapter.change(True)
        with self.assertRaises(Problem): self.approve()
        self.assertEqual(0,self.adapter.calls)
        self.tearDown();self.setUp();self.ready();self.adapter.change(True)
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls)
        self.adapter.change(False)
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.effects())

    def test_atomic_adapter_fence_prevents_change_after_observation(self):
        self.ready();self.adapter.on_apply=lambda _:self.adapter.change(False)
        self.assertEqual('failed_no_effect',self.execute()['state']);self.assertEqual(0,self.adapter.effects())

    def test_current_core_membership_of_approver_and_executor_and_expiration(self):
        self.ready()
        with self.store.transaction() as db: db.execute("UPDATE memberships SET role='viewer' WHERE user_id='demo' AND tenant='collaboration'")
        with self.assertRaises(Problem): self.execute(user='atlas')
        with self.assertRaises(Problem): self.execute(user='demo')
        self.assertEqual(0,self.adapter.calls)
        self.tearDown();self.setUp();self.prepare();self.approve(ttl_seconds=1)
        with patch('centerway.controlled_execution._time',return_value=datetime(2000,1,1,tzinfo=timezone.utc)):
            with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls)

    def test_new_evidence_or_catalogue_and_changes_during_observe_refuse_dispatch(self):
        self.ready()
        def add_data(_):
            body=fixture('collaboration','context','c04');body['records'][0]['external_id']='new-now'
            EvidenceRepository(self.store).ingest('demo',body)
        self.adapter.on_observe=add_data
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls)
        self.tearDown();self.setUp();self.ready()
        config=fixture('collaboration','config','c04');config['capabilities']=[]
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls)

    def test_revocation_during_io_preserves_result_even_when_caller_cannot_read(self):
        self.ready()
        def revoke(_):
            with self.store.transaction() as db: db.execute("DELETE FROM memberships WHERE user_id='demo' AND tenant='collaboration'")
        self.adapter.on_apply=revoke
        with self.assertRaises(Problem): self.execute()
        result=self.get(user='atlas');self.assertEqual('test_applied',result['state']);self.assertEqual(1,self.adapter.effects())
        self.execute(user='atlas');self.assertEqual(1,self.adapter.calls)

    def test_scope_adapter_permissions_and_capability_guarantees(self):
        for user in ('leitor','unknown'):
            with self.assertRaises(Problem): self.prepare(user=user)
        for tenant,customer in [('billing','fictional-account'),('collaboration','other')]:
            with self.assertRaises(Problem): self.engine.prepare('demo',tenant,customer,'proposal','exec-1',self.adapter)
        for field,value in [('tenant','billing'),('capability_id','arbitrary'),('kind','real_connector'),('idempotent',False),('atomic_conditions',False)]:
            descriptor=self.adapter.descriptor();descriptor[field]=value
            with patch.object(self.adapter,'descriptor',return_value=descriptor):
                with self.assertRaises(Problem): self.prepare()
        self.assertEqual(0,self.adapter.calls)
        self.prepare()
        with self.assertRaises(Problem): self.engine.get('atlas','billing','fictional-account','exec-1')
        with self.assertRaises(Problem): self.engine.get('demo','collaboration','other','exec-1')
        self.assertEqual('awaiting_human_approval',self.get(user='leitor')['state'])

    def test_bad_snapshot_missing_conflicting_stale_or_untyped_values_are_refused(self):
        original=self.adapter.observe
        transforms=[lambda s:s.update(observed_at='2020-01-01T00:00:00Z'),lambda s:s.update(facts=[]),
                    lambda s:s['facts'].append(deepcopy(s['facts'][0])),lambda s:s['facts'][0].update(value=1),
                    lambda s:s['facts'][0].update(field='invented'),lambda s:s.update(customer='another'),
                    lambda s:s.update(revision=True),lambda s:s.update(extra='no'),lambda s:s['facts'][0].update(value=False)]
        for transform in transforms:
            def malformed(b):
                s=original(b);transform(s);return s
            with patch.object(self.adapter,'observe',side_effect=malformed):
                with self.assertRaises(Problem): self.prepare()
        self.assertEqual(0,self.adapter.calls)

    def test_missing_adapter_unavailable_and_no_action_not_executable(self):
        with self.assertRaises(Problem): self.engine.prepare('demo','collaboration','fictional-account','proposal','exec-1')
        self.repo.propose('demo','collaboration','fictional-account',self.parents['collaboration']['id'],1,'none',FixtureAdapter(kind='no_action'))
        with self.assertRaises(Problem): self.prepare(request='none')
        self.assertEqual(0,self.adapter.calls)

    def test_audit_immutability_integrity_and_explicit_setup_only(self):
        self.ready()
        with self.assertRaises(ValueError): install(self.store)
        with self.store.transaction() as db:
            for table in ('c05_intents','c05_approvals','c05_audit'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM '+table)
            db.execute('DROP TRIGGER c05_immutable_c05_audit_UPDATE')
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls)
        with self.store.transaction() as db:
            db.execute("UPDATE c05_audit SET payload='{}' WHERE id=1")
            db.execute(GUARDS['c05_immutable_c05_audit_UPDATE'])
        with self.assertRaises(Problem): self.execute()
        self.assertEqual(0,self.adapter.calls)


class ExecutionProductionTests(unittest.TestCase):
    def test_expired_demo_during_dispatch_retains_receipt_without_reopening_access(self):
        import tempfile
        from centerway.preview import provision
        from centerway.ai_proposals import install as install_c04,ProposalRepository
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'demo.sqlite3';provision(path,root/'secrets.json','https://demo.example.invalid')
            store=Store.open_existing(path);parent=fixtures.ProposalSafetyTests().prepare(store,'founder','atlas')
            install_c04(store);ProposalRepository(store).propose('founder','atlas','fictional-account',parent['id'],1,'proposal',FixtureAdapter())
            install(store);engine=ExecutionRepository(store);adapter=PersistentTestAdapter(root/'fake.sqlite3','atlas')
            token=secrets.token_urlsafe(32)
            with store.transaction() as db: db.execute('INSERT INTO sessions VALUES (?,?,?)',(token,'founder',(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
            intent=engine.prepare('founder','atlas','fictional-account','proposal','test',adapter)
            engine.approve('founder','atlas','fictional-account','test',intent['record_hash'],human_confirmed=True,session_token=token,adapter=adapter)
            def expire(_):
                with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
            adapter.on_apply=expire
            with self.assertRaises(Problem): engine.execute('founder','atlas','fictional-account','test',adapter)
            self.assertEqual(1,adapter.effects())
            with store.transaction() as db:
                result=json.loads(db.execute('SELECT payload FROM c05_results').fetchone()[0]);self.assertEqual('test_applied',result['status'])
                self.assertIsNone(result['operational_recovered'])
            with self.assertRaises(Problem): engine.get('founder','atlas','fictional-account','test')
            with self.assertRaises(Problem): engine.execute('founder','atlas','fictional-account','test',adapter)
            self.assertEqual(1,adapter.calls)

    def test_production_declared_proposal_and_test_adapter_cannot_authorize_or_execute(self):
        import tempfile
        from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
        from centerway.ai_proposals import install as install_c04
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);accounts=root/'accounts.json';path=root/'production.sqlite3'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
            provision(path,root/'secrets.json','https://app.example.invalid',accounts)
            store=Store.open_existing(path);parent=fixtures.ProposalSafetyTests().prepare(store,'owner','collaboration',declared=True)
            install_c04(store)
            before=path.read_bytes()
            with self.assertRaises(Problem): ExecutionRepository(store)
            self.assertEqual(before,path.read_bytes());install(store);engine=ExecutionRepository(store)
            adapter=PersistentTestAdapter(root/'fake.sqlite3')
            # Even a well-formed binding cannot pass the unconditional production guard.
            binding={'classification':'declared','tenant':'collaboration','capability':{'id':'reopen-delivery-queue'}}
            with self.assertRaises(Problem): engine._adapter(adapter,binding)
            for call in (lambda:engine.prepare('owner','collaboration','fictional-account','absent','test',adapter),
                         lambda:engine.approve('owner','collaboration','fictional-account','test','0'*64,human_confirmed=True,adapter=adapter),
                         lambda:engine.execute('owner','collaboration','fictional-account','test',adapter)):
                with self.assertRaises(Problem): call()
            self.assertEqual(0,adapter.calls);self.assertEqual(0,adapter.observations)
            with self.assertRaises(Problem): ProductionPolicy(store).block_operation(store,'owner','collaboration')
            with store.transaction() as db:
                for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                self.assertEqual(0,db.execute('SELECT count(*) FROM c05_attempts').fetchone()[0])
