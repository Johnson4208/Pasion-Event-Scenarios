import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import event_topic_matcher as m
import event_news_preview as n

class TopicMatcherTests(unittest.TestCase):
 def test_vietnam_gdp_real_article(self):
  self.assertTrue(m.inspect("GDP Việt Nam tăng trưởng 7,1% trong quý III","Báo cáo Tổng cục thống kê","GDP growth","GDP growth economic output recession")["eligible"])
 def test_generic_science_article_not_gdp(self):
  self.assertFalse(m.inspect("Research and development of flowers in Vietnam","Universities and businesses collaborate in science","GDP growth","GDP growth economic output recession")["eligible"])
 def test_generic_growth_not_gdp(self):
  self.assertFalse(m.inspect("Flowers show growth in research","Research institutions developing partnerships","GDP growth","GDP growth economic output recession")["eligible"])
 def test_macro_headline(self):
  self.assertTrue(m.inspect("Vietnam economic growth forecast raised","GDP output expansion","GDP growth","GDP growth economic output recession")["eligible"])
 def test_trade_disruption_vietnam(self):
  self.assertTrue(m.inspect('Ùn tắc cảng biển gây gián đoạn vận tải tại Việt Nam','Hoạt động logistics bị trì hoãn','Trade disruption','shipping trade route supply disruption')['eligible'])
  self.assertFalse(m.inspect('Vietnam expands maritime transport investments','Supply chain development program','Trade disruption','shipping trade route supply disruption')['eligible'])
 def test_diagnostics_in_no_evidence_case(self):
  now=datetime(2026,10,21,12,tzinfo=timezone.utc)
  rows=[{"title":"Research collaboration improves flowers","description":"Academic research","source":"Example","published_at":(now-timedelta(days=1)).isoformat(),"url":"https://news.google.com/a"},
        {"title":"Vietnam GDP rises in third quarter","description":"Economic output grows","source":"Example","published_at":(now-timedelta(days=60)).isoformat(),"url":"https://news.google.com/b"}]
  with n._lock:n._cache.clear()
  with patch.object(n.event_feed_sources,"retrieve",return_value=(rows,{"feed_successes":3,"requests":5})):
   result=n.analyze("Economy","GDP growth","Vietnam","90 days",now)
  self.assertEqual(result["status"],"UNAVAILABLE")
  self.assertEqual(result["source_count"],0)
  self.assertEqual(result["filter_diagnostics"]["off_topic"],1)
  self.assertEqual(result["filter_diagnostics"]["stale"],1)

if __name__=="__main__":unittest.main()
