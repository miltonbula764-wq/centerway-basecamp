"""Explicit test fixtures only: lifecycle decisions never certify real recovery."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sqlite3
import json
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from centerway.continuity import Continuity,upgrade,TABLES,GUARDS
from centerway.core import Problem
from centerway.evidence import EvidenceRepository
from centerway.integrations import canonical,digest
from centerway.orchestration import Orchestrator
from centerway.store import Store
from test_ai_proposals import fixture,FixtureAdapter
import test_orchestration as orchestration_tests
import test_recovery as recovery_tests

ROOT=Path(__file__).resolve().parents[1]
CLOSE_AT='2026-01-10T00:00:00+00:00'


class ContinuityTests(unittest.TestCase):
    setUpBase=orchestration_tests.OrchestrationTests.setUpBase
    tearDown=orchestration_tests.OrchestrationTests.tearDown
    clock=orchestration_tests.OrchestrationTests.clock
    register=orchestration_tests.OrchestrationTests.register
    pump=orchestration_tests.OrchestrationTests.pump
    latest=orchestration_tests.OrchestrationTests.latest
    approve_case=orchestration_tests.OrchestrationTests.approve_case
    def setUp(self):
        orchestration_tests.OrchestrationTests.setUp(self);self.life=Continuity(self.store)
    def context(self,case='case-1',user='demo',tenant='collaboration',customer='fictional-account'):
        return self.life.context(user,tenant,customer,case)
    def close(self,case='case-1',request='close-1',reason='Explicit test follow-up decision, not real recovery.',disposition='not_recovered',context=None,user='demo',token=None,at=CLOSE_AT):
        ctx=context or self.context(case);s=ctx['context']
        with patch('centerway.continuity.now',return_value=at):
            return self.life.close(user,'collaboration','fictional-account',case,request,reason,disposition,s['checkpoint_version'],s['context_hash'],human_confirmed=True,session_token=token or self.session_token)
    def fresh(self):
        for suffix,directory in [('evidence','detection'),('context','c04')]:
            body=fixture('collaboration',suffix,directory)
            for r in body['records']:
                r['external_id']='cycle-2-'+r['external_id']
                r['occurred_at']=(datetime.fromisoformat(r['occurred_at'].replace('Z','+00:00'))+timedelta(days=10)).isoformat()
                if r['period']:
                    r['period']={k:(datetime.fromisoformat(v.replace('Z','+00:00'))+timedelta(days=10)).isoformat() for k,v in r['period'].items()}
            EvidenceRepository(self.store).ingest('demo',body)
    def open(self,case='case-2',previous='case-1',request='open-2',user='demo'):
        return self.life.open(user,'collaboration','fictional-account',case,request,'Explicit new incident supported by fresh test evidence.',previous,human_confirmed=True,session_token=self.session_token)
    def complete(self):
        with self.clock(): self.pump();self.approve_case();self.pump()
        p=self.latest();execution_id=p['refs']['c05']['execution_id'];plan=fixture('collaboration','plan','c06');plan['execution_id']=execution_id
        self.orch.recovery.append_plan('demo','collaboration','fictional-account',execution_id,plan,0)
        EvidenceRepository(self.store).ingest('demo',fixture('collaboration','after','c06'))
        self.pump(as_of='2026-01-01T00:08:00Z');return self.latest()

    def test_closure_is_explicit_immutable_audited_and_never_implies_value_recovery(self):
        self.pump();before=self.orch.history('demo','collaboration','fictional-account','case-1')['history']
        ctx=self.context();closed=self.close(context=ctx)
        self.assertEqual('demo',closed['actor']);self.assertEqual('closed',closed['payload']['status']);self.assertEqual('not_recovered',closed['payload']['request']['disposition'])
        self.assertFalse(closed['payload']['closure_means_recovery']);self.assertFalse(closed['payload']['real_recovery_demonstrated']);self.assertIsNone(closed['payload']['value_recovered'])
        self.assertEqual(ctx['context'],closed['payload']['snapshot']);self.assertTrue(closed['payload']['snapshot']['evidence'])
        self.assertNotIn(self.session_token,canonical(closed))
        self.assertEqual([],self.orch.query('demo','collaboration')['items'])
        item=self.orch.query('leitor','collaboration',lifecycle='closed')['items'][0]
        self.assertEqual('closed',item['lifecycle']);self.assertEqual(closed['record_hash'],item['closure']['record_hash'])
        self.assertEqual(before,self.orch.history('demo','collaboration','fictional-account','case-1')['history'])
        self.assertEqual('closed',self.context()['lifecycle']);self.assertEqual(closed,self.close(context=ctx))
        with self.assertRaises(Problem): self.close(request='another-close')
        with self.assertRaises(Problem): self.pump()
        with self.store.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM continuity_closures')

    def test_positive_c06_never_closes_automatically_and_old_sources_remain_unchanged(self):
        p=self.complete();self.assertEqual('verification_recorded',p['state']);self.assertEqual('active',self.context()['lifecycle'])
        with self.store.transaction() as db:
            tables=('detection_runs','investigation_versions','c04_requests','c04_results','c05_intents','c05_approvals','c05_attempts','c05_results','recovery_plans','recovery_runs','orchestration_events')
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        closed=self.close(disposition='follow_up_complete');self.assertEqual('demonstrated',closed['payload']['snapshot']['verifications'][0]['value_state'])
        self.assertFalse(closed['payload']['real_recovery_demonstrated']);self.assertEqual(1,self.adapter.effects())
        with self.store.transaction() as db: self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})

    def test_new_cycle_requires_fresh_data_and_cannot_reuse_old_c02_c04_or_approvals(self):
        old=self.complete();self.close()
        with self.assertRaises(Problem): self.open()
        self.fresh();opening=self.open();self.assertEqual(2,opening['payload']['cycle_number']);self.assertEqual('case-1',opening['payload']['previous_case_id'])
        self.assertTrue(opening['payload']['new_evidence_ids']);self.assertEqual(opening,self.open())
        active=self.orch.query('demo','collaboration')['items'];self.assertEqual(['case-2'],[r['case_id'] for r in active])
        self.assertEqual(2,len(self.orch.query('demo','collaboration',lifecycle='all')['items']))
        p=self.latest(self.pump(case='case-2',as_of='2026-01-01T00:04:00Z'));self.assertEqual('awaiting_data',p['state']);self.assertNotIn('c02',p['refs'])
        p=self.latest(self.pump(case='case-2',as_of='2026-01-11T00:04:00Z'));self.assertEqual('awaiting_investigation',p['state'])
        self.assertNotEqual(old['refs']['c02']['id'],p['refs']['c02']['id']);self.assertNotIn('c04',p['refs']);self.assertNotIn('c05',p['refs'])
        doc=fixture('collaboration','declaration','investigation');doc.update(c02_run_id=p['refs']['c02']['id']);doc['hypotheses']=[];doc['requirements']=[]
        self.c03.append('demo','collaboration','fictional-account',p['refs']['c02']['id'],doc,0)
        self.adapter.change(True);recovery_tests.FixtureClock.current=datetime(2026,1,11,0,5,tzinfo=timezone.utc)
        with self.clock(): p=self.latest(self.pump(case='case-2',as_of='2026-01-11T00:04:00Z'))
        self.assertEqual('awaiting_approval',p['state']);self.assertNotEqual(old['refs']['c04']['request_id'],p['refs']['c04']['request_id'])
        self.assertNotEqual(old['refs']['c05']['execution_id'],p['refs']['c05']['execution_id']);self.assertNotIn('approval_hash',p['refs']['c05'])
        self.assertEqual(1,self.adapter.calls)
        with self.clock(): self.pump(case='case-2',as_of='2026-01-11T00:04:00Z')
        self.assertEqual(1,self.adapter.calls)
        self.assertEqual(old['refs'],self.context()['closure']['payload']['snapshot']['refs'])
        # Complete a second independent intervention only after its own explicit approval.
        new_id=p['refs']['c05']['execution_id']
        with self.clock():
            intent=self.engine.get('demo','collaboration','fictional-account',new_id)['intent']
            self.engine.approve('demo','collaboration','fictional-account',new_id,intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter)
            self.pump(case='case-2',as_of='2026-01-11T00:04:00Z')
        plan=fixture('collaboration','plan','c06');plan['execution_id']=new_id
        for check in plan['checks']:
            for window in ('before','after'):
                for edge in ('start','end'): check[window][edge]=(datetime.fromisoformat(check[window][edge].replace('Z','+00:00'))+timedelta(days=10)).isoformat()
        self.orch.recovery.append_plan('demo','collaboration','fictional-account',new_id,plan,0)
        after=fixture('collaboration','after','c06')
        for r in after['records']:
            r['external_id']='cycle-2-'+r['external_id'];r['occurred_at']=(datetime.fromisoformat(r['occurred_at'].replace('Z','+00:00'))+timedelta(days=10)).isoformat()
            if r['period']: r['period']={k:(datetime.fromisoformat(v.replace('Z','+00:00'))+timedelta(days=10)).isoformat() for k,v in r['period'].items()}
        EvidenceRepository(self.store).ingest('demo',after)
        p=self.latest(self.pump(case='case-2',as_of='2026-01-11T00:08:00Z'))
        self.assertEqual('verification_recorded',p['state']);self.assertEqual(2,self.adapter.calls);self.assertEqual(2,self.adapter.effects())
        self.assertEqual('active',self.context(case='case-2')['lifecycle']);self.assertEqual(old['refs'],self.context()['closure']['payload']['snapshot']['refs'])

    def test_prepared_old_grant_is_fenced_below_c05_even_while_its_session_is_valid(self):
        with self.clock():
            self.pump();self.approve_case();execution_id=self.latest()['refs']['c05']['execution_id']
            recovery_tests.FixtureClock.current=datetime(2026,1,1,0,6,tzinfo=timezone.utc)
            self.close(at='2026-01-01T00:06:00+00:00',disposition='cancelled')
            with self.assertRaises(sqlite3.IntegrityError): self.engine.execute('demo','collaboration','fictional-account',execution_id,self.adapter)
        self.assertEqual(0,self.adapter.calls)
        with self.store.transaction() as db: self.assertEqual(0,db.execute('SELECT count(*) FROM c05_attempts').fetchone()[0])

    def test_closed_cycle_cannot_acquire_new_investigation_inference_or_verification(self):
        p=self.complete();self.close();refs=p['refs'];self.fresh()
        doc=fixture('collaboration','declaration','investigation');doc['c02_run_id']=refs['c02']['id'];doc['hypotheses'][0]['statement']='Explicit forbidden late revision.'
        with self.assertRaises(sqlite3.IntegrityError): self.c03.append('demo','collaboration','fictional-account',refs['c02']['id'],doc,1)
        ai=FixtureAdapter()
        with self.assertRaises(sqlite3.IntegrityError): self.repo.propose('demo','collaboration','fictional-account',refs['c02']['id'],1,'arbitrary-new-request',ai)
        self.assertEqual(0,ai.calls)
        with self.assertRaises(sqlite3.IntegrityError): self.orch.recovery.evaluate('demo','collaboration','fictional-account',refs['c05']['execution_id'],1,'2026-01-11T00:04:00Z')
        self.assertEqual(1,self.adapter.calls)
        self.assertEqual(1,len(self.orch.recovery.history('demo','collaboration','fictional-account',refs['c05']['execution_id'])['runs']))

    def test_final_uncertainty_requires_explicit_review_but_cannot_unlock_a_new_cycle(self):
        with self.clock():
            self.pump();self.approve_case();self.adapter.failure='after';self.pump()
        ctx=self.context();self.assertTrue(ctx['context']['unresolved_executions'])
        with self.assertRaises(Problem): self.close(context=ctx,disposition='cancelled')
        ids=[ctx['context']['evidence'][0]['id']]
        review=self.life.review('demo','collaboration','fictional-account','case-1','review-1','Explicit acknowledgement of an uncertain test effect.',ids,ctx['context']['context_hash'],human_confirmed=True,session_token=self.session_token)
        self.assertEqual('unresolved',review['payload']['status']);self.assertFalse(review['payload']['allows_closure']);self.assertFalse(review['payload']['allows_new_cycle'])
        self.assertEqual(review,self.context()['reviews'][0]);self.assertEqual(1,self.adapter.calls)
        with self.assertRaises(Problem): self.close(disposition='cancelled')
        with self.assertRaises(Problem): self.open()
        with self.assertRaises(Problem): self.register(case='bypass')

    def test_unattributed_legacy_uncertainty_of_same_customer_is_not_ignored(self):
        with self.clock():
            self.engine.prepare('demo','collaboration','fictional-account','proposal','legacy-exec',self.adapter)
            intent=self.engine.get('demo','collaboration','fictional-account','legacy-exec')['intent']
            self.engine.approve('demo','collaboration','fictional-account','legacy-exec',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter)
            self.adapter.failure='crash-after'
            with self.assertRaises(KeyboardInterrupt): self.engine.execute('demo','collaboration','fictional-account','legacy-exec',self.adapter)
        self.assertIn('legacy-exec',self.context()['context']['unresolved_executions'])
        with self.assertRaises(Problem): self.close()
        self.assertEqual(1,self.adapter.calls)

    def test_unowned_prepared_grant_is_disclosed_and_invalidated_by_customer_closure(self):
        with self.clock():
            self.engine.prepare('demo','collaboration','fictional-account','proposal','legacy-prepared',self.adapter)
            intent=self.engine.get('demo','collaboration','fictional-account','legacy-prepared')['intent']
            self.engine.approve('demo','collaboration','fictional-account','legacy-prepared',intent['record_hash'],human_confirmed=True,session_token=self.session_token,adapter=self.adapter)
            ctx=self.context();self.assertEqual('legacy-prepared',ctx['context']['other_prepared_intents'][0]['execution_id'])
            self.assertTrue(ctx['context']['other_prepared_intents'][0]['future_dispatch_invalidated_on_close'])
            recovery_tests.FixtureClock.current=datetime(2026,1,1,0,6,tzinfo=timezone.utc)
            self.close(context=ctx,at='2026-01-01T00:06:00+00:00',disposition='cancelled')
            with self.assertRaises(sqlite3.IntegrityError): self.engine.execute('demo','collaboration','fictional-account','legacy-prepared',self.adapter)
        self.assertEqual(0,self.adapter.calls)

    def test_pending_ai_cannot_be_erased_by_closure_or_another_case(self):
        def interrupt(_): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.pump(ai=FixtureAdapter(callback=interrupt))
        ctx=self.context();self.assertTrue(ctx['context']['pending_inferences'])
        with self.assertRaises(Problem): self.close(context=ctx)
        with self.assertRaises(Problem): self.open()

    def test_close_wins_race_and_fences_dispatch_after_observation(self):
        with self.clock():
            self.pump();self.approve_case();execution_id=self.latest()['refs']['c05']['execution_id']
            original=self.adapter.observe;once=False
            def close_after_observe(binding):
                nonlocal once
                snapshot=original(binding)
                if not once:
                    once=True;self.close(at='2026-01-01T00:06:00+00:00',disposition='cancelled')
                return snapshot
            with patch.object(self.adapter,'observe',side_effect=close_after_observe):
                with self.assertRaises(sqlite3.IntegrityError): self.engine.execute('demo','collaboration','fictional-account',execution_id,self.adapter)
        self.assertEqual('closed',self.context()['lifecycle']);self.assertEqual(0,self.adapter.calls)

    def test_dispatch_wins_race_and_pending_effect_blocks_closure_until_receipt(self):
        started=threading.Event();release=threading.Event()
        def wait(_): started.set();self.assertTrue(release.wait(5))
        with self.clock():
            self.pump();self.approve_case();self.adapter.on_apply=wait
            with ThreadPoolExecutor(max_workers=1) as pool:
                task=pool.submit(self.pump);self.assertTrue(started.wait(5))
                try:
                    with self.assertRaises(Problem): self.close(disposition='cancelled')
                finally: release.set()
                task.result(timeout=10)
        self.assertEqual('active',self.context()['lifecycle']);self.close(disposition='not_recovered');self.assertEqual(1,self.adapter.calls)

    def test_concurrent_opening_and_closing_preserve_one_active_and_one_closure(self):
        ctx=self.context()
        with ThreadPoolExecutor(max_workers=2) as pool: closed=list(pool.map(lambda _:self.close(context=ctx),range(2)))
        self.assertEqual(closed[0],closed[1]);self.fresh()
        def candidate(i):
            try: return self.open(case='case-'+str(i),request='open-'+str(i))
            except Problem: return None
        with ThreadPoolExecutor(max_workers=2) as pool: opened=list(pool.map(candidate,(2,3)))
        self.assertEqual(1,sum(o is not None for o in opened));self.assertEqual(1,len(self.orch.query('demo','collaboration')['items']))
        self.assertEqual(2,len(self.orch.query('demo','collaboration',lifecycle='all')['items']))

    def test_stale_snapshot_permissions_confirmation_and_cross_scope_evidence_are_rejected(self):
        ctx=self.context();self.pump()
        with self.assertRaises(Problem): self.close(context=ctx)
        for user in ('leitor','unknown'):
            with self.assertRaises(Problem): self.close(user=user)
        with self.assertRaises(Problem): self.close(token='forged-token-never-valid')
        s=self.context()['context']
        with self.assertRaises(ValueError): self.life.close('demo','collaboration','fictional-account','case-1','close','why','cancelled',s['checkpoint_version'],s['context_hash'],human_confirmed=False,session_token=self.session_token)
        with self.assertRaises(Problem): self.context(tenant='billing',user='atlas')
        with self.assertRaises(Problem): self.context(customer='other-customer')
        with self.store.transaction() as db: db.execute('DELETE FROM sessions WHERE token=?',(self.session_token,))
        with self.assertRaises(Problem): self.close()

    def test_closed_case_worker_is_skipped_and_context_remains_frozen_after_new_evidence(self):
        self.pump();closed=self.close();snapshot=self.context();self.fresh()
        result=self.orch.process_batch('demo','collaboration','2026-01-11T00:04:00Z')
        self.assertEqual(0,result['processed']);self.assertEqual(snapshot,self.context())
        self.assertEqual('case-1',self.register()['case']['case_id']);self.assertEqual(snapshot,self.context())
        with self.assertRaises(Problem): self.pump()
        self.assertEqual(closed,self.context()['closure'])

    def test_reopening_does_not_use_late_old_evidence_or_wrong_predecessor(self):
        self.close()
        body=fixture('collaboration','context','c04');body['records'][0]['external_id']='late-old-evidence';body['records'][0]['occurred_at']='2026-01-02T00:00:00Z'
        EvidenceRepository(self.store).ingest('demo',body)
        with self.assertRaises(Problem): self.open()
        self.fresh()
        with self.assertRaises(Problem): self.open(previous='wrong-case')
        with self.assertRaises(Problem): self.register(case='bypass')
        self.assertEqual(1,len(self.orch.query('demo','collaboration',lifecycle='all')['items']))

    def test_backup_preserves_all_cycles_closure_snapshot_and_active_pointer(self):
        from centerway.ops import backup
        self.close();self.fresh();self.open()
        self.assertEqual('verified',backup(self.path,self.root/'continuity-copy.sqlite3')['status'])
        replica=Continuity(Store.open_existing(self.root/'continuity-copy.sqlite3'))
        self.assertEqual(self.context(),replica.context('demo','collaboration','fictional-account','case-1'))
        self.assertEqual(['case-2'],[r['case_id'] for r in replica.orch.query('demo','collaboration')['items']])

    def test_review_cannot_cite_another_saas_evidence_or_change_scope(self):
        with self.clock(): self.pump();self.approve_case();self.adapter.failure='after';self.pump()
        ctx=self.context()['context']
        with self.store.transaction() as db: other=db.execute("SELECT id FROM evidence_items WHERE tenant='billing' LIMIT 1").fetchone()[0]
        with self.assertRaises(Problem): self.life.review('demo','collaboration','fictional-account','case-1','review','Explicit test review.',[other],ctx['context_hash'],human_confirmed=True,session_token=self.session_token)
        with self.store.transaction() as db: self.assertEqual(0,db.execute('SELECT count(*) FROM continuity_reviews').fetchone()[0])

    def test_schema_guards_and_closure_hash_tampering_fail_closed(self):
        self.close()
        with self.store.transaction() as db: db.execute('DROP TRIGGER continuity_immutable_continuity_closures_UPDATE')
        with self.assertRaises(Problem): self.context()
        with self.store.transaction() as db:
            db.execute("UPDATE continuity_closures SET payload='{}'");db.execute(GUARDS['continuity_immutable_continuity_closures_UPDATE'])
        with self.assertRaises(Problem): self.context()


class UpgradeTests(unittest.TestCase):
    setUpBase=orchestration_tests.OrchestrationTests.setUpBase
    tearDown=orchestration_tests.OrchestrationTests.tearDown
    def setUp(self):
        import test_controlled_execution as e
        from centerway.recovery import install as install_c06
        from centerway.orchestration import TABLES as BASE,GUARDS as BG
        e.ExecutionTests.setUp(self);install_c06(self.store)
        legacy_cases="CREATE TABLE orchestration_cases(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(tenant,customer), UNIQUE(tenant,customer,case_id))"
        parent=self.parents['collaboration'];c03=self.c03.get('demo','collaboration','fictional-account',parent['id'])
        proposal=self.repo.get('demo','collaboration','fictional-account','proposal')
        with self.store.transaction() as db:
            for name,sql in BASE.items(): db.execute(legacy_cases if name=='orchestration_cases' else sql)
            for sql in BG.values(): db.execute(sql)
            db.execute("INSERT INTO orchestration_metadata VALUES ('orchestration-v1','sandbox')")
            case={'id':1,'tenant':'collaboration','customer':'fictional-account','case_id':'legacy-case','actor':'demo','created_at':'2026-01-01T00:00:00+00:00'}
            case['record_hash']=digest(case);db.execute('INSERT INTO orchestration_cases VALUES (?,?,?,?,?,?,?)',tuple(case.values()))
            refs={'c02':{'id':parent['id'],'record_hash':parent['record_hash'],'basis':'fixture'},'c03':{'version':1,'record_hash':c03['record_hash']},
                  'c04':{'request_id':'proposal','record_hash':proposal['result']['record_hash'],'status':'proposal_validated','inference_kind':'test_fixture'}}
            event={'tenant':'collaboration','customer':'fictional-account','case_id':'legacy-case','version':1,'parent_hash':None,
                   'payload':canonical({'state':'awaiting_execution','blockers':['connector_unavailable'],'refs':refs,'basis':{},'operational_state':'inactive','real_recovery_demonstrated':False,'core_transition_authorized':False}),'actor':'demo','created_at':'2026-01-01T00:01:00+00:00'}
            event['record_hash']=digest(event);db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?,?,?,?,?,?)',tuple(event.values()))
    def test_explicit_upgrade_preserves_all_old_rows_and_backfills_provenance(self):
        with self.store.transaction() as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        with self.assertRaises(Problem): Orchestrator(self.store)
        cli=subprocess.run([sys.executable,'-m','centerway.continuity','upgrade','--db',str(self.path)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(0,cli.returncode,cli.stderr);result=json.loads(cli.stdout);self.assertEqual(1,result['cases_preserved'])
        with self.store.transaction() as db:
            self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables});self.assertEqual([],db.execute('PRAGMA foreign_key_check').fetchall())
        view=Continuity(self.store).context('demo','collaboration','fictional-account','legacy-case')
        self.assertTrue(view['opening']['payload']['legacy_upgrade']);self.assertEqual('active',view['lifecycle'])
        with self.assertRaises(ValueError): upgrade(self.store)
    def test_upgrade_rollback_and_mismatched_schema_do_not_repair_or_modify_sources(self):
        with self.store.transaction() as db: sql=db.execute("SELECT sql FROM sqlite_master WHERE name='orchestration_cases'").fetchone()[0]
        with patch('centerway.continuity.install_storage',side_effect=RuntimeError('test-interruption')):
            with self.assertRaises(RuntimeError): upgrade(self.store)
        with self.store.transaction() as db:
            self.assertEqual(sql,db.execute("SELECT sql FROM sqlite_master WHERE name='orchestration_cases'").fetchone()[0]);self.assertEqual(1,db.execute('SELECT count(*) FROM orchestration_events').fetchone()[0])
            db.execute('DROP TRIGGER orchestration_immutable_orchestration_events_UPDATE')
        before=Path(self.store.path).read_bytes()
        with self.assertRaises(ValueError): upgrade(self.store)
        self.assertEqual(before,Path(self.store.path).read_bytes())

    def test_upgrade_refuses_unrecognized_case_index_without_discarding_it(self):
        with self.store.transaction() as db: db.execute('CREATE INDEX unexpected_case_idx ON orchestration_cases(customer)')
        before=Path(self.store.path).read_bytes()
        with self.assertRaises(ValueError): upgrade(self.store)
        self.assertEqual(before,Path(self.store.path).read_bytes())
        with self.store.transaction() as db: self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='unexpected_case_idx'").fetchone())
