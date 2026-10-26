import unittest
import json
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit
import event_feed_sources as s

class RegionalNewsTests(unittest.TestCase):
 def test_world_global_are_not_lexical_search_terms(self):
  self.assertEqual(s.geography('World')[1],'')
  self.assertEqual(s.geography('global')[1],'')
 def test_regions_are_explicit(self):
  self.assertEqual(s.geography('Asia')[0],'Asia')
  self.assertEqual(s.geography('Southeast Asia')[0],'Southeast Asia')
  self.assertEqual(s.geography('Vietnam')[2],'VN')
  self.assertEqual(s.geography('United States')[2],'US')
 def test_official_feeds_are_factor_and_region_scoped(self):
  self.assertEqual(s._official_jobs('Inflation',s.geography('United States')),['BLS CPI'])
  self.assertEqual(s._official_jobs('Labor market',s.geography('USA')),['BLS Employment Situation'])
  self.assertEqual(len(s._official_jobs('Oil supply',s.geography('US'))),2)
  self.assertEqual(s._official_jobs('Inflation',s.geography('Vietnam')),[])
  self.assertEqual(s._official_jobs('Oil supply',s.geography('World')),[])

 def test_first_party_rss_rejects_foreign_links_or_unknown_timestamps(self):
  from datetime import datetime,timezone,timedelta
  date=(datetime.now(timezone.utc)-timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S +0000')
  document=f"""<rss><channel>
    <item><title>Consumer Price Index rises</title><link>https://www.bls.gov/news.release/cpi.htm</link><pubDate>{date}</pubDate><description>Latest CPI release</description></item>
    <item><title>Forged release</title><link>https://evil.example.org/fake</link><pubDate>{date}</pubDate></item>
    <item><title>Undated data</title><link>https://www.bls.gov/news.release/undated.htm</link></item>
  </channel></rss>""".encode()
  with patch.object(s,'_get',return_value=document) as get:
   rows=s._official_rss('BLS CPI')
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['source_tier'],'PRIMARY_OFFICIAL_UNVERIFIED_CLAIM')
  self.assertEqual(rows[0]['publisher_domain'],'www.bls.gov')
  self.assertTrue(rows[0]['source_direct'])
  self.assertEqual(rows[0]['time_basis'],'PUBLISHED')
  self.assertEqual(get.call_args.args[0],'https://www.bls.gov/feed/cpi.rss')

 def test_official_feed_rejects_unrecognized_feed_name(self):
  with self.assertRaises(s.FeedError):s._official_rss('user-provided')
  self.assertIn('www.eia.gov',s._get.__code__.co_consts.__repr__())

 def test_official_statistics_discovery_is_indexed_not_automatically_verified(self):
  queries=s._variants('GDP growth economic output recession','Vietnam',s.geography('Vietnam'),factor='GDP growth')
  self.assertEqual(len(queries),4)
  self.assertNotIn('site:nso.gov.vn',queries[0][0])

 def test_user_text_cannot_change_provider_host(self):
  with self.assertRaises(ValueError):s.geography('https://private.example')
  with self.assertRaises(ValueError):s.geography('Asia\nattack')
 def test_success_with_secondary_source_available(self):
  def job(q,edition):
   return [{'title':'Oil supply tightens','url':'https://news.google.com/articles/x','source':'Example',
      'description':'Crude production','published_at':'2026-10-20T02:00:00+00:00','provider':'Google News RSS'}]
  with patch.object(s,'_rss',side_effect=job),patch.object(s,'_gdelt',side_effect=s.FeedError('GDELT unavailable')):
   rows,coverage=s.retrieve('oil supply','Asia')
  self.assertEqual(coverage['region'],'Asia')
  self.assertEqual(coverage['feed_successes'],4)
  self.assertEqual(coverage['requests'],5)
  self.assertTrue(rows)

 def test_gdelt_preserves_seconds_and_first_seen_time_basis(self):
  payload={'articles':[{'title':'GDP report','url':'https://example.org/gdp','domain':'example.org','seendate':'20200102T123456Z'}]}
  with patch.object(s,'_get',return_value=json.dumps(payload).encode()):
   rows=s._gdelt('GDP')
  self.assertEqual(rows[0]['published_at'],'2020-01-02T12:34:56+00:00')
  self.assertEqual(rows[0]['time_basis'],'FIRST_SEEN')

 def test_scope_is_distinct_from_foreign_and_unconfirmed_context(self):
  self.assertEqual(s.scope_relation('Lạm phát Việt Nam hạ nhiệt','','Vietnam'),'DIRECT_SCOPE')
  self.assertEqual(s.scope_relation('US inflation rises','','Vietnam','Federal Reserve'),'EXTERNAL_CONTEXT')
  self.assertEqual(s.scope_relation('Inflation report released','','Vietnam'),'UNVERIFIED_SCOPE')
  self.assertEqual(s.scope_relation('Inflation report released','','World'),'GLOBAL_SCOPE')
  self.assertEqual(s.scope_relation('US inflation rises','','United States'),'DIRECT_SCOPE')
  self.assertEqual(s.scope_relation('U.S. inflation rises','','Vietnam'),'EXTERNAL_CONTEXT')
  self.assertEqual(s.scope_relation('Tell us about inflation','','United States'),'UNVERIFIED_SCOPE')

 def test_publisher_name_cannot_establish_the_articles_geographical_scope(self):
  self.assertEqual(s.scope_relation('Iran conflict could spread - Vietnam.vn','Iran conflict Vietnam.vn','Vietnam','Vietnam.vn'),'EXTERNAL_CONTEXT')
  self.assertEqual(s.scope_relation('Inflation report - Vietnam.vn','Inflation data Vietnam.vn','Vietnam','Vietnam.vn'),'UNVERIFIED_SCOPE')
  self.assertEqual(s.scope_relation('Vietnam inflation cools - Vietnam.vn','','Vietnam','Vietnam.vn'),'DIRECT_SCOPE')

 def test_vietnamese_cities_are_explicit_regional_evidence(self):
  titles=('Hà Nội tăng trưởng GDP', 'Hanoi inflation cools',
          'Ho Chi Minh City inflation cools', 'Thành phố Hồ Chí Minh tăng trưởng GDP',
          'TP. Hồ Chí Minh công bố CPI', 'TP.HCM công bố CPI', 'HCMC publishes inflation data')
  for focus in ('Vietnam','Asia','Southeast Asia'):
   for title in titles:
    with self.subTest(focus=focus,title=title):
     self.assertEqual(s.scope_relation(title,'',focus,'Reuters'),'DIRECT_SCOPE')
  self.assertEqual(s.scope_relation('Hanoi inflation cools - Hanoi Times','','Vietnam','Hanoi Times'),'DIRECT_SCOPE')

 def test_supported_regions_include_curated_country_names_and_demonyms(self):
  examples=(('Ukraine ceasefire talks begin','Europe'),('Ukrainian inflation eases','Europe'),
            ('Nigerian inflation eases','Africa'),('Kenya publishes GDP','Africa'),
            ('Colombian GDP expands','Latin America'),('Japanese GDP expands','Asia'),
            ('Philippine GDP expands','Southeast Asia'),('Lebanese ceasefire talks begin','Middle East'))
  for title,focus in examples:
   with self.subTest(title=title,focus=focus):
    self.assertEqual(s.scope_relation(title,'',focus),'DIRECT_SCOPE')
  self.assertEqual(s.scope_relation('Japanese inflation rises','','Vietnam'),'EXTERNAL_CONTEXT')
  self.assertEqual(s.scope_relation('Nigerian inflation eases','','Europe'),'EXTERNAL_CONTEXT')

 def test_country_focus_names_and_demonyms_use_canonical_aliases(self):
  for focus,title,country in (('Japan','Japanese GDP expands','Japan'),
                              ('Ukrainian','Ukraine ceasefire talks begin','Ukraine'),
                              ('Nigeria','Nigerian inflation eases','Nigeria'),
                              ('Britain','British inflation eases','United Kingdom')):
   with self.subTest(focus=focus):
    self.assertEqual(s.geography(focus)[0],country)
    self.assertEqual(s.scope_relation(title,'',focus),'DIRECT_SCOPE')
  # Selecting a specific city remains a city search, not a whole-country search.
  self.assertEqual(s.geography('Hanoi')[0],'Hanoi')

 def test_city_and_country_publishers_do_not_make_foreign_articles_local(self):
  for title,description,source in (
   ('Iran conflict escalates - Hanoi Times','Iran ceasefire report Hanoi Times','Hanoi Times'),
   ('Ho Chi Minh City News: Iran conflict escalates','','Ho Chi Minh City News'),
   ('Vietnam.vn: Iran conflict escalates','','Vietnam.vn'),
   ('Iran conflict escalates - Vietnam.vn','','Vietnam.vn'),
  ):
   with self.subTest(title=title):
    self.assertEqual(s.scope_relation(title,description,'Vietnam',source),'EXTERNAL_CONTEXT')
  self.assertEqual(s.scope_relation('CPI report released - Hanoi Times','','Vietnam','Hanoi Times'),'UNVERIFIED_SCOPE')
  self.assertEqual(s.scope_relation('Inflation report - US News','Inflation report US News','United States','US News'),'UNVERIFIED_SCOPE')

 def test_localized_queries_cover_every_supported_factor_without_more_requests(self):
  from event_news_preview import _TOPICS
  self.assertEqual(set(s.VIETNAMESE_TOPICS),{factor for factors in _TOPICS.values() for factor in factors})
  for factors in _TOPICS.values():
   for factor,(terms,_) in factors.items():
    with self.subTest(factor=factor):
     queries=s._variants(terms,'Vietnam',s.geography('Vietnam'),factor=factor,lookback_days=45)
     self.assertEqual(len(queries),4)
     self.assertTrue(all(query.endswith('when:45d') for query,_ in queries))
     vietnamese=[query for query,edition in queries if edition[1]=='VN']
     self.assertTrue(vietnamese)
     self.assertTrue(any(phrase in query for query in vietnamese for phrase in s.VIETNAMESE_TOPICS[factor]))
  conflict=s._variants('conflict escalation ceasefire regional security','Vietnam',s.geography('Vietnam'),factor='Conflict risk')
  self.assertIn('"xung đột"',conflict[-1][0])
  self.assertIn('"ngừng bắn"',conflict[-1][0])

 def test_vietnamese_editions_use_canonical_language_without_needing_redirects(self):
  for terms,factor in (('conflict escalation ceasefire','Conflict risk'),
                       ('shipping trade route supply disruption','Trade disruption')):
   with self.subTest(factor=factor):
    queries=s._variants(terms,'Vietnam',s.geography('Vietnam'),factor=factor)
    vietnamese=[edition for _,edition in queries if edition[1]=='VN']
    self.assertTrue(vietnamese)
    self.assertTrue(all(edition==('vi','VN','VN:vi') for edition in vietnamese))
    with patch.object(s,'_get',return_value=b'<rss><channel/></rss>') as fetch:
     s._rss('"xung đột" Việt Nam',vietnamese[0])
    params=parse_qs(urlsplit(fetch.call_args.args[0]).query)
    self.assertEqual(params['hl'],['vi'])
    self.assertEqual(params['gl'],['VN'])
    self.assertEqual(params['ceid'],['VN:vi'])

 def test_requested_lookback_reaches_google_queries_and_gdelt(self):
  for days in (1,7,45,60,90):
   with self.subTest(days=days):
    queries=s._variants('GDP growth output','World',s.geography('World'),factor='GDP growth',lookback_days=days)
    self.assertTrue(all(query.endswith(f'when:{days}d') for query,_ in queries))
    with patch.object(s,'_get',return_value=b'{"articles":[]}') as fetch:
     self.assertEqual(s._gdelt('GDP',lookback_days=days),[])
    self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0]).query)['timespan'],[f'{days}d'])
  with patch.object(s,'_get',return_value=b'{"articles":[]}') as fetch:
   s._gdelt('GDP')
  self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0]).query)['timespan'],['30d'])

 def test_invalid_lookback_is_rejected_before_provider_requests(self):
  for invalid in (0,-1,91,True,30.0,'30',None):
   with self.subTest(invalid=invalid),patch.object(s,'_get') as fetch,patch.object(s,'_rss') as rss:
    with self.assertRaises(ValueError):s.retrieve('GDP','Vietnam',lookback_days=invalid)
    with self.assertRaises(ValueError):s._gdelt('GDP',lookback_days=invalid)
    fetch.assert_not_called();rss.assert_not_called()

 def test_per_request_results_distinguish_failure_empty_and_articles(self):
  def rss(query,edition):
   if edition[1]=='GB':raise s.FeedError('NEWS_HTTP_403')
   if edition[1]=='VN':return []
   return [{'title':'GDP update','provider':'Google News RSS'}]
  with patch.object(s,'_rss',side_effect=rss),patch.object(s,'_gdelt',return_value=[]) as gdelt:
   rows,coverage=s.retrieve('GDP growth output','Vietnam',factor='GDP growth',lookback_days=45)
  self.assertEqual(coverage['requests'],6)
  self.assertEqual(coverage['feed_successes'],5)
  self.assertEqual(coverage['lookback_days'],45)
  self.assertEqual(len(coverage['request_results']),6)
  self.assertTrue(any(x['provider']=='Google News official-site discovery' for x in coverage['request_results']))
  self.assertEqual(len(rows),2)
  by_edition={row['edition']:row for row in coverage['request_results']}
  self.assertEqual(by_edition['GB']['status'],'FAILED')
  self.assertEqual(by_edition['GB']['reason'],'NEWS_HTTP_403')
  self.assertEqual(by_edition['VN']['status'],'SUCCESS')
  self.assertEqual(by_edition['VN']['returned_count'],0)
  self.assertEqual(by_edition['US']['returned_count'],1)
  self.assertEqual(gdelt.call_args.kwargs,{'lookback_days':45})

 def test_all_failed_requests_preserve_diagnostics_in_feed_error(self):
  with patch.object(s,'_rss',side_effect=s.FeedError('NEWS_HTTP_403')),patch.object(s,'_gdelt',side_effect=s.FeedError('NEWS_HTTP_429')):
   with self.assertRaises(s.FeedError) as caught:
    s.retrieve('conflict escalation ceasefire','Vietnam',factor='Conflict risk',lookback_days=45)
  self.assertEqual(str(caught.exception),'ALL_NEWS_FEEDS_UNAVAILABLE')
  coverage=caught.exception.coverage
  self.assertEqual(coverage['feed_successes'],0)
  self.assertEqual(coverage['requests'],5)
  self.assertEqual(len(coverage['request_results']),5)
  self.assertTrue(all(row['status']=='FAILED' and row['returned_count']==0 for row in coverage['request_results']))
  self.assertEqual({row['reason'] for row in coverage['request_results']},{'NEWS_HTTP_403','NEWS_HTTP_429'})

 def test_arbitrary_provider_errors_do_not_disclose_urls_or_payloads(self):
  with patch.object(s,'_rss',side_effect=s.FeedError('https://example.invalid/?token=PRIVATE')),patch.object(s,'_gdelt',return_value=[]):
   _,coverage=s.retrieve('GDP','Vietnam')
  serialized=json.dumps(coverage)
  self.assertNotIn('PRIVATE',serialized)
  self.assertNotIn('https://',serialized)
  self.assertEqual({row['reason'] for row in coverage['feed_failures']},{'PROVIDER_RESPONSE_ERROR'})

 def test_http_status_codes_are_preserved_without_provider_error_bodies(self):
  for status in (403,429,503):
   with self.subTest(status=status),patch.object(s._OPENER,'open',side_effect=HTTPError('https://news.google.com/private?token=PRIVATE',status,'secret response',{},None)):
    with self.assertRaises(s.FeedError) as caught:s._get('https://news.google.com/rss','application/xml')
    self.assertEqual(str(caught.exception),f'NEWS_HTTP_{status}')

 def test_unreachable_port_bulletins_are_failed_not_successful_empty(self):
  with patch.object(s,'_get',side_effect=s.FeedError('NEWS_HTTP_403')):
   with self.assertRaises(s.FeedError) as caught:s._port_report_vietnam()
  self.assertEqual(str(caught.exception),'PORT_REPORTS_UNAVAILABLE')
if __name__=='__main__':unittest.main()
