import concurrent.futures
import json
import sqlite3
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from centerway.core import Core, Problem
from centerway.store import Store, encode
from centerway.synthetic import populate, sample_rows, EXPECTED_COUNTS


class MultiClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'db.sqlite3'
        self.store = Store(self.path,seed_demo=False)
        self.core = Core(self.store)
        self.core.create_customer('demo','atlas','one','Primeiro')
        self.core.create_customer('demo','atlas','two','Segundo')
        self.core.create_customer('demo','nimbus','one','Outro tenant')

    def tearDown(self):
        self.temp.cleanup()

    def problem(self,status,operation,*args):
        with self.assertRaises(Problem) as caught:
            operation(*args)
        self.assertEqual(status,caught.exception.status)

    def prepare(self,customer='one'):
        self.core.ingest('demo','atlas',customer,sample_rows())
        case_id = self.core.advance('demo','atlas',customer)['case_id']
        for _ in range(3):
            self.core.advance('demo','atlas',customer,case_id)
        return case_id

    def test_same_saas_clients_isolated_and_case_cannot_be_relabelled(self):
        case_id = self.prepare()
        before = self.core.view('demo','atlas','two')
        for operation in (self.core.advance,self.core.execute,self.core.verify,self.core.simulate_usage):
            self.problem(404,operation,'demo','atlas','two',case_id)
        self.problem(404,self.core.view,'demo','atlas','two',case_id)
        self.core.execute('demo','atlas','one',case_id)
        after = self.core.view('demo','atlas','two')
        for key in ('environment','case','cases','history'):
            self.assertEqual(before[key],after[key])
        self.assertFalse(after['history'][0]['detail']['customer']=='one')
        self.assertEqual(0,self.core.view('demo','nimbus','one')['environment']['revision'])

    def test_validation_is_atomic_and_canonical(self):
        valid = sample_rows()
        invalid = [None, [], [True], [dict(valid[0],extra=1)], [dict(valid[0],value=True)],
                   [dict(valid[0],value=-1)], [dict(valid[0],value=1.5)], [dict(valid[0],value=1000001)],
                   [dict(valid[0],day=(date.today()+timedelta(days=1)).isoformat())],
                   [dict(valid[0],day='20261001')], [dict(valid[0],source='')], [valid[0],valid[0]],valid*27]
        for rows in invalid:
            with self.subTest(rows=rows):
                self.problem(400,self.core.ingest,'demo','atlas','one',rows)
        # Conflict on the last day must roll back all earlier inserts in this batch.
        self.core.ingest('demo','atlas','one',[valid[-1]])
        self.problem(409,self.core.ingest,'demo','atlas','one',[*valid[:-1],dict(valid[-1],value=999)])
        with self.store.transaction() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM observations').fetchone()[0])
            self.assertEqual(1,db.execute('SELECT count(*) FROM ingestion_batches').fetchone()[0])

    def test_reordered_retries_and_overlapping_batches_do_not_duplicate_or_invalidate(self):
        rows = sample_rows()
        self.core.ingest('demo','atlas','one',rows)
        case_id = self.core.advance('demo','atlas','one')['case_id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _:self.core.ingest('demo','atlas','one',rows[::-1]),range(6)))
        self.assertTrue(all(r['reused'] for r in results))
        result = self.core.ingest('demo','atlas','one',rows[:3])
        self.assertEqual(0,result['inserted'])
        self.assertEqual('observed',self.core.view('demo','atlas','one')['case']['stage'])
        with self.store.transaction() as db:
            self.assertEqual(14,db.execute('SELECT count(*) FROM observations').fetchone()[0])

    def test_new_observations_invalidate_unexecuted_snapshot_and_new_cycle_keeps_history(self):
        self.core.ingest('demo','atlas','one',sample_rows(days=3))
        first = self.core.advance('demo','atlas','one')['case_id']
        self.core.ingest('demo','atlas','one',sample_rows())
        self.assertEqual('stale_evidence',self.core.view('demo','atlas','one')['case']['stage'])
        self.problem(409,self.core.execute,'demo','atlas','one',first)
        second = self.core.advance('demo','atlas','one')['case_id']
        self.assertNotEqual(first,second)
        for _ in range(3):
            self.core.advance('demo','atlas','one',second)
        self.core.execute('demo','atlas','one',second)
        self.core.verify('demo','atlas','one',second)
        third = self.core.advance('demo','atlas','one')['case_id']
        self.assertNotEqual(second,third)
        self.problem(409,self.core.verify,'demo','atlas','one',second)
        old = self.core.view('demo','atlas','one',second)
        self.assertTrue(old['case']['verification']['value_recovered'])
        self.assertEqual(3,len(old['cases']))
        self.assertEqual('stale_evidence',self.core.view('demo','atlas','one',first)['case']['stage'])
        self.assertTrue(self.core.execute('demo','atlas','one',second)['reused'])

    def test_concurrent_cycles_for_different_clients_and_single_active_per_client(self):
        for customer in ('one','two'):
            self.core.ingest('demo','atlas',customer,sample_rows())
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda c:self.core.advance('demo','atlas',c),['one','two']*4))
        self.assertEqual(2,len({r['case_id'] for r in results}))
        self.assertEqual(2,sum(not r.get('reused',False) for r in results))

    def test_parallel_interventions_are_independent_per_customer(self):
        cases = {customer:self.prepare(customer) for customer in ('one','two')}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda customer:self.core.execute('demo','atlas',customer,cases[customer]),['one','two']*4))
        self.assertEqual(2,sum(not result['reused'] for result in results))
        for customer in ('one','two'):
            result = self.core.verify('demo','atlas',customer,cases[customer])
            self.assertEqual(12,result['gained'])
            view = self.core.view('demo','atlas',customer)
            self.assertEqual(1,len([h for h in view['history'] if h['stage']=='C05']))

    def test_registration_and_ingestion_permissions_and_append_only_batches(self):
        self.problem(403,self.core.create_customer,'leitor','nimbus','new','Nome')
        self.problem(403,self.core.ingest,'leitor','nimbus','one',sample_rows())
        self.problem(403,self.core.ingest,'atlas','nimbus','one',sample_rows())
        self.problem(404,self.core.ingest,'demo','atlas','missing',sample_rows())
        self.problem(409,self.core.create_customer,'demo','atlas','one','Duplicado')
        self.problem(400,self.core.create_customer,'demo','atlas','bad id','Nome')
        self.problem(400,self.core.create_customer,'demo','atlas','new',' ')
        self.core.ingest('demo','atlas','one',sample_rows())
        for command in ('DELETE FROM ingestion_batches','UPDATE ingestion_batches SET inserted=999'):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.store.transaction() as db:
                    db.execute(command)

    def test_mission01_index_migration_preserves_observations_and_audit(self):
        first = self.prepare()
        self.core.execute('demo','atlas','one',first)
        self.core.verify('demo','atlas','one',first)
        before = self.core.view('demo','atlas','one')
        with self.store.transaction() as db:
            db.execute('DROP INDEX one_active_case')
            db.execute('CREATE UNIQUE INDEX one_case_per_customer ON cases(tenant,customer)')
            db.execute('PRAGMA user_version=0')
        migrated = Core(Store(self.path))
        self.assertEqual(before,migrated.view('demo','atlas','one'))
        second = migrated.advance('demo','atlas','one')['case_id']
        self.assertNotEqual(first,second)
        self.assertEqual('verified',migrated.view('demo','atlas','one',first)['case']['stage'])


