"""F03 integration: actual author/reviewer sessions; commits only in disposable PostgreSQL."""
import concurrent.futures
import json
import subprocess
import unittest
import uuid

import test_foundation as f

T = '61000000-0000-0000-0000-000000000001'
B = '61000000-0000-0000-0000-000000000002'
C = '62000000-0000-0000-0000-000000000001'
C2 = '62000000-0000-0000-0000-000000000002'
S = '63000000-0000-0000-0000-000000000001'
AUTHOR = 'investigator_a'
REVIEWER = 'investigator_reviewer'


def append(inv, kind, data, ident=None, revision=0, tenant=T, client=C):
    return 'SELECT centerway.append_investigation_record(' + ','.join([
        f.literal(tenant), f.literal(client), f.literal(inv), f.literal(kind),
        f.literal(ident or str(uuid.uuid4())), str(revision), "'synthetic F03 test'",
        f.literal(json.dumps(data))+'::jsonb']) + ')'


def factor(**patch):
    return dict(scope='internal', category='operating process',
                hypothesis='A missing prerequisite may impede the declared outcome',
                requirement='The agreed prerequisite must be available for the objective',
                condition='The agreed prerequisite is available', test_protocol='Inspect the recorded prerequisite',
                assessment_at='2024-02-15T12:00:00Z', control='saas', responsible_party='Synthetic operations team') | patch


def evidence(fid, purpose='condition_met', assertion=False, **patch):
    return dict(factor_id=fid, factor_revision=1, purpose=purpose, kind='document', assertion=assertion,
                source_id=S, source_revision=1, reference='synthetic://observation', content_sha256='a'*64,
                collected_at='2024-02-15T12:00:00Z') | patch


def verification(eid, assertion=False, **patch):
    return dict(evidence_id=eid, evidence_revision=1, verdict='confirmed', checked_assertion=assertion,
                method='Reproduce the explicit check using the cited record', explanation='Synthetic verification record',
                source_id=S, source_revision=1, reference='synthetic://review', content_sha256='b'*64,
                checked_at='2024-02-16T12:00:00Z') | patch


def run(inv, cutoff='clock_timestamp()', tenant=T, client=C):
    return f'SELECT centerway.run_investigation({f.literal(tenant)},{f.literal(client)},{f.literal(inv)},{cutoff})'


def read(inv, rid, tenant=T, client=C):
    return f'SELECT centerway.read_investigation_context({f.literal(tenant)},{f.literal(client)},{f.literal(inv)},{f.literal(rid)})'


class InvestigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sql = f"""
        CREATE ROLE investigator_a LOGIN IN ROLE centerway_api;
        CREATE ROLE investigator_reviewer LOGIN IN ROLE centerway_api;
        CREATE ROLE investigator_reviewer2 LOGIN IN ROLE centerway_api;
        CREATE ROLE investigator_b LOGIN IN ROLE centerway_api;
        CREATE ROLE investigator_outsider LOGIN;
        INSERT INTO centerway.companies VALUES ('{T}','Synthetic F03 A'),('{B}','Synthetic F03 B');
        INSERT INTO centerway.clients VALUES ('{T}','{C}','A1'),('{T}','{C2}','A2'),('{B}','{C}','B1');
        INSERT INTO centerway.memberships VALUES
          ('investigator_a','{T}'),('investigator_reviewer','{T}'),('investigator_reviewer2','{T}'),('investigator_b','{B}');
        """
        r = f.query(sql, 'postgres', False)
        assert r.returncode == 0, r.stderr
        r = f.query(f.append('source', dict(name='Synthetic investigation source', locator='synthetic://f03',
                    method='Recorded observation'), S, tenant=T, client=C), AUTHOR, False)
        assert r.returncode == 0, r.stderr

    def sql(self, sql, user=AUTHOR, commit=True):
        # Separate real sessions need committed fixtures for reviewer visibility.
        r = f.query('BEGIN;'+sql+';COMMIT;' if commit else sql, user, rollback=not commit)
        self.assertEqual(r.returncode,0,r.stderr)
        return r.stdout.strip().splitlines()

    def obj(self, sql, user=AUTHOR):
        return json.loads(self.sql(sql,user)[-1])

    def fails(self, sql, message, user=AUTHOR):
        r = f.query(sql,user)
        self.assertNotEqual(r.returncode,0,r.stdout)
        self.assertIn(message,r.stderr)

    def investigation(self, value=9, usage=False):
        k, inv = str(uuid.uuid4()), str(uuid.uuid4())
        sql = f.append('contract', f.contract(source_id=S), k, tenant=T, client=C)
        if value is not None:
            sql += ';'+f.append('evidence', f.evidence(contract_id=k, source_id=S, observed_value=value,
                                evidence_type='usage' if usage else 'outcome'), tenant=T, client=C)
        sql += f";SELECT centerway.run_detection('{T}','{C}','{k}',ARRAY[1],clock_timestamp(),2)"
        detection = self.obj(sql)
        self.obj(f"SELECT centerway.open_investigation('{T}','{C}','{inv}','{detection['id']}',1,'Synthetic investigation question')")
        return inv,detection

    def supported(self, inv, factor_patch=None, condition=False, requirement=True):
        fid = self.obj(append(inv,'factor',factor(**(factor_patch or {}))))['id']
        ids, reviews = [], []
        for purpose, value in [('requirement_applies',requirement),('condition_met',condition)]:
            eid = self.obj(append(inv,'evidence',evidence(fid,purpose,value)))['id']
            rid = self.obj(append(inv,'verification',verification(eid,value)),REVIEWER)['id']
            ids.append(eid); reviews.append(rid)
        return fid,ids,reviews

    def test_demonstrated_impediment_has_facts_refs_and_no_causal_promotion(self):
        inv,detection = self.investigation()
        fid,ids,reviews = self.supported(inv)
        report = self.obj(run(inv))
        result = report['result']
        self.assertEqual(result['status'],'impedimento_demonstrado')
        self.assertEqual(len(result['observed_facts']),2)
        self.assertEqual(len(result['hypotheses']),1)
        self.assertEqual(result['hypotheses'][0]['causal_status'],'not_established')
        self.assertNotIn('statement',result['observed_facts'][0])
        self.assertEqual(result['contradictions'],[])
        self.assertEqual(result['missing_information'],[])
        self.assertEqual(len(result['intervention_candidates']),1)
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['independent_verification'],'not_established')
        self.assertEqual(result['causal_inference'],'not_performed')
        self.assertEqual(result['intervention_candidates'][0]['factor_id'],fid)
        self.assertEqual(len(result['intervention_candidates'][0]['supporting_facts']),2)
        self.assertEqual(report['input_snapshot']['detection'],detection)
        fact = next(x for x in result['observed_facts'] if x['predicate']=='condition_met')
        self.assertEqual(fact['evidence_refs'],[dict(id=ids[1],revision=1)])
        self.assertEqual(fact['verification_refs'],[dict(id=reviews[1],revision=1)])

    def test_hypothesis_without_evidence_is_not_a_fact(self):
        inv,_ = self.investigation()
        self.obj(append(inv,'factor',factor(hypothesis='Unproven causal speculation')))
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'inconclusivo')
        self.assertEqual(result['observed_facts'],[])
        self.assertEqual(result['intervention_candidates'],[])
        self.assertEqual(result['hypotheses'][0]['statement'],'Unproven causal speculation')
        self.assertEqual({x['reason'] for x in result['missing_information']},{'evidence_missing'})

    def test_external_nontechnical_factors_are_supported(self):
        inv,_ = self.investigation()
        self.supported(inv,dict(scope='external',category='client procurement',control='client',
                               responsible_party='Synthetic purchasing team',requirement='Approved purchasing budget is required',
                               condition='Approved purchasing budget is available',
                               hypothesis='A budget constraint may impede the agreed outcome'))
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'impedimento_demonstrado')
        self.assertEqual(result['intervention_candidates'][0]['scope'],'external')
        self.assertEqual(result['intervention_candidates'][0]['control'],'client')

    def test_verified_declaration_without_review_is_insufficient_and_self_review_fails(self):
        inv,_ = self.investigation()
        fid = self.obj(append(inv,'factor',factor()))['id']
        eid = self.obj(append(inv,'evidence',evidence(fid)))['id']
        self.fails(append(inv,'verification',verification(eid)),'self_verification_forbidden')
        self.fails(append(inv,'evidence',evidence(fid,verified=True)),'unknown_or_reserved_field')
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'inconclusivo')
        self.assertEqual(result['observed_facts'],[])
        self.assertIn('verification_missing',[x['reason'] for x in result['missing_information']])

    def test_contradictory_evidence_is_not_resolved_by_majority(self):
        inv,_ = self.investigation()
        fid,_,_ = self.supported(inv)
        for assertion in (True,False):
            eid = self.obj(append(inv,'evidence',evidence(fid,assertion=assertion)))['id']
            self.obj(append(inv,'verification',verification(eid,assertion)),REVIEWER)
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'inconclusivo')
        self.assertIn('conflicting_assertions',[x['reason'] for x in result['contradictions']])
        self.assertEqual([x['predicate'] for x in result['observed_facts']],['requirement_applies'])
        self.assertEqual(result['intervention_candidates'],[])

    def test_disagreement_between_reviewers_and_unverifiable_checks(self):
        for verdict in ('rejected','unverifiable'):
            with self.subTest(verdict=verdict):
                inv,_ = self.investigation()
                _,ids,_ = self.supported(inv)
                checked = True if verdict=='rejected' else None
                self.obj(append(inv,'verification',verification(ids[1],verdict=verdict,checked_assertion=checked)),
                         'investigator_reviewer2')
                result = self.obj(run(inv))['result']
                self.assertEqual(result['status'],'inconclusivo')
                if verdict=='rejected':
                    self.assertIn('verification_rejected',[x['reason'] for x in result['contradictions']])
                else:
                    self.assertIn('verification_unverifiable',[x['reason'] for x in result['missing_information']])

    def test_empty_investigation_and_unreliable_detection_stay_inconclusive(self):
        inv,_ = self.investigation()
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'inconclusivo')
        self.assertEqual(result['missing_information'],[{'reason':'no_factors_submitted'}])
        for value,usage in [(None,False),(9,True),(20,False)]:
            inv,_ = self.investigation(value,usage)
            self.supported(inv)
            result = self.obj(run(inv))['result']
            self.assertEqual(result['status'],'inconclusivo')
            self.assertEqual(result['intervention_candidates'],[])
            self.assertIn('no_supported_deterioration_in_selected_period',[x['reason'] for x in result['missing_information']])

    def test_usage_evidence_cannot_demonstrate_impediment(self):
        inv,_ = self.investigation()
        fid = self.obj(append(inv,'factor',factor()))['id']
        for purpose, assertion in [('requirement_applies',True),('condition_met',False)]:
            eid = self.obj(append(inv,'evidence',evidence(fid,purpose,assertion,kind='usage_context')))['id']
            self.obj(append(inv,'verification',verification(eid,assertion)),REVIEWER)
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'inconclusivo')
        self.assertEqual(result['observed_facts'],[])
        self.assertEqual(len(result['excluded_evidence']),2)

    def test_condition_satisfied_or_requirement_inapplicable_is_not_impediment(self):
        for condition,requirement in [(True,True),(False,False)]:
            inv,_ = self.investigation()
            self.supported(inv,condition=condition,requirement=requirement)
            result = self.obj(run(inv))['result']
            self.assertEqual(result['status'],'nenhum_impedimento_demonstrado')
            self.assertEqual(result['intervention_candidates'],[])

    def test_unknown_control_and_unresolved_other_factor_block_handoff(self):
        inv,_ = self.investigation()
        self.supported(inv,dict(control='unknown',responsible_party=None))
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'impedimento_demonstrado')
        self.assertEqual(result['intervention_candidates'],[])
        inv,_ = self.investigation()
        self.supported(inv)
        self.obj(append(inv,'factor',factor(hypothesis='Another unresolved factor')))
        result = self.obj(run(inv))['result']
        self.assertEqual(result['status'],'inconclusivo')
        self.assertTrue(any(x['status']=='impedimento_demonstrado' for x in result['factor_conclusions']))
        self.assertEqual(result['intervention_candidates'],[])

    def test_corrected_evidence_needs_new_verification_and_history_is_frozen(self):
        inv,_ = self.investigation()
        fid,ids,_ = self.supported(inv)
        old = self.obj(run(inv))
        cutoff = old['as_of']
        self.obj(append(inv,'evidence',evidence(fid,assertion=True),ids[1],1))
        intermediate = self.obj(run(inv))['result']
        self.assertEqual(intermediate['status'],'inconclusivo')
        self.assertIn('verification_missing',[x['reason'] for x in intermediate['missing_information']])
        self.obj(append(inv,'verification',verification(ids[1],True,evidence_revision=2)),REVIEWER)
        new = self.obj(run(inv))
        self.assertEqual(new['result']['status'],'nenhum_impedimento_demonstrado')
        self.assertEqual(self.obj(read(inv,old['id'])),old)
        self.assertEqual(self.obj(run(inv,f.literal(cutoff)+'::timestamptz'))['id'],old['id'])

    def test_factor_revision_does_not_reuse_old_proposition_evidence(self):
        inv,_ = self.investigation()
        fid,_,_ = self.supported(inv)
        self.obj(append(inv,'factor',factor(condition='A different explicit condition'),fid,1))
        result = self.obj(run(inv))
        self.assertEqual(result['result']['status'],'inconclusivo')
        self.assertEqual(result['input_snapshot']['factors'][0]['factor']['revision'],2)
        self.assertEqual(result['input_snapshot']['factors'][0]['evidence'],[])

    def test_verification_corrections_cannot_change_reviewer_or_subject(self):
        inv,_ = self.investigation()
        _,ids,reviews = self.supported(inv)
        self.obj(append(inv,'verification',verification(ids[1],verdict='unverifiable',checked_assertion=None),reviews[1],1),REVIEWER)
        self.assertEqual(self.obj(run(inv))['result']['status'],'inconclusivo')
        self.obj(append(inv,'verification',verification(ids[1]),reviews[1],2),REVIEWER)
        self.assertEqual(self.obj(run(inv))['result']['status'],'impedimento_demonstrado')
        self.fails(append(inv,'verification',verification(ids[1]),reviews[1],3),'correction_changes_review_subject','investigator_reviewer2')
        self.fails(append(inv,'verification',verification(ids[0],True),reviews[1],3),'correction_changes_review_subject',REVIEWER)
        self.fails(append(inv,'verification',verification(ids[1])),'duplicate key',REVIEWER)

    def test_validation_period_scope_reserved_fields_and_exact_references(self):
        inv,d = self.investigation()
        fid = self.obj(append(inv,'factor',factor()))['id']
        eid = self.obj(append(inv,'evidence',evidence(fid)))['id']
        for patch in [dict(hypothesis=' '),dict(scope='technical_only'),dict(control='client',responsible_party=None),
                      dict(assessment_at='2024-03-01T00:00:00Z'),dict(assessment_at='2024-01-01T00:00:00Z'),
                      dict(assessment_at='2024-02-15'),dict(actor='forged'),dict(requirement=True)]:
            self.assertNotEqual(f.query(append(inv,'factor',factor(**patch)),AUTHOR).returncode,0)
        for patch in [dict(assertion='false'),dict(source_revision=2),dict(factor_revision=2),
                      dict(content_sha256='bad'),dict(collected_at='2099-01-01T00:00:00Z')]:
            self.assertNotEqual(f.query(append(inv,'evidence',evidence(fid,**patch)),AUTHOR).returncode,0)
        self.fails(append(inv,'verification',verification(eid,checked_assertion=True)),'verdict_assertion_mismatch',REVIEWER)
        self.fails(append(inv,'verification',verification(eid,checked_at='2024-02-14T00:00:00Z')),'invalid_verification_time',REVIEWER)
        earlier = self.obj(append(inv,'evidence',evidence(fid,collected_at='2024-02-01T00:00:00Z')))['id']
        self.fails(append(inv,'verification',verification(earlier,checked_at='2024-02-02T00:00:00Z')),'invalid_verification_time',REVIEWER)
        self.fails(append(inv,'evidence',evidence(fid,purpose='requirement_applies'),eid,1),'correction_changes_proposition')
        self.fails(append(inv,'factor',factor(),fid,0),'revision_conflict')
        self.fails(f"SELECT centerway.open_investigation('{T}','{C}','{uuid.uuid4()}','{d['id']}',2,'question')",'period_not_in_detection')
        self.fails(run(inv,"'infinity'::timestamptz"),'invalid_cutoff')
        self.fails(run(inv,"'2024-01-01Z'::timestamptz"),'investigation_not_available_at_cutoff')

    def test_isolation_permissions_immutability_and_cross_investigation_references(self):
        inv,d = self.investigation()
        fid,ids,_ = self.supported(inv)
        report = self.obj(run(inv))
        for table in ('investigations','investigation_factor_versions','investigation_evidence_versions',
                      'investigation_verification_versions','investigation_runs'):
            self.assertEqual(self.sql(f"SELECT count(*) FROM centerway.{table} WHERE tenant_id='{T}'",'investigator_b'),['0'])
            for statement in [f'INSERT INTO centerway.{table} DEFAULT VALUES',f'DELETE FROM centerway.{table}',
                              f'TRUNCATE centerway.{table}',f"UPDATE centerway.{table} SET tenant_id='{B}'"]:
                self.fails(statement,'permission denied')
            self.fails(f'DELETE FROM centerway.{table}','append_only','postgres')
        self.assertEqual(self.sql(read(inv,report['id'])+' IS NULL','investigator_b'),['t'])
        self.fails(run(inv,tenant=B),'not_authorized')
        self.fails(run(inv),'permission denied','investigator_outsider')
        self.fails(run(inv,client=C2),'investigation_not_available_at_cutoff')
        self.fails(append(inv,'factor',factor(),tenant=B),'not_authorized')
        self.fails("SELECT centerway._evaluate_investigation('{}')",'permission denied')
        other,_ = self.investigation()
        self.fails(append(other,'evidence',evidence(fid)),'violates foreign key constraint')
        self.fails(append(other,'verification',verification(ids[0],True)),'query returned no rows',REVIEWER)
        self.fails(f"SELECT centerway.open_investigation('{T}','{C2}','{uuid.uuid4()}','{d['id']}',1,'question')",'query returned no rows')
        self.sql(f"SET app.tenant_id='{B}'; CREATE TEMP TABLE investigations(trap text);"+run(inv))

    def test_audit_idempotency_and_concurrent_runs(self):
        inv,_ = self.investigation()
        self.supported(inv)
        cutoff = f.literal(self.sql('SELECT clock_timestamp()::text')[-1])+'::timestamptz'
        call = run(inv,cutoff)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:f.query(call,AUTHOR,False),range(2)))
        for r in results: self.assertEqual(r.returncode,0,r.stderr)
        a,b = (json.loads(r.stdout) for r in results)
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(self.obj("SET timezone='Pacific/Honolulu';"+call)['id'],a['id'])
        audit = self.obj(f"SELECT snapshot FROM centerway.audit_log WHERE entity='investigation_runs' AND snapshot->>'id'='{a['id']}'")
        self.assertEqual(audit,a)
        self.assertEqual(self.sql(f"SELECT count(*) FROM centerway.audit_log WHERE entity='investigation_runs' AND snapshot->>'id'='{a['id']}'"),['1'])
        self.assertEqual(a['actor'],AUTHOR)

    def test_concurrent_factor_corrections_have_one_winner(self):
        inv,_ = self.investigation()
        fid = self.obj(append(inv,'factor',factor()))['id']
        call = append(inv,'factor',factor(hypothesis='Revised explicit hypothesis'),fid,1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:f.query(call,AUTHOR,False),range(2)))
        self.assertEqual(sorted(r.returncode==0 for r in results),[False,True])
        self.assertTrue(any('revision_conflict' in r.stderr for r in results))
        self.assertEqual(self.sql(f"SELECT count(*) FROM centerway.investigation_factor_versions WHERE investigation_id='{inv}' AND id='{fid}'"),['2'])

    def test_failed_transaction_does_not_leave_run_or_audit(self):
        inv,_ = self.investigation()
        self.fails(run(inv)+';SELECT 1/0','division by zero')
        self.assertEqual(self.sql(f"SELECT count(*) FROM centerway.investigation_runs WHERE investigation_id='{inv}'"),['0'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM centerway.audit_log WHERE entity='investigation_runs' AND snapshot->>'investigation_id'='{inv}'"),['0'])

    def test_late_verification_commit_creates_revision_and_preserves_earlier_report(self):
        inv,_ = self.investigation()
        _,ids,reviews = self.supported(inv)
        worker = subprocess.Popen(['docker','exec','-i',f.CONTAINER,'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
                                   '-U',REVIEWER,'-d','postgres'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            worker.stdin.write('BEGIN;'+append(inv,'verification',verification(ids[1],verdict='unverifiable',checked_assertion=None),reviews[1],1)+';\n')
            worker.stdin.flush()
            self.assertEqual(json.loads(worker.stdout.readline())['revision'],2)
            cutoff=f.literal(self.sql('SELECT clock_timestamp()::text')[-1])+'::timestamptz'
            old=self.obj(run(inv,cutoff))
            worker.stdin.write('COMMIT;\n'); worker.stdin.flush()
            _,stderr=worker.communicate(timeout=15)
            self.assertEqual(worker.returncode,0,stderr)
            new=self.obj(run(inv,cutoff))
            self.assertEqual(new['revision_of'],old['id'])
            self.assertEqual(new['revision'],2)
            self.assertEqual(old['result']['status'],'impedimento_demonstrado')
            self.assertEqual(new['result']['status'],'inconclusivo')
            self.assertEqual(self.obj(read(inv,old['id'])),old)
        finally:
            if worker.poll() is None: worker.kill(); worker.communicate()
