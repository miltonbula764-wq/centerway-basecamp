"""Integration tests against real non-owner PostgreSQL login roles; synthetic data only."""
import concurrent.futures
import json
import os
import subprocess
import unittest
import uuid

CONTAINER = os.environ['CW_TEST_CONTAINER']
T = '10000000-0000-0000-0000-000000000001'
OTHER_T = '10000000-0000-0000-0000-000000000002'
C = '20000000-0000-0000-0000-000000000001'
OTHER_C = '20000000-0000-0000-0000-000000000002'
S = '30000000-0000-0000-0000-000000000001'
K = '40000000-0000-0000-0000-000000000001'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def query(sql, user='tenant_a', rollback=True):
    if rollback:
        sql = 'BEGIN; ' + sql + '; ROLLBACK;'
    return subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-qAt',
                           '-v', 'ON_ERROR_STOP=1', '-U', user, '-d', 'postgres'],
                          input=sql, text=True, capture_output=True)


def append(kind, data, ident=None, revision=0, tenant=T, client=C):
    ident = ident or str(uuid.uuid4())
    return ('SELECT centerway.append_version(' + ','.join([
        literal(tenant), literal(client), literal(kind), literal(ident), str(revision),
        "'synthetic test'", literal(json.dumps(data)) + '::jsonb']) + ')')


def contract(**changes):
    data = dict(objective='Synthetic objective', expected_outcome='Synthetic outcome',
                indicator='Synthetic outcome metric', unit='units', measurement_method='documented total',
                direction='higher', baseline=10, minimum_acceptable=15, target=20,
                baseline_start='2024-01-01T00:00:00Z', baseline_end='2024-02-01T00:00:00Z',
                period_start='2024-02-01T00:00:00Z', period_end='2024-03-01T00:00:00Z',
                source_id=S, source_revision=1, baseline_reference='synthetic://baseline')
    return data | changes


def evidence(**changes):
    return dict(contract_id=K, contract_revision=1, source_id=S, source_revision=1,
                evidence_type='outcome', quality='verified', observed_value=15, unit='units',
                measurement_method='documented total', period_start='2024-02-01T00:00:00Z',
                period_end='2024-03-01T00:00:00Z', reference='synthetic://result', content_sha256='a'*64) | changes


