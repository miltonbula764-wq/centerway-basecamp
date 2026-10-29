"""F02 integration tests; synthetic data and real non-owner database sessions."""
import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
import subprocess
import unittest
import uuid

import test_foundation as f

T = '51000000-0000-0000-0000-000000000001'
B = '51000000-0000-0000-0000-000000000002'
C = '52000000-0000-0000-0000-000000000001'
C2 = '52000000-0000-0000-0000-000000000002'
S = '53000000-0000-0000-0000-000000000001'
USER = 'detector_a'


def append(kind, data, ident=None, revision=0, tenant=T, client=C):
    return f.append(kind, data, ident, revision, tenant, client)


def run(k, revisions=(1,), required=2, cutoff='clock_timestamp()', tenant=T, client=C):
    return (f'SELECT centerway.run_detection({f.literal(tenant)},{f.literal(client)},'
            f'{f.literal(k)},ARRAY{list(revisions)}::integer[],{cutoff},{required})')


def period(index=0, **changes):
    start = datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return f.contract(source_id=S, period_start=start.isoformat(),
                      period_end=(start + timedelta(days=1)).isoformat()) | changes


def evidence(k, revision=1, index=0, value=9, **changes):
    c = period(index)
    return f.evidence(contract_id=k, contract_revision=revision, source_id=S,
                      period_start=c['period_start'], period_end=c['period_end'], observed_value=value) | changes


def series(values=(9,), direction='higher', patches=None):
    k = str(uuid.uuid4())
    statements = []
    evidence_ids = []
    for i, value in enumerate(values):
        change = (patches or {}).get(i, {})
        c = period(i, **change)
        if direction == 'lower':
            c.update(direction='lower', minimum_acceptable=5, target=0)
        statements.append(append('contract', c, k, i))
        eid = str(uuid.uuid4())
        evidence_ids.append(eid)
        if value is not None:
            statements.append(append('evidence', evidence(k, i+1, i, value), eid))
    return k, evidence_ids, ';'.join(statements)


class DetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provision = f"""
        CREATE ROLE detector_a LOGIN IN ROLE centerway_api;
        CREATE ROLE detector_b LOGIN IN ROLE centerway_api;
        CREATE ROLE detector_outsider LOGIN;
        INSERT INTO centerway.companies VALUES ('{T}','Synthetic detection A'),('{B}','Synthetic detection B');
        INSERT INTO centerway.clients VALUES ('{T}','{C}','A1'),('{T}','{C2}','A2'),('{B}','{C}','B1');
        INSERT INTO centerway.memberships VALUES ('detector_a','{T}'),('detector_b','{B}');
        """
        result = f.query(provision, 'postgres', False)
        assert result.returncode == 0, result.stderr
        result = f.query(append('source', dict(name='Synthetic source', locator='synthetic://f02', method='documented total'), S), USER, False)
        assert result.returncode == 0, result.stderr

    def ok(self, sql, user=USER, rollback=True):
        result = f.query(sql, user, rollback)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()

    def fails(self, sql, message, user=USER):
        result = f.query(sql, user)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def detect(self, sql):
        return json.loads(self.ok(sql)[-1])

    def test_automatic_states_in_both_directions(self):
        for direction, cases in [
            ('higher', [(9,'deterioracao_demonstrada'),(10,'valor_insuficiente'),(14,'valor_insuficiente'),(15,'valor_demonstrado')]),
            ('lower', [(11,'deterioracao_demonstrada'),(10,'valor_insuficiente'),(6,'valor_insuficiente'),(5,'valor_demonstrado')])]:
            for value, expected in cases:
                with self.subTest(direction=direction, value=value):
                    k, _, setup = series((value,), direction)
                    result = self.detect(setup + ';' + run(k))
                    self.assertEqual(result['state'], expected)
                    self.assertEqual(result['result']['periods'][0]['observed_value'], value)
                    self.assertIsNone(result['result']['sustained_deterioration'])
                    self.assertEqual(result['result']['independent_verification'], 'not_established')
                    self.assertEqual(result['result']['causal_inference'], 'not_performed')

    def test_missing_usage_partial_disputed_and_incomplete_windows(self):
        for patch, code in [
            (None, 'missing_evidence'),
            ({'evidence_type':'usage'}, 'no_outcome_evidence'),
            ({'quality':'partial'}, 'partial_quality'),
            ({'quality':'disputed'}, 'disputed_quality'),
            ({'period_end':'2024-02-01T12:00:00Z'}, 'no_complete_window')]:
            with self.subTest(patch=patch):
                k, _, setup = series((None,))
                if patch is not None:
                    setup += ';' + append('evidence', evidence(k, **patch))
                result = self.detect(setup + ';' + run(k))['result']
                self.assertEqual(result['state'], 'resultado_inconclusivo')
                self.assertIsNone(result['periods'][0]['observed_value'])
                self.assertIn(code, result['periods'][0]['reason_codes'])

    def test_contradictory_reports_are_not_resolved_by_vote_or_order(self):
        for values in [(9,15), (9,9,15), (9,8)]:
            k, _, setup = series((None,))
            setup += ';' + ';'.join(append('evidence', evidence(k, value=v)) for v in values)
            result = self.detect(setup + ';' + run(k))['result']
            self.assertEqual(result['state'], 'resultado_inconclusivo')
            self.assertIn('contradictory_results', result['periods'][0]['reason_codes'])
            self.assertEqual(len(result['periods'][0]['considered_evidence_refs']), len(values))
            self.assertIsNone(result['periods'][0]['observed_value'])

    def test_agreement_is_not_independent_verification_and_usage_cannot_veto(self):
        k, _, setup = series((9,))
        setup += ';' + append('evidence', evidence(k, value=9))
        setup += ';' + append('evidence', evidence(k, value=500, evidence_type='usage', quality='disputed'))
        result = self.detect(setup + ';' + run(k))['result']
        self.assertEqual(result['state'], 'deterioracao_demonstrada')
        self.assertEqual(result['independent_verification'], 'not_established')
        self.assertEqual(len(result['periods'][0]['considered_evidence_refs']), 2)
        self.assertEqual(result['periods'][0]['excluded_evidence_refs'][0]['reason'], 'usage_is_not_outcome')

    def test_uncertain_outcome_blocks_even_with_verified_full_result(self):
        k, _, setup = series((9,))
        setup += ';' + append('evidence', evidence(k, quality='disputed', period_end='2024-02-01T12:00:00Z'))
        result = self.detect(setup + ';' + run(k))['result']
        self.assertEqual(result['state'], 'resultado_inconclusivo')
        self.assertIn('disputed_quality', result['periods'][0]['reason_codes'])

    def test_sustained_deterioration_and_signed_comparisons(self):
        for direction, values, expected_trend in [
            ('higher',(9,8,7),'worsening'), ('lower',(11,12,13),'worsening'),
            ('higher',(7,8,9),'improving'), ('higher',(9,9,9),'unchanged')]:
            with self.subTest(direction=direction, values=values):
                k, _, setup = series(values, direction)
                result = self.detect(setup + ';' + run(k, (3,1,2), 3))['result']
                self.assertTrue(result['sustained_deterioration'])
                self.assertEqual(result['sustained_reason'], 'sustained_baseline_deterioration')
                self.assertEqual([p['contract_revision'] for p in result['periods']], [1,2,3])
                self.assertEqual(result['periods'][-1]['comparison']['status'], expected_trend)
                self.assertEqual(result['periods'][-1]['comparison']['delta'], values[-1]-values[-2])

    def test_worsening_above_baseline_is_not_sustained_baseline_deterioration(self):
        k, _, setup = series((20,18,16))
        result = self.detect(setup + ';' + run(k, (1,2,3), 3))['result']
        self.assertEqual(result['state'], 'valor_demonstrado')
        self.assertEqual(result['periods'][-1]['comparison']['status'], 'worsening')
        self.assertFalse(result['sustained_deterioration'])

    def test_missing_period_breaks_streak_without_skipping_it(self):
        k, _, setup = series((9,None,8))
        result = self.detect(setup + ';' + run(k, (1,2,3), 3))['result']
        self.assertEqual(result['state'], 'deterioracao_demonstrada')
        self.assertIsNone(result['sustained_deterioration'])
        self.assertEqual(result['sustained_reason'], 'inconclusive_period')
        self.assertEqual(result['periods'][-1]['comparison']['status'], 'inconclusive')

    def test_only_trailing_required_periods_determine_sustained_status(self):
        k, _, setup = series((None,9,8))
        result = self.detect(setup + ';' + run(k, (1,2,3), 2))['result']
        self.assertTrue(result['sustained_deterioration'])
        result = self.detect(setup + ';' + run(k, (1,2,3), 4))['result']
        self.assertIsNone(result['sustained_deterioration'])
        self.assertEqual(result['sustained_reason'], 'insufficient_periods')

    def test_gaps_overlaps_durations_and_changed_contracts_block_comparison(self):
        scenarios = [
            ({'period_start':'2024-02-03T00:00:00Z','period_end':'2024-02-04T00:00:00Z'}, 'non_contiguous_periods'),
            ({'period_start':'2024-02-01T12:00:00Z','period_end':'2024-02-02T12:00:00Z'}, 'non_contiguous_periods'),
            ({'period_end':'2024-02-04T00:00:00Z'}, 'unequal_duration'),
            ({'minimum_acceptable':16}, 'incompatible_contracts'),
            ({'objective':'Changed business objective'}, 'incompatible_contracts'),
            ({'source_revision':2}, 'incompatible_contracts'),
        ]
        for patch, reason in scenarios:
            with self.subTest(patch=patch):
                k, _, setup = series((9,))
                if 'source_revision' in patch:
                    setup += ';' + append('source', dict(name='New source', locator='synthetic://new', method='manual'), S, 1)
                setup += ';' + append('contract', period(1, **patch), k, 1)
                ep = {key:val for key,val in patch.items() if key in ('period_start','period_end','source_revision')}
                setup += ';' + append('evidence', evidence(k, 2, 1, 8, **ep))
                result = self.detect(setup + ';' + run(k, (1,2)))['result']
                self.assertIsNone(result['sustained_deterioration'])
                self.assertEqual(result['periods'][-1]['comparison']['reason'], reason)
                self.assertIsNone(result['periods'][-1]['comparison']['delta'])

    def test_latest_correction_selected_and_historical_cutoff_preserved(self):
        k, ids, setup = series((9,))
        setup += ";SELECT set_config('test.cutoff',clock_timestamp()::text,true)"
        call = run(k, cutoff="current_setting('test.cutoff')::timestamptz")
        setup += ';' + call
        setup += ';' + append('evidence', evidence(k, value=15), ids[0], 1)
        rows = self.ok(setup + ';' + call + ';' + run(k))
        first, historical, current = (json.loads(rows[i]) for i in (-4,-2,-1))
        self.assertEqual(first['id'], historical['id'])
        self.assertEqual(historical['state'], 'deterioracao_demonstrada')
        self.assertEqual(current['state'], 'valor_demonstrado')
        self.assertEqual(current['input_snapshot'][0]['evidence'][0]['revision'], 2)
        self.assertEqual(len(current['input_snapshot'][0]['evidence']), 1)

    def test_not_closed_and_cutoff_before_contract(self):
        k = str(uuid.uuid4())
        setup = append('contract', period(period_start='2099-01-01T00:00:00Z', period_end='2099-01-02T00:00:00Z'), k)
        result = self.detect(setup + ';' + run(k))['result']
        self.assertIn('period_not_closed', result['periods'][0]['reason_codes'])
        self.assertEqual(result['state'], 'resultado_inconclusivo')
        self.fails(setup + ';' + run(k, cutoff="'2024-01-01Z'::timestamptz"), 'contract_not_available_at_cutoff')

    def test_idempotency_canonical_order_timezone_and_audit(self):
        k, _, setup = series((9,8))
        setup += ";SELECT set_config('test.cutoff',clock_timestamp()::text,true)"
        cutoff = "current_setting('test.cutoff')::timestamptz"
        rows = self.ok(setup + ';' + run(k,(1,2),cutoff=cutoff) +
                       "; SET timezone='Pacific/Honolulu';" + run(k,(2,1),cutoff=cutoff) +
                       f";SELECT count(*) FROM centerway.audit_log WHERE entity='detection_runs' AND snapshot->>'contract_id'='{k}'")
        self.assertEqual(json.loads(rows[-3])['id'], json.loads(rows[-2])['id'])
        self.assertEqual(rows[-1], '1')
        self.assertEqual(json.loads(rows[-2])['actor'], USER)

    def test_exact_investigation_snapshot_and_unchanged_f01_assessments(self):
        k, ids, setup = series((9,))
        setup += ';' + run(k)
        setup += f";SELECT centerway.read_detection_context('{T}','{C}',(SELECT id FROM centerway.detection_runs WHERE contract_id='{k}'))"
        setup += ';' + append('evidence', evidence(k,value=15),ids[0],1)
        setup += f";SELECT centerway.read_detection_context('{T}','{C}',(SELECT id FROM centerway.detection_runs WHERE contract_id='{k}'))"
        setup += f";SELECT count(*) FROM centerway.assessment_versions WHERE contract_id='{k}'"
        rows = self.ok(setup)
        before, after = json.loads(rows[-4]), json.loads(rows[-2])
        self.assertEqual(before, after)
        self.assertEqual(before['input_snapshot'][0]['evidence'][0]['observed_value'], 9)
        self.assertEqual(rows[-1], '0')

    def test_authorization_immutability_and_private_evaluator(self):
        k, _, setup = series((9,))
        self.fails(run(k,tenant=B), 'not_authorized')
        self.fails(run(k), 'permission denied', 'detector_outsider')
        self.fails(setup + ';' + run(k,client=C2), 'contract_not_available_at_cutoff')
        self.fails("SELECT centerway._evaluate_detection('[]',clock_timestamp(),2)", 'permission denied')
        for stmt in ['INSERT INTO centerway.detection_runs DEFAULT VALUES',
                     'UPDATE centerway.detection_runs SET state=\'valor_demonstrado\'',
                     'DELETE FROM centerway.detection_runs','TRUNCATE centerway.detection_runs']:
            self.fails(stmt, 'permission denied')
        self.fails('DELETE FROM centerway.detection_runs', 'append_only', 'postgres')
        rows = self.ok(f"SET app.tenant_id='{B}'; SELECT count(*) FROM centerway.detection_runs WHERE tenant_id='{B}'")
        self.assertEqual(rows, ['0'])
        self.ok('CREATE TEMP TABLE contract_versions(trap text); CREATE TEMP TABLE evidence_versions(trap text);' + setup + ';' + run(k))

    def test_invalid_configuration_and_duplicate_windows(self):
        k, _, setup = series((9,))
        for call in [run(k,()), run(k,(1,1)), run(k,(0,)), run(k,(1,),1), run(k,(1,),121),
                     run(k,cutoff="'infinity'::timestamptz"), run(k,cutoff="'2099-01-01Z'::timestamptz"),
                     run(k).replace('ARRAY[1]::integer[]','NULL'),
                     run(k).replace('ARRAY[1]::integer[]','ARRAY[NULL]::integer[]'),
                     run(k).replace('ARRAY[1]::integer[]','ARRAY[[1,2],[3,4]]::integer[]')]:
            self.assertNotEqual(f.query(setup+';'+call,USER).returncode, 0)
        self.fails(setup + ';' + append('contract',period(),k,1) + ';' + run(k,(1,2)), 'multiple_versions_for_same_period')
        self.fails(setup + ';' + run(k,(2,)), 'contract_not_available_at_cutoff')

    def test_concurrent_identical_requests_reuse_one_audited_run(self):
        k, _, setup = series((9,8))
        self.ok(setup,rollback=False)
        cutoff = self.ok('SELECT clock_timestamp()::text')[-1]
        call = run(k,(1,2),cutoff=f.literal(cutoff)+'::timestamptz')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: f.query(call,USER,False),range(2)))
        for result in results:
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(results[0].stdout)['id'],json.loads(results[1].stdout)['id'])
        self.assertEqual(self.ok(f"SELECT count(*) FROM centerway.audit_log WHERE entity='detection_runs' AND snapshot->>'contract_id'='{k}'"), ['1'])
        self.assertEqual(self.ok(f"SELECT count(*) FROM centerway.detection_runs WHERE contract_id='{k}'",'detector_b'), ['0'])
        run_id = json.loads(results[0].stdout)['id']
        self.assertEqual(self.ok(f"SELECT centerway.read_detection_context('{T}','{C}','{run_id}') IS NULL",'detector_b'), ['t'])

    def test_late_commit_creates_revision_without_mutating_previous_snapshot(self):
        k, ids, setup = series((9,))
        self.ok(setup,rollback=False)
        worker = subprocess.Popen(['docker','exec','-i',f.CONTAINER,'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
                                   '-U',USER,'-d','postgres'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,text=True)
        try:
            worker.stdin.write('BEGIN;'+append('evidence',evidence(k,value=15),ids[0],1)+';\n')
            worker.stdin.flush()
            self.assertEqual(json.loads(worker.stdout.readline())['revision'],2)
            cutoff = self.ok('SELECT clock_timestamp()::text')[-1]
            call = run(k,cutoff=f.literal(cutoff)+'::timestamptz')
            old = json.loads(self.ok(call,rollback=False)[-1])
            worker.stdin.write('COMMIT;\n')
            worker.stdin.flush()
            _, stderr = worker.communicate(timeout=15)
            self.assertEqual(worker.returncode,0,stderr)
            new = json.loads(self.ok(call,rollback=False)[-1])
            self.assertEqual(new['revision'],2)
            self.assertEqual(new['revision_of'],old['id'])
            self.assertNotEqual(new['input_hash'],old['input_hash'])
            self.assertEqual(old['state'],'deterioracao_demonstrada')
            self.assertEqual(new['state'],'valor_demonstrado')
            persisted = self.detect(f"SELECT centerway.read_detection_context('{T}','{C}','{old['id']}')")
            self.assertEqual(old,persisted)
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.communicate()
