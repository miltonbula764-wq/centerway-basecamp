"""Technical approvals/AI inputs here are TEST fixtures, not human approval of the delivered demonstration."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from centerway.core import Problem
from centerway.journey import Journey,initialize,markdown,prepare_suite
from centerway.integrations import canonical
from centerway.store import Store


class JourneyTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def create(self,scenario='complete',name=None):
        directory=self.root/(name or scenario);initialize(directory,scenario);lab=Journey(directory)
        lab.login(directory/'credentials.json');lab.ingest(directory/'inputs/initial-evidence.json');lab.advance();return lab
    def prepared(self,scenario='complete'):
        lab=self.create(scenario);lab.investigate(lab.root/'inputs/investigation.json');lab.advance();lab.fixture(True);return lab
    def fixture_approval(self,lab):
        # Unit-test driver assertion ONLY; no physical human or real AI is claimed.
        intent=lab.intent()['intent'];return lab.approve(intent['record_hash'],'APROVO '+intent['record_hash'])

    def test_actual_engines_complete_persisted_effect_and_post_collection_no_real_recovery(self):
        lab=self.prepared();self.assertEqual('awaiting_approval',lab.latest()['state']);self.assertEqual(0,len(lab.service.inspect()['effects']))
        self.fixture_approval(lab);lab.execute();lab.plan();first=lab.verify()
        self.assertEqual('insufficient',first['payload']['assessment']['operational_recovery']['state'])
        lab.collect();result=lab.verify();assessment=result['payload']['assessment']
        for dimension in ('execution','operational_recovery','value_recovery'): self.assertEqual('demonstrated',assessment[dimension]['state'])
        self.assertFalse(assessment['real_recovery_demonstrated']);self.assertIsNone(assessment['value_recovered']);self.assertIsNone(assessment['operational_recovered'])
        report=lab.report();self.assertEqual(1,report['summary']['effects']);self.assertEqual(2,report['summary']['samples']);self.assertFalse(report['summary']['case_closed'])
        self.assertEqual('test_fixture',report['summary']['ai'][0]['inference_kind']);self.assertIn('NOT_AI',markdown(report))
        with lab.store.transaction() as db: token=db.execute('SELECT token FROM sessions').fetchone()[0]
        self.assertNotIn(token,canonical(report));self.assertNotIn(json.loads((lab.root/'credentials.json').read_text())['password'],canonical(report))
        ids={r['id'] for r in report['engines']['evidence']};self.assertTrue(all(ref['evidence_id'] in ids for ref in result['payload']['inputs']['evidence_refs']))
        self.assertEqual(sorted(e['recorded_at'] for e in report['timeline']),[e['recorded_at'] for e in report['timeline']])

    def test_operation_only_and_uncertain_are_independent_computed_results(self):
        for scenario,expected in [('operation_only',('demonstrated','demonstrated','not_demonstrated')),('uncertain',('execution_uncertain','demonstrated','demonstrated'))]:
            with self.subTest(scenario=scenario):
                lab=self.prepared(scenario);self.fixture_approval(lab);lab.execute();lab.plan();lab.collect();run=lab.verify();a=run['payload']['assessment']
                self.assertEqual(expected,tuple(a[k]['state'] for k in ('execution','operational_recovery','value_recovery')))
                self.assertFalse(a['real_recovery_demonstrated']);self.assertEqual(1,len(lab.service.inspect()['effects']))
                lab.execute();self.assertEqual(1,len(lab.service.inspect()['effects']))
                if scenario=='uncertain': self.assertEqual('needs_review',lab.latest()['state'])

    def test_required_blocked_scenarios_do_not_fabricate_documents_or_inference(self):
        for scenario,state in [('insufficient','awaiting_data'),('contradictory','needs_review'),('investigation_pending','awaiting_investigation')]:
            lab=self.create(scenario);r=lab.report();self.assertEqual(state,r['summary']['case_state'])
            self.assertEqual([],r['engines']['c03']);self.assertEqual([],r['engines']['c04']);self.assertEqual([],r['engines']['c05'])
        lab=self.create('ai_unavailable');lab.investigate(lab.root/'inputs/investigation.json')
        with patch('centerway.ai_adapter.build_opener',side_effect=AssertionError('No inference without configured consent')):
            lab.advance();self.assertEqual('awaiting_ai',lab.latest()['state'])
            with self.assertRaises(Problem): lab.advance('/missing-private-config',False)
        self.assertEqual([],lab.report()['engines']['c04'])
        with self.assertRaises(Problem): lab.fixture(False)

    def test_explicit_approval_current_session_hash_conditions_and_no_automatic_dispatch(self):
        lab=self.prepared('approval_pending');intent=lab.intent()['intent'];self.assertEqual(0,len(lab.service.inspect()['effects']))
        with self.assertRaises(Problem): lab.approve(intent['record_hash'],'yes')
        with self.assertRaises(Problem): lab.approve('0'*64,'APROVO '+'0'*64)
        with self.assertRaises(Problem): lab.execute()
        with lab.store.transaction() as db: db.execute('DELETE FROM sessions')
        with self.assertRaises(Problem): self.fixture_approval(lab)
        self.assertEqual(0,len(lab.service.inspect()['effects']))
        lab.login(lab.root/'credentials.json');self.fixture_approval(lab)
        with lab.service.connect() as db: db.execute('UPDATE synthetic_state SET paused=0,revision=revision+1')
        with self.assertRaises(Problem): lab.execute()
        self.assertEqual(0,len(lab.service.inspect()['effects']))

    def test_process_restart_replays_collection_receipt_and_c06_without_duplicate_effects(self):
        lab=self.prepared();self.fixture_approval(lab);lab.execute();lab.plan()
        lab=Journey(lab.root);lab.collect();first=lab.verify();before=lab.report()
        result=subprocess.run([sys.executable,'-m','centerway.journey','--workspace',str(lab.root),'resume'],capture_output=True,text=True,timeout=20)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        after=Journey(lab.root).report();self.assertEqual(1,after['summary']['effects']);self.assertEqual(2,after['summary']['samples'])
        self.assertEqual(len(before['engines']['evidence']),len(after['engines']['evidence']))
        self.assertEqual(len(before['engines']['c06'][0]['runs']),len(after['engines']['c06'][0]['runs']))
        self.assertEqual(first['record_hash'],after['engines']['c06'][0]['runs'][-1]['record_hash'])

    def test_scope_isolation_storage_tamper_no_existing_db_or_private_pilot_override(self):
        lab=self.prepared();body=json.loads((lab.root/'inputs/initial-evidence.json').read_text());body['tenant']='foreign'
        path=self.root/'foreign.json';path.write_text(json.dumps(body))
        with self.assertRaises(Problem):lab.ingest(path)
        binding=lab.intent()['intent']['payload']['binding'];binding['customer']='foreign'
        with self.assertRaises(Problem):lab.service.observe(binding)
        with lab.service.connect() as db:db.execute("INSERT INTO synthetic_state VALUES ('foreign','foreign',1,1,1)")
        self.assertEqual(1,len(lab.service.inspect()['state']))
        with self.assertRaises(ValueError):initialize(lab.root,'complete')
        bare=self.root/'bare';bare.mkdir(mode=0o700);Store(bare/'centerway.sqlite3',seed_demo=False)
        with self.assertRaises(ValueError):Journey(bare)
        with lab.store.transaction() as db:db.execute('DROP TRIGGER journey_immutable_journey_events_UPDATE')
        with self.assertRaises(ValueError):Journey(lab.root)

    def test_lock_reports_read_only_and_exports_are_engine_derived(self):
        lab=self.prepared();before=lab.report()
        with lab.lock():
            proc=subprocess.run([sys.executable,'-m','centerway.journey','--workspace',str(lab.root),'advance'],capture_output=True,text=True)
            self.assertEqual(1,proc.returncode);self.assertIn('409',proc.stdout)
        after=lab.report();self.assertEqual(before['engines'],after['engines'])
        directory=self.root/'report'
        proc=subprocess.run([sys.executable,'-m','centerway.journey','--workspace',str(lab.root),'report','--out-dir',str(directory)],capture_output=True,text=True)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)
        report=json.loads((directory/'engine-output.json').read_text());self.assertEqual(before['engines'],report['engines'])
        self.assertIn('test_fixture_NOT_AI',(directory/'chronology.md').read_text())
        self.assertEqual('awaiting_approval',json.loads((directory/'manifest.json').read_text())['summary']['case_state'])


if __name__=='__main__':unittest.main()
