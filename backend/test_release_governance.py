import unittest
from datetime import datetime,timezone,timedelta
import release_governance as g

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.pass_gate=dict(status='PASS',report_id='fixture-report',source_ids=['fixture-source'],release_owner='fixture-reviewer',calculation_version='fixture-v1',snapshot_id='fixture-snapshot',
                            known_at=self.now.isoformat(),expires_at=(self.now+timedelta(days=1)).isoformat())
    def evidence(self,feature):return {k:dict(self.pass_gate) for k in g.BASE_GATES+g.FEATURES[feature]}
    def test_missing_or_historical_summary_cannot_promote(self):
        for evidence in (None,{'historical_58_1_summary':'PASS'}, {'contract':{'status':'PASS'}}):
            self.assertEqual(g.evaluate('financial_research',evidence,self.now)['status'],'REVIEW_ONLY')
    def test_all_gates_required_and_independent(self):
        evidence=self.evidence('financial_research')
        self.assertEqual(g.evaluate('financial_research',evidence,self.now)['status'],'RESEARCH_READY')
        evidence['source']['status']='FAIL'
        result=g.evaluate('financial_research',evidence,self.now)
        self.assertFalse(result['release_ready']);self.assertIn('SOURCE_EVIDENCE_MISSING_FAILED_OR_STALE',result['reason_codes'])
        self.assertEqual(g.evaluate('valuation',self.evidence('valuation'),self.now)['status'],'RESEARCH_READY')
    def test_expiry_future_revision_and_missing_lineage_abstain(self):
        for change in ({'expires_at':self.now.isoformat()}, {'known_at':(self.now+timedelta(days=1)).isoformat()}, {'source_ids':[]}, {'release_owner':''}):
            evidence=self.evidence('market_models');evidence['future_cohort'].update(change)
            self.assertEqual(g.evaluate('market_models',evidence,self.now)['status'],'REVIEW_ONLY')
    def test_shadow_never_implies_execution(self):
        result=g.evaluate('distribution',self.evidence('distribution'),self.now)
        self.assertEqual(result['status'],'SHADOW_VALIDATED');self.assertFalse(result['execution_eligible']);self.assertIsNone(result['allocation_weight'])