class ScaleTests(unittest.TestCase):
    def test_150_clients_75_per_saas_mixed_situations_and_persisted_results(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'scale.sqlite3'
            start = time.monotonic()
            store = Store(path,seed_demo=False)
            report = populate(store)
            elapsed = time.monotonic()-start
            core = Core(Store(path))
            view = core.view('demo')
            self.assertEqual(150,len(view['registry']))
            self.assertEqual(EXPECTED_COUNTS,report['counts'])
            for tenant in ('atlas','nimbus'):
                self.assertEqual(75,len(core.view('demo',tenant)['registry']))
            self.assertEqual(75,len(core.view('atlas')['registry']))
            self.assertTrue(all(r['tenant']=='atlas' for r in core.view('atlas')['registry']))
            self.assertEqual(75,len(core.view('leitor')['registry']))
            # Actual persisted effects; distinguish operational-only Nimbus from value recovery.
            atlas = core.view('demo','atlas','client-001')
            self.assertTrue(all(j['status']=='delivered' for j in atlas['environment']['state']['backlog']))
            nimbus = core.view('demo','nimbus','client-009')
            self.assertTrue(nimbus['case']['verification']['operational_recovered'])
            self.assertFalse(nimbus['case']['verification']['value_recovered'])
            self.assertEqual('insufficient_data',core.view('demo','atlas','client-003')['case']['stage'])
            self.assertEqual('needs_review',core.view('demo','atlas','client-004')['case']['stage'])
            with store.transaction() as db:
                self.assertEqual(44,db.execute('SELECT count(*) FROM executions').fetchone()[0])
                self.assertEqual(44,db.execute("SELECT count(*) FROM history WHERE stage='C05'").fetchone()[0])
            with self.assertRaises(Problem):
                populate(store)
            print(f'\n150-client sandbox: {elapsed:.2f}s, counts={report["counts"]}')


class EvidenceQualityTests(unittest.TestCase):
    def test_mixed_sources_and_zero_baseline_stay_exceptions(self):
        with tempfile.TemporaryDirectory() as temp:
            core=Core(Store(Path(temp)/'quality.sqlite3',seed_demo=False))
            for customer in ('mixed','zero'):
                core.create_customer('demo','atlas',customer,customer)
                rows=sample_rows(baseline=0 if customer=='zero' else 10)
                if customer=='mixed':
                    rows[-1]['source']='other-source'
                core.ingest('demo','atlas',customer,rows)
                case_id=core.advance('demo','atlas',customer)['case_id']
                core.advance('demo','atlas',customer,case_id)
                view=core.view('demo','atlas',customer)
                self.assertEqual('insufficient_data',view['case']['stage'])
                self.assertIsNone(view['case']['decision'])
            self.assertEqual(2,core.view('demo')['counts']['exceptions'])
