import json
import unittest
import uuid
import test_foundation as f
import test_investigation as i

class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if f.query("SELECT 1 FROM pg_roles WHERE rolname='investigator_a'",'postgres').stdout.strip()!='1':
            i.InvestigationTests.setUpClass()

    def setUp(self):
        self.h=i.InvestigationTests()

    def prepare(self, category, client=i.C):
        if client==i.C:
            _,d=self.h.investigation()
        else:
            k=str(uuid.uuid4())
            self.h.sql(f.append('source',dict(name='Synthetic',locator='synthetic://client2',method='manual'),i.S,tenant=i.T,client=client))
            self.h.sql(f.append('contract',f.contract(source_id=i.S),k,tenant=i.T,client=client))
            self.h.sql(f.append('evidence',f.evidence(contract_id=k,source_id=i.S,observed_value=9),tenant=i.T,client=client))
            d=self.h.obj(f"SELECT centerway.run_detection('{i.T}','{client}','{k}',ARRAY[1],clock_timestamp(),2)")
        rid,oid=str(uuid.uuid4()),str(uuid.uuid4())
        self.h.sql(f"SELECT centerway.register_discovery_rule('{i.T}','{rid}',{f.literal(category)},'condition_met',false)")
        factor=i.factor(category=category)
        ev=[{k:v for k,v in i.evidence(str(uuid.uuid4()),p,a).items() if k not in ('factor_id','factor_revision')}
            for p,a in [('requirement_applies',True),('condition_met',False)]]
        self.h.sql(f"SELECT centerway.register_discovery_input('{i.T}','{client}','{oid}','{d['contract_id']}',1,{f.literal(json.dumps(factor))}::jsonb,{f.literal(json.dumps(ev))}::jsonb)")
        return rid,oid

    def batch(self):
        return self.h.obj(f"SELECT centerway.discover_impediments('{i.T}',clock_timestamp())")['discoveries']

    def test_routing_reuse_and_real_reviews(self):
        rid,oid=self.prepare(str(uuid.uuid4()))
        entries=self.batch()
        entry=next(x for x in entries if x['origin']['input_id']==oid)
        self.assertEqual(entry['report']['result']['status'],'inconclusivo')
        inv=entry['origin']['investigation_id']
        self.assertEqual(next(x for x in self.batch() if x['origin']['input_id']==oid)['origin'],entry['origin'])
        for bundle in entry['report']['input_snapshot']['factors'][0]['evidence']:
            e=bundle['evidence']
            self.h.obj(i.append(inv,'verification',i.verification(e['id'],e['assertion'])),i.REVIEWER)
        updated=next(x for x in self.batch() if x['origin']['input_id']==oid)
        self.assertEqual(updated['report']['result']['status'],'impedimento_demonstrado')
        self.assertFalse(updated['report']['result']['execution_authorized'])

    def test_multiple_clients_and_isolation(self):
        self.prepare(str(uuid.uuid4()))
        self.prepare(str(uuid.uuid4()),i.C2)
        self.assertEqual({x['origin']['client_id'] for x in self.batch()},{i.C,i.C2})
        self.h.fails(f"SELECT centerway.discover_impediments('{i.T}',clock_timestamp())",'not_authorized','investigator_b')
        self.assertEqual(self.h.sql('SELECT count(*) FROM centerway.discoveries','investigator_b'),['0'])
        self.h.fails('DELETE FROM centerway.discovery_rules','permission denied')
        self.h.fails("SELECT centerway.discover_impediments(NULL,clock_timestamp())",'not_authorized')

    def test_unmatched_rule_does_not_create_discovery(self):
        rid,_=self.prepare(str(uuid.uuid4()))
        unmatched=str(uuid.uuid4())
        self.h.sql(f"SELECT centerway.register_discovery_rule('{i.T}','{unmatched}','unmatched','condition_met',true)")
        entries=self.batch()
        self.assertTrue(all(x['origin']['rule_id']!= unmatched for x in entries))
        self.h.fails("SELECT centerway.discover_impediments('"+i.T+"','infinity')",'invalid_cutoff')
