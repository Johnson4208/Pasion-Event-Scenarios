import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import finance_core as f


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.now=datetime(2025,1,10,tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def calendar(self,year):
        return {'year':str(year),'start':f'{year}-01-01','end':f'{year}-12-31',
                'quarter_ends':[f'{year}-03-31',f'{year}-06-30',f'{year}-09-30',f'{year}-12-31']}

    def fact(self,metric,value,start='2024-01-01',end='2024-03-31',kind='Q',**extra):
        return {'id':metric+'-'+start+'-'+end+'-'+kind,'definition_id':metric,'value':value,'scale':'1',
                'period_start':start,'period_end':end,'period_type':kind,'currency':'USD','unit':'currency',
                'scope':'consolidated','accounting_basis':'US_GAAP','restatement_basis':'original',
                'revision':'1','report_id':'report-2024','reviewed':True,'evidence':{'page':2,'table':'Income','tag':metric},**extra}

    def ingest(self,facts,year=2024,**extra):
        payload={'issuer':{'ticker':'TEST','name':'Test issuer'},'calendar':self.calendar(year),
                 'reports':[{'id':f'report-{year}','document_id':'admin-doc','published_at':'2024-04-01T00:00:00Z','indexed_at':'2024-04-02T00:00:00Z'}],
                 'facts':facts}
        f.ingest(self.root,payload,'admin@example.com',extra.get('now',self.now))

    def test_quarter_ytd_and_zero_are_distinct(self):
        self.ingest([self.fact('revenue','100'),self.fact('revenue','240',end='2024-06-30',kind='YTD'),
                     self.fact('cfo','0',start='2024-04-01',end='2024-06-30')])
        result=f.company(self.root,'TEST','Q','2024-06-30')
        self.assertEqual(result['metrics']['revenue']['value'],'140')
        self.assertEqual(result['metrics']['cfo']['value'],'0')
        self.assertEqual(result['metrics']['cfo_margin']['value'],'0')
        self.assertEqual(result['metrics']['revenue']['period_start'],'2024-04-01')

    def test_standalone_is_not_resubtracted_and_ttm_is_not_doubled(self):
        self.ingest([self.fact('revenue','100'),self.fact('revenue','140',start='2024-04-01',end='2024-06-30'),
                     self.fact('revenue','240',end='2024-06-30',kind='YTD')])
        self.assertEqual(f.company(self.root,'TEST','Q','2024-06-30')['metrics']['revenue']['value'],'140')
        self.assertIsNone(f.company(self.root,'TEST','TTM','2024-06-30')['metrics']['revenue']['value'])

    def test_scope_period_and_da_eligibility_gate_ratios(self):
        self.ingest([self.fact('revenue','100'),self.fact('net_income','10',scope='parent'),
                     self.fact('ebit','20'),self.fact('da_expense','5'),
                     self.fact('cfo','30',end='2024-06-30',kind='YTD')])
        result=f.company(self.root,'TEST','Q','2024-03-31')['metrics']
        self.assertIsNone(result['net_margin']['value'])
        self.assertEqual(result['net_margin']['reason_codes'],['INCOMPATIBLE_CONTEXT'])
        self.assertIsNone(result['ebitda']['value'])
        self.assertIsNone(result['cfo_margin']['value'])

    def test_ebitda_average_balances_and_lineage(self):
        self.ingest([self.fact('revenue','100'),self.fact('net_income','10'),self.fact('net_income_common','10'),
                     self.fact('ebit','20'),self.fact('da_expense','5',da_eligible=True),
                     self.fact('assets','80',start='2023-12-31',end='2023-12-31',kind='INSTANT'),
                     self.fact('assets','120',start='2024-03-31',kind='INSTANT')])
        result=f.company(self.root,'TEST','Q','2024-03-31')['metrics']
        self.assertEqual(result['ebitda']['value'],'25')
        self.assertEqual(result['roa']['value'],'10.0')
        self.assertIsNone(result['roe']['value'])
        self.assertEqual(len(result['ebitda']['source_ids']),2)
        source=f.evidence(self.root,result['ebitda']['source_ids'][0])
        self.assertEqual(source['evidence']['page'],2)
        self.assertNotIn('document_id',source)

    def test_known_at_and_invalid_values(self):
        self.ingest([self.fact('revenue','0')])
        earlier=f.company(self.root,'TEST','Q',origin='2024-07-01T00:00:00Z')
        self.assertEqual(earlier['status'],'UNAVAILABLE')
        self.assertEqual(f.company(self.root,'TEST','Q')['metrics']['revenue']['value'],'0')
        with self.assertRaises(ValueError):
            self.ingest([self.fact('revenue','NaN')],year=2024)

    def test_annual_ytd_ttm_bridge_and_missing_prior(self):
        self.ingest([self.fact('revenue','500',end='2023-12-31',start='2023-01-01',kind='FY',report_id='report-2023'),
                     self.fact('revenue','240',end='2023-06-30',start='2023-01-01',kind='YTD',report_id='report-2023')],year=2023)
        self.ingest([self.fact('revenue','275',end='2024-06-30',kind='YTD')])
        self.assertEqual(f.company(self.root,'TEST','TTM','2024-06-30')['metrics']['revenue']['value'],'535')

    def test_comparison_rejects_currency_and_preserves_context(self):
        self.ingest([self.fact('revenue','100')])
        result=f.compare(self.root,['TEST','MISSING'],'Q')
        self.assertFalse(result['rows'][0]['comparable'])
        self.assertTrue(f.compare(self.root,['TEST','TEST'],'Q')['rows'][0]['comparable'])
        a=f.company(self.root,'TEST','Q')['metrics']['revenue']
        self.assertFalse(f.compatible(a,dict(a,currency='VND')))

    def test_non_calendar_fiscal_period(self):
        calendar={'year':'FY2024','start':'2023-07-01','end':'2024-06-30','quarter_ends':['2023-09-30','2023-12-31','2024-03-31','2024-06-30']}
        facts=[self.fact('revenue','100',start='2023-07-01',end='2023-09-30'),
               self.fact('revenue','230',start='2023-07-01',end='2023-12-31',kind='YTD')]
        f.ingest(self.root,{'issuer':{'ticker':'TEST','name':'Test'},'calendar':calendar,
             'reports':[{'id':'report-2024','document_id':'doc','published_at':'2024-01-01T00:00:00Z','indexed_at':'2024-01-02T00:00:00Z'}],'facts':facts},'admin',self.now)
        self.assertEqual(f.company(self.root,'TEST','Q','2023-12-31')['metrics']['revenue']['value'],'130')

    def test_revisions_are_loaded_only_after_known_at(self):
        self.ingest([self.fact('revenue','100')])
        with f.database(self.root) as db:
            import json
            old=json.loads(db.execute('SELECT payload FROM facts').fetchone()[0])
            revised=dict(old,id='amended-revenue',revision='2',value='110',known_at='2025-02-01T00:00:00+00:00',source_ids=['amended-revenue'])
            db.execute('INSERT INTO facts VALUES (?,?,?)',('amended-revenue','TEST',json.dumps(revised)))
        self.assertEqual(f.company(self.root,'TEST','Q',origin='2025-01-15T00:00:00Z')['metrics']['revenue']['value'],'100')
        self.assertEqual(f.company(self.root,'TEST','Q',origin='2025-02-15T00:00:00Z')['metrics']['revenue']['value'],'110')
