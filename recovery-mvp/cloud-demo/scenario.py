"""Explicit synthetic fixture through the unchanged authenticated HTTPS API.
Verification records are test fixtures by a separate demo login, never human proof.
"""
import hashlib
import http.client
import json
from pathlib import Path
import ssl
from datetime import datetime, timedelta, timezone
import uuid

from runtime import ROOT, PersistentDemo, private_json
from demo.provision import T, C, S


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class Scenario:
    def __init__(self, demo):
        self.demo = demo
        self.context = ssl.create_default_context(cafile=str(demo.state/'pki'/'ca.crt'))
        self.tokens = {}

    def request(self, method, path, data=None, user='alice'):
        headers = {'Content-Type':'application/json'}
        if user in self.tokens:
            headers['Authorization'] = 'Bearer '+self.tokens[user]
        conn = http.client.HTTPSConnection('localhost',self.demo.port,context=self.context,timeout=30)
        try:
            conn.request(method,path,json.dumps(data) if data is not None else None,headers)
            response = conn.getresponse()
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
        finally:
            conn.close()

    def login(self, user):
        status, body = self.request('POST','/v1/sessions',dict(username=user,password=self.demo.credentials[user]),user)
        if status != 201:
            raise RuntimeError('Synthetic fixture login failed')
        self.tokens[user] = body['access_token']

    def command(self, operation, arguments, user='alice', key=None):
        payload = dict(request_id=key or uid(),operation=operation,arguments=arguments)
        status, body = self.request('POST',f'/v1/tenants/{T}/clients/{C}/operations',payload,user)
        if status != 200 or body['data']['status'] != 'completed':
            raise RuntimeError('Synthetic fixture command rejected: '+operation)
        return body['data']['result'], payload

    def value(self, kind, data, ident=None, revision=0):
        return self.command('append_value',dict(kind=kind,id=ident or uid(),expected_revision=revision,
            reason='SYNTHETIC C03 fixture; never real business evidence',data=data))[0]

    def investigation(self, inv, kind, data, user='alice'):
        return self.command('append_investigation',dict(investigation_id=inv,kind=kind,id=uid(),expected_revision=0,
            reason='SYNTHETIC C03 fixture; not human or independent verification',data=data),user)[0]

    def run(self):
        if (self.demo.state/'scenario-started.json').exists():
            raise ValueError('Scenario already started; inspect receipts instead of reseeding')
        private_json(self.demo.state/'scenario-started.json',dict(synthetic_only=True,started_at=now()))
        self.login('alice'); self.login('reviewer')
        anchor = datetime.now(timezone.utc)
        stamp = lambda seconds: (anchor+timedelta(seconds=seconds)).isoformat()
        contract = dict(objective='SYNTHETIC contracted business outcome',expected_outcome='SYNTHETIC agreed outcome total',
            indicator='SYNTHETIC outcome units',unit='units',measurement_method='synthetic test total',direction='higher',
            baseline=10,minimum_acceptable=15,target=20,baseline_start=stamp(-120),baseline_end=stamp(-80),
            period_start=stamp(-60),period_end=stamp(-40),source_id=S,source_revision=1,
            baseline_reference='synthetic://c03/baseline')
        k = self.value('contract',contract)['id']
        def outcome(revision,start,end,value):
            return dict(contract_id=k,contract_revision=revision,source_id=S,source_revision=1,evidence_type='outcome',
                quality='verified',observed_value=value,unit='units',measurement_method='synthetic test total',
                period_start=start,period_end=end,reference='synthetic://c03/declared-outcome',
                content_sha256=hashlib.sha256(f'SYNTHETIC {revision} {value}'.encode()).hexdigest())
        self.value('evidence',outcome(1,contract['period_start'],contract['period_end'],9))
        contract.update(period_start=stamp(-40),period_end=stamp(-20))
        self.value('contract',contract,k,1)
        self.value('evidence',outcome(2,contract['period_start'],contract['period_end'],8))
        detection,_ = self.command('detect',dict(contract_id=k,revisions=[1,2],as_of=now(),required_periods=2))
        inv = uid()
        self.command('open_investigation',dict(id=inv,detection_id=detection['id'],contract_revision=2,
            question='SYNTHETIC check of explicit prerequisite; no causal claim'))
        factor = self.investigation(inv,'factor',dict(scope='internal',category='SYNTHETIC demonstration prerequisite',
            hypothesis='SYNTHETIC missing prerequisite may impede outcome; unproven causality',
            requirement='SYNTHETIC agreed prerequisite must exist',condition='SYNTHETIC prerequisite is available',
            test_protocol='SYNTHETIC fixture comparison',assessment_at=stamp(-30),control='saas',responsible_party='SYNTHETIC team'))
        for purpose, assertion in [('requirement_applies',True),('condition_met',False)]:
            e = self.investigation(inv,'evidence',dict(factor_id=factor['id'],factor_revision=1,purpose=purpose,
                kind='document',assertion=assertion,source_id=S,source_revision=1,reference='synthetic://c03/prerequisite',
                content_sha256='a'*64,collected_at=now()))
            self.investigation(inv,'verification',dict(evidence_id=e['id'],evidence_revision=1,verdict='confirmed',
                checked_assertion=assertion,method='SYNTHETIC scripted fixture, not human verification',
                explanation='SYNTHETIC separate test principal only; independence not established',source_id=S,source_revision=1,
                reference='synthetic://c03/test-review',content_sha256='b'*64,checked_at=now()),'reviewer')
        report,_ = self.command('investigate',dict(investigation_id=inv,as_of=now()))
        # Catalog + bounded prior authorization were installed administratively by setup_policy.
        decision, intervention_request = self.command('intervene',dict(investigation_id=inv,report_id=report['id']))
        if decision['status'] != 'executed':
            raise RuntimeError('Synthetic-only intervention blocked')
        status, journey = self.request('GET',f'/v1/tenants/{T}/clients/{C}/journey')
        if status != 200:
            raise RuntimeError('Synthetic journey unavailable')
        execution = next(e for e in journey['data']['executions'] if e['id'] == decision['execution_id'])
        anchor = datetime.fromisoformat(execution['recorded_at'].replace('Z','+00:00'))
        windows = []
        for expected,left,right in [(2,-20,-10),(3,10,20)]:
            start=(anchor+timedelta(milliseconds=left)).isoformat(); end=(anchor+timedelta(milliseconds=right)).isoformat()
            contract.update(period_start=start,period_end=end)
            self.value('contract',contract,k,expected)
            windows.append((start,end))
        self.value('evidence',outcome(3,*windows[0],8))
        plan = uid()
        self.command('plan_recovery',dict(id=plan,decision_id=decision['id'],pre_revision=3,post_revision=4,
            reason='SYNTHETIC millisecond windows solely for deterministic demonstration'))
        missing,_ = self.command('evaluate_recovery',dict(plan_id=plan,as_of=now()))
        # Supplying a declared synthetic outcome is fixture input, not a derived business result.
        self.value('evidence',outcome(4,*windows[1],15))
        recovered,_ = self.command('evaluate_recovery',dict(plan_id=plan,as_of=now()))
        result=dict(synthetic_only=True,contract_id=k,detection_id=detection['id'],investigation_id=inv,
            decision_id=decision['id'],plan_id=plan,intervention_request=intervention_request,
            missing_status=missing['result']['status'],recovery_result=recovered['result'])
        private_json(self.demo.state/'scenario-result.json',result)
        return result


