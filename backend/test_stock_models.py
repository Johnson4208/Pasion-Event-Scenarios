import copy
import math
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import stock_models as s


class StockModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.start=datetime(2020,1,1,tzinfo=timezone.utc)
        self.bars=[]
        for i in range(460):
            close=100+math.sin(i*.4)*8+i*.02
            stamp=(self.start+timedelta(days=i)).isoformat()
            self.bars.append({'as_of':stamp,'known_at':stamp,'session_number':i,'complete':True,'open':close,'high':close+1,'low':close-1,'close':close,'volume':100})
        self.freeze_time=self.start+timedelta(days=300,hours=1)

    def tearDown(self):
        self.temp.cleanup()

    def frozen(self):
        return s.freeze(self.root,'TEST',5,self.bars[:301],'Synthetic test fixture',self.freeze_time)

    def test_frozen_model_abstains_before_future_cohort(self):
        model=self.frozen()
        report=s.evaluate(self.root,model['model_id'],self.bars[:301],self.freeze_time)
        self.assertEqual(report['sample_count'],0)
        self.assertIsNone(report['p_up'])
        self.assertEqual(report['status'],'UNCERTAIN')
        for fold in model['walk_forward']:
            self.assertLess(fold['train_end'],fold['test_start'])

    def test_future_bars_incomplete_sessions_and_negative_volume_rejected(self):
        for change in [{'complete':False},{'volume':-1},{'known_at':'2030-01-01T00:00:00Z'}]:
            bars=copy.deepcopy(self.bars[:301]);bars[-1].update(change)
            with self.assertRaises(ValueError):
                s.freeze(self.root,'TEST',5,bars,'Test',self.freeze_time)

    def test_revised_features_and_changed_training_snapshot_rejected(self):
        model=self.frozen()
        changed=copy.deepcopy(self.bars);changed[0]['close']+=.1
        with self.assertRaises(ValueError):
            s.evaluate(self.root,model['model_id'],changed,self.start+timedelta(days=460))
        changed=copy.deepcopy(self.bars[:301]);changed[299]['known_at']=(self.start+timedelta(days=310)).isoformat()
        with self.assertRaises(ValueError):
            s.features(changed,300)

    def test_expiry_and_poor_skill_suppress_direction(self):
        model=self.frozen();evaluation_time=self.start+timedelta(days=459,hours=1)
        with patch.object(s,'calibrated',return_value=.99):
            report=s.evaluate(self.root,model['model_id'],self.bars,evaluation_time)
        self.assertGreaterEqual(report['sample_count'],80)
        self.assertLess(report['brier_skill'],0)
        self.assertIsNone(report['p_up'])
        state=s.analysis(self.root,'TEST',evaluation_time)['horizons'][0]
        self.assertEqual(state['direction'],'UNCERTAIN')
        expired=s.analysis(self.root,'TEST',evaluation_time+timedelta(days=2))['horizons'][0]
        self.assertEqual(expired['status'],'UNAVAILABLE')
        replay=s.analysis(self.root,'TEST',self.freeze_time)['horizons'][0]
        self.assertEqual(replay['features'],{})
        self.assertNotIn('brier_skill',replay)

    def test_ready_probability_is_complementary_and_data_coverage_is_not_confidence(self):
        model=self.frozen();evaluation_time=self.start+timedelta(days=459,hours=1)
        def oracle(package,x):
            # Deterministic synthetic fixture to exercise the release gate, not model performance.
            i=next(j for j in range(20,len(self.bars)) if s.features(self.bars,j)==x)
            if i+5>=len(self.bars):return .7
            return .99 if self.bars[i+5]['close']>self.bars[i]['close'] else .01
        with patch.object(s,'calibrated',side_effect=oracle):
            report=s.evaluate(self.root,model['model_id'],self.bars,evaluation_time)
        self.assertEqual(report['status'],'READY')
        self.assertAlmostEqual(report['p_up']+report['p_down'],1)
        state=s.analysis(self.root,'TEST',evaluation_time)
        self.assertIsNone(state['confidence'])
        self.assertEqual(state['horizons'][0]['direction'],'UP')
