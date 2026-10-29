import concurrent.futures
import uuid
import json
import unittest
import test_foundation as f
import test_investigation as i

class InterventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if f.query("SELECT 1 FROM pg_roles WHERE rolname='investigator_a'",'postgres').stdout.strip()!='1':
            i.InvestigationTests.setUpClass()

    def setUp(self): self.h=i.InvestigationTests()

    def setup_case(self, supported=True, expected=False, initial=False, attempts=1, principal=i.AUTHOR, risk=1, maxrisk=1, expired=False):
        inv,_=self.h.investigation()
        if supported: self.h.supported(inv)
        report=self.h.obj(i.run(inv))
        resource,cat,policy=(str(uuid.uuid4()) for _ in range(3))
        sql=f"""
        INSERT INTO centerway.intervention_revocations SELECT tenant_id,client_id,id,'isolate synthetic test' FROM centerway.intervention_policies p WHERE NOT EXISTS(SELECT 1 FROM centerway.intervention_revocations v WHERE v.policy_id=p.id);
        INSERT INTO centerway.sandbox_flags VALUES('{i.T}','{i.C}','{resource}','isolated_synthetic',{str(initial).lower()},NULL);
        INSERT INTO centerway.intervention_catalog VALUES('{i.T}','{cat}','Synthetic flag','operating process','internal','saas','set_synthetic_flag',{str(expected).lower()},{str(not expected).lower()},{risk},1);
        INSERT INTO centerway.intervention_policies VALUES('{i.T}','{i.C}','{policy}','{cat}','{resource}','{principal}',clock_timestamp()-interval '1 day',clock_timestamp()+interval '{'-1 hour' if expired else '1 hour'}',{attempts},{maxrisk},interval '1 hour',interval '10 years');
        """
        self.h.sql(sql,'postgres')
        return inv,report,resource,policy

    def call(self,inv,report):
        return f"SELECT centerway.run_intervention('{i.T}','{i.C}','{inv}','{report['id']}')"

    def test_execute_reverse_and_duplicate(self):
        inv,r,res,p=self.setup_case()
        outcome=self.h.obj(self.call(inv,r))
        self.assertEqual(outcome['status'],'executed')
        self.assertEqual(outcome['value_recovery'],'not_evaluated')
        self.assertEqual(self.h.sql(f"SELECT value FROM centerway.sandbox_flags WHERE id='{res}'"),['t'])
        self.assertEqual(self.h.obj(self.call(inv,r))['status'],'blocked')
        undo=f"SELECT centerway.undo_intervention('{i.T}','{i.C}','{outcome['execution_id']}')"
        a=self.h.obj(undo); b=self.h.obj(undo)
        self.assertEqual(a,b)
        self.assertEqual(self.h.sql(f"SELECT value FROM centerway.sandbox_flags WHERE id='{res}'"),['f'])
        self.assertEqual(self.h.obj(self.call(inv,r))['status'],'blocked')

    def test_authorization_uncertainty_and_risk(self):
        for args in [dict(supported=False),dict(principal=i.REVIEWER),dict(risk=2,maxrisk=1),dict(expired=True)]:
            inv,r,res,p=self.setup_case(**args)
            # Other policies cannot target this case: revoke all policies except this one.
            self.h.sql(f"INSERT INTO centerway.intervention_revocations SELECT tenant_id,client_id,id,'test scope' FROM centerway.intervention_policies p WHERE id<>'{p}' AND NOT EXISTS(SELECT 1 FROM centerway.intervention_revocations v WHERE v.policy_id=p.id)",'postgres')
            self.assertEqual(self.h.obj(self.call(inv,r))['status'],'blocked')
            self.assertEqual(self.h.sql(f"SELECT value FROM centerway.sandbox_flags WHERE id='{res}'"),['f'])

    def test_failure_and_concurrency(self):
        inv,r,res,p=self.setup_case(initial=True)
        self.h.sql(f"INSERT INTO centerway.intervention_revocations SELECT tenant_id,client_id,id,'test scope' FROM centerway.intervention_policies p WHERE id<>'{p}' AND NOT EXISTS(SELECT 1 FROM centerway.intervention_revocations v WHERE v.policy_id=p.id)",'postgres')
        self.assertEqual(self.h.obj(self.call(inv,r))['status'],'failed')
        self.assertEqual(self.h.obj(self.call(inv,r))['status'],'blocked')
        inv,r,res,p=self.setup_case()
        call=self.call(inv,r)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:f.query(call,i.AUTHOR,False),range(2)))
        for result in results: self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(sorted(json.loads(x.stdout)['status'] for x in results),['blocked','executed'])

    def test_stale_report_revocation_and_isolation(self):
        inv,r,res,p=self.setup_case()
        self.h.obj(i.append(inv,'factor',i.factor(hypothesis='New uncertainty')))
        self.assertEqual(self.h.obj(self.call(inv,r))['reason'],'stale_report')
        inv,r,res,p=self.setup_case()
        self.h.sql(f"INSERT INTO centerway.intervention_revocations VALUES('{i.T}','{i.C}','{p}','revoked')",'postgres')
        self.h.sql(f"INSERT INTO centerway.intervention_revocations SELECT tenant_id,client_id,id,'test scope' FROM centerway.intervention_policies p WHERE NOT EXISTS(SELECT 1 FROM centerway.intervention_revocations v WHERE v.policy_id=p.id)",'postgres')
        self.assertEqual(self.h.obj(self.call(inv,r))['status'],'blocked')
        self.h.fails(self.call(inv,r),'not_authorized','investigator_b')
        self.assertEqual(self.h.sql('SELECT count(*) FROM centerway.sandbox_flags','investigator_b'),['0'])
        self.h.fails('INSERT INTO centerway.intervention_policies DEFAULT VALUES','permission denied')
        self.h.fails('UPDATE centerway.sandbox_flags SET value=true','permission denied')