def setup_policy(demo):
    from demo.provision import T,C
    # Administrative setup only, never available to an API caller. One synthetic flag, one attempt,
    # risk <=1, account http_alice, valid for 24 hours; no real connectors or business effects.
    ids = [uid() for _ in range(3)]
    resource, catalog, policy = ids
    demo.sql(f"""INSERT INTO centerway.sandbox_flags VALUES('{T}','{C}','{resource}','isolated_synthetic',false,NULL);
    INSERT INTO centerway.intervention_catalog VALUES('{T}','{catalog}','SYNTHETIC demonstration flag',
    'SYNTHETIC demonstration prerequisite','internal','saas','set_synthetic_flag',false,true,1,1);
    INSERT INTO centerway.intervention_policies VALUES('{T}','{C}','{policy}','{catalog}','{resource}','http_alice',
    clock_timestamp(),clock_timestamp()+interval '24 hours',1,1,interval '1 hour',interval '1 hour');""")


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',required=True); parser.add_argument('--caddy',required=True)
    args=parser.parse_args()
    demo=PersistentDemo(args.state,args.caddy)
    demo.read_manifest()
    try:
        result=Scenario(demo).run()
        print('SYNTHETIC fixture completed; causal attribution not established. Private result: '+str(demo.state/'scenario-result.json'))
    except Exception:
        print('SYNTHETIC fixture failed; inspect private receipts; do not automatically reseed.',file=__import__('sys').stderr)
        raise SystemExit(1)
