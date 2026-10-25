"""C03 structured review is inactive; no causal conclusions or original-data writes."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from centerway.core import Problem
from centerway.detection import DetectionRepository,install as install_c02,GUARDS as C02_GUARDS
from centerway.evidence import EvidenceRepository,install as install_evidence
from centerway.integrations import IntegrationRepository,install as install_integrations
from centerway.investigation import InvestigationRepository,install,GUARDS
from centerway.ops import backup
from centerway.store import Store

ROOT=Path(__file__).resolve().parents[1]
AS_OF='2026-01-01T00:04:00Z'


def fixture(tenant,suffix,directory='detection'):
    return json.loads((ROOT/'examples'/directory/f'{tenant}-{suffix}.json').read_text())


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'runtime.sqlite3'
        self.store=Store(self.path,seed_demo=False)
        with self.store.transaction() as db:
            db.executemany('INSERT INTO memberships VALUES (?,?,?)',[
                *[('demo',tenant,'operator') for tenant in ('collaboration','billing','support')],
                ('atlas','collaboration','operator'),('leitor','collaboration','viewer')])
        install_integrations(self.store)
        for tenant in ('collaboration','billing','support'):
            IntegrationRepository(self.store).append('demo',tenant,fixture(tenant,'config'),0)
        install_evidence(self.store)
        for tenant in ('collaboration','billing','support'):
            EvidenceRepository(self.store).ingest('demo',fixture(tenant,'evidence'))
            EvidenceRepository(self.store).ingest('demo',fixture(tenant,'context','investigation'))
        install_c02(self.store);self.c02=DetectionRepository(self.store);self.parents={}
        for tenant in ('collaboration','billing','support'):
            self.c02.append_criteria('demo',tenant,fixture(tenant,'criteria'),0)
            self.parents[tenant]=self.c02.evaluate('demo',tenant,'fictional-account',1,AS_OF)
        install(self.store);self.repo=InvestigationRepository(self.store)

    def tearDown(self): self.temp.cleanup()

    def document(self,tenant='collaboration',parent=None):
        doc=fixture(tenant,'declaration','investigation')
        doc['c02_run_id']=(parent or self.parents[tenant])['id']
        return doc

    def append(self,document=None,expected=0,parent=None,tenant='collaboration',customer='fictional-account',user='demo'):
        parent=parent or self.parents[tenant]
        return self.repo.append(user,tenant,customer,parent['id'],document if document is not None else self.document(tenant,parent),expected)

    def get(self,tenant='collaboration',parent=None,version=None,user='demo'):
        return self.repo.get(user,tenant,'fictional-account',(parent or self.parents[tenant])['id'],version)

    def count(self):
        with self.store.transaction() as db: return db.execute('SELECT count(*) FROM investigation_versions').fetchone()[0]

    def test_three_saas_facts_provenance_unconfirmed_hypotheses_and_supported_conditions(self):
        for tenant in ('collaboration','billing','support'):
            result=self.append(tenant=tenant);payload=result['payload']
            self.assertEqual('inactive',payload['operational_state']);self.assertEqual('not_established',payload['causal_status'])
            self.assertEqual('synthetic',payload['classification']);self.assertEqual(13,len(payload['facts']))
            self.assertEqual('unconfirmed',payload['hypotheses'][0]['state'])
            self.assertEqual(1,len(payload['supported_impediments']))
            impediment=payload['supported_impediments'][0]
            self.assertEqual('observed_condition_only',impediment['support_scope'])
            self.assertEqual('observed_requirement_noncompliance',impediment['claim_type'])
            self.assertEqual('not_established',impediment['causal_status'])
            for fact in payload['facts']:
                self.assertEqual(tenant,fact['provenance']['tenant']);self.assertEqual('fictional-account',fact['provenance']['customer'])
                self.assertEqual(1,fact['provenance']['config_version']);self.assertEqual(payload['config_hash'],fact['provenance']['config_hash'])
                self.assertTrue(fact['provenance']['source_ref']);self.assertEqual(64,len(fact['provenance']['record_hash']))
            self.assertEqual(payload,self.get(tenant)['payload'])
        self.assertEqual(3,self.count())

    def test_deterioration_or_correlation_does_not_generate_causes_hypotheses_or_blockers(self):
        doc=self.document();doc['hypotheses']=[];doc['requirements']=[]
        payload=self.append(doc)['payload']
        self.assertEqual('demonstrated',payload['c02_findings']['dimensions']['operational_deterioration']['state'])
        self.assertEqual([],payload['hypotheses']);self.assertEqual([],payload['supported_impediments'])
        doc=self.document();doc['hypotheses'][0]['statement']='Processing delay caused the observed value loss.'
        doc['hypotheses'][0]['support_refs']=[{'evidence_id':7,'field':'value'},{'evidence_id':9,'field':'outcome_count'}]
        payload=self.append(doc,expected=1)['payload']
        self.assertEqual('unconfirmed',payload['hypotheses'][0]['state'])
        self.assertEqual('operator_declared_references_only',payload['hypotheses'][0]['support_scope'])
        self.assertEqual('not_established',payload['causal_status'])

    def test_unsupported_hypotheses_remain_explicitly_unconfirmed(self):
        doc=self.document();doc['hypotheses'][0]['support_refs']=[]
        payload=self.append(doc)['payload']
        self.assertEqual([],payload['hypotheses'][0]['support_refs'])
        self.assertEqual('unconfirmed',payload['hypotheses'][0]['state'])
        self.assertNotIn('confirmed_causes',payload)
        for mutation in (lambda d:d['hypotheses'][0].update(state='confirmed'),lambda d:d.update(facts=[]),lambda d:d.update(confirmed_causes=['made-up'])):
            invalid=deepcopy(doc);mutation(invalid)
            with self.assertRaises(ValueError): self.append(invalid,expected=1)
        self.assertEqual(1,self.count())

    def test_missing_observations_never_become_impediments_or_false_values(self):
        parent=self.c02.evaluate('demo','collaboration','empty-account',1,AS_OF)
        doc=self.document(parent=parent);doc['customer']='empty-account';doc['hypotheses'][0]['support_refs']=[]
        payload=self.append(doc,parent=parent,customer='empty-account')['payload']
        self.assertEqual([],payload['facts']);self.assertEqual([],payload['supported_impediments'])
        self.assertEqual('insufficient',payload['requirements'][0]['status'])
        self.assertTrue(any(g['kind']=='requirement_gap' and g['no_observation'] for g in payload['missing_information']))
        self.assertTrue(any(g['kind']=='c02_gap' for g in payload['missing_information']))
        self.assertEqual('not_established',payload['causal_status'])

    def test_context_contradictions_are_detected_even_when_c02_did_not_use_that_source(self):
        old=self.append();body=fixture('collaboration','context','investigation')
        body['records'][0]['external_id']='opposite-claim';body['records'][0]['payload']['paused']=False
        EvidenceRepository(self.store).ingest('demo',body)
        parent=self.c02.evaluate('demo','collaboration','fictional-account',1,AS_OF)
        self.assertEqual('demonstrated',parent['payload']['operational_deterioration']['state'])
        payload=self.append(parent=parent)['payload']
        self.assertTrue(payload['contradictions']);self.assertEqual([],payload['supported_impediments'])
        self.assertEqual('contradictory',payload['requirements'][0]['status'])
        self.assertEqual([{'evidence_id':13,'field':'paused'}],payload['hypotheses'][0]['disputed_refs'])
        claims=[f for f in payload['facts'] if f['definition_id']=='operation-state']
        self.assertEqual({True,False},{f['payload']['paused'] for f in claims})
        self.assertTrue(all(f['disputed_fields']==['paused'] for f in claims))
        self.assertEqual(old['payload'],self.get()['payload'])

    def test_c02_conflicts_are_preserved_without_claiming_a_clean_observation_is_the_cause(self):
        body=fixture('collaboration','evidence');claim=deepcopy(body['records'][-3])
        claim['external_id']='disputed-delay';claim['payload']['value']=25;body['records']=[claim]
        EvidenceRepository(self.store).ingest('demo',body)
        parent=self.c02.evaluate('demo','collaboration','fictional-account',1,AS_OF)
        payload=self.append(parent=parent)['payload']
        self.assertEqual('contradictory',payload['c02_findings']['dimensions']['operational_deterioration']['state'])
        self.assertTrue(any(b['kind']=='c02_result' for c in payload['contradictions'] for b in c['detected_by']))
        self.assertEqual(1,len(payload['supported_impediments']))
        self.assertEqual('not_established',payload['supported_impediments'][0]['causal_status'])
        self.assertEqual('unconfirmed',payload['hypotheses'][0]['state'])

    def test_new_evidence_and_configuration_versions_do_not_silently_enter_an_old_investigation(self):
        first=self.append();old=deepcopy(first['payload'])
        body=fixture('collaboration','context','investigation');body['records'][0]['external_id']='after-c02'
        body['records'][0]['occurred_at']='2026-01-01T00:03:30Z';body['records'][0]['payload']['paused']=False
        new_id=EvidenceRepository(self.store).ingest('demo',body)['record_ids'][0]
        doc=self.document();doc['hypotheses'][0]['support_refs']=[{'evidence_id':new_id,'field':'paused'}]
        with self.assertRaises(ValueError): self.append(doc,expected=1)
        config=fixture('collaboration','config');config['evidence'][0]['fields']=[]
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        self.assertEqual(old,self.get()['payload'])
        self.assertEqual(1,self.get()['payload']['config_version'])

    def test_future_observations_are_labelled_and_cannot_support_current_hypotheses_or_requirements(self):
        body=fixture('collaboration','context','investigation');body['records'][0]['external_id']='future-to-c02'
        body['records'][0]['occurred_at']='2026-01-01T00:05:00Z'
        future_id=EvidenceRepository(self.store).ingest('demo',body)['record_ids'][0]
        parent=self.c02.evaluate('demo','collaboration','fictional-account',1,AS_OF)
        doc=self.document(parent=parent);doc['hypotheses'][0]['support_refs']=[{'evidence_id':future_id,'field':'paused'}]
        with self.assertRaises(ValueError): self.append(doc,parent=parent)
        doc['hypotheses'][0]['support_refs']=[]
        payload=self.append(doc,parent=parent)['payload']
        fact=next(f for f in payload['facts'] if f['evidence_id']==future_id)
        self.assertEqual('after_c02_as_of',fact['temporal_relation'])
        self.assertNotIn(future_id,[r['evidence_id'] for r in payload['requirements'][0]['checked_refs']])

    def test_revision_history_exact_retries_conflicts_and_detached_results(self):
        first=self.append();doc=self.document();doc['hypotheses'][0]['statement']='Revised, still unconfirmed hypothesis.'
        doc['provenance']['source_ref']='fixture:revision-two'
        second=self.append(doc,expected=1,user='atlas')
        self.assertEqual(first['record_hash'],second['parent_hash']);self.assertEqual('atlas',second['actor'])
        self.assertEqual(2,second['version']);self.assertEqual(first['payload'],self.get(version=1)['payload'])
        self.assertEqual(second['payload'],self.get()['payload'])
        self.assertEqual(1,self.append(expected=0)['version'])
        self.assertTrue(self.append(doc,expected=1)['reused']);self.assertEqual(2,self.count())
        other=deepcopy(doc);other['hypotheses'][0]['statement']='Different stale input'
        with self.assertRaises(Problem) as error: self.append(other,expected=0)
        self.assertEqual(409,error.exception.status)
        second['payload']['facts'][-1]['payload']['paused']=False
        self.assertTrue(self.get()['payload']['facts'][-1]['payload']['paused'])
        with self.assertRaises(Problem): self.get(version=3)
        with self.assertRaises(ValueError): self.get(version=True)

    def test_memberships_tenant_customer_and_parent_id_are_required_together(self):
        self.append();self.assertEqual(1,self.get(user='leitor')['version'])
        for operation in (lambda:self.append(user='leitor'),lambda:self.get(tenant='billing',user='atlas'),lambda:self.get(user='unknown')):
            with self.assertRaises(Problem) as error: operation()
            self.assertEqual(403,error.exception.status)
        with self.assertRaises(Problem) as error:
            self.repo.get('demo','collaboration','another-account',self.parents['collaboration']['id'])
        self.assertEqual(404,error.exception.status)
        with self.assertRaises(Problem) as error:
            self.repo.get('demo','billing','fictional-account',self.parents['collaboration']['id'])
        self.assertEqual(404,error.exception.status)
        with self.store.transaction() as db: db.execute("DELETE FROM memberships WHERE user_id='leitor' AND tenant='collaboration'")
        with self.assertRaises(Problem): self.get(user='leitor')

    def test_strict_claim_references_schema_types_and_resource_limits(self):
        mutations=[
            lambda d:d['hypotheses'][0]['support_refs'][0].update(evidence_id=26),
            lambda d:d['hypotheses'][0]['support_refs'][0].update(field='invented'),
            lambda d:d['hypotheses'][0]['contrary_refs'].extend(d['hypotheses'][0]['support_refs']),
            lambda d:d['requirements'][0]['selector'].update(field='invented'),
            lambda d:d['requirements'][0].update(window='baseline'),
            lambda d:d['requirements'][0].update(comparison='lt'),
            lambda d:d['requirements'][0].update(expected=0),
            lambda d:d['requirements'][0].pop('expected'),
            lambda d:d['requirements'][0].update(confirmed=True),
            lambda d:d.update(schema_version=True),
            lambda d:d.update(c02_run_id=True),
            lambda d:d.update(actor='forged'),
            lambda d:d['provenance'].update(recorded_at='2026-01-01T00:00:00'),
            lambda d:d['hypotheses'][0].update(statement='x'*65537),
            lambda d:d['hypotheses'].extend([deepcopy(d['hypotheses'][0])]*100),
        ]
        for mutation in mutations:
            doc=self.document();mutation(doc)
            with self.assertRaises((ValueError,Problem)): self.append(doc)
            self.assertEqual(0,self.count())

    def test_exact_predicates_and_normalized_timestamps_do_not_create_false_impediments(self):
        body=fixture('collaboration','context','investigation')
        event_config=fixture('collaboration','config')['events'][0]
        body['records']=[{'external_id':'context-event','kind':'event','definition_id':event_config['id'],'source_ref':event_config['source_ref'],
                          'occurred_at':'2026-01-01T00:03:00Z','period':None,'payload':{'account_id':'fictional-account','occurred_at':'2026-01-01T00:03:00Z'}}]
        EvidenceRepository(self.store).ingest('demo',body)
        parent=self.c02.evaluate('demo','collaboration','fictional-account',1,AS_OF)
        doc=self.document(parent=parent)
        requirement=doc['requirements'][0];requirement['selector']={'kind':'event','definition_id':event_config['id'],'field':'occurred_at'}
        requirement['expected']='2026-01-01T00:03:00+00:00'
        payload=self.append(doc,parent=parent)['payload']
        self.assertEqual('not_observed',payload['requirements'][0]['status']);self.assertEqual([],payload['supported_impediments'])
        numeric=self.document(parent=parent);numeric['requirements'][0]['selector']={'kind':'evidence','definition_id':'value-snapshot','field':'outcome_count'}
        numeric['requirements'][0].update(comparison='gte',expected=2)
        payload=self.append(numeric,expected=1,parent=parent)['payload']
        self.assertEqual(2,len(payload['supported_impediments'][0]['violation_refs']))

    def test_concurrent_exact_retries_create_one_version_and_parent_scope_has_a_database_guard(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.append(),range(2)))
        self.assertEqual([False,True],sorted(r['reused'] for r in results));self.assertEqual(1,self.count())
        with self.store.transaction() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO investigation_versions SELECT 'billing',customer,c02_run_id,version,parent_hash,c02_hash,input_hash,declaration,payload,actor,created_at,record_hash FROM investigation_versions WHERE tenant='collaboration'")
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM investigation_versions')

    def test_original_histories_are_unchanged_and_backup_replays_the_result(self):
        with self.store.transaction() as db:
            before={table:[tuple(row) for row in db.execute('SELECT * FROM '+table)] for table in ('evidence_items','evidence_batches','integration_versions','detection_runs','detection_criteria','history')}
        investigation=self.append()
        with self.store.transaction() as db:
            self.assertEqual(before,{table:[tuple(row) for row in db.execute('SELECT * FROM '+table)] for table in before})
        self.assertEqual('verified',backup(self.path,self.root/'snapshot.sqlite3')['status'])
        copied=InvestigationRepository(Store.open_existing(self.root/'snapshot.sqlite3'))
        self.assertEqual(investigation['payload'],copied.get('demo','collaboration','fictional-account',self.parents['collaboration']['id'])['payload'])

    def test_tampering_and_write_failure_never_repair_data_or_return_a_fabricated_result(self):
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER qa_fail_c03 BEFORE INSERT ON investigation_versions BEGIN SELECT RAISE(ABORT,'qa-marker'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.append()
        self.assertEqual(0,self.count())
        with self.store.transaction() as db: db.execute('DROP TRIGGER qa_fail_c03')
        self.append()
        with self.store.transaction() as db: db.execute('DROP TRIGGER investigation_immutable_investigation_versions_UPDATE')
        with self.assertRaises(Problem) as error: self.get()
        self.assertEqual(503,error.exception.status)
        with self.store.transaction() as db:
            db.execute("UPDATE investigation_versions SET payload='{}'")
            db.execute(GUARDS['investigation_immutable_investigation_versions_UPDATE'])
        with self.assertRaises(Problem) as error: self.get()
        self.assertEqual(503,error.exception.status)
        with self.store.transaction() as db: self.assertEqual('{}',db.execute('SELECT payload FROM investigation_versions').fetchone()[0])

    def test_parent_c02_integrity_is_rechecked_not_only_the_investigation_hash(self):
        self.append()
        with self.store.transaction() as db:
            db.execute('DROP TRIGGER detection_immutable_detection_runs_UPDATE')
            db.execute("UPDATE detection_runs SET actor='forged' WHERE tenant='collaboration'")
            db.execute(C02_GUARDS['detection_immutable_detection_runs_UPDATE'])
        with self.assertRaises(Problem) as error: self.get()
        self.assertEqual(503,error.exception.status)
        self.assertEqual(1,self.count())

    def test_analysis_limitations_are_not_fabricated_as_missing_observations_or_business_impediments(self):
        body=fixture('support','evidence');body['customer']='zero-baseline-account'
        for row in body['records'][:6]: row['payload']={field:0 for field in row['payload']}
        EvidenceRepository(self.store).ingest('demo',body)
        parent=self.c02.evaluate('demo','support','zero-baseline-account',1,AS_OF)
        doc=self.document('support',parent);doc['customer']='zero-baseline-account';doc['hypotheses']=[];doc['requirements']=[]
        payload=self.append(doc,parent=parent,tenant='support',customer='zero-baseline-account')['payload']
        self.assertEqual([],payload['missing_information']);self.assertEqual([],payload['supported_impediments'])
        self.assertEqual({'zero_baseline'},{entry['issue']['code'] for entry in payload['analysis_limitations']})
        self.assertEqual('not_established',payload['causal_status'])

    def test_cli_refuses_missing_databases_and_runs_against_a_prepared_snapshot(self):
        missing=self.root/'missing.sqlite3'
        run=subprocess.run([sys.executable,'-m','centerway.investigation','init','--db',str(missing)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(1,run.returncode);self.assertFalse(missing.exists())
        with self.assertRaises(ValueError): install(self.store)
        common=['--db',str(self.path),'--user','demo','--tenant','collaboration','--customer','fictional-account','--c02-run-id','1']
        run=subprocess.run([sys.executable,'-m','centerway.investigation','append',*common,'--file',str(ROOT/'examples/investigation/collaboration-declaration.json'),'--expected-version','0'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stderr);self.assertEqual('inactive',json.loads(run.stdout)['payload']['operational_state'])
        run=subprocess.run([sys.executable,'-m','centerway.investigation','get',*common,'--version','1'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stderr);self.assertEqual(1,json.loads(run.stdout)['version'])


class InvestigationSafetyTests(unittest.TestCase):
    def prepare(self,store,user,tenant,declared=False):
        install_integrations(store);config=fixture('collaboration','config');config['tenant']=tenant
        if declared:
            config['data_classification']='declared';config['provenance']['source_ref']='test:unverified-supplier-declaration'
        IntegrationRepository(store).append(user,tenant,config,0)
        install_evidence(store)
        for suffix,directory in (('evidence','detection'),('context','investigation')):
            body=fixture('collaboration',suffix,directory);body['tenant']=tenant
            EvidenceRepository(store).ingest(user,body)
        install_c02(store);c02=DetectionRepository(store);criteria=fixture('collaboration','criteria');criteria['tenant']=tenant
        c02.append_criteria(user,tenant,criteria,0)
        parent=c02.evaluate(user,tenant,'fictional-account',1,AS_OF)
        return parent

    def test_production_stays_inactive_even_with_supported_observations(self):
        from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'production.sqlite3';accounts=root/'accounts.json'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
            provision(path,root/'secrets.json','https://app.example.invalid',accounts)
            store=Store.open_existing(path);parent=self.prepare(store,'owner','collaboration',declared=True)
            before=path.read_bytes()
            with self.assertRaises(Problem): InvestigationRepository(store)
            self.assertEqual(before,path.read_bytes())
            install(store);repository=InvestigationRepository(store)
            doc=fixture('collaboration','declaration','investigation');doc['c02_run_id']=parent['id']
            payload=repository.append('owner','collaboration','fictional-account',parent['id'],doc,0)['payload']
            self.assertEqual(1,len(payload['supported_impediments']));self.assertEqual('inactive',payload['operational_state'])
            self.assertEqual('unconfirmed',payload['hypotheses'][0]['state']);self.assertEqual('not_established',payload['causal_status'])
            policy=ProductionPolicy(store);self.assertEqual([],policy.view(store,'owner')['registry'])
            with self.assertRaises(Problem) as error: policy.block_operation(store,'owner','collaboration')
            self.assertEqual(503,error.exception.status)
            with store.transaction() as db:
                for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                with self.assertRaises(sqlite3.IntegrityError): db.execute("INSERT INTO environments VALUES ('collaboration','c','Blocked','{}',0)")

    def test_private_demo_lease_is_preserved_for_existing_investigations(self):
        from centerway.preview import provision
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'demo.sqlite3';provision(path,root/'secrets.json','https://demo.example.invalid')
            store=Store.open_existing(path);parent=self.prepare(store,'founder','atlas')
            install(store);repository=InvestigationRepository(store)
            doc=fixture('collaboration','declaration','investigation');doc['tenant']='atlas';doc['c02_run_id']=parent['id']
            repository.append('founder','atlas','fictional-account',parent['id'],doc,0)
            with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
            for operation in (
                lambda:repository.get('founder','atlas','fictional-account',parent['id']),
                lambda:repository.append('founder','atlas','fictional-account',parent['id'],doc,1),
            ):
                with self.assertRaises(Problem) as error: operation()
                self.assertEqual(503,error.exception.status)
