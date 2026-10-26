import copy
from test_finance_ingestion import StageTests
import finance_ingestion as i
import finance_core as f

class ReportReviewTests(StageTests):
 def test_different_ownership_blocks_context_compatibility(self):
  fact=self.data['payload']['facts'][0]
  self.assertFalse(f.compatible({**fact,'ownership':'common'},{**fact,'ownership':'all shareholders'}))
 def test_duplicate_context_requires_new_revision(self):
  first=i.stage(self.root,self.data,'reviewer',self.now)['stage'];i.decide(self.root,{'stage_id':first['id'],'decision':'ACCEPT','note':'Accepted'},'reviewer',self.now)
  second=i.stage(self.root,self.data,'reviewer',self.now)['stage']
  with self.assertRaises(ValueError):i.decide(self.root,{'stage_id':second['id'],'decision':'ACCEPT','note':'Duplicate'},'reviewer',self.now)
 def test_corrected_value_retains_original_observation(self):
  self.data['payload']['facts'][0]['value']='110'
  self.data['payload']['facts'][0]['evidence']['interpretation_note']='Original extraction 100 corrected after original-file review'
  record=i.stage(self.root,self.data,'reviewer',self.now)['stage'];fact=record['payload']['facts'][0];raw=record['raw_observations'][fact['id']]
  self.assertEqual(raw['source_text'],'100');self.assertEqual(raw['proposed_value'],'110')
  i.decide(self.root,{'stage_id':record['id'],'decision':'ACCEPT','note':'Reviewed correction'},'reviewer',self.now)
  self.assertEqual(f.evidence(self.root,fact['id'])['value'],'110');self.assertEqual(i.history(self.root,'doc')['stages'][0]['raw_observations'][fact['id']]['source_text'],'100')
 def test_ambiguous_does_not_publish_and_country_layout_not_inferred(self):
  self.document['sections'][0]['table']=[['FY24','Metric'],['100','Revenue']]
  fact=self.data['payload']['facts'][0];fact['evidence'].update(row=1,column=0);fact['accounting_basis']='IFRS'
  record=i.stage(self.root,self.data,'reviewer',self.now)['stage'];self.assertEqual(next(iter(record['citations'].values()))['excerpt'],'100')
  i.decide(self.root,{'stage_id':record['id'],'decision':'AMBIGUOUS','note':'Ownership unclear'},'reviewer',self.now)
  with f.database(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],0)
 def test_cash_flow_da_is_not_automatically_eligible(self):
  self.data['payload']['facts'][0].update(definition_id='da_expense',da_eligible=False)
  record=i.stage(self.root,self.data,'reviewer',self.now)['stage'];self.assertFalse(record['payload']['facts'][0]['da_eligible'])
 def test_structured_context_must_match_reviewed_period(self):
  fact=self.data['payload']['facts'][0]
  fact['structured_context']={'namespace':'ifrs','concept':'Revenue','context_ref':'c1','unit_ref':'usd','entity_identifier':'TEST', 'decimals':'0','filing_id':'filing','amendment':'original','source_locator':'s1:1:1','dimensions':{},'period_start':'2020-01-01','period_end':fact['period_end'],'currency':'USD'}
  with self.assertRaises(ValueError):i.stage(self.root,self.data,'reviewer',self.now)
