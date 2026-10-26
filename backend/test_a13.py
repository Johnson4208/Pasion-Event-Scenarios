import unittest,sqlite3,json
from datetime import datetime,timezone,timedelta
import evidence_service as e
import event_research as events
class EvidenceBoundaryTests(unittest.TestCase):
 def test_clocks_and_verdicts(self):
  r=e.latency('2026-10-12T00:00:00Z','2026-10-12T01:00:00Z','2026-10-13T00:00:00Z')
  self.assertEqual(r['feed_latency_seconds'],3600);self.assertEqual(r['verification_latency_seconds'],82800)
  self.assertEqual(e.verdict([]),'INSUFFICIENT');self.assertEqual(e.verdict(['SUPPORTING','REFUTING']),'CONFLICTING')
  self.assertEqual(e.usable_event_time([{'known_at':'2026-10-12T00:00:00Z'},{'known_at':'2026-10-13T00:00:00Z'}]),'2026-10-13T00:00:00Z')
 def test_news_retrieval_is_proxy_and_not_visible_before_known(self):
  from unittest.mock import patch
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)')
  article={'id':'article','cluster_id':'announcement','provider':'Source','url':'https://example.com/story','revision':'1','published_at':'2026-10-12T00:00:00Z','ingested_at':'2026-10-13T00:00:00Z','known_at':'2026-10-13T00:00:00Z','claims':[{'id':'claim','text':'Announcement','review':{'id':'verdict','known_at':'2026-10-13T01:00:00Z','status':'SUPPORTED'}}]}
  try:
   with patch('news_evidence.feed',return_value={'articles':[article,article]}):
    claims=events.eligible(db,datetime(2026,10,14,tzinfo=timezone.utc));self.assertEqual(len(claims),1);self.assertEqual(claims[0]['input_type'],'PROXY');self.assertEqual(claims[0]['known_at'],'2026-10-13T01:00:00Z')
    self.assertEqual(events.eligible(db,datetime(2026,10,12,tzinfo=timezone.utc)),[])
  finally:db.close()
