"""C06 synthetic fixtures only. Fake C05 clock/adapter are test-only, never real recovery."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from centerway.core import Problem
from centerway.evidence import EvidenceRepository
from centerway.integrations import canonical,IntegrationRepository
from centerway.recovery import RecoveryRepository,install,GUARDS
from centerway.recovery_contract import validate
from centerway.store import Store
import test_controlled_execution as execution_tests
from test_ai_proposals import fixture,FixtureAdapter

ROOT=Path(__file__).resolve().parents[1]
AS_OF='2026-01-01T00:08:00Z'


class FixtureClock(datetime):
    """Explicit historical clock fixture; does not exist in the runtime."""
    current=datetime(2026,1,1,0,5,tzinfo=timezone.utc)
    @classmethod
    def now(cls,tz=None): return cls.current if tz is not None else cls.current.replace(tzinfo=None)


class RecoveryTests(unittest.TestCase):
    setUpBase=execution_tests.ExecutionTests.setUpBase
    tearDown=execution_tests.ExecutionTests.tearDown
    prepare=execution_tests.ExecutionTests.prepare
    approve=execution_tests.ExecutionTests.approve
    execute=execution_tests.ExecutionTests.execute
    ready=execution_tests.ExecutionTests.ready
    def setUp(self):
        execution_tests.ExecutionTests.setUp(self)
        install(self.store);self.recovery=RecoveryRepository(self.store)
        FixtureClock.current=datetime(2026,1,1,0,5,tzinfo=timezone.utc)

    def clock(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch('centerway.controlled_execution.datetime',FixtureClock))
        stack.enter_context(patch('centerway.controlled_execution.now',side_effect=lambda:FixtureClock.current.isoformat()))
        stack.enter_context(patch('test_controlled_execution.now',side_effect=lambda:FixtureClock.current.isoformat()))
        return stack

    def start(self,failure=None):
        self.adapter.failure=failure
        with self.clock():
            self.ready()
            if failure and failure.startswith('crash'):
                with self.assertRaises(KeyboardInterrupt): self.execute()
            else: self.execute()
        self.add_plan()

    def document(self,tenant='collaboration'): return fixture(tenant,'plan','c06')
    def add_plan(self,document=None,expected=0,tenant='collaboration',customer='fictional-account',execution='exec-1',user='demo'):
        return self.recovery.append_plan(user,tenant,customer,execution,document or self.document(tenant),expected)
    def ingest(self,body=None,tenant='collaboration'):
        return EvidenceRepository(self.store).ingest('demo',body or fixture(tenant,'after','c06'))
    def evaluate(self,user='demo',tenant='collaboration',customer='fictional-account',execution='exec-1',plan=1,as_of=AS_OF):
        return self.recovery.evaluate(user,tenant,customer,execution,plan,as_of)
    def get(self,version=1,user='demo',tenant='collaboration',customer='fictional-account',execution='exec-1'):
        return self.recovery.get(user,tenant,customer,execution,version)

    def test_explicit_before_after_and_receipt_link_never_claim_real_recovery(self):
        self.start();self.ingest();run=self.evaluate();a=run['payload']['assessment'];inputs=run['payload']['inputs']
        self.assertEqual('demonstrated',a['execution']['state']);self.assertEqual('demonstrated',a['operational_recovery']['state'])
        self.assertEqual('demonstrated',a['value_recovery']['state']);self.assertEqual('demonstrated',a['summary_state'])
        self.assertEqual('synthetic_test_only',a['assessment_scope']);self.assertFalse(a['real_recovery_demonstrated'])
        self.assertIsNone(a['operational_recovered']);self.assertIsNone(a['value_recovered']);self.assertFalse(a['automatic_closure'])
        self.assertFalse(a['core_transition_authorized']);self.assertEqual('inactive',a['operational_state'])
        self.assertEqual('not_established',a['causal_attribution']);self.assertEqual('blocked',a['external_execution'])
        self.assertTrue(inputs['c05']['intent_hash']);self.assertTrue(inputs['c05']['approval_hash']);self.assertTrue(inputs['c05']['attempt_hash'])
        self.assertEqual('test_applied',inputs['c05']['result']['payload']['status'])
        value=a['criteria_results'][1];self.assertEqual({'numerator':'2','denominator':'1'},value['delta'])
        self.assertEqual({'numerator':'1','denominator':'1'},value['windows']['before']['aggregate'])
        self.assertEqual({'numerator':'3','denominator':'1'},value['windows']['after']['aggregate'])
        for result in a['criteria_results']:
            for ref in result['windows']['after']['evidence_refs']:
                self.assertGreater(ref['occurred_at'],inputs['c05']['dispatch_at']);self.assertEqual(1,ref['config_version']);self.assertTrue(ref['source_ref']);self.assertTrue(ref['record_hash'])
        self.assertEqual(run['payload'],self.get(user='leitor')['payload'])

    def test_execution_success_without_post_evidence_is_insufficient_in_both_dimensions(self):
        self.start();a=self.evaluate()['payload']['assessment']
        self.assertEqual('demonstrated',a['execution']['state']);self.assertEqual('insufficient',a['operational_recovery']['state'])
        self.assertEqual('insufficient',a['value_recovery']['state']);self.assertEqual('insufficient',a['summary_state'])
        self.assertEqual(1,self.adapter.calls);self.assertEqual(1,self.adapter.effects())

    def test_three_saas_demonstrate_both_operation_only_and_neither_using_same_engine(self):
        expected={'collaboration':('demonstrated','demonstrated'),'billing':('demonstrated','not_demonstrated'),'support':('not_demonstrated','not_demonstrated')}
        for tenant in expected:
            if tenant=='collaboration': self.start()
            else:
                self.repo.propose('demo',tenant,'fictional-account',self.parents[tenant]['id'],1,'proposal',FixtureAdapter())
                adapter=execution_tests.PersistentTestAdapter(self.root/(tenant+'-service.sqlite3'),tenant,fixture(tenant,'config','c04')['capabilities'][0]['id'])
                with self.clock():
                    intent=self.engine.prepare('demo',tenant,'fictional-account','proposal','exec-1',adapter)
                    self.engine.approve('demo',tenant,'fictional-account','exec-1',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=adapter)
                    self.engine.execute('demo',tenant,'fictional-account','exec-1',adapter)
                self.add_plan(tenant=tenant)
            self.ingest(tenant=tenant);a=self.evaluate(tenant=tenant)['payload']['assessment']
            self.assertEqual(expected[tenant],(a['operational_recovery']['state'],a['value_recovery']['state']))
            self.assertEqual('demonstrated',a['execution']['state'])

    def test_reassessment_appends_versions_and_preserves_prior_insufficient_result(self):
        self.start();first=self.evaluate();self.assertEqual('insufficient',first['payload']['assessment']['summary_state'])
        self.ingest();second=self.evaluate();self.assertEqual(2,second['version']);self.assertEqual(first['record_hash'],second['parent_hash'])
        self.assertEqual('demonstrated',second['payload']['assessment']['summary_state']);self.assertEqual(first['payload'],self.get(1)['payload'])
        repeat=self.evaluate();self.assertTrue(repeat['reused']);self.assertEqual(second['record_hash'],repeat['record_hash']);self.assertEqual(1,self.adapter.calls)

    def test_contradiction_arriving_later_overrides_neither_fact_nor_prior_run(self):
        self.start();self.ingest();first=self.evaluate()
        body=fixture('collaboration','after','c06');row=body['records'][0];row['external_id']='contradictory-after';row['payload']['paused']=True;body['records']=[row]
        self.ingest(body);second=self.evaluate();a=second['payload']['assessment']
        self.assertEqual('contradictory',a['operational_recovery']['state']);self.assertEqual('demonstrated',a['value_recovery']['state'])
        self.assertEqual('contradictory',a['summary_state']);self.assertEqual('demonstrated',self.get(1)['payload']['assessment']['summary_state'])
        conflict=a['criteria_results'][0]['windows']['after']['contradictions'][0];self.assertEqual(2,len(conflict['evidence_ids']))
        self.assertEqual(1,self.adapter.calls)

    def test_uncertain_and_failed_execution_are_not_promoted_by_positive_post_evidence(self):
        for failure,execution_state in [('after','execution_uncertain'),('crash-after','execution_uncertain'),('before','not_demonstrated')]:
            with self.subTest(failure=failure):
                self.tearDown();self.setUp();self.start(failure);self.ingest();a=self.evaluate()['payload']['assessment']
                self.assertEqual(execution_state,a['execution']['state']);self.assertEqual('demonstrated',a['operational_recovery']['state'])
                self.assertEqual('demonstrated',a['value_recovery']['state']);self.assertEqual(execution_state,a['summary_state'])
                self.assertFalse(a['real_recovery_demonstrated']);self.assertEqual(1,self.adapter.calls)
                self.engine.execute('demo','collaboration','fictional-account','exec-1',self.adapter);self.assertEqual(1,self.adapter.calls)

    def test_inflight_pending_snapshot_replays_after_c05_receipt_arrives(self):
        started=threading.Event();release=threading.Event()
        def wait(_): started.set();self.assertTrue(release.wait(5))
        self.adapter.on_apply=wait
        with self.clock():
            self.ready()
            with ThreadPoolExecutor(max_workers=1) as pool:
                task=pool.submit(self.execute);self.assertTrue(started.wait(5))
                try:
                    self.add_plan();self.ingest();first=self.evaluate()
                    self.assertEqual('execution_uncertain',first['payload']['assessment']['execution']['state'])
                    self.assertIsNone(first['payload']['inputs']['c05']['result'])
                finally: release.set()
                task.result(timeout=10)
        second=self.evaluate();self.assertEqual(2,second['version']);self.assertEqual('demonstrated',second['payload']['assessment']['execution']['state'])
        self.assertEqual('execution_uncertain',self.get(1)['payload']['assessment']['execution']['state']);self.assertEqual(1,self.adapter.calls)

    def test_post_dispatch_but_pre_receipt_evidence_cannot_prove_recovery(self):
        self.adapter.on_apply=lambda _:setattr(FixtureClock,'current',datetime(2026,1,1,0,9,tzinfo=timezone.utc))
        self.start();self.ingest();a=self.evaluate(as_of='2026-01-01T00:10:00Z')['payload']['assessment']
        self.assertEqual('demonstrated',a['execution']['state']);self.assertEqual('insufficient',a['operational_recovery']['state'])
        after=a['criteria_results'][0]['windows']['after'];self.assertIn('window_not_after_receipt_or_dispatch',[r['code'] for r in after['issues']])
        self.assertTrue(after['excluded'])

    def test_plan_rejects_invented_targets_skipped_checks_bad_windows_and_implicit_defaults(self):
        self.start();doc=self.document()
        transforms=[lambda d:d.update(config_version=2),lambda d:d.update(capability_id='arbitrary'),lambda d:d.update(tenant='billing'),
                    lambda d:d['checks'].pop(),lambda d:d['checks'].append(deepcopy(d['checks'][0])),
                    lambda d:d['checks'][0].update(criterion_index=True),lambda d:d['checks'][0].update(target=False),
                    lambda d:d['checks'][0].update(coverage='partial'),lambda d:d['checks'][0].update(aggregation='mean'),
                    lambda d:d['checks'][0].update(sampling='period'),lambda d:d['checks'][0].update(method='assume_improvement'),
                    lambda d:d['checks'][0]['after'].update(start='2026-01-01T00:05:00Z'),
                    lambda d:d['checks'][0]['before'].update(end='2026-01-01T00:06:00Z'),
                    lambda d:d['checks'][0]['after'].update(cadence_seconds=0),lambda d:d['checks'][0]['after'].pop('cadence_seconds'),
                    lambda d:d['checks'][0]['after'].update(end='2026-01-01T00:08:01Z'),lambda d:d.update(schema_version=True)]
        for transform in transforms:
            bad=deepcopy(doc);transform(bad)
            with self.assertRaises((Problem,ValueError)): self.add_plan(bad,expected=1)
        with self.assertRaises(Problem): self.add_plan(doc,expected=0)
        self.assertEqual(1,len(self.recovery.history('demo','collaboration','fictional-account','exec-1')['plans']))

    def test_plan_revision_keeps_old_targets_and_results_reproducible(self):
        self.start();self.ingest();first=self.evaluate()
        doc=self.document();doc['checks'][1]['aggregation']='sum';second_plan=self.add_plan(doc,expected=1)
        second=self.evaluate(plan=2);self.assertEqual(2,second_plan['version']);self.assertEqual(2,second['plan_version'])
        self.assertEqual({'numerator':'6','denominator':'1'},second['payload']['assessment']['criteria_results'][1]['windows']['after']['aggregate'])
        self.assertEqual(first['payload'],self.get(1)['payload']);self.assertEqual(1,self.adapter.calls)

    def test_incomplete_windows_missing_fields_and_off_grid_samples_are_insufficient(self):
        self.start();body=fixture('collaboration','after','c06');body['records']=body['records'][:2];self.ingest(body)
        a=self.evaluate()['payload']['assessment'];self.assertEqual('insufficient',a['operational_recovery']['state'])
        self.assertEqual('insufficient',a['value_recovery']['state'])
        body=fixture('collaboration','after','c06');body['records']=[body['records'][2]];body['records'][0]['external_id']='off-grid'
        body['records'][0]['occurred_at']='2026-01-01T00:07:30Z';self.ingest(body)
        a=self.evaluate()['payload']['assessment'];self.assertEqual('insufficient',a['operational_recovery']['state'])
        self.assertIn('incompatible_sampling',[i['code'] for i in a['criteria_results'][0]['windows']['after']['issues']])

    def test_future_observation_window_not_complete_and_old_data_are_never_proof(self):
        self.start();self.ingest()
        a=self.evaluate(as_of='2026-01-01T00:07:00Z')['payload']['assessment']
        self.assertEqual('insufficient',a['operational_recovery']['state']);self.assertEqual('insufficient',a['value_recovery']['state'])
        refs=a['criteria_results'][0]['windows']['after']['excluded'];self.assertEqual('observed_after_as_of',refs[0]['code'])
        with self.assertRaises(ValueError): self.evaluate(as_of='2026-01-01T00:04:00Z')
        with self.assertRaises(ValueError): self.evaluate(as_of='2999-01-01T00:00:00Z')
        with self.assertRaises(ValueError): self.evaluate(plan=True)

    def test_already_met_before_is_not_a_demonstrated_recovery(self):
        self.start();self.ingest();doc=self.document()
        # The original fixture declares value 6 in both baseline buckets here.
        doc['checks'][1]['before'].update(start='2026-01-01T00:00:00Z',end='2026-01-01T00:02:00Z')
        self.add_plan(doc,expected=1);a=self.evaluate(plan=2)['payload']['assessment']
        self.assertEqual('not_demonstrated',a['value_recovery']['state']);self.assertEqual('target_already_met_before',a['criteria_results'][1]['reason_code'])
        self.assertEqual('demonstrated',a['criteria_results'][1]['windows']['after']['target_state'])

    def test_permissions_scope_and_no_intervention_creation(self):
        with self.assertRaises(Problem): self.add_plan()
        with self.clock(): self.ready()
        with self.assertRaises(Problem): self.add_plan() # Approved is not dispatched.
        with self.clock(): self.execute()
        self.add_plan();self.ingest();self.evaluate()
        for user,tenant,customer,execution in [('leitor','collaboration','fictional-account','exec-1'),('atlas','billing','fictional-account','exec-1'),
                ('unknown','collaboration','fictional-account','exec-1'),('demo','collaboration','another','exec-1'),('demo','collaboration','fictional-account','another')]:
            with self.assertRaises(Problem): self.evaluate(user=user,tenant=tenant,customer=customer,execution=execution)
        with self.assertRaises(Problem): self.get(user='atlas',tenant='billing')
        self.assertEqual(1,self.adapter.calls);self.assertEqual('demonstrated',self.get(user='leitor')['payload']['assessment']['summary_state'])

    def test_prior_engines_and_c05_are_unchanged_and_backup_preserves_all_versions(self):
        from centerway.ops import backup
        self.start();self.ingest()
        with self.store.transaction() as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'recovery_*'")]
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        first=self.evaluate();self.evaluate();self.add_plan(self.document(),expected=1);self.evaluate(plan=2)
        with self.store.transaction() as db:
            self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})
            for table in ('recovery_plans','recovery_runs'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM '+table)
                with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE "+table+" SET actor='forged'")
        self.assertEqual('verified',backup(self.path,self.root/'copy.sqlite3')['status'])
        replica=RecoveryRepository(Store.open_existing(self.root/'copy.sqlite3'))
        self.assertEqual(first['payload'],replica.get('demo','collaboration','fictional-account','exec-1',1)['payload'])

    def test_concurrent_identical_evaluations_reuse_one_version_and_never_call_adapter(self):
        self.start();self.ingest()
        with ThreadPoolExecutor(max_workers=2) as pool: runs=list(pool.map(lambda _:self.evaluate(),range(2)))
        self.assertEqual([1,1],[r['version'] for r in runs]);self.assertEqual({True,False},{r['reused'] for r in runs})
        self.assertEqual(1,self.adapter.calls)

    def test_integrity_missing_guards_modified_payload_and_independent_replay_fail_closed(self):
        self.start();self.ingest();self.evaluate()
        with self.store.transaction() as db: db.execute('DROP TRIGGER recovery_immutable_recovery_runs_UPDATE')
        with self.assertRaises(Problem): self.evaluate()
        with self.store.transaction() as db:
            db.execute("UPDATE recovery_runs SET payload='{}'");db.execute(GUARDS['recovery_immutable_recovery_runs_UPDATE'])
        with self.assertRaises(Problem): self.get()
        self.assertEqual(1,self.adapter.calls)

    def test_superseded_configurations_are_never_mixed_with_pinned_verification(self):
        self.start();self.ingest();first=self.evaluate()
        config=fixture('collaboration','config','c04');config['product']['description']='New synthetic configuration revision.'
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        body=fixture('collaboration','after','c06');body['config_version']=2;body['records']=[body['records'][0]]
        body['records'][0]['external_id']='wrong-config-after';body['records'][0]['payload']['paused']=True
        self.ingest(body);second=self.evaluate()
        self.assertEqual('demonstrated',second['payload']['assessment']['operational_recovery']['state'])
        self.assertEqual(1,len(second['payload']['inputs']['excluded_other_configuration_ids']))
        self.assertEqual(first['payload'],self.get(1)['payload'])

    def test_periods_spanning_intervention_and_incompatible_sampling_cannot_prove_value(self):
        self.start();body=fixture('collaboration','after','c06')
        body['records']=[r for r in body['records'] if r['definition_id']=='operation-state']
        span=fixture('collaboration','after','c06')['records'][1]
        span.update(external_id='spans-dispatch',period={'start':'2026-01-01T00:04:00Z','end':'2026-01-01T00:07:00Z'})
        body['records'].append(span);self.ingest(body);a=self.evaluate()['payload']['assessment']
        self.assertEqual('demonstrated',a['operational_recovery']['state']);self.assertEqual('insufficient',a['value_recovery']['state'])
        self.assertEqual('not_strictly_post_intervention',a['criteria_results'][1]['windows']['after']['excluded'][0]['code'])

    def test_value_conflicts_do_not_contaminate_operational_assessment(self):
        self.start();self.ingest()
        body=fixture('collaboration','after','c06');row=body['records'][1];row['external_id']='disputed-outcome';row['payload']['outcome_count']=0;body['records']=[row]
        self.ingest(body);a=self.evaluate()['payload']['assessment']
        self.assertEqual('demonstrated',a['operational_recovery']['state']);self.assertEqual('contradictory',a['value_recovery']['state'])
        self.assertIsNone(a['criteria_results'][1]['delta']);self.assertEqual('contradictory',a['summary_state'])

    def test_missing_baseline_prevents_recovery_even_when_post_target_is_met(self):
        self.start();self.ingest();doc=self.document()
        doc['checks'][0]['before'].update(start='2026-01-01T00:00:00Z',end='2026-01-01T00:01:00Z')
        self.add_plan(doc,expected=1);a=self.evaluate(plan=2)['payload']['assessment']
        self.assertEqual('insufficient',a['operational_recovery']['state'])
        self.assertEqual('demonstrated',a['criteria_results'][0]['windows']['after']['target_state'])

    def test_no_declared_value_target_never_infers_value_from_operation(self):
        # New configuration is supplied explicitly before creating C04/C05.
        config=fixture('collaboration','config','c04');config['capabilities'][0]['verification'].update(value=[],value_goal_refs=[])
        # A separate fresh repository for this configuration keeps the original
        # engines untouched; no mutation or rehashing of immutable source rows.
        import test_ai_proposals as proposals
        with self.store.transaction() as db: db.execute("INSERT INTO memberships VALUES ('demo','no-value','operator')")
        tenant='no-value';config['tenant']=tenant
        IntegrationRepository(self.store).append('demo',tenant,config,0)
        for suffix,directory in [('evidence','detection'),('context','c04')]:
            body=fixture('collaboration',suffix,directory);body['tenant']=tenant;self.ingest(body)
        criteria=fixture('collaboration','criteria');criteria['tenant']=tenant;self.c02.append_criteria('demo',tenant,criteria,0)
        parent=self.c02.evaluate('demo',tenant,'fictional-account',1,proposals.AS_OF)
        doc=fixture('collaboration','declaration','investigation');doc.update(tenant=tenant,c02_run_id=parent['id'])
        # The no-value tenant evidence IDs differ; explicit support is optional.
        doc['hypotheses']=[];doc['requirements']=[]
        self.c03.append('demo',tenant,'fictional-account',parent['id'],doc,0)
        self.repo.propose('demo',tenant,'fictional-account',parent['id'],1,'proposal',FixtureAdapter())
        adapter=execution_tests.PersistentTestAdapter(self.root/'no-value.sqlite3',tenant)
        with self.clock():
            intent=self.engine.prepare('demo',tenant,'fictional-account','proposal','exec-1',adapter)
            self.engine.approve('demo',tenant,'fictional-account','exec-1',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=adapter)
            self.engine.execute('demo',tenant,'fictional-account','exec-1',adapter)
        doc=self.document();doc['tenant']=tenant;doc['checks']=doc['checks'][:1];self.add_plan(doc,tenant=tenant)
        body=fixture('collaboration','after','c06');body['tenant']=tenant;self.ingest(body)
        a=self.evaluate(tenant=tenant)['payload']['assessment']
        self.assertEqual('demonstrated',a['operational_recovery']['state']);self.assertEqual('insufficient',a['value_recovery']['state'])
        self.assertEqual('no_declared_value_criteria',a['value_recovery']['reason_code'])

    def test_customer_isolation_accepts_external_customer_ids_without_sharing_evidence(self):
        customer='Account / 002'
        parent=execution_tests.fixtures.ProposalTests.new_subject(self,customer)
        self.repo.propose('demo','collaboration',customer,parent['id'],1,'proposal',FixtureAdapter())
        self.start();self.ingest();first=self.evaluate()
        with sqlite3.connect(self.adapter.path) as db: db.execute('INSERT INTO state VALUES (?,?,1,1)',('collaboration',customer))
        with self.clock():
            intent=self.engine.prepare('demo','collaboration',customer,'proposal','exec-1',self.adapter)
            self.engine.approve('demo','collaboration',customer,'exec-1',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter)
            self.engine.execute('demo','collaboration',customer,'exec-1',self.adapter)
        doc=self.document();doc['customer']=customer;self.add_plan(doc,customer=customer)
        a=self.evaluate(customer=customer)['payload']['assessment']
        self.assertEqual('insufficient',a['summary_state']);self.assertEqual(first['payload'],self.get()['payload'])
        body=fixture('collaboration','after','c06');body['customer']=customer
        for r in body['records']:
            if r['definition_id']=='value-snapshot': r['payload']['outcome_count']=1
        self.ingest(body);a=self.evaluate(customer=customer)['payload']['assessment']
        self.assertEqual('demonstrated',a['operational_recovery']['state']);self.assertEqual('not_demonstrated',a['value_recovery']['state'])
        self.assertEqual(2,self.adapter.calls)

    def test_receipt_clock_conflict_remains_uncertain_without_repeating_execution(self):
        self.adapter.on_apply=lambda _:setattr(FixtureClock,'current',datetime(2026,1,1,0,4,tzinfo=timezone.utc))
        self.start();self.ingest();a=self.evaluate()['payload']['assessment']
        self.assertEqual('execution_uncertain',a['execution']['state']);self.assertEqual('receipt_temporal_conflict',a['execution']['reason_code'])
        self.assertEqual('execution_uncertain',a['summary_state']);self.assertEqual(1,self.adapter.calls)

    def test_rehashing_a_forged_result_cannot_bypass_independent_replay(self):
        from centerway.integrations import digest
        self.start();self.ingest();self.evaluate()
        with self.store.transaction() as db:
            row=dict(db.execute('SELECT * FROM recovery_runs').fetchone());row.pop('record_hash')
            payload=json.loads(row['payload']);payload['assessment']['real_recovery_demonstrated']=True;row['payload']=canonical(payload)
            db.execute('DROP TRIGGER recovery_immutable_recovery_runs_UPDATE')
            db.execute('UPDATE recovery_runs SET payload=?,record_hash=?',(row['payload'],digest(row)))
            db.execute(GUARDS['recovery_immutable_recovery_runs_UPDATE'])
        with self.assertRaises(Problem): self.get()
        self.assertEqual(1,self.adapter.calls)

    def test_cli_explicit_setup_history_and_missing_file_are_safe(self):
        cli=[sys.executable,'-m','centerway.recovery']
        run=subprocess.run(cli+['init','--db',str(self.root/'missing.sqlite3')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(1,run.returncode);self.assertFalse((self.root/'missing.sqlite3').exists())
        with self.assertRaises(ValueError): install(self.store)
        self.start();self.ingest();self.evaluate()
        run=subprocess.run(cli+['history','--db',str(self.path),'--user','demo','--tenant','collaboration','--customer','fictional-account','--execution-id','exec-1'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stderr);self.assertEqual(1,len(json.loads(run.stdout)['runs']))


class RecoveryModeTests(unittest.TestCase):
    def test_production_has_no_c05_sources_and_c06_never_unlocks_business_operations(self):
        import tempfile
        from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
        from centerway.ai_proposals import install as install_c04
        from centerway.controlled_execution import install as install_c05
        import test_ai_proposals as proposals
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);accounts=root/'accounts.json';path=root/'production.sqlite3'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
            provision(path,root/'secrets.json','https://app.example.invalid',accounts)
            store=Store.open_existing(path);proposals.ProposalSafetyTests().prepare(store,'owner','collaboration',declared=True)
            install_c04(store);install_c05(store);before=path.read_bytes()
            with self.assertRaises(Problem): RecoveryRepository(store)
            self.assertEqual(before,path.read_bytes());install(store);repo=RecoveryRepository(store)
            for call in [lambda:repo.append_plan('owner','collaboration','fictional-account','exec-1',fixture('collaboration','plan','c06'),0),
                         lambda:repo.evaluate('owner','collaboration','fictional-account','exec-1',1,AS_OF),
                         lambda:repo.history('owner','collaboration','fictional-account','exec-1')]:
                with self.assertRaises(Problem): call()
            with self.assertRaises(Problem): ProductionPolicy(store).block_operation(store,'owner','collaboration')
            with store.transaction() as db:
                for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                for table in ('recovery_plans','recovery_runs','c05_attempts'): self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])

    def test_expired_private_demo_cannot_evaluate_or_read_c06(self):
        import tempfile,secrets
        from centerway.preview import provision
        from centerway.ai_proposals import install as install_c04,ProposalRepository
        from centerway.controlled_execution import install as install_c05,ExecutionRepository
        import test_ai_proposals as proposals
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'demo.sqlite3';provision(path,root/'secrets.json','https://demo.example.invalid')
            store=Store.open_existing(path);parent=proposals.ProposalSafetyTests().prepare(store,'founder','atlas')
            install_c04(store);ProposalRepository(store).propose('founder','atlas','fictional-account',parent['id'],1,'proposal',FixtureAdapter())
            install_c05(store);engine=ExecutionRepository(store);adapter=execution_tests.PersistentTestAdapter(root/'fake.sqlite3','atlas')
            token=secrets.token_urlsafe(32)
            with store.transaction() as db: db.execute('INSERT INTO sessions VALUES (?,?,?)',(token,'founder',(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
            # Normal real test clock: future windows are permitted in plans but
            # cannot demonstrate a completed recovery at the current as_of.
            intent=engine.prepare('founder','atlas','fictional-account','proposal','exec-1',adapter)
            engine.approve('founder','atlas','fictional-account','exec-1',intent['record_hash'],human_confirmed=True,session_token=token,adapter=adapter)
            result=engine.execute('founder','atlas','fictional-account','exec-1',adapter)
            install(store);repo=RecoveryRepository(store);doc=fixture('collaboration','plan','c06');doc['tenant']='atlas'
            boundary=datetime.fromisoformat(result['results']['payload']['created_at'])
            for c in doc['checks']:
                c['before'].update(start=(boundary-timedelta(minutes=3)).isoformat(),end=(boundary-timedelta(minutes=2)).isoformat())
                c['after'].update(start=(boundary+timedelta(minutes=1)).isoformat(),end=(boundary+timedelta(minutes=2)).isoformat())
            repo.append_plan('founder','atlas','fictional-account','exec-1',doc,0)
            repo.evaluate('founder','atlas','fictional-account','exec-1',1,boundary.isoformat())
            with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
            for call in [lambda:repo.evaluate('founder','atlas','fictional-account','exec-1',1,boundary.isoformat()),lambda:repo.history('founder','atlas','fictional-account','exec-1')]:
                with self.assertRaises(Problem): call()
            with store.transaction() as db: self.assertEqual(1,db.execute('SELECT count(*) FROM recovery_runs').fetchone()[0])
            self.assertEqual(1,adapter.calls)
