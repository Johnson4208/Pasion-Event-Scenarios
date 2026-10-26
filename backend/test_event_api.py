import http.client
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from datetime import datetime, timezone
from pathlib import Path
import event_news_preview
import event_forecasts
from test_event_forecasts import specification, NOW
import test_server as fixtures


class EventApiTests(unittest.TestCase):
    setUp=fixtures.ChangePasswordTests.setUp
    tearDown=fixtures.ChangePasswordTests.tearDown
    authorize=fixtures.AdminTests.authorize
    def call(self,method,path,data=None,token='active'):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        connection.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'solvai_session='+token})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result
    def test_authentication_roles_and_missing_contract(self):
        self.assertEqual(self.call('GET','/api/research/events',token='missing')[0],401)
        self.assertEqual(self.call('GET','/api/research/events')[1]['studies'],[])
        self.assertEqual(self.call('POST','/api/admin/events/evidence',{})[0],403)
        self.assertEqual(self.call('POST','/api/research/events',{})[0],400)
        self.assertEqual(self.call('POST','/api/research/events/resolve',{'version_id':'another'})[0],400)
        self.authorize();self.assertEqual(self.call('POST','/api/admin/events/evidence',{},token='admin')[0],400)

    def test_live_route_preserves_scope_and_evidence_only_contract(self):
        query={'category':'Economy','factor':'GDP growth','focus':'Vietnam','horizon':'30 days'}
        article={'title':'Vietnam GDP growth declines sharply','description':'Vietnam economic output contracts',
                 'url':'https://example.org/gdp','source':'API fixture',
                 'published_at':datetime.now(timezone.utc).isoformat()}
        with event_news_preview._lock:event_news_preview._cache.clear()
        with patch.object(event_news_preview.event_feed_sources,'retrieve',return_value=([article],{'feed_successes':1,'requests':1})):
            status,result=self.call('GET','/api/research/events/live?'+urlencode(query))
        with event_news_preview._lock:event_news_preview._cache.clear()
        self.assertEqual(status,200)
        self.assertEqual(result['focus'],'Vietnam')
        self.assertFalse(result['calibrated_probability'])
        self.assertEqual(result['items'][0]['direction'],-1)
        self.assertEqual(result['items'][0]['geographic_relation'],'DIRECT_SCOPE')
        self.assertEqual(result['dynamic_scenarios']['ranking_metric'],'SIGNED_EVIDENCE_BALANCE')
        self.assertEqual(result['dynamic_scenarios']['scenario_distribution']['status'],'WITHHELD_CONCENTRATED_EVIDENCE')
        self.assertIsNone(result['dynamic_scenarios']['scenario_distribution']['total_percent'])
        self.assertEqual(result['scenario_presentation']['type'],'UNAVAILABLE')
        self.assertFalse(result['calibrated_probability'])
        self.assertEqual(sum(s['scenario_share_percent'] for s in result['dynamic_scenarios']['ranked_scenarios']),0.0)
        self.assertTrue(all(s['experimental_probability'] is None or s['experimental_probability']['calibrated'] is False for s in result['dynamic_scenarios']['ranked_scenarios']))

    def test_live_feed_failure_is_reported_without_manufactured_results(self):
        with event_news_preview._lock:event_news_preview._cache.clear()
        with patch.object(event_news_preview.event_feed_sources,'retrieve',side_effect=event_news_preview.event_feed_sources.FeedError('ALL_NEWS_FEEDS_UNAVAILABLE')):
            status,result=self.call('GET','/api/research/events/live?'+urlencode({'category':'Economy','factor':'GDP growth','focus':'Vietnam','horizon':'30 days'}))
        self.assertEqual(status,503)
        self.assertEqual(result['items'],[])

    def test_failed_feed_diagnostics_survive_the_api_without_a_fake_report(self):
        coverage={'requests':5,'feed_successes':0,'raw_results':0,
                  'feed_failures':[{'provider':'Google News RSS','reason':'NEWS_HTTP_429'}],
                  'request_results':[{'provider':'Google News RSS','edition':'VN','status':'FAILED','returned_count':0,'reason':'NEWS_HTTP_429'}]}
        failure=event_news_preview.event_feed_sources.FeedError('ALL_NEWS_FEEDS_UNAVAILABLE')
        failure.coverage=coverage
        with event_news_preview._lock:event_news_preview._cache.clear()
        with patch.object(event_news_preview.event_feed_sources,'retrieve',side_effect=failure):
            status,result=self.call('GET','/api/research/events/live?'+urlencode({'category':'Economy','factor':'GDP growth','focus':'Vietnam','horizon':'30 days'}))
        self.assertEqual(status,503)
        self.assertEqual(result['coverage'],coverage)
        self.assertEqual(result['items'],[])
        self.assertNotIn('dynamic_scenarios',result)

    def test_complete_reference_family_is_available_even_if_news_transport_is_down(self):
        spec=specification()
        model=event_forecasts.build(spec,'automated synthetic fixture',NOW)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.json'
            path.write_text(json.dumps({'schema_version':1,'models':[model]}))
            with patch.dict(os.environ,{'PASION_EVENT_MODELS_PATH':str(path)}), patch.object(event_news_preview.event_feed_sources,'retrieve',side_effect=event_news_preview.event_feed_sources.FeedError('ALL_NEWS_FEEDS_UNAVAILABLE')):
                with event_news_preview._lock:event_news_preview._cache.clear()
                status,result=self.call('GET','/api/research/events/live?'+urlencode(spec['context']))
            with event_news_preview._lock:event_news_preview._cache.clear()
        self.assertEqual(status,200)
        self.assertEqual(result['status'],'FORECAST_AVAILABLE')
        self.assertEqual(result['coverage']['status'],'UNAVAILABLE')
        self.assertEqual(result['scenario_forecast']['status'],'REFERENCE_ESTIMATE_AVAILABLE')
        self.assertEqual(len(result['scenario_forecast']['probabilities']),3)
        self.assertAlmostEqual(sum(result['scenario_forecast']['probabilities'].values()),1)
        self.assertFalse(result['scenario_forecast']['news_adjusted'])

    def test_invalid_probability_basis_is_rejected_before_retrieval(self):
        query={'category':'Economy','factor':'GDP growth','focus':'Vietnam','horizon':'30 days','basis':'MADE_UP'}
        with patch.object(event_news_preview.event_feed_sources,'retrieve') as retrieve:
            self.assertEqual(self.call('GET','/api/research/events/live?'+urlencode(query))[0],400)
            retrieve.assert_not_called()
