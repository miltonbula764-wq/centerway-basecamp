import concurrent.futures
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from centerway.core import Core, Problem
from centerway.store import Store
from centerway import c02, c04


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'sandbox.sqlite3'
        self.store = Store(self.path)
        self.core = Core(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, tenant='atlas'):
        case_id = self.core.advance('demo', tenant)['case_id']
        for _ in range(3):
            self.core.advance('demo', tenant, case_id)
        return case_id

    def problem(self, status, operation, *args):
        with self.assertRaises(Problem) as caught:
            operation(*args)
        self.assertEqual(status, caught.exception.status)

    def test_atlas_full_cycle_persisted_jobs_survive_restart(self):
        case_id = self.prepare()
        case = self.core.view('demo', 'atlas')['case']
        self.assertEqual('resume_connector', case['decision']['action'])
        self.assertFalse(case['decision']['is_real_ai'])
        self.core.execute('demo', 'atlas', case_id)
        restarted = Core(Store(self.path))
        after = restarted.view('demo', 'atlas')
        self.assertTrue(all(j['status'] == 'delivered' for j in after['environment']['state']['backlog']))
        result = restarted.verify('demo', 'atlas', case_id)
        self.assertTrue(result['operational_recovered'])
        self.assertTrue(result['value_recovered'])
        self.assertEqual(12, result['gained'])
        view = restarted.view('demo', 'atlas')
        self.assertEqual(['C01','C02','C03','C04','C05','C06'], [h['stage'] for h in view['history']])
        self.assertEqual('verified', view['case']['stage'])

    def test_nimbus_operational_is_not_value_and_later_usage_recovers(self):
        case_id = self.prepare('nimbus')
        self.assertEqual('enable_workflow', self.core.view('demo','nimbus')['case']['decision']['action'])
        self.core.execute('demo', 'nimbus', case_id)
        result = self.core.verify('demo', 'nimbus', case_id)
        self.assertTrue(result['operational_recovered'])
        self.assertFalse(result['value_recovered'])
        self.assertEqual(0, result['gained'])
        self.core.simulate_usage('demo', 'nimbus', case_id)
        self.assertTrue(self.core.simulate_usage('demo', 'nimbus', case_id)['reused'])
        result = self.core.verify('demo', 'nimbus', case_id)
        self.assertTrue(result['value_recovered'])
        self.assertEqual(4, result['gained'])
        self.assertEqual(2, len([h for h in self.core.view('demo','nimbus')['history'] if h['stage'] == 'C06']))

    def test_tenant_isolation_same_customer_id_and_foreign_case(self):
        case_id = self.prepare()
        before = self.core.view('demo', 'nimbus')
        self.problem(403, self.core.view, 'atlas', 'nimbus')
        for operation in (self.core.execute,self.core.verify,self.core.advance):
            self.problem(404, operation, 'demo', 'nimbus', case_id)
        self.core.execute('atlas', 'atlas', case_id)
        self.assertEqual(before, self.core.view('demo', 'nimbus'))

    def test_viewer_cannot_write_any_stage_or_usage(self):
        case_id = self.prepare('nimbus')
        self.assertEqual('viewer', self.core.view('leitor','nimbus')['role'])
        for method in (self.core.advance, self.core.execute, self.core.verify, self.core.simulate_usage):
            self.problem(403, method, 'leitor', 'nimbus', case_id)
        self.problem(403, self.core.advance, 'leitor', 'nimbus')
        self.problem(403, self.core.view, 'leitor', 'atlas')

    def test_eight_concurrent_executions_have_exactly_one_effect(self):
        case_id = self.prepare()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.core.execute('demo','atlas',case_id), range(8)))
        self.assertEqual(1, sum(not r['reused'] for r in results))
        self.assertTrue(self.core.execute('demo','atlas',case_id)['reused'])
        view = self.core.view('demo','atlas')
        self.assertEqual(14, view['environment']['state']['completed_outcomes'])
        self.assertEqual(1, len([h for h in view['history'] if h['stage'] == 'C05']))
        self.core.verify('demo','atlas',case_id)
        self.assertTrue(self.core.execute('demo','atlas',case_id)['reused'])

    def test_duplicate_start_reuses_case_and_history(self):
        first = self.core.advance('demo','atlas')
        second = self.core.advance('demo','atlas')
        self.assertEqual(first['case_id'], second['case_id'])
        self.assertTrue(second['reused'])
        self.assertEqual(1,len(self.core.view('demo','atlas')['history']))

    def test_insufficient_persisted_evidence_blocks_intervention(self):
        # Test-only corruption; there is no API to delete evidence.
        with self.store.transaction() as db:
            db.execute('DROP TRIGGER immutable_observations_DELETE')
            db.execute("DELETE FROM observations WHERE tenant='atlas' AND id=(SELECT min(id) FROM observations WHERE tenant='atlas')")
        case_id = self.core.advance('demo','atlas')['case_id']
        self.core.advance('demo','atlas',case_id)
        view = self.core.view('demo','atlas')
        self.assertEqual('insufficient_data',view['case']['stage'])
        self.assertIsNone(view['case']['decision'])
        self.problem(409,self.core.execute,'demo','atlas',case_id)
        self.problem(409,self.core.advance,'demo','atlas',case_id)
        self.assertEqual(0,view['environment']['revision'])

    def test_zero_baseline_and_healthy_signal(self):
        for values, expected in [([0]*14,'insufficient_data'),([10]*14,'healthy')]:
            result = c02.detect({'sufficient':True,'rows':[{'id':i,'value':v} for i,v in enumerate(values)]})
            self.assertEqual(expected,result['status'])

    def test_stale_investigation_blocks_effects(self):
        case_id = self.prepare()
        with self.store.transaction() as db:
            db.execute("UPDATE environments SET revision=revision+1 WHERE tenant='atlas'")
        self.problem(409,self.core.execute,'demo','atlas',case_id)
        self.assertEqual('paused',self.core.view('demo','atlas')['environment']['state']['connector'])

    def test_catalogue_rejection_and_unknown_cause(self):
        self.assertIsNone(c04.decide('atlas', {'cause':'unknown','sha256':'hash','observation_ids':[],'revision':0})['action'])
        case_id = self.prepare()
        with patch.dict(c04.CATALOGUE, {'resume_connector':{**c04.CATALOGUE['resume_connector'],'tenant':'nimbus'}}):
            self.problem(403,self.core.execute,'demo','atlas',case_id)
        self.assertEqual(0,self.core.view('demo','atlas')['environment']['revision'])

    def test_partial_failure_rolls_back_all_effects(self):
        case_id = self.prepare()
        before = self.core.view('demo','atlas')
        with patch.object(self.core,'audit',side_effect=RuntimeError('write failure')):
            with self.assertRaises(RuntimeError):
                self.core.execute('demo','atlas',case_id)
        self.assertEqual(before,self.core.view('demo','atlas'))
        self.assertFalse(self.core.execute('demo','atlas',case_id)['reused'])

    def test_wrong_order_and_premature_usage(self):
        case_id = self.core.advance('demo','nimbus')['case_id']
        for operation in (self.core.execute,self.core.verify,self.core.simulate_usage):
            self.problem(409,operation,'demo','nimbus',case_id)

    def test_append_only_observations_history_executions(self):
        case_id = self.prepare()
        self.core.execute('demo','atlas',case_id)
        for table in ('observations','history','executions'):
            for command in (f'DELETE FROM {table}', f'UPDATE {table} SET tenant=tenant'):
                with self.assertRaises(sqlite3.IntegrityError):
                    with self.store.transaction() as db:
                        db.execute(command)
