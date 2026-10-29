import concurrent.futures
import json
import unittest
import uuid
from datetime import datetime,timedelta
import test_foundation as f
import test_investigation as i

class JourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if f.query("SELECT 1 FROM pg_roles WHERE rolname='investigator_a'",'postgres').stdout.strip()!='1':
            i.InvestigationTests.setUpClass()
    def setUp(self): self.h=i.InvestigationTests()
    def call(self,op,args,key=None):
        return f"SELECT centerway.operate('{i.T}','{i.C}','{key or uuid.uuid4()}',{f.literal(op)},{f.literal(json.dumps(args))}::jsonb)"
    def op(self,op,args,user=i.AUTHOR,key=None):
        receipt=self.h.obj(self.call(op,args,key),user)
        self.assertEqual(receipt['status'],'completed',receipt)
        return receipt['result']
    def value(self,kind,data,ident=None,rev=0):
        return self.op('append_value',dict(kind=kind,data=data,id=ident or str(uuid.uuid4()),expected_revision=rev,reason='Synthetic integration fixture'))
    def now(self): return self.h.sql('SELECT clock_timestamp()::text')[-1]
    def journey(self): return self.h.obj(f"SELECT centerway.client_journey('{i.T}','{i.C}')")

    def pipeline(self,parallel=False,authorized=True,resource_bad=False):
        k=self.value('contract',f.contract(source_id=i.S))['id']
        self.value('evidence',f.evidence(contract_id=k,source_id=i.S,observed_value=9))
        detection=self.op('detect',dict(contract_id=k,revisions=[1],as_of=self.now(),required_periods=2))
        category=str(uuid.uuid4()); rid=str(uuid.uuid4()); oid=str(uuid.uuid4())
        self.h.sql(f"SELECT centerway.register_discovery_rule('{i.T}','{rid}','{category}','condition_met',false)")
        obs=[{key:value for key,value in i.evidence(str(uuid.uuid4()),purpose,assertion).items() if key not in ('factor_id','factor_revision')}
             for purpose,assertion in [('requirement_applies',True),('condition_met',False)]]
        self.h.sql(f"SELECT centerway.register_discovery_input('{i.T}','{i.C}','{oid}','{k}',1,{f.literal(json.dumps(i.factor(category=category)))}::jsonb,{f.literal(json.dumps(obs))}::jsonb)")
        discovered=self.op('discover_company',dict(as_of=self.now()))
        entry=next(x for x in discovered['discoveries'] if x['origin']['input_id']==oid and x['origin']['detection_id']==detection['id'])
        inv=entry['origin']['investigation_id']
        self.assertEqual(entry['report']['result']['status'],'inconclusivo')
        self.assertTrue(any(x.get('investigation_id')==inv and x['next']=='supply_evidence_or_verification' for x in self.journey()['work_items']))
        for bundle in entry['report']['input_snapshot']['factors'][0]['evidence']:
            e=bundle['evidence']
            self.op('append_investigation',dict(investigation_id=inv,kind='verification',id=str(uuid.uuid4()),expected_revision=0,
              reason='Real separate reviewer fixture',data=i.verification(e['id'],e['assertion'])),i.REVIEWER)
        report=self.op('investigate',dict(investigation_id=inv,as_of=self.now()))
        resource,cat,policy=(str(uuid.uuid4()) for _ in range(3))
        principal=i.AUTHOR if authorized else i.REVIEWER
        self.h.sql(f"""INSERT INTO centerway.sandbox_flags VALUES('{i.T}','{i.C}','{resource}','isolated_synthetic',{str(resource_bad).lower()},NULL);
        INSERT INTO centerway.intervention_catalog VALUES('{i.T}','{cat}','Synthetic integration flag','{category}','internal','saas','set_synthetic_flag',false,true,1,1);
        INSERT INTO centerway.intervention_policies VALUES('{i.T}','{i.C}','{policy}','{cat}','{resource}','{principal}',clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour',1,1,interval '1 hour',interval '10 years');""",'postgres')
        args=dict(investigation_id=inv,report_id=report['id']); key=str(uuid.uuid4()); call=self.call('intervene',args,key)
        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                rs=list(pool.map(lambda _:f.query(call,i.AUTHOR,False),range(2)))
            for r in rs: self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(rs[0].stdout),json.loads(rs[1].stdout))
        receipt=self.h.obj(call); decision=receipt['result']
        self.assertEqual(self.h.obj(call),receipt) # resume after response loss
        self.assertEqual(decision['status'],('failed' if resource_bad else 'executed') if authorized else 'blocked')
        if not authorized or resource_bad: return
        self.assertEqual(self.h.sql(f"SELECT count(*) FROM centerway.intervention_executions WHERE decision_id='{decision['id']}'"),['1'])
        anchor=datetime.fromisoformat(self.h.sql(f"SELECT recorded_at::text FROM centerway.intervention_executions WHERE id='{decision['execution_id']}'")[-1])
        windows=[]
        for revision,left,right in [(1,-2,-1),(2,1,2)]:
            start=(anchor+timedelta(milliseconds=left)).isoformat(); end=(anchor+timedelta(milliseconds=right)).isoformat()
            self.value('contract',f.contract(source_id=i.S,period_start=start,period_end=end),k,revision)
            windows.append((start,end))
        start,end=windows[0]
        self.value('evidence',f.evidence(contract_id=k,contract_revision=2,source_id=i.S,period_start=start,period_end=end,observed_value=9))
        plan=str(uuid.uuid4())
        self.op('plan_recovery',dict(id=plan,decision_id=decision['id'],pre_revision=2,post_revision=3,reason='Explicit test windows'))
        missing=self.op('evaluate_recovery',dict(plan_id=plan,as_of=self.now()))
        self.assertEqual(missing['result']['status'],'resultado_inconclusivo')
        return k,plan,windows[1]

    def test_complete_flow_recovery_and_concurrency(self):
        k,p,(start,end)=self.pipeline(parallel=True)
        self.value('evidence',f.evidence(contract_id=k,contract_revision=3,source_id=i.S,period_start=start,period_end=end,observed_value=15))
        result=self.op('evaluate_recovery',dict(plan_id=p,as_of=self.now()))
        self.assertEqual(result['result']['status'],'recuperacao_completa')
        self.assertEqual(result['result']['causal_attribution'],'not_established')
        self.assertTrue(any(x.get('plan_id')==p and x['next']=='review_observed_recovery' for x in self.journey()['work_items']))

    def test_complete_flow_no_recovery_and_authorization(self):
        k,p,(start,end)=self.pipeline()
        self.value('evidence',f.evidence(contract_id=k,contract_revision=3,source_id=i.S,period_start=start,period_end=end,observed_value=8))
        self.assertEqual(self.op('evaluate_recovery',dict(plan_id=p,as_of=self.now()))['result']['status'],'ausencia_de_recuperacao')
        self.pipeline(authorized=False)
        self.pipeline(resource_bad=True)

    def test_errors_identity_and_isolation(self):
        key=str(uuid.uuid4()); call=self.call('append_value',dict(kind='contract',id=str(uuid.uuid4()),expected_revision=0,reason='Invalid fixture',data={}),key)
        failed=self.h.obj(call)
        self.assertEqual(failed['status'],'error'); self.assertEqual(self.h.obj(call),failed)
        self.h.fails(self.call('discover_company',dict(as_of=self.now()),key),'request_identity_conflict')
        self.h.fails(self.call('discover_company',dict(as_of=self.now())),'not_authorized','investigator_b')
        self.assertEqual(self.h.sql(f"SELECT centerway.client_journey('{i.T}','{i.C}') IS NULL",'investigator_b'),['t'])
        self.h.fails('INSERT INTO centerway.operation_receipts DEFAULT VALUES','permission denied')
        self.h.fails('DELETE FROM centerway.operation_receipts','permission denied')
        inv,_=self.h.investigation()
        self.h.supported(inv,condition=True)
        self.op('investigate',dict(investigation_id=inv,as_of=self.now()))
        self.assertTrue(any(x.get('investigation_id')==inv and x['next']=='review_investigation_conclusion' for x in self.journey()['work_items']))
