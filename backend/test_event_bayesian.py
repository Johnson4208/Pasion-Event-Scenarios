import unittest
import event_bayesian as b

class BayesianTests(unittest.TestCase):
 def test_valid_independent_evidence_can_exceed_70_percent(self):
  model={'reviewed':True,'holdout_validated':True,'holdout_sample_count':200,'model_version':'validated-v1'}
  prior={'yes':0.2,'no':0.8}
  evidence=[{'group_id':'a','reviewed':True,'independence_reviewed':True,'likelihood_ratio':{'yes':5,'no':1}},
            {'group_id':'b','reviewed':True,'independence_reviewed':True,'likelihood_ratio':{'yes':8,'no':1}}]
  result=b.revision(prior,evidence,model)
  self.assertGreater(result['posterior']['yes'],.9)
  self.assertAlmostEqual(sum(result['posterior'].values()),1)
 def test_unreviewed_or_duplicate_fails_closed(self):
  model={'reviewed':True,'holdout_validated':True,'holdout_sample_count':200,'model_version':'v1'}
  prior={'yes':.2,'no':.8}
  item={'group_id':'a','reviewed':True,'independence_reviewed':True,'likelihood_ratio':{'yes':5,'no':1}}
  for data in ([dict(item,independence_reviewed=False)],[item,item]):
   with self.assertRaises(b.ModelUnavailable):b.revision(prior,data,model)
 def test_no_validation_no_probability(self):
  with self.assertRaises(b.ModelUnavailable):b.revision({'a':.5,'b':.5},[],{'reviewed':True,'holdout_validated':False})
  self.assertIsNone(b.unavailable()['posterior'])
if __name__=='__main__':unittest.main()
