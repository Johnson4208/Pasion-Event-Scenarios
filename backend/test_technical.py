import copy
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import technical as t


class TechnicalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.start=datetime(2024,1,1,tzinfo=timezone.utc)
        self.bars=[]
        for i in range(40):
            stamp=(self.start+timedelta(days=i)).isoformat()
            self.bars.append({'as_of':stamp,'known_at':stamp,'session_number':i,'complete':True,'open':100,'high':101,'low':99,'close':100,'volume':100})

    def tearDown(self):self.temp.cleanup()

    def payload(self,bars):
        return {'provider_verified':True,'adjustments_verified':True,'adjustment_policy':'unadjusted_no_actions','source':'Synthetic tests','venue':'TEST','calendar':'fixture','currency':'USD','timezone':'UTC','bars':bars}

    def test_rvol_uses_only_prior20_and_zero_is_real(self):
        self.bars[-1]['volume']=400
        self.assertEqual(t.rvol(self.bars,39)['value'],4)
        self.bars[-1]['volume']=0
        self.assertEqual(t.rvol(self.bars,39)['value'],0)
        self.assertEqual(t.volume_state(0),'NO_TRADES')
        self.bars[-1]['volume']=None
        self.assertEqual(t.rvol(self.bars,39)['status'],'UNAVAILABLE')
        self.bars[-1]['volume']=-1
        self.assertEqual(t.rvol(self.bars,39)['reason_codes'],['INVALID_VOLUME'])

    def test_flat_zero_flow_policy_and_insufficient_sma200(self):
        values=t.indicators(self.bars)
        self.assertEqual(values['RSI14']['value'],50)
        self.assertEqual(values['MFI14']['value'],50)
        self.assertEqual(values['MACD']['value'],0)
        self.assertEqual(values['OBV']['value'],0)
        self.assertEqual(values['SMA200']['status'],'UNAVAILABLE')
        for bar in self.bars:bar['volume']=0
        self.assertEqual(t.indicators(self.bars)['CMF20']['status'],'UNAVAILABLE')

    def test_events_have_evidence_and_follow_through_is_not_backdated(self):
        self.bars[30].update(low=97,close=100.5,volume=300)
        self.bars[31].update(high=103,close=102,volume=150)
        before=t.events('TEST',self.bars[:31])
        after=t.events('TEST',self.bars[:32])
        parent=next(e for e in before if e['rule']=='SPRING_CANDIDATE')
        self.assertEqual(parent,next(e for e in after if e['id']==parent['id']))
        follow=next(e for e in after if e['rule']=='SPRING_FOLLOW_THROUGH')
        self.assertEqual(follow['bar_index'],31)
        self.assertNotEqual(follow['bar_time'],parent['bar_time'])
        self.assertEqual(parent['source_bar']['volume'],300)

    def test_future_and_negative_data_rejected_and_partial_bar_excluded(self):
        self.bars[-1]['complete']=False
        t.ingest(self.root,'TEST',self.payload(self.bars),self.start+timedelta(days=40))
        data=t.analyze(self.root,'TEST')
        self.assertEqual(len(data['bars']),39)
        self.assertIsNone(data['trade_idea']['quantity'])
        self.assertIsNone(data['trap_radar']['probability'])
        invalid=copy.deepcopy(self.bars);invalid[-1]['volume']=-1
        with self.assertRaises(ValueError):t.ingest(self.root,'TEST',self.payload(invalid))
        invalid=copy.deepcopy(self.bars);invalid[-1]['known_at']='2099-01-01T00:00:00Z'
        with self.assertRaises(ValueError):t.ingest(self.root,'TEST',self.payload(invalid))

    def test_snapshot_known_after_origin_is_absent(self):
        t.ingest(self.root,'TEST',self.payload(self.bars),self.start+timedelta(days=60))
        replay=t.analyze(self.root,'TEST',(self.start+timedelta(days=45)).isoformat())
        self.assertEqual(replay['status'],'UNAVAILABLE')
        self.assertEqual(replay['events'],[])
