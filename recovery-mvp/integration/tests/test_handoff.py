"""Golden examples are captured, not authored. Live tests require real private C03 HTTPS."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import socket
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from capture import capture
from matrix import render
from contracts import validate,validate_record,ContractError,source_hashes,fixture_difference
from sanitize import Sanitizer,UUID_RE,FIXED_IDS,TIME_RE


def load():
    return json.loads((HERE/'fixtures'/'v1'/'capture.json').read_text())


def case(document,ident):
    return next(c for c in document['cases'] if c['id']==ident)


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical=load()
        cls.live=capture(os.environ['CENTERWAY_TEST_CADDY'])

    def test_canonical_fixtures_match_fresh_real_c03_api(self):
        difference=fixture_difference(self.canonical,self.live)
        if difference is not None:
            self.fail('Canonical/live contract mismatch at '+difference)
        self.assertEqual(len(self.live['cases']),71)

    def test_openapi_version_schema_and_offline_validation(self):
        schema=json.loads((HERE/'fixtures'/'v1'/'bundle.schema.json').read_text())
        self.assertEqual((HERE/'fixtures'/'v1'/'CASE_MATRIX.md').read_text(),render(self.canonical))
        # Validation is offline: no resolver or client may fetch a remote schema.
        with patch.object(socket,'create_connection',side_effect=AssertionError('Offline schema made a network call')):
            for document in (self.canonical,self.live):
                validate(schema,document)
                self.assertEqual(document['contracts'],source_hashes())
                ids=[c['id'] for c in document['cases']]
                self.assertEqual(len(ids),len(set(ids)))
                for record in document['cases']: validate_record(record)

    def test_authorized_principals_pagination_and_transport_errors(self):
        d=self.live
        for actor in ('alice','reviewer','reader','bob'):
            session=case(d,f'session-{actor}-1')['response']['json']
            self.assertEqual(session['username'],actor)
            self.assertEqual(session['principal'],'http_'+actor)
        for ident in ('authentication-required-401','changed-scope-invalidates-session-401','revoked-session-401'):
            self.assertEqual(case(d,ident)['response']['status'],401)
        for ident in ('bob-denied-company-a-403','alice-denied-company-b-403','reader-denied-client-403','reader-denied-intervention-403','reviewer-denied-intervention-403'):
            self.assertEqual(case(d,ident)['response']['status'],403)
        for ident,status in [('unknown-route-404',404),('idempotency-conflict-409',409),('engine-error-receipt-422',422),('invalid-envelope-422',422),('directory-invalid-limit-422',422),('database-unavailable-503',503),('api-unavailable-503',503),('logout-204',204)]:
            self.assertEqual(case(d,ident)['response']['status'],status)
        first=case(d,'directory-page-1')['response']['json']; last=case(d,'directory-page-2')['response']['json']
        self.assertEqual(first['next_cursor'],first['data'][-1]['client_id'])
        self.assertIsNone(last['next_cursor'])
        self.assertNotEqual(first['data'][0]['client_id'],last['data'][0]['client_id'])
        self.assertEqual(case(d,'directory-page-empty')['response']['json']['data'],[])
        self.assertEqual(case(d,'network-failure')['transport_error'],'connection_refused')
        self.assertIsNone(case(d,'network-failure')['response'])

    def test_receipt_business_semantics_gaps_recovery_and_idempotency(self):
        d=self.live
        blocked=case(d,'intervene-01')['response']['json']['data']
        executed=case(d,'intervene-02')['response']['json']['data']
        replay=case(d,'intervention-idempotent-replay')['response']['json']['data']
        self.assertEqual(blocked['status'],'completed')
        self.assertEqual(blocked['result']['status'],'blocked')
        self.assertEqual(executed['status'],'completed')
        self.assertEqual(executed['result']['status'],'executed')
        self.assertEqual(executed,replay)
        self.assertEqual(case(d,'engine-error-receipt-422')['response']['json']['data']['status'],'error')
        missing=case(d,'investigate-01')['response']['json']['data']['result']['result']
        self.assertEqual(missing['status'],'inconclusivo')
        self.assertTrue(missing['missing_information'])
        self.assertEqual(missing['intervention_candidates'],[])
        for ident,status in [('evaluate_recovery-01','resultado_inconclusivo'),('evaluate_recovery-02','recuperacao_completa')]:
            recovery=case(d,ident)['response']['json']['data']['result']['result']
            self.assertEqual(recovery['status'],status)
            self.assertEqual(recovery['causal_attribution'],'not_established')
            self.assertEqual(recovery['independent_verification'],'not_established')
            self.assertTrue(recovery['execution_succeeded'])
        self.assertIsNone(case(d,'evaluate_recovery-01')['response']['json']['data']['result']['result']['improvement_observed'])
        self.assertTrue(case(d,'evaluate_recovery-02')['response']['json']['data']['result']['result']['improvement_observed'])
        final=case(d,'journey-with-error-receipt')['response']['json']['data']
        self.assertEqual(len(final['executions']),1)
        self.assertTrue(any(o['status']=='error' for o in final['operations']))
        self.assertTrue(any(w['next']=='review_execution_blocker' for w in final['work_items']))
        self.assertTrue(any(w['next']=='review_observed_recovery' for w in final['work_items']))
        self.assertEqual(final['authorization_basis'],'engine_checks_required_at_execution')
        detection=case(d,'detect-01')['response']['json']['data']['result']['result']
        self.assertTrue(detection['sustained_deterioration'])
        self.assertEqual(detection['independent_verification'],'not_established')
        self.assertEqual(detection['causal_inference'],'not_performed')
        report=case(d,'investigate-02')['response']['json']['data']['result']['result']
        self.assertEqual(report['status'],'impedimento_demonstrado')
        self.assertFalse(report['execution_authorized'])
        self.assertEqual(report['independent_verification'],'not_established')
        self.assertTrue(all(h['causal_status']=='not_established' for h in report['hypotheses']))

    def test_export_has_only_synthetic_data_typed_placeholders_and_valid_windows(self):
        for document in (self.canonical,self.live):
            Sanitizer([]).secret_safe(document)
            def inspect(value,key=''):
                if isinstance(value,dict):
                    for k,v in value.items(): inspect(v,k)
                elif isinstance(value,list):
                    for v in value: inspect(v,key)
                elif isinstance(value,str):
                    for match in UUID_RE.finditer(value):
                        self.assertTrue(match.group() in FIXED_IDS or re.fullmatch(r'00000000-0000-4000-8000-[0-9a-f]{12}',match.group()))
                    if TIME_RE.fullmatch(value): self.assertTrue(value.startswith(('2024-','2025-')))
                    if key in {'input_hash','request_key'}: self.assertRegex(value,r'^0{56}[0-9a-f]{8}$')
            inspect(document)
            # Sanitized examples retain actual business-window constraints; jitter is not evidence.
            contracts=[]
            for record in document['cases']:
                body=record['request']['json']
                if isinstance(body,dict) and body.get('operation')=='append_value' and body['arguments']['kind']=='contract':
                    c=body['arguments']['data']; contracts.append(c)
                    left,end,start,right=(datetime.fromisoformat(c[k]) for k in ('baseline_start','baseline_end','period_start','period_end'))
                    self.assertLess(left,end); self.assertLessEqual(end,start); self.assertLess(start,right)
            self.assertEqual(len(contracts),4)
            duration=lambda c:datetime.fromisoformat(c['period_end'])-datetime.fromisoformat(c['period_start'])
            self.assertEqual(duration(contracts[0]),duration(contracts[1]))
            self.assertEqual(contracts[0]['period_end'],contracts[1]['period_start'])
            self.assertEqual(duration(contracts[2]),duration(contracts[3]))
            execution=case(document,'journey-with-error-receipt')['response']['json']['data']['executions'][0]
            anchor=datetime.fromisoformat(execution['recorded_at'])
            self.assertLessEqual(datetime.fromisoformat(contracts[2]['period_end']),anchor)
            self.assertLessEqual(anchor,datetime.fromisoformat(contracts[3]['period_start']))

    def test_fail_closed_for_secrets_and_contract_drift(self):
        with self.assertRaises(ContractError): validate({'$ref':'https://example.invalid/schema'}, {})
        for timestamp in ('not-a-date','2025-02-30T00:00:00Z','2025-01-01T00:00:00','2025-01-01T00:00:00+01:99'):
            with self.assertRaises(ContractError): validate({'type':'string','format':'date-time'},timestamp)
        validate({'type':'string','format':'date-time'},'2025-01-01T00:00:00Z')
        secret='SYNTHETIC_PRIVATE_SECRET_NEVER_EXPORT'
        for value in ({'value':secret},{'dsn':'x'},{'password':'raw-value'},{'access_token':'x'*43},{'Authorization':'x'},{'email':'real@example.invalid'},{'extra':'Bearer '+'x'*43}):
            with self.assertRaises(ContractError): Sanitizer([secret]).secret_safe(value)
        for ident,mutate in [
            ('intervene-01',lambda c:c['response']['json']['data'].update(status='blocked')),
            ('evaluate_recovery-02',lambda c:c['response']['json']['data']['result']['result'].update(causal_attribution='established')),
            ('evaluate_recovery-02',lambda c:c['response']['json']['data']['result']['result'].update(improvement_observed='true')),
            ('journey-initial',lambda c:c['response']['json']['data'].update(contract_version='unknown')),
            ('directory-reader',lambda c:c['response']['json']['data'][0].update(secret='x')),
        ]:
            changed=copy.deepcopy(case(self.canonical,ident)); mutate(changed)
            with self.assertRaises(ContractError): validate_record(changed)
        for ident,mutate in [
            ('journey-initial',lambda c:c['response']['json']['data']['contracts'][0].update(unknown_field=True)),
            ('evaluate_recovery-01',lambda c:c['response']['json']['data']['result']['result'].update(improvement_observed=False)),
            ('append_value-01',lambda c:c['request']['json']['arguments']['data'].update(period_end='2025-01-01T12:00:00+00:00')),
            ('directory-reader',lambda c:c['response']['json']['data'][0].update(client_id='b2000000-0000-0000-0000-000000000001')),
        ]:
            changed=copy.deepcopy(case(self.canonical,ident)); mutate(changed)
            self.assertIsNotNone(fixture_difference(case(self.canonical,ident),changed))

    def test_placeholder_bindings_cannot_hide_broken_references_or_types(self):
        a='00000000-0000-4000-8000-000000000001'; b='00000000-0000-4000-8000-000000000002'
        c='00000000-0000-4000-8000-000000000003'
        self.assertIsNone(fixture_difference({'id':a,'ref':a},{'id':b,'ref':b}))
        self.assertIsNotNone(fixture_difference({'id':a,'ref':a},{'id':b,'ref':c}))
        self.assertIsNotNone(fixture_difference({'ids':[a,b]},{'ids':[c,c]}))
        self.assertIsNotNone(fixture_difference({'value':True},{'value':1}))
        self.assertIsNotNone(fixture_difference({'value':None},{'value':0}))
        self.assertIsNotNone(fixture_difference({'x':1},{'x':1,'extra':2}))


if __name__=='__main__': unittest.main()
