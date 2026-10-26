import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
import finance_core as f
import finance_ingestion as i
from test_finance_core import FinanceTests

class StageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.now=datetime(2025,1,10,tzinfo=timezone.utc)
  self.document={'status':'ready','sections':[{'id':'s1','page':2,'title':'Income','text':'Revenue 100','table':[['Metric','2024'],['Revenue','100']]}]}
  self.p1=patch('document_service.get_document',return_value=self.document);self.p2=patch('document_service.get_original',return_value=('source.pdf',b'original'))
  self.p1.start();self.p2.start()
  helper=FinanceTests();fact=helper.fact('revenue','100');fact['evidence'].update(section_id='s1',row=1,column=1,ownership='Common issuer',interpretation_note='Reviewed original cell')
  self.data={'document_id':'doc','payload':{'issuer':{'ticker':'TEST','name':'Test'},'calendar':helper.calendar(2024),'reports':[{'id':'r','document_id':'doc','published_at':'2024-04-01T00:00:00Z','indexed_at':'2024-04-02T00:00:00Z'}],'facts':[fact]}}
 def tearDown(self):self.p1.stop();self.p2.stop();self.temp.cleanup()
 def test_stage_not_live_accept_exact_source_and_no_admin_original(self):
  s=i.stage(self.root,self.data,'admin',self.now)['stage']
  with f.database(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],0)
  result=i.decide(self.root,{'stage_id':s['id'],'decision':'ACCEPT','note':'Context reviewed'},'admin',self.now)
  evidence=f.evidence(self.root,result['decision']['fact_ids'][0]);self.assertEqual(evidence['source_excerpt']['excerpt'],'100');self.assertNotIn('document_id',evidence)
  with self.assertRaises(ValueError):i.decide(self.root,{'stage_id':s['id'],'decision':'REJECT','note':'Again'},'admin',self.now)
 def test_bad_source_and_rejection(self):
  invalid=copy.deepcopy(self.data);invalid['payload']['facts'][0]['evidence']['row']=50
  with self.assertRaises(ValueError):i.stage(self.root,invalid,'admin',self.now)
  s=i.stage(self.root,self.data,'admin',self.now)['stage'];i.decide(self.root,{'stage_id':s['id'],'decision':'REJECT','note':'Wrong taxonomy'},'admin',self.now)
  with f.database(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0],0)
 def test_identity_warning_does_not_adjust_values(self):
  facts=[]
  for metric,value in [('assets','100'),('liabilities','80'),('equity','30')]:
   fact=copy.deepcopy(self.data['payload']['facts'][0]);fact.update(definition_id=metric,value=value,period_start='2024-03-31',period_end='2024-03-31',period_type='INSTANT');facts.append(fact)
  warnings=i.warnings(facts);self.assertEqual(warnings[0]['difference'],'-10');self.assertEqual(facts[0]['value'],'100')
