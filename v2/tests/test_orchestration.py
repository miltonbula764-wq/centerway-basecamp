"""Orchestration technical fixtures only: no real model, connector or recovery."""
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
from centerway.orchestration import Orchestrator,install,GUARDS,STATES
from centerway.recovery import install as install_c06
from centerway.store import Store
from test_ai_proposals import fixture,FixtureAdapter
import test_controlled_execution as execution_tests
import test_recovery as recovery_tests

ROOT=Path(__file__).resolve().parents[1]
DETECTION_AT='2026-01-01T00:04:00Z'
VERIFICATION_AT='2026-01-01T00:08:00Z'


class OrchestrationTests(unittest.TestCase):
    setUpBase=execution_tests.ExecutionTests.setUpBase
    tearDown=execution_tests.ExecutionTests.tearDown
    clock=recovery_tests.RecoveryTests.clock
    def setUp(self):
        execution_tests.ExecutionTests.setUp(self);install_c06(self.store);install(self.store)
        self.orch=Orchestrator(self.store);recovery_tests.FixtureClock.current=datetime(2026,1,1,0,5,tzinfo=timezone.utc)
        self.ai=FixtureAdapter();self.register()
    def register(self,customer='fictional-account',tenant='collaboration',case='case-1',user='demo'):
        return self.orch.register(user,tenant,customer,case)
    def pump(self,customer='fictional-account',tenant='collaboration',case='case-1',as_of=DETECTION_AT,ai=None,adapter=None,dispatch=True,user='demo',**kwargs):
        return self.orch.process_case(user,tenant,customer,case,as_of,ai_adapter=ai or self.ai,
                    execution_adapter=adapter or self.adapter,allow_test_dispatch=dispatch,**kwargs)
    def latest(self,view=None):
        return (view or self.orch.history('demo','collaboration','fictional-account','case-1'))['history'][-1]['payload']
    def approve_case(self,user='demo'):
        p=self.latest();execution_id=p['refs']['c05']['execution_id'];intent=self.engine.get(user,'collaboration','fictional-account',execution_id)['intent']
        return self.engine.approve(user,'collaboration','fictional-account',execution_id,intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter)
    def new_customer(self,customer,tenant='collaboration',kind='deteriorating'):
        self.register(customer,tenant)
        if kind=='empty': return
        body=fixture(tenant,'evidence');body['customer']=customer
        if kind=='incomplete': body['records']=body['records'][:2]
        if kind=='stable':
            for row in body['records']:
                if row['definition_id']=='value-snapshot': row['payload']['outcome_count']=6
                elif row['kind']=='metric': row['payload']['value']=5
                else: row['payload']['delay_seconds']=5
        EvidenceRepository(self.store).ingest('demo',body)
        context=fixture(tenant,'context','c04');context['customer']=customer;EvidenceRepository(self.store).ingest('demo',context)
    def declare(self,customer='fictional-account',tenant='collaboration'):
        p=self.latest(self.orch.history('demo',tenant,customer,'case-1'));parent=p['refs']['c02']['id']
        declaration=fixture(tenant,'declaration','investigation');declaration.update(customer=customer,c02_run_id=parent)
        declaration['hypotheses']=[];declaration['requirements']=[]
        return self.c03.append('demo',tenant,customer,parent,declaration,0)

    def test_complete_routing_stops_for_human_then_automatically_verifies_without_closure(self):
        with self.clock():
            p=self.latest(self.pump());self.assertEqual('awaiting_approval',p['state']);self.assertEqual(1,self.ai.calls)
            self.assertEqual(0,self.adapter.effects());self.approve_case()
            p=self.latest(self.pump());self.assertEqual('awaiting_verification',p['state']);self.assertEqual(1,self.adapter.effects())
        self.assertTrue(p['refs']['c05']['attempt_hash']);execution_id=p['refs']['c05']['execution_id']
        plan=fixture('collaboration','plan','c06');plan['execution_id']=execution_id
        self.orch.recovery.append_plan('demo','collaboration','fictional-account',execution_id,plan,0)
        p=self.latest(self.pump(as_of=VERIFICATION_AT));self.assertEqual('awaiting_verification',p['state'])
        EvidenceRepository(self.store).ingest('demo',fixture('collaboration','after','c06'))
        p=self.latest(self.pump(as_of=VERIFICATION_AT));self.assertEqual('verification_recorded',p['state'])
        self.assertEqual('demonstrated',p['refs']['c06']['value_state']);self.assertFalse(p['real_recovery_demonstrated'])
        self.assertFalse(p['core_transition_authorized']);self.assertEqual(1,self.ai.calls);self.assertEqual(1,self.adapter.calls)
        before=len(self.orch.history('demo','collaboration','fictional-account','case-1')['history'])
        self.pump(as_of='2026-01-01T00:10:00Z')
        self.assertEqual(before,len(self.orch.history('demo','collaboration','fictional-account','case-1')['history']))
        self.assertEqual(1,self.adapter.calls)

    def test_default_configuration_never_calls_ai_or_prepares_execution(self):
        p=self.latest(self.orch.process_case('demo','collaboration','fictional-account','case-1',DETECTION_AT))
        self.assertEqual('awaiting_ai',p['state']);self.assertEqual(['authorized_ai_not_configured'],p['blockers'])
        with self.store.transaction() as db: self.assertEqual(0,db.execute("SELECT count(*) FROM c04_requests WHERE request_id LIKE 'orch-%'").fetchone()[0])
        # Adding explicitly labelled test AI later is permitted: absence did not reserve a fake response.
        p=self.latest(self.orch.process_case('demo','collaboration','fictional-account','case-1',DETECTION_AT,ai_adapter=self.ai))
        self.assertEqual('awaiting_execution',p['state']);self.assertEqual(['connector_unavailable'],p['blockers'])
        self.assertEqual('test_fixture',p['refs']['c04']['inference_kind']);self.assertEqual(0,self.adapter.calls)

    def test_no_investigation_is_fabricated_and_operator_declaration_is_consumed(self):
        self.new_customer('new-client')
        p=self.latest(self.pump(customer='new-client'));self.assertEqual('awaiting_investigation',p['state']);self.assertEqual(0,self.ai.calls)
        with self.store.transaction() as db: self.assertEqual(0,db.execute("SELECT count(*) FROM investigation_versions WHERE customer='new-client'").fetchone()[0])
        self.declare('new-client')
        p=self.latest(self.orch.process_case('demo','collaboration','new-client','case-1',DETECTION_AT,ai_adapter=self.ai))
        self.assertEqual('awaiting_execution',p['state']);self.assertEqual(1,self.ai.calls)

    def test_case_and_engine_idempotence_hold_across_restarts_and_clock_only_ticks(self):
        with self.clock(): self.pump()
        first=self.orch.history('demo','collaboration','fictional-account','case-1');self.register()
        reopened=Orchestrator(Store.open_existing(self.path))
        for as_of in (DETECTION_AT,'2026-01-01T00:04:30Z','2026-01-01T00:05:00Z'):
            with self.clock(): reopened.process_case('demo','collaboration','fictional-account','case-1',as_of,ai_adapter=self.ai,execution_adapter=self.adapter)
        self.assertEqual(first,self.orch.history('demo','collaboration','fictional-account','case-1'));self.assertEqual(1,self.ai.calls)
        with self.assertRaises(Problem): self.register(case='another-case')
        self.assertEqual(0,self.adapter.calls)

    def test_new_pre_dispatch_evidence_invalidates_routing_without_reusing_human_approval(self):
        with self.clock(): self.pump();self.approve_case()
        old=self.latest();body=fixture('collaboration','context','c04');body['records'][0]['external_id']='new-observed-state';body['records'][0]['payload']['paused']=False
        EvidenceRepository(self.store).ingest('demo',body)
        p=self.latest(self.pump());self.assertEqual('awaiting_investigation',p['state'])
        self.assertNotEqual(old['refs']['c02']['id'],p['refs']['c02']['id']);self.assertNotIn('c05',p['refs']);self.assertEqual(0,self.adapter.calls)
        with self.assertRaises(Problem): self.engine.execute('demo','collaboration','fictional-account',old['refs']['c05']['execution_id'],self.adapter)
        self.assertEqual(0,self.adapter.calls)

    def test_new_investigation_revision_creates_new_proposal_but_never_a_new_approval(self):
        with self.clock(): self.pump()
        old=self.latest();doc=fixture('collaboration','declaration','investigation');doc['c02_run_id']=old['refs']['c02']['id'];doc['hypotheses'][0]['statement']='Explicit revised test hypothesis, still unconfirmed.'
        self.c03.append('demo','collaboration','fictional-account',old['refs']['c02']['id'],doc,1)
        with self.clock(): p=self.latest(self.pump())
        self.assertEqual('awaiting_approval',p['state']);self.assertNotEqual(old['refs']['c04']['request_id'],p['refs']['c04']['request_id'])
        self.assertEqual(2,self.ai.calls);self.assertEqual(0,self.adapter.calls)

    def test_no_action_and_invalid_model_outputs_do_not_prepare_or_execute(self):
        p=self.latest(self.pump(ai=FixtureAdapter(kind='no_action')));self.assertEqual('no_action',p['state'])
        self.assertNotIn('c05',p['refs']);self.assertEqual(0,self.adapter.calls)
        self.new_customer('bad-ai');self.pump(customer='bad-ai');self.declare('bad-ai')
        p=self.latest(self.pump(customer='bad-ai',ai=FixtureAdapter(raw='untrusted-do-not-store')))
        self.assertEqual('needs_review',p['state']);self.assertNotIn('untrusted-do-not-store',canonical(p));self.assertNotIn('c05',p['refs'])

    def test_approval_expiry_revocation_dispatch_opt_in_and_current_conditions_are_enforced(self):
        with self.clock():
            self.pump();self.approve_case();p=self.latest(self.pump(dispatch=False));self.assertEqual('awaiting_execution',p['state'])
        with self.store.transaction() as db: db.execute('DELETE FROM sessions WHERE token=?',(self.session_token,))
        with self.clock(): p=self.latest(self.pump())
        self.assertEqual('needs_review',p['state']);self.assertEqual(['human_approval_invalid_or_expired'],p['blockers']);self.assertEqual(0,self.adapter.calls)
        self.adapter.change(False)
        with self.clock(): p=self.latest(self.pump())
        self.assertEqual('needs_review',p['state']);self.assertEqual(0,self.adapter.calls)

    def test_refused_current_conditions_require_review_without_repeated_execution_attempts(self):
        with self.clock():
            self.pump();self.approve_case();self.adapter.change(False)
            p=self.latest(self.pump());self.assertEqual('needs_review',p['state']);self.assertEqual(['execution_revalidation_refused'],p['blockers'])
            observations=self.adapter.observations
            with self.store.transaction() as db: count=db.execute('SELECT count(*) FROM c05_audit').fetchone()[0]
            self.pump();self.assertEqual(observations,self.adapter.observations)
            with self.store.transaction() as db: self.assertEqual(count,db.execute('SELECT count(*) FROM c05_audit').fetchone()[0])
        self.assertEqual(0,self.adapter.calls);self.assertEqual(0,self.adapter.effects())

    def test_crash_after_provider_response_reuses_request_without_second_inference(self):
        original=self.orch._record;interrupted=False
        def interrupt(user,case,expected,state,blockers,refs,basis):
            nonlocal interrupted
            if refs.get('c04',{}).get('record_hash') and not interrupted:
                interrupted=True;raise KeyboardInterrupt()
            return original(user,case,expected,state,blockers,refs,basis)
        with self.clock(),patch.object(self.orch,'_record',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.pump()
        self.assertEqual(1,self.ai.calls)
        with self.clock(): p=self.latest(self.pump())
        self.assertEqual('awaiting_approval',p['state']);self.assertEqual(1,self.ai.calls)

    def test_crash_during_provider_call_remains_pending_without_automatic_retry(self):
        def interrupt(_): raise KeyboardInterrupt()
        ai=FixtureAdapter(callback=interrupt)
        with self.assertRaises(KeyboardInterrupt): self.pump(ai=ai)
        p=self.latest(self.pump(ai=ai));self.assertEqual('awaiting_ai',p['state']);self.assertEqual(['inference_pending_or_interrupted_no_retry'],p['blockers'])
        self.assertEqual(1,ai.calls);self.assertEqual(0,self.adapter.calls)

    def test_crash_after_c05_effect_retains_uncertainty_and_never_repeats_intervention(self):
        with self.clock():
            self.pump();self.approve_case();self.adapter.failure='crash-after'
            with self.assertRaises(KeyboardInterrupt): self.pump()
        p=self.latest(self.pump(as_of=VERIFICATION_AT));self.assertEqual('needs_review',p['state'])
        self.assertEqual('uncertain_pending',p['refs']['c05']['state']);self.assertEqual(1,self.adapter.effects())
        self.pump(as_of=VERIFICATION_AT);self.assertEqual(1,self.adapter.calls)

    def test_concurrent_workers_do_not_duplicate_provider_calls_or_state_versions(self):
        started=threading.Event();release=threading.Event()
        def wait(_): started.set();self.assertTrue(release.wait(5))
        self.ai.callback=wait
        with self.clock(),ThreadPoolExecutor(max_workers=1) as pool:
            task=pool.submit(self.pump);self.assertTrue(started.wait(5))
            try:
                p=self.latest(self.pump());self.assertEqual('awaiting_ai',p['state']);self.assertEqual(1,self.ai.calls)
            finally: release.set()
            task.result(timeout=10)
            self.pump()
        self.assertEqual(1,self.ai.calls);self.assertEqual('awaiting_approval',self.latest()['state'])
        history=self.orch.history('demo','collaboration','fictional-account','case-1')['history']
        self.assertEqual(list(range(1,len(history)+1)),[r['version'] for r in history])

    def test_post_dispatch_lineage_is_fenced_when_new_inputs_arrive_during_a_tick(self):
        with self.clock(): self.pump();self.approve_case()
        old=self.latest();original_sources=self.orch._sources;once=False
        def race(user,case,as_of):
            nonlocal once
            if not once:
                once=True
                with self.clock(): self.engine.execute('demo','collaboration','fictional-account',old['refs']['c05']['execution_id'],self.adapter)
                body=fixture('collaboration','context','c04');body['records'][0]['external_id']='after-dispatch-race';body['records'][0]['payload']['paused']=False
                EvidenceRepository(self.store).ingest('demo',body)
            return original_sources(user,case,as_of)
        with patch.object(self.orch,'_sources',side_effect=race): self.pump()
        p=self.latest(self.pump(as_of=VERIFICATION_AT))
        self.assertEqual(old['refs']['c02'],p['refs']['c02']);self.assertEqual(old['refs']['c04'],p['refs']['c04'])
        self.assertEqual(old['refs']['c05']['execution_id'],p['refs']['c05']['execution_id']);self.assertTrue(p['refs']['c05']['attempt_hash'])
        self.assertEqual(1,self.adapter.calls)

    def test_batch_limits_isolation_bad_customer_and_restart_after_interruption(self):
        for name,kind in [('a-empty','empty'),('b-incomplete','incomplete'),('c-stable','stable'),('d-investigate','deteriorating')]: self.new_customer(name,kind=kind)
        original=self.orch.process_case
        def fail(user,tenant,customer,*args,**kwargs):
            if customer=='b-incomplete': raise RuntimeError('private-worker-marker')
            return original(user,tenant,customer,*args,**kwargs)
        results=[];cursor=0
        with patch.object(self.orch,'process_case',side_effect=fail):
            while True:
                page=self.orch.process_batch('demo','collaboration',DETECTION_AT,after=cursor,limit=2);results+=page['items'];cursor=page['next_after']
                if cursor is None: break
        self.assertEqual(5,len(results));self.assertEqual(1,sum(r['error'] is not None for r in results));self.assertNotIn('private-worker-marker',canonical(results))
        self.orch.process_batch('demo','collaboration',DETECTION_AT,limit=25)
        states={r['customer']:r['state'] for r in self.orch.query('demo','collaboration')['items']}
        self.assertEqual('awaiting_data',states['a-empty']);self.assertEqual('awaiting_data',states['b-incomplete'])
        self.assertEqual('stable',states['c-stable']);self.assertEqual('awaiting_investigation',states['d-investigate'])
        for kwargs in ({'limit':26},{'limit':0},{'budget_seconds':61},{'after':-1}):
            with self.assertRaises(ValueError): self.orch.process_batch('demo','collaboration',DETECTION_AT,**kwargs)
        with self.assertRaises(Problem): self.orch.process_batch('atlas','billing',DETECTION_AT)

    def test_150_customers_across_two_saas_are_bounded_independent_and_persisted(self):
        for i in range(150):
            tenant='collaboration' if i%2==0 else 'billing';kind=('empty','incomplete','stable','deteriorating','deteriorating')[i%5]
            self.new_customer('synthetic-'+str(i),tenant,kind)
        processed=0
        for tenant in ('collaboration','billing'):
            cursor=0
            while True:
                result=self.orch.process_batch('demo',tenant,DETECTION_AT,after=cursor,limit=25,budget_seconds=60)
                self.assertLessEqual(result['processed'],25);processed+=result['processed'];cursor=result['next_after']
                if cursor is None: break
        self.assertEqual(151,processed) # Includes the scoped fixture account.
        page=self.orch.query('demo','billing',state='stable',limit=50)
        self.assertEqual(15,len(page['items']));self.assertEqual(0,self.ai.calls);self.assertEqual(0,self.adapter.calls)
        reopened=Orchestrator(Store.open_existing(self.path));self.assertEqual(page,reopened.query('demo','billing',state='stable',limit=50))
        with self.store.transaction() as db:
            self.assertEqual(0,db.execute('SELECT count(*) FROM c05_attempts').fetchone()[0])
            self.assertEqual(151,db.execute('SELECT count(*) FROM orchestration_cases').fetchone()[0])

    def test_current_permissions_query_filters_and_tampering_fail_closed(self):
        self.pump()
        for user in ('leitor','unknown'):
            with self.assertRaises(Problem): self.pump(user=user)
            with self.assertRaises(Problem): self.register(user=user)
        self.assertEqual('awaiting_approval',self.orch.query('leitor','collaboration')['items'][0]['state'])
        with self.assertRaises(Problem): self.orch.query('atlas','billing')
        with self.assertRaises(Problem): self.orch.history('demo','collaboration','other','case-1')
        with self.assertRaises(ValueError): self.orch.query('demo','collaboration',case_id='case-1')
        with self.assertRaises(ValueError): self.orch.query('demo','collaboration',state='recovered')
        with self.store.transaction() as db:
            for table in ('orchestration_cases','orchestration_events'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM '+table)
            db.execute('DROP TRIGGER orchestration_immutable_orchestration_events_UPDATE')
        with self.assertRaises(Problem): self.orch.query('demo','collaboration')
        with self.store.transaction() as db:
            db.execute("UPDATE orchestration_events SET payload='{}'");db.execute(GUARDS['orchestration_immutable_orchestration_events_UPDATE'])
        with self.assertRaises(Problem): self.orch.history('demo','collaboration','fictional-account','case-1')

    def test_batch_continues_from_committed_case_after_process_interruption(self):
        self.new_customer('next-customer',kind='stable');original=self.orch.process_case;interrupted=False
        def interrupt(*args,**kwargs):
            nonlocal interrupted
            result=original(*args,**kwargs)
            if not interrupted: interrupted=True;raise KeyboardInterrupt()
            return result
        with patch.object(self.orch,'process_case',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.orch.process_batch('demo','collaboration',DETECTION_AT)
        with self.store.transaction() as db: before=db.execute('SELECT count(*) FROM detection_runs').fetchone()[0]
        result=Orchestrator(Store.open_existing(self.path)).process_batch('demo','collaboration',DETECTION_AT)
        self.assertEqual(2,result['processed']);self.assertEqual('stable',result['items'][1]['state'])
        with self.store.transaction() as db: self.assertEqual(before+1,db.execute('SELECT count(*) FROM detection_runs').fetchone()[0])

    def test_budget_and_step_limits_checkpoint_progress_without_requiring_stage_selection(self):
        with patch('centerway.orchestration.monotonic',side_effect=[0,2]):
            page=self.orch.process_batch('demo','collaboration',DETECTION_AT,budget_seconds=1)
        self.assertEqual(0,page['processed']);self.assertEqual(0,page['next_after'])
        first=self.pump(max_steps=1);self.assertEqual('awaiting_investigation',self.latest(first)['state'])
        with self.clock(): self.pump(max_steps=1);self.pump(max_steps=1);final=self.pump(max_steps=1)
        self.assertEqual('awaiting_approval',self.latest(final)['state']);self.assertEqual(1,self.ai.calls)

    def test_core_sandbox_and_declared_source_data_are_preserved(self):
        tables=('environments','observations','cases','executions','history','integration_versions','evidence_items','evidence_batches','investigation_versions')
        with self.store.transaction() as db: before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        with self.clock(): self.pump();self.approve_case();self.pump()
        with self.store.transaction() as db: self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})

    def test_explicit_cli_setup_does_not_create_missing_database_or_seed_cases(self):
        cli=[sys.executable,'-m','centerway.orchestration']
        run=subprocess.run(cli+['init','--db',str(self.root/'missing.sqlite3')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(1,run.returncode);self.assertFalse((self.root/'missing.sqlite3').exists())
        with self.assertRaises(ValueError): install(self.store)
        args=['--db',str(self.path),'--user','demo','--tenant','collaboration']
        run=subprocess.run(cli+['run-batch',*args,'--as-of',DETECTION_AT],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stderr);self.assertEqual('awaiting_ai',json.loads(run.stdout)['items'][0]['state'])
