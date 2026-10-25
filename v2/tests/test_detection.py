"""Adaptive C02 stays inactive; all configurations/evidence are synthetic fixtures."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from centerway.core import Core,Problem
from centerway.detection import DetectionRepository,install,GUARDS
from centerway.detection_contract import validate
from centerway.evidence import EvidenceRepository,install as install_evidence
from centerway.integrations import IntegrationRepository,install as install_integrations
from centerway.ops import backup
from centerway.store import Store

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=ROOT/'examples/detection'
AS_OF='2026-01-01T00:04:00Z'


def fixture(tenant,suffix): return json.loads((EXAMPLES/f'{tenant}-{suffix}.json').read_text())


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'runtime.sqlite3'
        self.store=Store(self.path,seed_demo=False)
        with self.store.transaction() as db:
            db.executemany('INSERT INTO memberships VALUES (?,?,?)',[
                *[('demo',t,'operator') for t in ('collaboration','billing','support')],
                ('atlas','collaboration','operator'),('leitor','collaboration','viewer')])
        install_integrations(self.store)
        for tenant in ('collaboration','billing','support'):
            IntegrationRepository(self.store).append('demo',tenant,fixture(tenant,'config'),0)
        install_evidence(self.store);install(self.store);self.repo=DetectionRepository(self.store)
        for tenant in ('collaboration','billing','support'):
            self.repo.append_criteria('demo',tenant,fixture(tenant,'criteria'),0)

    def tearDown(self): self.temp.cleanup()

    def ingest(self,tenant='collaboration',customer='fictional-account',body=None):
        body=deepcopy(body if body is not None else fixture(tenant,'evidence'));body['customer']=customer
        return EvidenceRepository(self.store).ingest('demo',body)

    def run_c02(self,tenant='collaboration',customer='fictional-account',version=1,through=None,as_of=AS_OF):
        return self.repo.evaluate('demo',tenant,customer,version,as_of,through)

    def counts(self):
        with self.store.transaction() as db:
            return db.execute('SELECT count(*) FROM detection_runs').fetchone()[0]

    def test_three_saas_three_methods_demonstrate_only_against_declared_criteria(self):
        for tenant in ('collaboration','billing','support'):
            self.ingest(tenant);run=self.run_c02(tenant);result=run['payload']
            self.assertEqual('inactive',result['operational_state']);self.assertEqual('synthetic',result['classification'])
            self.assertEqual('declared_criteria_and_supplied_evidence',result['proof_scope'])
            self.assertEqual('demonstrated',result['operational_deterioration']['state'])
            self.assertEqual('demonstrated',result['value_loss']['state'])
            self.assertEqual(12,len(result['evidence']));self.assertEqual(1,result['config_version'])
            self.assertEqual(fixture(tenant,'criteria'),result['criteria_snapshot'])
            self.assertEqual(result,self.repo.get('leitor' if tenant=='collaboration' else 'demo',tenant,'fictional-account',run['id'])['payload'])
        support=self.run_c02('support')['payload']['criteria_results']
        self.assertEqual({'numerator':'3','denominator':'1'},support[0]['measured'])
        self.assertEqual({'numerator':'-5','denominator':'6'},support[1]['measured'])

    def test_stable_is_demonstrated_only_with_complete_explicit_coverage(self):
        for tenant in ('collaboration','billing','support'):
            body=fixture(tenant,'evidence')
            for row in body['records']:
                if row['definition_id']=='processing-delay': row['payload']['value']=5
                elif row['definition_id']=='processing-snapshot': row['payload']['delay_seconds']=5
                else: row['payload']['outcome_count']=6
            self.ingest(tenant,body=body);result=self.run_c02(tenant)['payload']
            self.assertEqual('stable',result['operational_deterioration']['state'])
            self.assertEqual('stable',result['value_loss']['state'])

    def test_absence_and_partial_samples_never_become_deterioration(self):
        result=self.run_c02()['payload']
        self.assertEqual('insufficient',result['operational_deterioration']['state'])
        self.assertEqual('insufficient',result['value_loss']['state'])
        body=fixture('collaboration','evidence')
        body['records']=[r for r in body['records'] if r['external_id']!='fictional-processing-delay-3']
        self.ingest(body=body);result=self.run_c02()['payload']
        self.assertEqual('insufficient',result['operational_deterioration']['state'])
        self.assertEqual('demonstrated',result['value_loss']['state'])
        self.assertTrue(any(i['code']=='missing_samples' for i in result['criteria_results'][0]['issues']))
        self.assertIsNone(result['criteria_results'][0]['measured'])

    def test_operational_deterioration_cannot_prove_value_loss_or_missing_dimension(self):
        body=fixture('collaboration','evidence');body['records']=[r for r in body['records'] if r['definition_id']!='value-snapshot']
        self.ingest(body=body);result=self.run_c02()['payload']
        self.assertEqual('demonstrated',result['operational_deterioration']['state'])
        self.assertEqual('insufficient',result['value_loss']['state'])
        criteria=fixture('collaboration','criteria');criteria['criteria']=criteria['criteria'][:1]
        self.repo.append_criteria('demo','collaboration',criteria,1)
        self.assertEqual('insufficient',self.run_c02(version=2)['payload']['value_loss']['state'])
        usage=fixture('collaboration','criteria');usage['criteria'][0]['dimension']='value'
        with self.assertRaises(ValueError): self.repo.append_criteria('demo','collaboration',usage,2)

    def test_conflicts_are_preserved_and_old_snapshots_remain_reproducible(self):
        self.ingest();old=self.run_c02();body=fixture('collaboration','evidence')
        claim=deepcopy(body['records'][-3]);claim['external_id']='contradictory-new-claim';claim['payload']['value']=30
        self.ingest(body={**body,'records':[claim]});new=self.run_c02()
        self.assertNotEqual(old['id'],new['id'])
        self.assertEqual('contradictory',new['payload']['operational_deterioration']['state'])
        self.assertIsNone(new['payload']['criteria_results'][0]['measured'])
        self.assertTrue(new['payload']['criteria_results'][0]['contradictions'])
        self.assertEqual(old['payload'],self.repo.get('demo','collaboration','fictional-account',old['id'])['payload'])
        self.assertEqual(old['id'],self.run_c02(through=old['payload']['through'])['id'])
        self.assertEqual(13,len(new['payload']['evidence']))
        value_claim=deepcopy(body['records'][-1]);value_claim['external_id']='disputed-value';value_claim['payload']['outcome_count']=3
        self.ingest(body={**body,'records':[value_claim]})
        self.assertEqual('contradictory',self.run_c02()['payload']['value_loss']['state'])

    def test_late_baseline_conflicts_and_corroborating_conflicts_are_not_arbitrarily_resolved(self):
        self.ingest('billing');body=fixture('billing','evidence')
        late=deepcopy(body['records'][0]);late['external_id']='late-baseline-claim';late['occurred_at']=AS_OF;late['payload']['value']=8
        self.ingest('billing',body={**body,'records':[late]})
        result=self.run_c02('billing')['payload']
        self.assertEqual('contradictory',result['operational_deterioration']['state'])
        self.assertEqual('baseline',result['criteria_results'][0]['contradictions'][0]['window'])
        self.ingest('collaboration');body=fixture('collaboration','evidence')
        conflicting=deepcopy(body['records'][-2]);conflicting['external_id']='corroboration-conflict';conflicting['payload']['delay_seconds']=19
        self.ingest(body={**body,'records':[conflicting]})
        self.assertEqual('contradictory',self.run_c02()['payload']['operational_deterioration']['state'])

    def test_zero_baseline_is_insufficient_not_infinite_loss_or_automatic_fallback(self):
        body=fixture('support','evidence')
        for row in body['records'][:6]:
            row['payload']={key:0 for key in row['payload']}
        self.ingest('support',body=body);result=self.run_c02('support')['payload']
        for dimension in ('operational_deterioration','value_loss'): self.assertEqual('insufficient',result[dimension]['state'])
        for criterion in result['criteria_results']:
            self.assertIn({'code':'zero_baseline'},criterion['issues']);self.assertIsNone(criterion['measured'])

    def test_repeated_identical_bucket_claims_do_not_weight_aggregates_twice(self):
        body=fixture('collaboration','evidence')
        body['records'][6]['payload']['value']=10;body['records'][7]['payload']['delay_seconds']=10
        repeated=deepcopy(body['records'][6]);repeated['external_id']='same-bucket-later-same-value';repeated['occurred_at']=AS_OF
        body['records'].append(repeated);self.ingest(body=body)
        result=self.run_c02()['payload']['criteria_results'][0]
        self.assertEqual({'numerator':'15','denominator':'1'},result['measured'])
        self.assertFalse(result['contradictions'])

    def test_exact_arithmetic_aggregations_and_comparison_boundaries(self):
        body=fixture('collaboration','evidence')
        body['records'][6]['payload']['value']=0.1;body['records'][7]['payload']['delay_seconds']=0.1
        body['records'][9]['payload']['value']=0.2;body['records'][10]['payload']['delay_seconds']=0.2
        self.ingest(body=body)
        for i,(aggregation,number) in enumerate((('sum',{'numerator':'3','denominator':'10'}),('mean',{'numerator':'3','denominator':'20'}),('min',{'numerator':'1','denominator':'10'}),('max',{'numerator':'1','denominator':'5'})),start=2):
            criteria=fixture('collaboration','criteria');criteria['criteria']=criteria['criteria'][:1]
            criterion=criteria['criteria'][0];criterion['aggregation']=aggregation;criterion['threshold']=0.3
            self.repo.append_criteria('demo','collaboration',criteria,i-1)
            result=self.run_c02(version=i)['payload']['criteria_results'][0]
            self.assertEqual(number,result['measured']);self.assertEqual('stable',result['state'])
        for i,(comparison,expected) in enumerate((('lt','stable'),('lte','demonstrated'),('gt','stable'),('gte','demonstrated')),start=6):
            criteria=fixture('collaboration','criteria');criteria['criteria']=criteria['criteria'][:1]
            criterion=criteria['criteria'][0];criterion.update(aggregation='sum',comparison=comparison,threshold=0.3)
            self.repo.append_criteria('demo','collaboration',criteria,i-1)
            self.assertEqual(expected,self.run_c02(version=i)['payload']['criteria_results'][0]['state'])

    def test_incompatible_periods_and_future_observations_are_not_used_as_proof(self):
        self.ingest();body=fixture('collaboration','evidence')
        partial=deepcopy(body['records'][6]);partial['external_id']='partial-period';partial['period']['start']='2026-01-01T00:02:30Z'
        self.ingest(body={**body,'records':[partial]})
        result=self.run_c02()['payload']
        self.assertEqual('insufficient',result['operational_deterioration']['state'])
        self.assertTrue(any(i['code']=='incompatible_sampling' for i in result['criteria_results'][0]['issues']))
        body=fixture('billing','evidence')
        for row in body['records']: row['occurred_at']='2026-01-01T00:05:00Z'
        self.ingest('billing',body=body)
        self.assertEqual('insufficient',self.run_c02('billing')['payload']['operational_deterioration']['state'])
        with self.assertRaises(ValueError): self.run_c02(as_of='2099-01-01T00:04:00Z')

    def test_criteria_validation_no_inferred_thresholds_units_or_cross_tenant_references(self):
        original=fixture('collaboration','criteria');config=fixture('collaboration','config')
        mutations=[
            lambda d:d['criteria'][0].pop('threshold'),
            lambda d:d['criteria'][0].update(threshold=True),
            lambda d:d['criteria'][0].update(threshold=float('inf')),
            lambda d:d['criteria'][0].update(threshold_unit='milliseconds'),
            lambda d:d['criteria'][0].update(coverage='best_effort'),
            lambda d:d['criteria'][0].update(cadence_seconds=70),
            lambda d:d['criteria'][0].update(window_seconds=1000000,cadence_seconds=1),
            lambda d:d['criteria'][0].update(metric_ref='foreign-metric'),
            lambda d:d['criteria'][0].update(goal_refs=[]),
            lambda d:d['criteria'][0].update(evidence_refs=['operation-state']),
            lambda d:d['criteria'][0].update(aggregation='automatic'),
            lambda d:d['criteria'][0].update(comparison=[]),
            lambda d:d['criteria'][0].update(method='eval'),
            lambda d:d['criteria'][0].update(window_seconds=True),
            lambda d:d['criteria'][1]['source'].update(kind='metric',definition_id='completed-items',field='value'),
            lambda d:d['criteria'][1]['source'].update(field='missing'),
            lambda d:d['criteria'].append(deepcopy(d['criteria'][0])),
            lambda d:d.update(activate=True),
        ]
        before=self.path.read_bytes()
        for mutation in mutations:
            doc=deepcopy(original);mutation(doc)
            with self.assertRaises(ValueError): validate(doc,config)
            with self.assertRaises(ValueError): self.repo.append_criteria('demo','collaboration',doc,1)
            self.assertEqual(before,self.path.read_bytes())
        foreign=fixture('billing','criteria')
        with self.assertRaises(Problem) as error: self.repo.append_criteria('demo','collaboration',foreign,1)
        self.assertEqual(403,error.exception.status)

    def test_configuration_and_criteria_versions_are_pinned_and_never_reinterpreted(self):
        self.ingest();first=self.run_c02()
        revised=fixture('collaboration','criteria');revised['criteria'][0]['threshold']=100
        second=self.repo.append_criteria('atlas','collaboration',revised,1)
        self.assertEqual(2,second['version']);self.assertEqual('atlas',second['actor'])
        self.assertEqual('stable',self.run_c02(version=2)['payload']['operational_deterioration']['state'])
        self.assertEqual(first['payload'],self.repo.get('demo','collaboration','fictional-account',first['id'])['payload'])
        with self.assertRaises(Problem) as error: self.repo.append_criteria('demo','collaboration',revised,1)
        self.assertEqual(409,error.exception.status)
        config=fixture('collaboration','config');config['metrics'][-1]['unit']='milliseconds'
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        revised['config_version']=2
        with self.assertRaises(ValueError): self.repo.append_criteria('demo','collaboration',revised,2)
        revised['criteria'][0]['threshold_unit']='milliseconds'
        self.repo.append_criteria('demo','collaboration',revised,2)
        result=self.run_c02(version=3)['payload']
        self.assertEqual([],result['evidence']);self.assertEqual('insufficient',result['operational_deterioration']['state'])
        self.assertEqual(2,result['config_version'])

    def test_permissions_subject_isolation_and_current_memberships(self):
        self.ingest();run=self.run_c02()
        self.assertEqual(run['payload'],self.repo.get('leitor','collaboration','fictional-account',run['id'])['payload'])
        for operation in (
            lambda:self.repo.evaluate('leitor','collaboration','fictional-account',1,AS_OF),
            lambda:self.repo.append_criteria('leitor','collaboration',fixture('collaboration','criteria'),1),
            lambda:self.repo.criteria('atlas','billing',1),
            lambda:self.repo.get('atlas','billing','fictional-account',run['id']),
        ):
            with self.assertRaises(Problem) as error: operation()
            self.assertEqual(403,error.exception.status)
        with self.assertRaises(Problem) as error: self.repo.get('demo','collaboration','other-client',run['id'])
        self.assertEqual(404,error.exception.status)
        self.assertEqual('insufficient',self.run_c02(customer='other-client')['payload']['value_loss']['state'])
        with self.store.transaction() as db: db.execute("DELETE FROM memberships WHERE user_id='leitor' AND tenant='collaboration'")
        with self.assertRaises(Problem): self.repo.get('leitor','collaboration','fictional-account',run['id'])

    def test_idempotent_concurrent_runs_and_original_evidence_history_are_unchanged(self):
        self.ingest()
        with self.store.transaction() as db:
            before={table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in ('evidence_items','evidence_batches','integration_versions','history')}
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs=list(pool.map(lambda _:self.run_c02(),range(2)))
        self.assertEqual([False,True],sorted(r['reused'] for r in runs));self.assertEqual(1,self.counts())
        with self.store.transaction() as db:
            after={table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in before}
        self.assertEqual(before,after)
        self.assertEqual('verified',backup(self.path,self.root/'snapshot.sqlite3')['status'])
        copied=DetectionRepository(Store.open_existing(self.root/'snapshot.sqlite3'))
        self.assertEqual(runs[0]['payload'],copied.get('demo','collaboration','fictional-account',runs[0]['id'])['payload'])

    def test_append_only_tamper_detection_and_no_automatic_repair(self):
        self.ingest();run=self.run_c02()
        with self.store.transaction() as db:
            for table in ('detection_criteria','detection_runs','detection_metadata'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM '+table)
            db.execute('DROP TRIGGER detection_immutable_detection_runs_UPDATE')
        with self.assertRaises(Problem) as error: self.repo.get('demo','collaboration','fictional-account',run['id'])
        self.assertEqual(503,error.exception.status)
        with self.store.transaction() as db:
            db.execute("UPDATE detection_runs SET payload='{}'")
            db.execute(GUARDS['detection_immutable_detection_runs_UPDATE'])
        with self.assertRaises(Problem): self.repo.get('demo','collaboration','fictional-account',run['id'])
        with self.store.transaction() as db: self.assertEqual('{}',db.execute('SELECT payload FROM detection_runs').fetchone()[0])

    def test_optional_numeric_value_is_insufficient_and_never_filled_with_zero(self):
        config=fixture('collaboration','config')
        config['evidence'][1]['fields'][0]['required']=False
        config['evidence'][1]['fields'].append({'name':'note','type':'string','required':True})
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        criteria=fixture('collaboration','criteria');criteria['config_version']=2
        self.repo.append_criteria('demo','collaboration',criteria,1)
        body=fixture('collaboration','evidence');body['config_version']=2
        for row in body['records']:
            if row['definition_id']=='value-snapshot': row['payload']={'note':'Outcome measurement not supplied'}
        self.ingest(body=body);result=self.run_c02(version=2)['payload']
        self.assertEqual('demonstrated',result['operational_deterioration']['state'])
        self.assertEqual('insufficient',result['value_loss']['state'])
        self.assertIsNone(result['criteria_results'][1]['measured'])

    def test_sql_failure_rolls_back_results_and_criteria_tampering_is_not_repaired(self):
        self.ingest()
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER qa_fail_run BEFORE INSERT ON detection_runs BEGIN SELECT RAISE(ABORT,'qa-private-marker'); END")
            original=[tuple(row) for row in db.execute('SELECT * FROM evidence_items')]
        with self.assertRaises(sqlite3.IntegrityError): self.run_c02()
        self.assertEqual(0,self.counts())
        with self.store.transaction() as db:
            self.assertEqual(original,[tuple(row) for row in db.execute('SELECT * FROM evidence_items')])
            db.execute('DROP TRIGGER qa_fail_run')
            db.execute('DROP TRIGGER detection_immutable_detection_criteria_UPDATE')
            db.execute("UPDATE detection_criteria SET actor='forged' WHERE tenant='collaboration'")
            db.execute(GUARDS['detection_immutable_detection_criteria_UPDATE'])
        with self.assertRaises(Problem) as error: self.repo.criteria('demo','collaboration',1)
        self.assertEqual(503,error.exception.status)
        with self.store.transaction() as db:
            self.assertEqual('forged',db.execute("SELECT actor FROM detection_criteria WHERE tenant='collaboration'").fetchone()[0])

    def test_dimension_summary_cannot_ignore_an_incomplete_or_contradictory_criterion(self):
        self.ingest();doc=fixture('collaboration','criteria')
        extra=deepcopy(doc['criteria'][0]);extra['id']='longer-explicit-window';extra['window_seconds']=300
        doc['criteria'].append(extra);self.repo.append_criteria('demo','collaboration',doc,1)
        result=self.run_c02(version=2)['payload']
        self.assertEqual('demonstrated',result['criteria_results'][0]['state'])
        self.assertEqual('insufficient',result['operational_deterioration']['state'])
        body=fixture('collaboration','evidence');row=deepcopy(body['records'][-3])
        row['external_id']='disputed-current';row['payload']['value']=21
        self.ingest(body={**body,'records':[row]})
        self.assertEqual('contradictory',self.run_c02(version=2)['payload']['operational_deterioration']['state'])

    def test_numeric_state_snapshots_require_exact_declared_sampling_without_interpolation(self):
        config=fixture('collaboration','config');config['evidence'][-1]['kind']='state'
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        criteria=fixture('collaboration','criteria');criteria['config_version']=2
        criteria['criteria'][0]['source']={'kind':'evidence','definition_id':'processing-snapshot','field':'delay_seconds'}
        self.repo.append_criteria('demo','collaboration',criteria,1)
        body=fixture('collaboration','evidence');body['config_version']=2
        for row in body['records']:
            if row['definition_id']=='processing-snapshot': row['period']=None
        self.ingest(body=body)
        self.assertEqual('demonstrated',self.run_c02(version=2)['payload']['operational_deterioration']['state'])
        row=deepcopy(body['records'][-2]);row['external_id']='unaligned-point';row['occurred_at']='2026-01-01T00:03:30Z'
        self.ingest(body={**body,'records':[row]})
        result=self.run_c02(version=2)['payload']
        self.assertEqual('insufficient',result['operational_deterioration']['state'])
        self.assertTrue(any(i['code']=='incompatible_sampling' for i in result['criteria_results'][0]['issues']))

    def test_setup_and_cli_are_explicit_no_http_changes_no_missing_database_creation(self):
        missing=self.root/'missing.sqlite3'
        result=subprocess.run([sys.executable,'-m','centerway.detection','init','--db',str(missing)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(1,result.returncode);self.assertFalse(missing.exists())
        with self.assertRaises(ValueError): install(self.store)
        for tenant in ('collaboration','billing','support'):
            result=subprocess.run([sys.executable,'-m','centerway.detection','validate','--file',str(EXAMPLES/f'{tenant}-criteria.json'),'--config-file',str(EXAMPLES/f'{tenant}-config.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
        self.ingest()
        commands=[['criteria','--version','1'],['evaluate','--customer','fictional-account','--criteria-version','1','--as-of',AS_OF],['get','--customer','fictional-account','--run-id','1']]
        for command in commands:
            result=subprocess.run([sys.executable,'-m','centerway.detection',*command,'--db',str(self.path),'--user','demo','--tenant','collaboration'],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr);json.loads(result.stdout)


class DetectionSafetyTests(unittest.TestCase):
    def prepare(self,store,user,tenant,declared=False):
        install_integrations(store)
        config=fixture('collaboration','config');config['tenant']=tenant
        if declared:
            config['data_classification']='declared';config['provenance']['source_ref']='test:unverified-supplier-claim'
        IntegrationRepository(store).append(user,tenant,config,0)
        install_evidence(store);body=fixture('collaboration','evidence');body['tenant']=tenant
        EvidenceRepository(store).ingest(user,body)
        install(store);repository=DetectionRepository(store)
        criteria=fixture('collaboration','criteria');criteria['tenant']=tenant
        repository.append_criteria(user,tenant,criteria,0)
        return repository

    def test_demonstrated_inactive_production_result_never_enables_business_operations(self):
        from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);accounts=root/'accounts.json'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
            path=root/'production.sqlite3';provision(path,root/'private-secrets.json','https://app.example.invalid',accounts)
            store=Store.open_existing(path);repo=self.prepare(store,'owner','collaboration',declared=True)
            run=repo.evaluate('owner','collaboration','fictional-account',1,AS_OF)
            self.assertEqual('demonstrated',run['payload']['operational_deterioration']['state'])
            self.assertEqual('inactive',run['payload']['operational_state'])
            self.assertEqual('declared_criteria_and_supplied_evidence',run['payload']['proof_scope'])
            policy=ProductionPolicy(store);self.assertEqual([],policy.view(store,'owner')['registry'])
            with self.assertRaises(Problem) as error: policy.block_operation(store,'owner','collaboration')
            self.assertEqual(503,error.exception.status)
            with store.transaction() as db:
                for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                with self.assertRaises(sqlite3.IntegrityError): db.execute("INSERT INTO environments VALUES ('collaboration','c','Blocked','{}',0)")

    def test_private_demo_lease_cannot_be_bypassed_and_missing_storage_is_not_created(self):
        from centerway.preview import provision
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'demo.sqlite3';provision(path,root/'secrets.json','https://demo.example.invalid')
            store=Store.open_existing(path)
            # The detector cannot install anything merely by being constructed.
            install_integrations(store);install_evidence(store);before=path.read_bytes()
            with self.assertRaises(Problem): DetectionRepository(store)
            self.assertEqual(before,path.read_bytes())
            config=fixture('collaboration','config');config['tenant']='atlas'
            IntegrationRepository(store).append('founder','atlas',config,0);install(store)
            repo=DetectionRepository(store);doc=fixture('collaboration','criteria');doc['tenant']='atlas'
            repo.append_criteria('founder','atlas',doc,0)
            run=repo.evaluate('founder','atlas','fictional-account',1,AS_OF)
            self.assertEqual('insufficient',run['payload']['value_loss']['state'])
            with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
            for operation in (lambda:repo.evaluate('founder','atlas','fictional-account',1,AS_OF),lambda:repo.get('founder','atlas','fictional-account',run['id'])):
                with self.assertRaises(Problem) as error: operation()
                self.assertEqual(503,error.exception.status)
