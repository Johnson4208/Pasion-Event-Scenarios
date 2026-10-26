import copy
import sqlite3
import unittest
from datetime import datetime,timezone,timedelta
import event_research as events


class EventTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)');self.db.executemany('INSERT INTO accounts VALUES (?)',[('one',),('two',)])
        self.now=datetime(2026,10,13,tzinfo=timezone.utc)
        self.claim={'reviewed':True,'claim_key':'policy','claim':'Policy announced','provider':'Test source','source_url':'https://example.com/policy',
            'revision':'original','input_type':'ACTUAL','input_policy':'Reviewed official announcement',
            'published_at':'2026-10-12T00:00:00Z','ingested_at':'2026-10-12T02:00:00Z','revised_at':'2026-10-12T00:00:00Z'}
        self.data={'question':'Will demand improve?','event_definition':'Demand threshold at maturity','category':'Economy','factor':'Growth',
            'focus':'Test country','cluster_id':'policy-2026','cutoff':self.now.isoformat(),'maturity':(self.now+timedelta(days=1)).isoformat(),
            'outcomes':[{'id':k,'name':k,'resolution_rule':'Outcome rule '+k,'condition':'Conditional '+k,'assumption':'Manual judgment',
                'weight':None,'evidence':[]} for k in ('up','other')]}
    def tearDown(self):self.db.close()

    def test_acceptance_gate_revisions_and_snapshot_freeze(self):
        first=events.ingest(self.db,self.claim,self.now)['evidence']
        self.assertEqual(events.evidence(self.db,'2026-10-12T23:00:00Z',self.now)['claims'],[])
        self.data['outcomes'][0]['evidence']=[{'id':first['id'],'stance':'SUPPORTING','relevance':'Demand mechanism'}]
        study=events.save(self.db,'one',self.data,self.now)['study']
        later=self.now+timedelta(hours=1);claim=copy.deepcopy(self.claim);claim.update(claim='Corrected policy',revision='corrected',revised_at=later.isoformat())
        events.ingest(self.db,claim,later)
        self.assertEqual(events.evidence(self.db,self.now.isoformat(),later)['claims'][0]['claim'],'Policy announced')
        self.assertEqual(events.evidence(self.db,now=later)['claims'][0]['claim'],'Corrected policy')
        self.assertEqual(events.history(self.db,'one')['studies'][0]['outcomes'][0]['evidence'][0]['claim']['claim'],'Policy announced')
        self.assertEqual(study['downstream_policy'],'NO_STOCK_P_UP_OR_KELLY_INPUT')

    def test_empty_evidence_and_weights_are_not_probabilities(self):
        study=events.save(self.db,'one',self.data,self.now)['study']
        self.assertIsNone(study['outcomes'][0]['weight']);self.assertEqual(study['outcomes'][0]['evidence_status'],'MISSING_EVIDENCE')
        self.data['outcomes'][0]['weight']='60';self.data['outcomes'][1]['weight']='40'
        study=events.save(self.db,'one',self.data,self.now)['study']
        self.assertEqual(study['weight_policy'],'ANALYTICAL_JUDGMENT_NOT_PROBABILITY')
        for weights in [('60',None),('60','60'),('NaN','0')]:
            invalid=copy.deepcopy(self.data)
            for outcome,weight in zip(invalid['outcomes'],weights):outcome['weight']=weight
            with self.assertRaises((ValueError,ArithmeticError)):events.save(self.db,'one',invalid,self.now)

    def test_ownership_lineage_and_historical_label(self):
        study=events.save(self.db,'one',self.data,self.now)['study']
        self.assertEqual(events.history(self.db,'two')['studies'],[])
        self.data['parent_id']=study['id']
        with self.assertRaises(ValueError):events.save(self.db,'two',self.data,self.now)
        self.data['cutoff']='2026-10-11T00:00:00Z'
        child=events.save(self.db,'one',self.data,self.now)['study']
        self.assertEqual(child['parent_id'],study['id']);self.assertIn('RETROSPECTIVE',child['temporal_status'])
        self.assertEqual(len(events.history(self.db,'one')['studies']),2)

    def test_future_and_ambiguous_evidence_is_ineligible(self):
        invalid=copy.deepcopy(self.claim);invalid['published_at']='2027-01-01T00:00:00Z'
        with self.assertRaises(ValueError):events.ingest(self.db,invalid,self.now)
        first=events.ingest(self.db,self.claim,self.now)['evidence'];events.ingest(self.db,self.claim,self.now)
        self.assertEqual(events.evidence(self.db,now=self.now)['claims'],[])
        self.data['outcomes'][0]['evidence']=[{'id':first['id'],'stance':'OPPOSING','relevance':'Relevant'}]
        with self.assertRaises(ValueError):events.save(self.db,'one',self.data,self.now)

    def test_resolution_requires_maturity_owner_actual_and_is_immutable(self):
        study=events.save(self.db,'one',self.data,self.now)['study']
        claim=events.ingest(self.db,self.claim,self.now)['evidence']
        data={'version_id':study['id'],'outcome_id':'up','evidence_id':claim['id'],'observed_at':self.now.isoformat(),'explanation':'Threshold observed'}
        with self.assertRaises(ValueError):events.resolve(self.db,'one',data,self.now)
        later=self.now+timedelta(days=2);data['observed_at']=later.isoformat()
        with self.assertRaises(ValueError):events.resolve(self.db,'two',data,later)
        result=events.resolve(self.db,'one',data,later)
        self.assertIn('MANUALLY',result['resolution']['status'])
        with self.assertRaises(ValueError):events.resolve(self.db,'one',data,later)
        self.assertEqual(events.history(self.db,'two')['resolutions'],[])
        self.assertEqual(events.history(self.db,'one')['studies'][0],study)

    def test_proxy_cannot_resolve_and_future_cutoff_rejected(self):
        study=events.save(self.db,'one',self.data,self.now)['study'];self.claim['input_type']='PROXY'
        claim=events.ingest(self.db,self.claim,self.now)['evidence'];later=self.now+timedelta(days=2)
        with self.assertRaises(ValueError):events.resolve(self.db,'one',{'version_id':study['id'],'outcome_id':'up','evidence_id':claim['id'],'observed_at':later.isoformat(),'explanation':'Proxy'},later)
        self.data['cutoff']=(self.now+timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):events.save(self.db,'one',self.data,self.now)
