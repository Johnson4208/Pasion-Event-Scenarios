import copy,unittest
from datetime import datetime,timezone,timedelta
import stock_models as s
class A09Tests(unittest.TestCase):
 def bars(self):
  start=datetime(2026,1,1,tzinfo=timezone.utc)
  return [{'close':100+i*.1,'known_at':(start+timedelta(days=i)).isoformat()} for i in range(40)]
 def test_features_cannot_see_future(self):
  bars=self.bars();before=s.features(bars,25);changed=copy.deepcopy(bars)
  for b in changed[26:]:b['close']=100000
  self.assertEqual(before,s.features(changed,25))
  changed[5]['known_at']=changed[39]['known_at']
  with self.assertRaises(ValueError):s.features(changed,25)
 def test_skill_gates_and_constant_prediction_not_confidence(self):
  self.assertEqual(s.reliability([.99,.01],[1,0],.5)['status'],'READY')
  self.assertEqual(s.reliability([.99,.99],[1,0],.5)['status'],'UNCERTAIN')
  self.assertEqual(s.reliability([.99,.99],[1,1],.5)['status'],'UNCERTAIN')
 def test_artifact_identity_is_content_based(self):
  self.assertEqual(s.artifact_hash({'a':1,'b':2}),s.artifact_hash({'b':2,'a':1}))
  self.assertNotEqual(s.artifact_hash([1]),s.artifact_hash([2]))
