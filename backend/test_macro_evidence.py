import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
import macro_evidence as macro
import finance_core


class MacroTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=datetime(2026,10,12,tzinfo=timezone.utc)
        self.data={'id':'US_CPI_YOY','name':'US CPI YoY','scope':'unitedStates','kind':'cpi','unit':'percent YoY',
            'frequency':'monthly','timezone':'America/New_York','calendar':'US publication calendar',
            'provider':'Reviewed test source','source_url':'https://example.com/cpi','reviewed':True,
            'rule':{'low':'1','high':'3','meaning':'CPI context range'},
            'observations':[{'period_start':'2026-09-01','period_end':'2026-09-30','value':'2.5',
                'release_at':'2026-10-10T08:00:00-04:00','known_at':'2026-10-10T13:00:00Z',
                'expires_at':'2026-11-10T13:00:00Z','revision':'initial'}]}
    def tearDown(self):self.temp.cleanup()

    def test_release_and_acceptance_gate_country_isolation(self):
        macro.ingest(self.root,self.data,self.now)
        past=macro.summary(self.root,'unitedStates','2026-10-11T00:00:00Z',self.now)
        self.assertEqual(past['status'],'UNAVAILABLE');self.assertEqual(past['series'][0]['history'],[])
        current=macro.summary(self.root,'unitedStates',now=self.now)
        self.assertEqual(current['status'],'PARTIAL');self.assertEqual(current['coverage']['covered'],['cpi'])
        self.assertEqual(current['series'][0]['heuristic_fit'],'WITHIN_RANGE')
        for scope in ('japan','vietnam','world','americas'):
            self.assertEqual(macro.summary(self.root,scope,now=self.now)['series'],[])

    def test_revision_vintage_does_not_leak_or_fallback(self):
        macro.ingest(self.root,self.data,self.now)
        later=self.now+timedelta(days=2)
        revision=copy.deepcopy(self.data);revision['observations'][0].update(value=None,revision='corrected',release_at=later.isoformat(),known_at=later.isoformat())
        macro.ingest(self.root,revision,later)
        past=macro.summary(self.root,'unitedStates',self.now.isoformat(),later)
        self.assertEqual(past['series'][0]['latest']['value'],'2.5')
        current=macro.summary(self.root,'unitedStates',now=later)
        self.assertIsNone(current['series'][0]['latest']['value']);self.assertIsNone(current['series'][0]['heuristic_fit'])

    def test_stale_and_ambiguous_suppress_fit(self):
        macro.ingest(self.root,self.data,self.now)
        stale=macro.summary(self.root,'unitedStates',now=self.now+timedelta(days=40))
        self.assertEqual(stale['series'][0]['status'],'STALE');self.assertIsNone(stale['series'][0]['heuristic_fit'])
        macro.ingest(self.root,self.data,self.now)
        ambiguous=macro.summary(self.root,'unitedStates',now=self.now)
        self.assertEqual(ambiguous['series'][0]['latest']['reason'],'AMBIGUOUS_REVISION')

    def test_validation_immutable_definition_future_nan(self):
        macro.ingest(self.root,self.data,self.now)
        for change in ({'unit':'index'},{'reviewed':False}):
            invalid=copy.deepcopy(self.data);invalid.update(change)
            with self.assertRaises(ValueError):macro.ingest(self.root,invalid,self.now)
        for field,value in [('value','NaN'),('release_at','2026-12-01T00:00:00Z'),('known_at','2026-12-01T00:00:00Z')]:
            invalid=copy.deepcopy(self.data);invalid['observations'][0][field]=value
            with self.assertRaises(ValueError):macro.ingest(self.root,invalid,self.now)
        with self.assertRaises(ValueError):macro.summary(self.root,'japan','2027-01-01T00:00:00Z',self.now)

    def test_regime_requires_all_scoped_rules(self):
        for kind in macro.KINDS:
            data=copy.deepcopy(self.data);data['id']='US_'+kind;data['kind']=kind
            macro.ingest(self.root,data,self.now)
        summary=macro.summary(self.root,'unitedStates',now=self.now)
        self.assertEqual(summary['regime']['status'],'HEURISTIC')
        self.assertEqual(summary['regime']['fit'],'WITHIN_ALL_REVIEWED_RANGES')
        self.assertEqual(len(summary['regime']['source_ids']),5)
        self.assertEqual(macro.summary(self.root,'japan',now=self.now)['regime']['status'],'UNAVAILABLE')

    def mapping(self):
        with finance_core.database(self.root) as db:
            db.execute('INSERT INTO issuers VALUES (?,?)',('TEST','Test issuer'))
            db.execute('INSERT INTO facts VALUES (?,?,?)',('fact','TEST',json.dumps({'known_at':self.now.isoformat(),'status':'READY','value':'100'})))
        return {'reviewed':True,'ticker':'TEST','segment':'Smelter','commodity':'Copper','grade':'Grade A','location':'Japan',
            'volume_unit':'tonne','currency':'USD','contract_reset':'Half output floats; all input floats','inventory_lag':'Same scenario period',
            'hedge_scope':'None; explicit hedge PnL assumption required','period_start':'2027-01-01','period_end':'2027-12-31',
            'output_volume':'100','input_volume':'80','output_repricing_fraction':'.5','input_repricing_fraction':'1',
            'fact_ids':['fact'],'expires_at':'2026-12-01T00:00:00Z'}

    def test_commodity_producer_price_rise_can_reduce_ebit(self):
        mapping=macro.exposure(self.root,self.mapping(),self.now)['exposure']
        data={'exposure_id':mapping['id'],'currency':'USD','volume_unit':'tonne','output_price_delta':'10','input_price_delta':'10',
            'pass_through':'100','hedge_pnl':'-20','incremental_costs':'30'}
        result=macro.stress(self.root,data,self.now)
        self.assertEqual(result['delta_ebit'],'-250.0')
        self.assertEqual(result['status'],'SCENARIO');self.assertEqual(result['exposure']['fact_ids'],['fact'])
        self.assertEqual(result['forecast_status'],'PROPOSED_SCENARIO_REQUIRES_F04_DRIVER_REVIEW')
        data['currency']='JPY'
        with self.assertRaises(ValueError):macro.stress(self.root,data,self.now)

    def test_commodity_requires_evidence_and_origin_coverage(self):
        data=self.mapping();data['fact_ids']=['unknown']
        with self.assertRaises(ValueError):macro.exposure(self.root,data,self.now)
        data['fact_ids']=['fact'];mapping=macro.exposure(self.root,data,self.now)['exposure']
        result=macro.stress(self.root,{'exposure_id':mapping['id'],'origin':'2026-10-11T00:00:00Z'},self.now)
        self.assertIsNone(result['delta_ebit'])
        self.assertEqual(macro.stress(self.root,{'exposure_id':mapping['id']},self.now+timedelta(days=60))['status'],'UNAVAILABLE')