def assessment(eid=None, state='valor_demonstrado', **changes):
    return dict(contract_id=K, contract_revision=1, evidence_id=eid,
                evidence_revision=1 if eid else None, state=state,
                rationale='Synthetic explicit assessment') | changes


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sql = f"""
        CREATE ROLE tenant_a LOGIN IN ROLE centerway_api;
        CREATE ROLE tenant_b LOGIN IN ROLE centerway_api;
        CREATE ROLE outsider LOGIN;
        INSERT INTO centerway.companies VALUES ('{T}','Synthetic A'),('{OTHER_T}','Synthetic B');
        INSERT INTO centerway.clients VALUES ('{T}','{C}','Client A'),('{T}','{OTHER_C}','Client A2'),('{OTHER_T}','{C}','Client B');
        INSERT INTO centerway.memberships VALUES ('tenant_a','{T}'),('tenant_b','{OTHER_T}');
        """
        result = query(sql, 'postgres', False)
        assert result.returncode == 0, result.stderr
        source = dict(name='Synthetic source', locator='synthetic://source', method='documented total')
        for tenant, user in [(T, 'tenant_a'), (OTHER_T, 'tenant_b')]:
            result = query(append('source', source, S, tenant=tenant) + ';' +
                           append('contract', contract(), K, tenant=tenant), user, False)
            assert result.returncode == 0, result.stderr

    def ok(self, sql, user='tenant_a'):
        r = query(sql, user)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip().splitlines()

    def fails(self, sql, message, user='tenant_a'):
        r = query(sql, user)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(message, r.stderr)

    def test_states_both_directions_and_boundaries(self):
        for direction, minimum, target, cases in [
            ('higher', 15, 20, [(9,'deterioracao_demonstrada'),(10,'valor_insuficiente'),(14,'valor_insuficiente'),(15,'valor_demonstrado'),(20,'valor_demonstrado')]),
            ('lower', 5, 0, [(11,'deterioracao_demonstrada'),(10,'valor_insuficiente'),(6,'valor_insuficiente'),(5,'valor_demonstrado'),(0,'valor_demonstrado')])]:
            for value, state in cases:
                with self.subTest(direction=direction, value=value):
                    k, e = str(uuid.uuid4()), str(uuid.uuid4())
                    self.ok(append('contract', contract(direction=direction, minimum_acceptable=minimum, target=target), k) + ';' +
                            append('evidence', evidence(contract_id=k, observed_value=value), e) + ';' +
                            append('assessment', assessment(e, state, contract_id=k)))

    def test_missing_partial_disputed_usage_are_inconclusive(self):
        self.ok(append('assessment', assessment(state='resultado_inconclusivo')))
        self.fails(append('assessment', assessment()), 'unsupported_conclusion')
        for patch in [dict(quality='partial'), dict(quality='disputed'), dict(evidence_type='usage'),
                      dict(period_end='2024-02-15T00:00:00Z')]:
            e = str(uuid.uuid4())
            prefix = append('evidence', evidence(**patch), e) + ';'
            self.ok(prefix + append('assessment', assessment(e, 'resultado_inconclusivo')))
            self.fails(prefix + append('assessment', assessment(e)), 'unsupported_conclusion')
        e = str(uuid.uuid4())
        self.fails(append('evidence', evidence(observed_value=9), e) + ';' +
                   append('assessment', assessment(e)), 'unsupported_conclusion')

    def test_strict_input_validation(self):
        for patch in [dict(objective=' '), dict(objective='\t\n'), dict(baseline=None), dict(minimum_acceptable=9),
                      dict(target=14), dict(direction='unknown'), dict(baseline_start='infinity'),
                      dict(period_start='2024-03-01T00:00:00Z'), dict(baseline_end='2024-02-02T00:00:00Z'),
                      dict(baseline='NaN'), dict(baseline=True), dict(objective={'bad': 1}),
                      dict(period_start='2024-02-01'), dict(actor='forged'), dict(extra=1)]:
            with self.subTest(patch=patch):
                r = query(append('contract', contract(**patch)))
                self.assertNotEqual(r.returncode, 0)
        missing = contract()
        del missing['indicator']
        self.fails(append('contract', missing), 'null value')

    def test_evidence_compatibility_and_reference_integrity(self):
        for patch in [dict(unit='different'), dict(measurement_method='different'),
                      dict(period_start='2024-01-31T00:00:00Z'), dict(content_sha256='invalid'),
                      dict(source_revision=2), dict(contract_revision=2)]:
            with self.subTest(patch=patch):
                self.assertNotEqual(query(append('evidence', evidence(**patch))).returncode, 0)
        self.fails(append('evidence', evidence(), client=OTHER_C), 'query returned no rows')
        e, k = str(uuid.uuid4()), str(uuid.uuid4())
        self.fails(append('contract', contract(), k) + ';' + append('evidence', evidence(), e) + ';' +
                   append('assessment', assessment(e, contract_id=k)), 'incompatible_contract')
        self.fails(append('assessment', assessment(str(uuid.uuid4()))), 'query returned no rows')

    def test_tenant_isolation_and_real_permissions(self):
        self.assertEqual(self.ok('SELECT count(*) FROM centerway.contract_versions'), ['1'])
        self.assertEqual(self.ok(f"SELECT count(*) FROM centerway.contract_versions WHERE tenant_id='{OTHER_T}'"), ['0'])
        self.assertEqual(self.ok(f"SET app.tenant_id='{OTHER_T}'; SELECT count(*) FROM centerway.audit_log WHERE tenant_id='{OTHER_T}'"), ['0'])
        self.fails(append('contract', contract(), tenant=OTHER_T), 'not_authorized')
        self.fails('SELECT * FROM centerway.contract_versions', 'permission denied', 'outsider')
        self.fails(append('contract', contract()), 'permission denied', 'outsider')
        for sql in ['UPDATE centerway.contract_versions SET objective=\'x\'',
                    'DELETE FROM centerway.evidence_versions', 'TRUNCATE centerway.source_versions',
                    'INSERT INTO centerway.audit_log DEFAULT VALUES',
                    'INSERT INTO centerway.contract_versions DEFAULT VALUES',
                    f"INSERT INTO centerway.memberships VALUES ('tenant_a','{OTHER_T}')"]:
            self.fails(sql, 'permission denied')
        self.fails('SET ROLE tenant_b', 'permission denied')
        self.ok('CREATE TEMP TABLE pg_attribute (trap text); ' + append('contract', contract()))

    def test_versioning_audit_and_read_port(self):
        e, a = str(uuid.uuid4()), str(uuid.uuid4())
        sql = ';'.join([append('evidence', evidence(), e), append('assessment', assessment(e), a),
                        append('evidence', evidence(observed_value=9), e, 1),
                        append('assessment', assessment(e, 'deterioracao_demonstrada', evidence_revision=2), a, 1),
                        append('contract', contract(target=25), K, 1),
                        f"SELECT centerway.read_contract_context('{T}','{C}','{K}',1)"])
        context = json.loads(self.ok(sql)[-1])
        self.assertEqual(context['contract']['target'], 20)
        self.assertEqual([x['observed_value'] for x in context['evidence_history']], [15, 9])
        self.assertEqual([x['state'] for x in context['assessment_history']], ['valor_demonstrado','deterioracao_demonstrada'])
        self.assertTrue(all(x['actor'] == 'tenant_a' for x in context['evidence_history']))
        self.assertTrue(all(x['validation_policy'] == 'f01-v1' for x in context['assessment_history']))
        audited = json.loads(self.ok(append('evidence', evidence(), e) + ';' +
                            f"SELECT snapshot FROM centerway.audit_log WHERE entity='evidence_versions' AND snapshot->>'id'='{e}'")[-1])
        self.assertEqual(audited['observed_value'], 15)
        self.assertEqual(audited['actor'], 'tenant_a')
        self.assertEqual(audited['revision'], 1)
        self.fails(append('assessment', assessment(state='resultado_inconclusivo', validation_policy='forged')), 'unknown_or_reserved_field')
        self.assertEqual(self.ok(f"SELECT count(*) FROM centerway.audit_log WHERE entity='contract_versions' AND actor='tenant_a'"), ['1'])
        self.assertEqual(self.ok(f"SELECT centerway.read_contract_context('{OTHER_T}','{C}','{K}',1) IS NULL"), ['t'])
        self.fails(append('contract', contract(), K, 0), 'revision_conflict')
        self.fails(append('contract', contract(), K, 3), 'revision_conflict')
        self.fails('UPDATE centerway.contract_versions SET objective=\'changed\'', 'append_only', 'postgres')
        self.fails('DELETE FROM centerway.audit_log', 'append_only', 'postgres')
        self.fails(append('evidence', evidence(), e) + ';' +
                   append('evidence', evidence(period_end='2024-02-20T00:00:00Z'), e, 1), 'correction_changes_measurement')

    def test_sources_future_periods_and_correction_subject(self):
        source = dict(name='Corrected source', locator='synthetic://source-v2', method='documented total')
        self.ok(append('source', source, S, 1) + ';' +
                append('contract', contract(source_revision=2), K, 1))
        future = contract(baseline_start='2099-01-01T00:00:00Z', baseline_end='2099-02-01T00:00:00Z',
                          period_start='2099-02-01T00:00:00Z', period_end='2099-03-01T00:00:00Z')
        self.fails(append('contract', future), 'future_baseline')
        k, e = str(uuid.uuid4()), str(uuid.uuid4())
        future = contract(period_start='2099-02-01T00:00:00Z', period_end='2099-03-01T00:00:00Z')
        self.fails(append('contract', future, k) + ';' +
                   append('evidence', evidence(contract_id=k, period_start=future['period_start'],
                                              period_end=future['period_end'])), 'incompatible_evidence')
        self.ok(append('contract', future, k) + ';' +
                append('assessment', assessment(state='resultado_inconclusivo', contract_id=k)))
        self.fails(append('assessment', assessment(e, evidence_revision=None)), 'query returned no rows')
        self.fails(append('assessment', assessment(state='resultado_inconclusivo', evidence_revision=1)), 'violates check constraint')
        self.fails(append('contract', contract(), k) + ';' + append('evidence', evidence(), e) + ';' +
                   append('evidence', evidence(contract_id=k), e, 1), 'correction_changes_contract')
        self.fails(append('contract', contract(source_id=str(uuid.uuid4()))), 'violates foreign key constraint')

    def test_failure_is_atomic(self):
        before = self.ok('SELECT count(*) FROM centerway.audit_log')[0]
        self.fails(append('contract', contract()) + ';' + append('contract', contract(objective='')), 'violates check constraint')
        self.assertEqual(self.ok('SELECT count(*) FROM centerway.audit_log')[0], before)

    def test_concurrent_revision_has_one_winner(self):
        ident = str(uuid.uuid4())
        sql = append('source', dict(name='Synthetic race', locator='synthetic://race', method='manual'), ident)
        # Commits are confined to this disposable DB; this is the deliberate rollback exception.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: query(sql, rollback=False), range(2)))
        self.assertEqual(sorted(r.returncode == 0 for r in results), [False, True])
        self.assertTrue(any('revision_conflict' in r.stderr for r in results))
        self.assertEqual(self.ok(f"SELECT count(*) FROM centerway.source_versions WHERE id='{ident}'"), ['1'])
        sql = append('source', dict(name='Synthetic correction', locator='synthetic://race', method='manual'), ident, 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: query(sql, rollback=False), range(2)))
        self.assertEqual(sorted(r.returncode == 0 for r in results), [False, True])
        self.assertEqual(self.ok(f"SELECT count(*) FROM centerway.source_versions WHERE id='{ident}'"), ['2'])
