"""HTTP contract checks for automatic, source-backed research forecasts."""
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import server
import event_news_preview
import test_server as fixtures
import test_event_api as event_api_fixtures


class ResearchForecastApiTests(unittest.TestCase):
    setUp = fixtures.ChangePasswordTests.setUp
    tearDown = fixtures.ChangePasswordTests.tearDown
    call = event_api_fixtures.EventApiTests.call

    def context(self):
        return dict(category='Markets', factor='Equity volatility', focus='United States',
                    horizon='30 days', basis='END_STATE')

    def model(self):
        now = datetime.now(timezone.utc)
        return dict(schema_version=2, method='RETROSPECTIVE_SERIES_REFERENCE_V1',
                    status='RESEARCH_ESTIMATE_AVAILABLE', context=self.context(),
                    as_of=now.isoformat(), forecast_origin_at=now.isoformat(),
                    maturity_at=(now+timedelta(days=30)).isoformat(),
                    source={'profile_id':'us-volatility'})

    def test_forecast_routes_require_a_current_session_before_any_data_work(self):
        with patch.object(server.event_series_forecasts, 'prepare') as prepare, \
                patch.object(server.event_series_forecasts, 'options') as options:
            for method, route, data in (
                ('POST','/api/research/events/forecast',self.context()),
                ('GET','/api/research/events/forecast-options',None),
                ('GET','/api/research/events/forecast-history',None),
            ):
                self.assertEqual(self.call(method,route,data,token='missing')[0],401)
            prepare.assert_not_called()
            options.assert_not_called()

    def test_primary_forecast_does_not_depend_on_live_news(self):
        model = self.model()
        with patch.object(server.event_forecasts,'forecast',return_value={'status':'UNAVAILABLE'}), \
                patch.object(server.event_series_forecasts,'prepare',return_value=model) as prepare, \
                patch.object(server.event_forecast_ledger,'record',return_value={'status':'PENDING','id':'synthetic'}) as record, \
                patch.object(server.event_forecast_ledger,'resolve_due',return_value={}), \
                patch.object(event_news_preview.event_feed_sources,'retrieve') as news:
            code, result = self.call('POST','/api/research/events/forecast',self.context())
        self.assertEqual(code,200)
        prepare.assert_called_once_with(**self.context())
        record.assert_called_once_with(model)
        news.assert_not_called()
        self.assertEqual(result['scenario_forecast'],model)
        self.assertEqual(result['status'],'FORECAST_AVAILABLE')
        self.assertEqual(result['generated_at'],model['as_of'])
        self.assertEqual(result['evidence_status'],'NOT_REQUESTED')
        self.assertEqual(result['dynamic_scenarios']['ranked_scenarios'],[])
        self.assertFalse(result['calibrated_probability'])

    def test_unsupported_question_is_specific_and_never_manufactures_a_distribution(self):
        context = dict(category='Geopolitics',factor='Conflict risk',focus='Vietnam',horizon='30 days',basis='END_STATE')
        model = {'schema_version':2,'status':'UNSUPPORTED_CONTEXT','context':context,
                 'missing_requirements':['MEASURABLE_END_STATE_REQUIRED','HISTORICAL_OUTCOMES_REQUIRED'],
                 'probabilities':None,'scenarios':[]}
        with patch.object(server.event_forecasts,'forecast',return_value={'status':'UNAVAILABLE'}), \
                patch.object(server.event_series_forecasts,'prepare',return_value=model), \
                patch.object(server.event_forecast_ledger,'record') as record:
            code, result = self.call('POST','/api/research/events/forecast',context)
        self.assertEqual(code,200)
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertEqual(result['scenario_forecast'],model)
        self.assertEqual(result['focus'],'Vietnam')
        record.assert_not_called()

    def test_input_cannot_select_arbitrary_files_urls_or_unknown_contexts(self):
        with patch.object(server.event_series_forecasts,'prepare') as prepare:
            for payload in (
                dict(self.context(),source_url='https://example.invalid/history'),
                dict(self.context(),path='../accounts.sqlite3'),
                dict(self.context(),factor='unknown'),
                dict(self.context(),horizon='100000 days'),
                dict(self.context(),focus='https://private.invalid'),
                dict(self.context(),basis='UNKNOWN'),
                ['invalid'],
            ):
                self.assertEqual(self.call('POST','/api/research/events/forecast',payload)[0],400)
            prepare.assert_not_called()

    def test_existing_reviewed_catalog_remains_usable_without_retraining(self):
        model = {'status':'REFERENCE_ESTIMATE_AVAILABLE','as_of':datetime.now(timezone.utc).isoformat()}
        with patch.object(server.event_forecasts,'forecast',return_value=model), \
                patch.object(server.event_series_forecasts,'prepare') as prepare:
            code, result = self.call('POST','/api/research/events/forecast',self.context())
        self.assertEqual(code,200)
        self.assertEqual(result['scenario_forecast'],model)
        prepare.assert_not_called()

    def test_recording_failure_is_disclosed_without_erasing_the_research_estimate(self):
        with patch.object(server.event_forecasts,'forecast',return_value={'status':'UNAVAILABLE'}), \
                patch.object(server.event_series_forecasts,'prepare',return_value=self.model()), \
                patch.object(server.event_forecast_ledger,'record',side_effect=sqlite3.OperationalError('synthetic lock')):
            code, result = self.call('POST','/api/research/events/forecast',self.context())
        self.assertEqual(code,200)
        self.assertEqual(result['status'],'FORECAST_AVAILABLE')
        self.assertEqual(result['forecast_recording']['status'],'RECORDING_UNAVAILABLE')

    def test_available_profiles_and_prospective_summary_have_explicit_policies(self):
        with patch.object(server.event_series_forecasts,'options',return_value=[{'id':'us-volatility'}]), \
                patch.object(server.event_forecast_ledger,'summary',return_value={'calibration_status':'NOT_ESTABLISHED','resolved_count':0}):
            code, profiles = self.call('GET','/api/research/events/forecast-options')
            self.assertEqual(code,200)
            self.assertEqual(profiles['profiles'],[{'id':'us-volatility'}])
            self.assertIn('NOT_PROSPECTIVELY_CALIBRATED',profiles['policy'])
            code, history = self.call('GET','/api/research/events/forecast-history')
            self.assertEqual(code,200)
            self.assertEqual(history['calibration_status'],'NOT_ESTABLISHED')

    def test_resolution_failure_preserves_a_successfully_recorded_forecast(self):
        with patch.object(server.event_forecasts,'forecast',return_value={'status':'UNAVAILABLE'}), \
                patch.object(server.event_series_forecasts,'prepare',return_value=self.model()), \
                patch.object(server.event_forecast_ledger,'record',return_value={'status':'PENDING','id':'synthetic'}), \
                patch.object(server.event_forecast_ledger,'resolve_due',side_effect=sqlite3.OperationalError('synthetic lock')):
            code, result = self.call('POST','/api/research/events/forecast',self.context())
        self.assertEqual(code,200)
        self.assertEqual(result['forecast_recording']['status'],'PENDING')
        self.assertEqual(result['forecast_recording']['resolution_status'],'TEMPORARILY_UNAVAILABLE')

    def test_a_prepared_series_estimate_survives_news_transport_failure(self):
        model = self.model()
        with event_news_preview._lock:
            event_news_preview._cache.clear()
        with patch.object(event_news_preview.event_forecasts,'forecast',return_value={'status':'UNAVAILABLE'}), \
                patch.object(event_news_preview.event_series_forecasts,'forecast',return_value=model), \
                patch.object(event_news_preview.event_feed_sources,'retrieve',side_effect=event_news_preview.event_feed_sources.FeedError('ALL_NEWS_FEEDS_UNAVAILABLE')):
            report = event_news_preview.analyze(**self.context())
        with event_news_preview._lock:
            event_news_preview._cache.clear()
        self.assertEqual(report['status'],'FORECAST_AVAILABLE')
        self.assertEqual(report['scenario_forecast'],model)
        self.assertEqual(report['items'],[])
        self.assertEqual(report['coverage']['status'],'UNAVAILABLE')
