import os
import tempfile
import unittest
from unittest.mock import patch
import event_agent_store as store
class IndependentEventStoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'PASION_EVENT_AGENT_DB':os.path.join(self.tmp.name,'independent.sqlite3')})
  self.env.start()
  store.init()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def sample(self):
  return {'status':'EVIDENCE_AVAILABLE','items':[{'id':'source1','title':'Oil update','url':'https://example.org','published_at':'2026-10-21T00:00:00Z','direction':-1}],
    'dynamic_scenarios':{'ranked_scenarios':[{'id':'risk','rank':1,'support_index':.5}]},'source_count':1}
 def test_unchanged_evidence_does_not_duplicate_version(self):
  watch=next(x for x in store.watches() if x['factor']=='Oil supply' and x['focus']=='World' and x['horizon']=='30 days')
  store.write_result(watch['id'],self.sample(),'2026-10-21T01:00:00Z')
  changed=self.sample();changed['generated_at']='2026-10-21T01:30:00Z'
  store.write_result(watch['id'],changed,'2026-10-21T01:30:00Z')
  result=store.read('Energy','Oil supply','World','30 days')
  self.assertEqual(len(result['versions']),1)
  self.assertEqual(result['last_poll']['status'],'UNCHANGED')
 def test_evidence_change_produces_revision(self):
  watch=next(x for x in store.watches() if x['factor']=='Oil supply' and x['focus']=='World' and x['horizon']=='30 days')
  store.write_result(watch['id'],self.sample(),'2026-10-21T01:00:00Z')
  nextval=self.sample();nextval['items'].append({'id':'source2','title':'New release','url':'https://example.org/2','published_at':'2026-10-21T01:00:00Z','direction':1})
  store.write_result(watch['id'],nextval,'2026-10-21T01:30:00Z')
  result=store.read('Energy','Oil supply','World','30 days')
  self.assertEqual(len(result['versions']),2)
  self.assertEqual(result['latest']['changes']['added_source_ids'],['source2'])
 def test_fetch_error_does_not_delete_previous(self):
  watch=next(x for x in store.watches() if x['factor']=='Oil supply' and x['focus']=='World' and x['horizon']=='30 days')
  store.write_result(watch['id'],self.sample(),'2026-10-21T01:00:00Z')
  store.write_failure(watch['id'],'NO_CONNECTION','2026-10-21T01:30:00Z')
  result=store.read('Energy','Oil supply','World','30 days')
  self.assertEqual(len(result['versions']),1)
  self.assertEqual(result['last_poll']['status'],'FETCH_FAILED')
 def test_store_is_separate_from_account_memory(self):
  path=store.location()
  self.assertNotIn('accounts.sqlite3',str(path))
  db=store.connect()
  self.assertEqual({x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} & {'accounts','sessions','portfolio'},set())
  db.close()
if __name__=='__main__':unittest.main()
