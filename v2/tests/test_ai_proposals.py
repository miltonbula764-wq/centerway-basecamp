"""Explicit test fixtures only: these responses are NOT real model inference."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator

from centerway.ai_adapter import AIAdapter,Completion,ProviderError,configured_adapter
from centerway.ai_proposals import ProposalRepository,install,GUARDS
from centerway.c04_contract import RESPONSE_SCHEMA
from centerway.core import Problem
from centerway.detection import DetectionRepository,install as install_c02
from centerway.evidence import EvidenceRepository,install as install_evidence
from centerway.integrations import IntegrationRepository,install as install_integrations,canonical
from centerway.investigation import InvestigationRepository,install as install_c03
from centerway.ops import backup
from centerway.store import Store

ROOT=Path(__file__).resolve().parents[1]
AS_OF='2026-01-01T00:04:00Z'


def fixture(tenant,suffix,directory='detection'):
    return json.loads((ROOT/'examples'/directory/f'{tenant}-{suffix}.json').read_text())


def fixture_response(context,kind='action_proposal',reason=None):
    """Deterministic test data, not a simulator offered to runtime users."""
    investigation=context['investigation'];caps=context['configuration']['capabilities']
    kind=kind if caps else 'no_action';refs=[]
    if kind=='action_proposal':
        for condition in caps[0]['conditions']:
            for fact in investigation['facts']:
                if fact['definition_id']==condition['evidence_ref'] and fact['provenance']['occurred_at']==context['lineage']['as_of'] and condition['field'] in fact['payload']:
                    refs.append({'evidence_id':fact['evidence_id'],'field':condition['field']})
        if not refs:
            fact=investigation['facts'][-1] if investigation['facts'] else None
            refs=[{'evidence_id':fact['evidence_id'],'field':next(iter(fact['payload']))}] if fact else []
    return {'schema_version':1,'context_hash':context['context_hash'],
            'hypothesis_reviews':[{'hypothesis_id':h['id'],'disposition':'retain_unconfirmed','support_refs':h['support_refs'],'contrary_refs':h['contrary_refs']} for h in investigation['hypotheses']],
            'impediment_refs':[r['requirement_id'] for r in investigation['supported_impediments']],
            'contradiction_refs':list(range(len(investigation['contradictions']))),
            'missing_information_refs':list(range(len(investigation['missing_information']))),
            'analysis_limitation_refs':list(range(len(investigation['analysis_limitations']))),
            'recommendation':{'kind':kind,'capability_id':caps[0]['id'] if kind=='action_proposal' else None,
                              'reason_code':reason or ('catalogue_match' if kind=='action_proposal' else 'human_review_required' if kind=='human_review' else 'no_safe_action'),
                              'evidence_refs':refs,'criterion_refs':[r['criterion_id'] for r in investigation['c02_findings']['criteria_results'] if r['state']=='demonstrated']}}


class FixtureAdapter(AIAdapter):
    inference_kind='test_fixture'
    def __init__(self,transform=None,callback=None,kind='action_proposal',raw=None,reason=None):
        self.calls=0;self.transform=transform;self.callback=callback;self.kind=kind;self.raw=raw;self.reason=reason
    def descriptor(self): return {'protocol':'test-fixture','requested_model':'fixture-not-a-real-model','inference_kind':self.inference_kind}
    def generate(self,context):
        self.calls+=1
        if self.callback: self.callback(context)
        response=fixture_response(context,self.kind,self.reason)
        if self.transform: self.transform(response,context)
        return Completion(self.raw if self.raw is not None else canonical(response),'fixture-not-a-real-model','fixture-response')


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'runtime.sqlite3'
        self.store=Store(self.path,seed_demo=False)
        with self.store.transaction() as db:
            db.executemany('INSERT INTO memberships VALUES (?,?,?)',[
                *[('demo',tenant,'operator') for tenant in ('collaboration','billing','support')],
                ('atlas','collaboration','operator'),('leitor','collaboration','viewer')])
        install_integrations(self.store)
        for tenant in ('collaboration','billing','support'): IntegrationRepository(self.store).append('demo',tenant,fixture(tenant,'config','c04'),0)
        install_evidence(self.store)
        for tenant in ('collaboration','billing','support'):
            EvidenceRepository(self.store).ingest('demo',fixture(tenant,'evidence'))
            EvidenceRepository(self.store).ingest('demo',fixture(tenant,'context','c04'))
        install_c02(self.store);self.c02=DetectionRepository(self.store);self.parents={}
        for tenant in ('collaboration','billing','support'):
            self.c02.append_criteria('demo',tenant,fixture(tenant,'criteria'),0)
            self.parents[tenant]=self.c02.evaluate('demo',tenant,'fictional-account',1,AS_OF)
        install_c03(self.store);self.c03=InvestigationRepository(self.store)
        for tenant in self.parents:
            doc=fixture(tenant,'declaration','investigation');doc['c02_run_id']=self.parents[tenant]['id']
            self.c03.append('demo',tenant,'fictional-account',self.parents[tenant]['id'],doc,0)
        install(self.store);self.repo=ProposalRepository(self.store)

    def tearDown(self): self.temp.cleanup()

    def propose(self,adapter=None,request='request-1',tenant='collaboration',customer='fictional-account',parent=None,version=1,user='demo'):
        return self.repo.propose(user,tenant,customer,(parent or self.parents[tenant])['id'],version,request,adapter)

    def get(self,request='request-1',tenant='collaboration',user='demo'):
        return self.repo.get(user,tenant,'fictional-account',request)

    def counts(self):
        with self.store.transaction() as db:
            return tuple(db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('c04_requests','c04_results'))

    def new_subject(self,customer,paused=True,moment=AS_OF):
        body=fixture('collaboration','evidence');body['customer']=customer;EvidenceRepository(self.store).ingest('demo',body)
        body=fixture('collaboration','context','c04');body['customer']=customer
        body['records'][0]['occurred_at']=moment;body['records'][0]['payload']['paused']=paused
        record_id=EvidenceRepository(self.store).ingest('demo',body)['record_ids'][0]
        parent=self.c02.evaluate('demo','collaboration',customer,1,AS_OF)
        doc=fixture('collaboration','declaration','investigation');doc.update(customer=customer,c02_run_id=parent['id'])
        doc['hypotheses'][0]['support_refs']=[{'evidence_id':record_id,'field':'paused'}]
        self.c03.append('demo','collaboration',customer,parent['id'],doc,0)
        return parent

    def test_no_credentials_or_ambient_key_never_falls_back_to_simulation_or_network(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'ambient-key-must-not-be-used'}),patch('centerway.ai_adapter.build_opener',side_effect=AssertionError('Network forbidden')):
            result=self.propose(configured_adapter())
        payload=result['result']['payload'];receipt=result['result']['receipt']
        self.assertEqual('unavailable',payload['status']);self.assertEqual(['provider_not_configured'],payload['reason_codes'])
        self.assertEqual('unavailable',receipt['inference_kind']);self.assertFalse(receipt['completion_received'])
        self.assertIsNone(receipt['requested_model']);self.assertIsNone(payload['model_response'])
        self.assertNotIn('ambient-key-must-not-be-used',canonical(result));self.assertEqual((1,1),self.counts())

    def test_three_saas_explicit_fixtures_ground_only_declared_proposals_never_authorize(self):
        for tenant in ('collaboration','billing','support'):
            adapter=FixtureAdapter();result=self.propose(adapter,tenant=tenant);payload=result['result']['payload']
            self.assertEqual('test_fixture',result['result']['receipt']['inference_kind'])
            self.assertEqual('fixture-not-a-real-model',result['result']['receipt']['reported_model'])
            self.assertEqual('proposal_validated',payload['status']);self.assertFalse(payload['execution_authorized'])
            self.assertEqual('not_granted',payload['authorization']);self.assertTrue(payload['human_review_required'])
            self.assertEqual('inactive',payload['operational_state']);self.assertEqual('not_established',payload['causal_status'])
            self.assertEqual(fixture(tenant,'config','c04')['capabilities'][0]['id'],payload['validated_capability_id'])
            self.assertEqual('not_performed',payload['verification_status']);self.assertTrue(payload['verification_plan']['operational'])
            self.assertEqual('matched',result['result']['receipt']['revalidation']);self.assertEqual(1,adapter.calls)
            Draft202012Validator(RESPONSE_SCHEMA).validate(payload['model_response'])
            self.assertEqual(payload,self.get(tenant=tenant)['result']['payload'])
            context=result['request']['context'];self.assertEqual(tenant,context['lineage']['tenant'])
            self.assertEqual('saas_contract_for_selected_customer',context['goal_scope']);self.assertTrue(context['configuration']['value_goals'])

    def test_none_and_human_review_are_valid_outcomes_without_forcing_an_action(self):
        result=self.propose(FixtureAdapter(kind='no_action'))['result']['payload']
        self.assertEqual('no_action',result['status']);self.assertIsNone(result['validated_capability_id'])
        result=self.propose(FixtureAdapter(kind='human_review'),request='review')['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertIn('model_requested_review',result['reason_codes'])
        result=self.propose(FixtureAdapter(kind='no_action',reason='no_deterioration'),request='false-justification')['result']['payload']
        self.assertEqual('refused',result['status']);self.assertEqual(['unsupported_justification'],result['reason_codes'])

    def test_invented_actions_facts_causality_permissions_versions_and_prose_are_refused(self):
        invalid=[
            lambda r,c:r['recommendation'].update(capability_id='external-unlisted-action'),
            lambda r,c:r['recommendation'].update(evidence_refs=[{'evidence_id':26,'field':'paused'}]),
            lambda r,c:r['recommendation'].update(evidence_refs=[{'evidence_id':13,'field':'invented'}]),
            lambda r,c:r.update(context_hash='0'*64),
            lambda r,c:r.update(schema_version=True),
            lambda r,c:r.update(confirmed_causes=['invented']),
            lambda r,c:r.update(execution_authorized=True),
            lambda r,c:r.update(rationale='unsupported-private-marker'),
            lambda r,c:r['hypothesis_reviews'][0].update(state='confirmed'),
            lambda r,c:r.update(hypothesis_reviews=[]),
            lambda r,c:r.update(impediment_refs=['not-a-supported-impediment']),
            lambda r,c:r.update(contradiction_refs=[0]),
            lambda r,c:r['recommendation'].update(criterion_refs=['foreign-criterion']),
            lambda r,c:r['recommendation'].update(verification_status='passed'),
        ]
        for i,transform in enumerate(invalid):
            result=self.propose(FixtureAdapter(transform=transform),request='invalid-'+str(i))['result']
            self.assertEqual('refused',result['payload']['status']);self.assertFalse(result['payload']['execution_authorized'])
            self.assertIsNone(result['payload']['model_response']);self.assertEqual(64,len(result['response_hash']))
            self.assertNotIn('unsupported-private-marker',canonical(result))

    def test_catalogue_conditions_are_evaluated_without_inferring_persistence(self):
        older=self.new_subject('older-observation',moment='2026-01-01T00:03:00Z')
        result=self.propose(FixtureAdapter(),customer='older-observation',parent=older)['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertIn('conditions_not_demonstrated',result['reason_codes'])
        self.assertEqual('unknown',result['condition_checks'][0]['state'])
        false=self.new_subject('false-condition',paused=False)
        result=self.propose(FixtureAdapter(),customer='false-condition',parent=false,request='false')['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertEqual('not_satisfied',result['condition_checks'][0]['state'])
        result=self.propose(FixtureAdapter(transform=lambda r,c:r['recommendation'].update(evidence_refs=[{'evidence_id':1,'field':'value'}])),request='missing-citation')['result']['payload']
        self.assertEqual('refused',result['status']);self.assertIn('condition_evidence_not_cited',result['reason_codes'])

    def test_contradictions_and_insufficiency_cannot_be_hidden_or_arbitrated(self):
        body=fixture('collaboration','context','c04');body['records'][0]['external_id']='opposite';body['records'][0]['payload']['paused']=False
        EvidenceRepository(self.store).ingest('demo',body)
        parent=self.c02.evaluate('demo','collaboration','fictional-account',1,AS_OF)
        doc=fixture('collaboration','declaration','investigation');doc['c02_run_id']=parent['id']
        self.c03.append('demo','collaboration','fictional-account',parent['id'],doc,0)
        result=self.propose(FixtureAdapter(kind='human_review'),parent=parent)['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertIn('contradictory_evidence',result['reason_codes'])
        result=self.propose(FixtureAdapter(kind='human_review',transform=lambda r,c:r.update(contradiction_refs=[])),parent=parent,request='hide-conflict')['result']['payload']
        self.assertEqual('refused',result['status']);self.assertIn('omitted_or_invented_uncertainty',result['reason_codes'])
        empty=self.c02.evaluate('demo','collaboration','empty',1,AS_OF)
        doc.update(customer='empty',c02_run_id=empty['id']);doc['hypotheses'][0]['support_refs']=[]
        self.c03.append('demo','collaboration','empty',empty['id'],doc,0)
        result=self.propose(FixtureAdapter(kind='human_review'),customer='empty',parent=empty,request='empty')['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertIn('insufficient_evidence',result['reason_codes'])

    def test_permissions_and_isolation_are_checked_before_inference_and_on_audit_reads(self):
        adapter=FixtureAdapter()
        for user,tenant in (('leitor','collaboration'),('atlas','billing'),('unknown','collaboration')):
            with self.assertRaises(Problem) as error: self.propose(adapter,user=user,tenant=tenant)
            self.assertEqual(403,error.exception.status)
        self.assertEqual(0,adapter.calls);self.assertEqual((0,0),self.counts())
        self.propose(adapter);self.assertEqual('proposal_validated',self.get(user='leitor')['result']['payload']['status'])
        with self.assertRaises(Problem): self.get(tenant='billing',user='atlas')
        with self.assertRaises(Problem): self.repo.get('demo','collaboration','another-client','request-1')

    def test_permission_revocation_during_inference_is_audited_and_refused(self):
        def revoke(_):
            with self.store.transaction() as db: db.execute("UPDATE memberships SET role='viewer' WHERE user_id='demo' AND tenant='collaboration'")
        with self.assertRaises(Problem) as error: self.propose(FixtureAdapter(callback=revoke))
        self.assertEqual(403,error.exception.status)
        payload=self.get(user='atlas')['result']['payload']
        self.assertEqual('refused',payload['status']);self.assertIn('authorization_changed',payload['reason_codes'])
        self.assertEqual((1,1),self.counts())

    def test_new_data_or_c03_revisions_during_inference_force_review_without_locks(self):
        def add_data(_):
            body=fixture('collaboration','context','c04');body['records'][0]['external_id']='received-during-inference';body['records'][0]['payload']['paused']=False
            EvidenceRepository(self.store).ingest('demo',body)
        result=self.propose(FixtureAdapter(callback=add_data))['result']
        self.assertEqual('human_review',result['payload']['status']);self.assertIn('context_changed_during_inference',result['payload']['reason_codes'])
        self.assertEqual('context_changed',result['receipt']['revalidation'])
        self.assertNotEqual(result['receipt']['post_context_hash'],self.get()['request']['context_hash'])
        def revise(_):
            doc=fixture('billing','declaration','investigation');doc['c02_run_id']=self.parents['billing']['id']
            doc['hypotheses'][0]['statement']='Revised while provider was running'
            self.c03.append('demo','billing','fictional-account',self.parents['billing']['id'],doc,1)
        result=self.propose(FixtureAdapter(callback=revise),tenant='billing',request='revision')['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertIn('context_changed_during_inference',result['reason_codes'])

    def test_adapter_cannot_mutate_authoritative_context_or_catalogue(self):
        def mutate(context): context['configuration']['capabilities'][0]['id']='invented-during-provider-call'
        result=self.propose(FixtureAdapter(callback=mutate))['result']['payload']
        self.assertEqual('refused',result['status']);self.assertIn('capability_not_declared',result['reason_codes'])
        self.assertEqual('reopen-delivery-queue',self.get()['request']['context']['configuration']['capabilities'][0]['id'])

    def test_exact_retry_and_concurrent_pending_request_never_repeat_inference(self):
        started=threading.Event();release=threading.Event()
        def wait(_): started.set();self.assertTrue(release.wait(5))
        adapter=FixtureAdapter(callback=wait)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first=pool.submit(self.propose,adapter)
            self.assertTrue(started.wait(5))
            try:
                with self.assertRaises(Problem) as error: self.propose(adapter)
                self.assertEqual(409,error.exception.status)
                with self.assertRaises(Problem): self.get()
                self.assertEqual(1,adapter.calls)
            finally: release.set()
            result=first.result(timeout=10)
        repeated=self.propose(adapter)
        self.assertTrue(repeated['reused']);self.assertEqual(result['result'],repeated['result']);self.assertEqual(1,adapter.calls)
        self.assertEqual((1,1),self.counts())

    def test_interrupted_reserved_requests_are_not_automatically_retried(self):
        def interrupt(_): raise KeyboardInterrupt()
        adapter=FixtureAdapter(callback=interrupt)
        with self.assertRaises(KeyboardInterrupt): self.propose(adapter)
        self.assertEqual((1,0),self.counts())
        with self.assertRaises(Problem) as error: self.propose(adapter)
        self.assertEqual(409,error.exception.status);self.assertEqual(1,adapter.calls)

    def test_invalid_raw_responses_and_provider_failures_do_not_leak_untrusted_content(self):
        for i,raw in enumerate(('not-json-private-marker','{"schema_version":1,"schema_version":2}','{"x":NaN}','x'*65537)):
            result=self.propose(FixtureAdapter(raw=raw),request='raw-'+str(i))
            self.assertEqual('refused',result['result']['payload']['status'])
            self.assertNotIn('not-json-private-marker',canonical(result))
        def fail(_): raise ProviderError('private-untrusted-error-marker')
        result=self.propose(FixtureAdapter(callback=fail),request='provider-failed')
        self.assertEqual('human_review',result['result']['payload']['status'])
        self.assertNotIn('private-untrusted-error-marker',canonical(result))

    def test_previous_engines_and_business_tables_are_unchanged_and_backup_preserves_audit(self):
        tables=('environments','observations','cases','executions','history','integration_versions','evidence_items','evidence_batches','detection_runs','detection_criteria','investigation_versions')
        with self.store.transaction() as db: before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        result=self.propose(FixtureAdapter())
        with self.store.transaction() as db:
            self.assertEqual(before,{t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables})
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM c04_results')
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE c04_requests SET actor='forged'")
        self.assertEqual('verified',backup(self.path,self.root/'snapshot.sqlite3')['status'])
        copied=ProposalRepository(Store.open_existing(self.root/'snapshot.sqlite3'))
        self.assertEqual(result['result'],copied.get('demo','collaboration','fictional-account','request-1')['result'])

    def test_superseded_catalogue_cannot_turn_an_old_allowed_capability_into_current_permission(self):
        config=fixture('collaboration','config','c04');config['capabilities']=[]
        IntegrationRepository(self.store).append('demo','collaboration',config,1)
        result=self.propose(FixtureAdapter())['result']['payload']
        self.assertEqual('human_review',result['status']);self.assertIn('configuration_superseded',result['reason_codes'])
        self.assertIsNone(result['validated_capability_id'])

    def test_context_limit_refuses_without_truncation_or_provider_call(self):
        tenant='large-saas'
        with self.store.transaction() as db: db.execute("INSERT INTO memberships VALUES ('demo',?,'operator')",(tenant,))
        config=fixture('collaboration','config','c04');config['tenant']=tenant
        config['evidence'][0]['fields'].append({'name':'note','type':'string','required':False})
        IntegrationRepository(self.store).append('demo',tenant,config,0)
        body=fixture('collaboration','evidence');body['tenant']=tenant;EvidenceRepository(self.store).ingest('demo',body)
        template=fixture('collaboration','context','c04');template['tenant']=tenant
        for offset in range(0,110,20):
            rows=[]
            for i in range(offset,min(offset+20,110)):
                record=deepcopy(template['records'][0]);record['external_id']='large-'+str(i);record['payload']['note']='x'*1990+str(i)
                rows.append(record)
            EvidenceRepository(self.store).ingest('demo',{**template,'records':rows})
        criteria=fixture('collaboration','criteria');criteria['tenant']=tenant;self.c02.append_criteria('demo',tenant,criteria,0)
        parent=self.c02.evaluate('demo',tenant,'fictional-account',1,AS_OF)
        doc=fixture('collaboration','declaration','investigation');doc.update(tenant=tenant,c02_run_id=parent['id']);doc['hypotheses']=[];doc['requirements']=[]
        self.c03.append('demo',tenant,'fictional-account',parent['id'],doc,0)
        adapter=FixtureAdapter()
        with self.assertRaises(Problem) as error: self.propose(adapter,tenant=tenant,parent=parent)
        self.assertEqual(413,error.exception.status);self.assertEqual(0,adapter.calls);self.assertEqual((0,0),self.counts())

    def test_tamper_is_refused_without_repair_and_cli_is_unavailable_without_credentials(self):
        cli=[sys.executable,'-m','centerway.ai_proposals']
        run=subprocess.run(cli+['init','--db',str(self.root/'missing.sqlite3')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(1,run.returncode);self.assertFalse((self.root/'missing.sqlite3').exists())
        with self.assertRaises(ValueError): install(self.store)
        args=['--db',str(self.path),'--user','demo','--tenant','collaboration','--customer','fictional-account','--request-id','cli-request']
        run=subprocess.run(cli+['propose',*args,'--c02-run-id','1','--c03-version','1'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stderr);self.assertEqual('unavailable',json.loads(run.stdout)['result']['payload']['status'])
        with self.store.transaction() as db: db.execute('DROP TRIGGER c04_immutable_c04_results_UPDATE')
        with self.assertRaises(Problem): self.get(request='cli-request')
        with self.store.transaction() as db:
            db.execute("UPDATE c04_results SET payload='{}'")
            db.execute(GUARDS['c04_immutable_c04_results_UPDATE'])
        with self.assertRaises(Problem) as error: self.get(request='cli-request')
        self.assertEqual(503,error.exception.status)


class ProposalSafetyTests(unittest.TestCase):
    def prepare(self,store,user,tenant,declared=False):
        install_integrations(store);config=fixture('collaboration','config','c04');config['tenant']=tenant
        if declared:
            config['data_classification']='declared';config['provenance']['source_ref']='test:unverified-declaration'
        IntegrationRepository(store).append(user,tenant,config,0);install_evidence(store)
        for suffix,directory in (('evidence','detection'),('context','c04')):
            body=fixture('collaboration',suffix,directory);body['tenant']=tenant;EvidenceRepository(store).ingest(user,body)
        install_c02(store);c02=DetectionRepository(store);criteria=fixture('collaboration','criteria');criteria['tenant']=tenant
        c02.append_criteria(user,tenant,criteria,0);parent=c02.evaluate(user,tenant,'fictional-account',1,AS_OF)
        install_c03(store);doc=fixture('collaboration','declaration','investigation');doc.update(tenant=tenant,c02_run_id=parent['id'])
        InvestigationRepository(store).append(user,tenant,'fictional-account',parent['id'],doc,0)
        return parent

    def test_production_default_is_unavailable_and_test_fixtures_cannot_masquerade_as_real_ai(self):
        from centerway.production import provision,ProductionPolicy,BUSINESS_TABLES
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);accounts=root/'accounts.json';path=root/'production.sqlite3'
            accounts.write_text(json.dumps({'accounts':[{'user':'owner','memberships':[{'tenant':'collaboration','role':'operator'}]}]}));accounts.chmod(0o600)
            provision(path,root/'secrets.json','https://app.example.invalid',accounts)
            store=Store.open_existing(path);parent=self.prepare(store,'owner','collaboration',declared=True)
            before=path.read_bytes()
            with self.assertRaises(Problem): ProposalRepository(store)
            self.assertEqual(before,path.read_bytes());install(store);repository=ProposalRepository(store)
            result=repository.propose('owner','collaboration','fictional-account',parent['id'],1,'unavailable')
            self.assertEqual('unavailable',result['result']['payload']['status'])
            adapter=FixtureAdapter();result=repository.propose('owner','collaboration','fictional-account',parent['id'],1,'fixture',adapter)
            self.assertEqual('refused',result['result']['payload']['status']);self.assertEqual(0,adapter.calls)
            self.assertIn('fixture_forbidden_in_production',result['result']['payload']['reason_codes'])
            policy=ProductionPolicy(store)
            with self.assertRaises(Problem) as error: policy.block_operation(store,'owner','collaboration')
            self.assertEqual(503,error.exception.status)
            with store.transaction() as db:
                for table in BUSINESS_TABLES: self.assertEqual(0,db.execute('SELECT count(*) FROM '+table).fetchone()[0])
                with self.assertRaises(sqlite3.IntegrityError): db.execute("INSERT INTO environments VALUES ('collaboration','c','Blocked','{}',0)")

    def test_private_demo_expiration_during_a_call_is_recorded_without_reopening_access(self):
        from centerway.preview import provision
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'demo.sqlite3';provision(path,root/'secrets.json','https://demo.example.invalid')
            store=Store.open_existing(path);parent=self.prepare(store,'founder','atlas');install(store);repository=ProposalRepository(store)
            def expire(_):
                with store.transaction() as db: db.execute("UPDATE preview_metadata SET expires='2000-01-01T00:00:00+00:00'")
            with self.assertRaises(Problem) as error:
                repository.propose('founder','atlas','fictional-account',parent['id'],1,'expires-during-call',FixtureAdapter(callback=expire))
            self.assertEqual(503,error.exception.status)
            with self.assertRaises(Problem): repository.get('founder','atlas','fictional-account','expires-during-call')
            with store.transaction() as db:
                payload=json.loads(db.execute('SELECT payload FROM c04_results').fetchone()[0])
                self.assertEqual('refused',payload['status']);self.assertFalse(payload['execution_authorized'])
