import json
import uuid
import unittest
from datetime import datetime,timedelta
import test_foundation as f
import test_investigation as i
import test_yintervention as y

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): y.InterventionTests.setUpClass()

    def setUp(self):
        self.h=i.InvestigationTests(); self.four=y.InterventionTests(); self.four.setUp()

    def prepare(self,before=9,after=15,failed=False):
        inv,report,_,_=self.four.setup_case(initial=failed)
        decision=self.h.obj(self.four.call(inv,report))
        timestamp=decision['recorded_at']
        if decision['execution_id']:
            timestamp=self.h.sql(f"SELECT recorded_at::text FROM centerway.intervention_executions WHERE id='{decision['execution_id']}'")[-1]
        anchor=datetime.fromisoformat(timestamp)
        # These small synthetic test windows straddle the actual execution. No result is
        # derived from the sandbox flag; numerical observations are explicit fixtures.
        k=report['input_snapshot']['investigation']['contract_id']
        pre_start=(anchor-timedelta(milliseconds=2)).isoformat()
        pre_end=(anchor-timedelta(milliseconds=1)).isoformat()
        post_start=(anchor+timedelta(milliseconds=1)).isoformat()
        post_end=(anchor+timedelta(milliseconds=2)).isoformat()
        for rev,start,end in [(1,pre_start,pre_end),(2,post_start,post_end)]:
            self.h.obj(f.append('contract',f.contract(source_id=i.S,period_start=start,period_end=end),k,rev,tenant=i.T,client=i.C))
        ids=[]
        for rev,start,end,value in [(2,pre_start,pre_end,before),(3,post_start,post_end,after)]:
            eid=str(uuid.uuid4()); ids.append(eid)
            if value is not None:
                self.h.obj(f.append('evidence',f.evidence(contract_id=k,contract_revision=rev,source_id=i.S,
                  period_start=start,period_end=end,observed_value=value),eid,tenant=i.T,client=i.C))
        plan=str(uuid.uuid4())
        self.h.obj(f"SELECT centerway.create_recovery_plan('{i.T}','{i.C}','{plan}','{decision['id']}',2,3,'Synthetic test windows')")
        post=f.evidence(contract_id=k,contract_revision=3,source_id=i.S,period_start=post_start,period_end=post_end,observed_value=after or 15)
        return plan,decision,post,ids

    def run_plan(self,p,cutoff='clock_timestamp()'):
        return self.h.obj(f"SELECT centerway.evaluate_recovery('{i.T}','{i.C}','{p}',{cutoff})")

    def test_complete_partial_none_and_preexisting_value(self):
        for before,after,status in [(9,15,'recuperacao_completa'),(9,12,'recuperacao_parcial'),(9,9,'ausencia_de_recuperacao'),(9,8,'ausencia_de_recuperacao'),(16,17,'resultado_inconclusivo')]:
            with self.subTest(before=before,after=after):
                p,_,_,_=self.prepare(before,after)
                r=self.run_plan(p)['result']
                self.assertEqual(r['status'],status)
                self.assertEqual(r['improvement_observed'],after>before)
                self.assertEqual(r['minimum_met'],after>=15)
                self.assertEqual(r['baseline_met'],after>=10)
                self.assertTrue(r['execution_succeeded'])
                self.assertEqual(r['causal_attribution'],'not_established')

    def test_missing_conflicting_usage_and_failed_execution(self):
        p,_,post,_=self.prepare(after=None)
        self.assertEqual(self.run_plan(p)['result']['status'],'resultado_inconclusivo')
        self.h.obj(f.append('evidence',post|{'evidence_type':'usage'},tenant=i.T,client=i.C))
        self.assertEqual(self.run_plan(p)['result']['status'],'resultado_inconclusivo')
        p,_,post,_=self.prepare()
        self.h.obj(f.append('evidence',post|{'observed_value':7},tenant=i.T,client=i.C))
        self.assertEqual(self.run_plan(p)['result']['status'],'resultado_inconclusivo')
        p,_,_,_=self.prepare(failed=True)
        r=self.run_plan(p)['result']
        self.assertFalse(r['execution_succeeded'])
        self.assertEqual(r['reason'],'intervention_not_executed')

    def test_late_evidence_reevaluation_history_and_isolation(self):
        p,_,post,_=self.prepare(after=None)
        old=self.run_plan(p)
        self.h.obj(f.append('evidence',post,tenant=i.T,client=i.C))
        new=self.run_plan(p)
        self.assertEqual(old['result']['status'],'resultado_inconclusivo')
        self.assertEqual(new['result']['status'],'recuperacao_completa')
        old_cut=f.literal(old['as_of'])+'::timestamptz'
        self.assertEqual(self.run_plan(p,old_cut)['id'],old['id'])
        read=f"SELECT centerway.read_recovery_context('{i.T}','{i.C}','{p}','{old['id']}')"
        self.assertEqual(self.h.obj(read),old)
        self.assertEqual(self.h.sql(read+' IS NULL','investigator_b'),['t'])
        self.h.fails(f"SELECT centerway.evaluate_recovery('{i.T}','{i.C}','{p}',clock_timestamp())",'not_authorized','investigator_b')
        self.h.fails('DELETE FROM centerway.recovery_runs','permission denied')
        self.h.fails('UPDATE centerway.recovery_plans SET pre_revision=1','permission denied')

    def test_window_validation_and_reversal(self):
        p,dec,_,_=self.prepare()
        self.h.fails(f"SELECT centerway.create_recovery_plan('{i.T}','{i.C}','{uuid.uuid4()}','{dec['id']}',3,2,'bad windows')",'incompatible_recovery_windows')
        self.h.obj(f"SELECT centerway.undo_intervention('{i.T}','{i.C}','{dec['execution_id']}')")
        # Undo after the observation window does not rewrite the completed historical window.
        self.assertEqual(self.run_plan(p)['result']['status'],'recuperacao_completa')
