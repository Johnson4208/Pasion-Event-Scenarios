"""Synthetic measurements test research-model arithmetic, never production data."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import event_outcome_data
import event_series_forecasts as f


NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def snapshot(ident='us-volatility', count=4000, cadence=1, latest=None):
    """Deterministic nonfinancial fixture, conspicuously synthetic."""
    latest = latest or NOW.date()
    profile = event_outcome_data.PROFILES[ident]
    observations = []
    for index in range(count):
        period = latest-timedelta(days=(count-index-1)*cadence)
        value = 20+8*math.sin(index/17)+5*math.sin(index/53) if ident == 'us-volatility' else 5+math.sin(index/11)
        observations.append({'key': period.isoformat(), 'period': period.isoformat(), 'value': value,
                             'publication_at': None, 'vintage': 'SYNTHETIC_TEST_ONLY'})
    return {'schema_version': 1, 'profile_id': ident, 'profile': dict(profile),
            'retrieved_at': NOW.isoformat(),
            'source_urls': ['https://fred.stlouisfed.org/graph/fredgraph.csv?id='+profile['metric']],
            'response_sha256': hashlib.sha256(b'synthetic test only').hexdigest(),
            'observations': observations, 'point_in_time_ready': False}


def context(ident='us-volatility', horizon='30 days'):
    return {key: f._PROFILES[ident][key] for key in ('category', 'factor', 'focus')} | {'horizon': horizon, 'basis': 'END_STATE'}


class SeriesForecastTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {'PASION_EVENT_SERIES_DIR': str(self.root/'models'),
                                                   'PASION_EVENT_HISTORY_PATH': str(self.root/'outcomes.sqlite3')})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def build(self, ident='us-volatility', source=None, horizon='30 days'):
        return f._build(source or snapshot(ident), 'a'*64, context(ident, horizon), ident, f._PROFILES[ident], NOW)

    def test_options_declare_real_coverage_without_network_or_creating_state(self):
        with patch.object(event_outcome_data, 'collect', side_effect=AssertionError('GET must not collect')):
            options = f.options()
        self.assertEqual({row['profile_id'] for row in options}, {'us-volatility', 'us-mortgages'})
        self.assertTrue(all(row['label'] and row['scenarios'] for row in options))
        mortgages = next(row for row in options if row['profile_id'] == 'us-mortgages')
        self.assertNotIn('1 day', mortgages['supported_horizons'])
        self.assertIn('7 days', mortgages['supported_horizons'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unsupported_question_and_measurement_frequency_never_fetch_or_substitute(self):
        cases = [(dict(category='Geopolitics', factor='Conflict risk', focus='Vietnam', horizon='30 days', basis='END_STATE'), 'UNSUPPORTED_CONTEXT'),
                 (dict(context('us-mortgages'), horizon='1 day'), 'UNSUPPORTED_HORIZON'),
                 (dict(context(), basis='OCCURRENCE'), 'UNSUPPORTED_HORIZON')]
        with patch.object(event_outcome_data, 'collect', side_effect=AssertionError('Unsupported questions must not fetch')):
            for query, status in cases:
                with self.subTest(query=query):
                    result = f.prepare(**query, now=NOW)
                    self.assertEqual(result['status'], status)
                    self.assertEqual(result['context'], query)
                    self.assertIsNone(result['probabilities'])
                    self.assertTrue(result['missing_requirements'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_complete_symmetric_distribution_and_intervals_for_both_declared_sources(self):
        for ident, source in [('us-volatility', snapshot()), ('us-mortgages', snapshot('us-mortgages', 1000, 7))]:
            with self.subTest(ident=ident):
                result = self.build(ident, source)
                self.assertEqual(result['status'], 'RESEARCH_ESTIMATE_AVAILABLE')
                self.assertEqual(set(result['probabilities']), set(f._PROFILES[ident]['ids']))
                self.assertAlmostEqual(sum(result['probabilities'].values()), 1)
                n, k = result['training_sample_count'], len(result['scenarios'])
                for outcome, count in result['training_counts'].items():
                    p = result['probabilities'][outcome]
                    self.assertAlmostEqual(p, (count+.5)/(n+k/2))
                    lo, hi = result['intervals'][outcome]
                    self.assertLess(lo, p)
                    self.assertGreater(hi, p)
                self.assertFalse(result['calibrated_probability'])
                self.assertFalse(result['news_adjusted'])
                self.assertFalse(result['validation']['point_in_time_validated'])
                self.assertFalse(result['validation']['prospectively_calibrated'])
                self.assertTrue(f._valid_cached(result, context(ident), ident, f._PROFILES[ident], NOW))

    def test_holdout_is_later_disjoint_and_never_used_to_fit_probabilities(self):
        source = snapshot()
        profile = f._PROFILES['us-volatility']
        series = f._observations(source, 'us-volatility', NOW)
        pairs, _ = f._pairs(series, 30, profile)
        self.assertTrue(all(a['target'] < b['origin'] for a, b in zip(pairs, pairs[1:])))
        original = self.build(source=source)
        cutoff = original['training_period_end']
        changed = copy.deepcopy(source)
        # Alter only post-training measurements while keeping the same dates.
        for row in changed['observations']:
            if row['period'] > cutoff:
                row['value'] = 20
        later = self.build(source=changed)
        self.assertEqual(original['training_counts'], later['training_counts'])
        self.assertEqual(original['probabilities'], later['probabilities'])
        self.assertNotEqual(original['holdout_counts'], later['holdout_counts'])
        self.assertLess(original['training_period_end'], original['holdout_period_start'])
        self.assertLessEqual(original['holdout_period_end'], original['baseline']['observation_at'])

    def test_explicit_cut_boundaries_assign_each_outcome_once(self):
        origin = NOW.date()-timedelta(days=20)
        series = []
        changes = [-.26, -.25, -.10, .10, .25]
        for index, change in enumerate(changes):
            start = origin+timedelta(days=index*3)
            series.extend([(start, 100), (start+timedelta(days=1), 100*(1+change))])
        pairs, _ = f._pairs(series, 1, f._PROFILES['us-volatility'])
        self.assertEqual([row['outcome_id'] for row in pairs], f._PROFILES['us-volatility']['ids'])
        self.assertTrue(all(row['endpoint'] <= row['target'] for row in pairs))

    def test_missing_endpoint_is_skipped_and_future_measurement_is_never_borrowed(self):
        origin = NOW.date()-timedelta(days=40)
        profile = dict(f._PROFILES['us-volatility'], endpoint_gap_days=1)
        series = [(origin, 20), (origin+timedelta(days=2), 21), (origin+timedelta(days=4), 22), (origin+timedelta(days=30), 30)]
        pairs, skipped = f._pairs(series, 3, profile)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]['endpoint'], origin+timedelta(days=2))
        self.assertEqual(pairs[0]['target'], origin+timedelta(days=3))
        self.assertGreater(skipped, 0)

    def test_effective_horizon_includes_age_of_baseline_not_only_selected_days(self):
        source = snapshot(latest=NOW.date()-timedelta(days=3))
        result = self.build(source=source)
        self.assertEqual(result['baseline_age_days'], 3)
        self.assertEqual(result['effective_duration_days'], 33)
        self.assertEqual(datetime.fromisoformat(result['maturity_at']), NOW+timedelta(days=30))
        self.assertIn('33 calendar days', result['sampling_policy'])

    def test_stale_or_sparse_history_is_missing_evidence_not_zero_probability(self):
        for source, status in [(snapshot(latest=NOW.date()-timedelta(days=8)), 'STALE_SOURCE'),
                               (snapshot(count=200), 'INSUFFICIENT_HISTORY')]:
            with self.subTest(status=status):
                result = self.build(source=source)
                self.assertEqual(result['status'], status)
                self.assertIsNone(result['probabilities'])
                self.assertTrue(result['missing_requirements'])

    def test_invalid_context_values_future_dates_and_duplicate_rows_are_rejected(self):
        for change in ('wrong-profile', 'duplicate', 'future-period', 'future-retrieval', 'after-retrieval', 'nan', 'zero-vix', 'bool'):
            source = snapshot(count=20)
            if change == 'wrong-profile': source['profile']['metric'] = 'OTHER'
            elif change == 'duplicate': source['observations'].append(copy.deepcopy(source['observations'][0]))
            elif change == 'future-period': source['observations'][-1]['period'] = (NOW.date()+timedelta(days=1)).isoformat()
            elif change == 'future-retrieval': source['retrieved_at'] = (NOW+timedelta(hours=1)).isoformat()
            elif change == 'after-retrieval': source['retrieved_at'] = (NOW-timedelta(days=1)).isoformat()
            elif change == 'nan': source['observations'][0]['value'] = math.nan
            elif change == 'zero-vix': source['observations'][0]['value'] = 0
            else: source['observations'][0]['value'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                f._observations(source, 'us-volatility', NOW)

    def test_holdout_scores_are_actual_multiclass_scores_and_equal_counts_keep_ties(self):
        counts = {'lower': 20, 'little_change': 20, 'higher': 20}
        holdout = {'lower': 3, 'little_change': 4, 'higher': 3}
        result = f._validation(counts, holdout)
        self.assertAlmostEqual(result['brier_score'], 2/3)
        self.assertAlmostEqual(result['log_loss'], math.log(3))
        self.assertAlmostEqual(result['zero_change_benchmark_brier'], 1.2)
        self.assertEqual(result, f._validation(dict(reversed(list(counts.items()))), dict(reversed(list(holdout.items())))))
        p, _ = f.event_forecasts._estimate(counts, 60, 'END_STATE')
        self.assertEqual(len(set(p.values())), 1)

    def test_unobserved_outcomes_have_nonzero_prior_mass_but_limited_quality(self):
        source = snapshot()
        for row in source['observations']: row['value'] = 20
        result = self.build(source=source)
        self.assertTrue(all(p > 0 for p in result['probabilities'].values()))
        self.assertIn('RARE_OR_UNOBSERVED_OUTCOMES', result['validation']['quality_flags'])
        self.assertEqual(result['validation']['quality'], 'LIMITED')
        self.assertFalse(result['calibrated_probability'])

    def test_explicit_prepare_persists_history_and_reuses_same_day_snapshot(self):
        source = snapshot()
        with patch.object(event_outcome_data, 'collect', return_value=source) as collect:
            first = f.prepare(**context(), now=NOW)
            second = f.prepare(**context(horizon='7 days'), now=NOW+timedelta(seconds=5))
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(first['status'], 'RESEARCH_ESTIMATE_AVAILABLE')
        self.assertEqual(second['status'], 'RESEARCH_ESTIMATE_AVAILABLE')
        self.assertEqual(first['source']['snapshot_id'], second['source']['snapshot_id'])
        with patch.object(event_outcome_data, 'collect', side_effect=AssertionError('Read must not collect')):
            cached = f.forecast(**dict(context(), focus='USA'), now=NOW+timedelta(seconds=10))
        self.assertEqual(cached['status'], 'RESEARCH_ESTIMATE_AVAILABLE')
        self.assertEqual(cached['context']['focus'], 'USA')

    def test_provider_failure_and_rate_limit_preserve_previous_model(self):
        with patch.object(event_outcome_data, 'collect', return_value=snapshot()):
            ready = f.prepare(**context(), now=NOW)
        path = f._path('us-volatility', '30 days')
        before = path.read_bytes()
        later = NOW+timedelta(days=1)
        with patch.object(event_outcome_data, 'collect', side_effect=event_outcome_data.DataUnavailable('OUTCOME_PROVIDER_UNREACHABLE')) as collect:
            failed = f.prepare(**context(), now=later)
            limited = f.prepare(**context(), now=later+timedelta(seconds=1))
        self.assertEqual(failed['reason_code'], 'OUTCOME_PROVIDER_UNREACHABLE')
        self.assertEqual(limited['reason_code'], 'PREPARATION_BUSY_OR_RATE_LIMITED')
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(ready['status'], 'RESEARCH_ESTIMATE_AVAILABLE')

    def test_malformed_provider_data_is_not_persisted(self):
        source = snapshot()
        source['observations'][-1]['period'] = (NOW.date()+timedelta(days=1)).isoformat()
        with patch.object(event_outcome_data, 'collect', return_value=source):
            result = f.prepare(**context(), now=NOW)
        self.assertEqual(result['status'], 'SOURCE_UNAVAILABLE')
        self.assertFalse((self.root/'outcomes.sqlite3').exists())

    def test_busy_preparation_is_safe_and_does_not_collect(self):
        with f._preparation_lock('us-volatility'):
            with patch.object(event_outcome_data, 'collect', side_effect=AssertionError('Busy must not collect')):
                result = f.prepare(**context(), now=NOW)
        self.assertEqual(result['reason_code'], 'PREPARATION_BUSY_OR_RATE_LIMITED')

    def test_corrupted_cache_cannot_change_probability_validation_definition_or_source(self):
        original = self.build()
        for change in ('interval', 'probability', 'counts', 'validation', 'calibrated', 'definition', 'source-url', 'wrong-context', 'expiry', 'future-retrieval', 'period-leakage'):
            model = copy.deepcopy(original)
            outcome = model['scenarios'][0]['id']
            if change == 'interval': model['intervals'][outcome] = [0, 1]
            elif change == 'probability': model['probabilities'][outcome] += .001
            elif change == 'counts': model['training_counts'][outcome] += 1
            elif change == 'validation': model['validation']['brier_score'] = 0
            elif change == 'calibrated': model['calibrated_probability'] = True
            elif change == 'definition': model['scenarios'][0]['resolution_rule'] = 'A different outcome'
            elif change == 'source-url': model['source']['source_urls'] = ['https://example.org/unrelated']
            elif change == 'wrong-context': model['context']['focus'] = 'Vietnam'
            elif change == 'expiry': model['expires_at'] = (NOW+timedelta(hours=25)).isoformat()
            elif change == 'future-retrieval': model['source']['retrieved_at'] = (NOW+timedelta(seconds=1)).isoformat()
            else: model['training_period_end'] = model['holdout_period_start']
            with self.subTest(change=change):
                f._atomic_model(f._path('us-volatility', '30 days'), model)
                result = f.forecast(**context(), now=NOW)
                self.assertEqual(result['status'], 'RESEARCH_NOT_PREPARED')
                self.assertIsNone(result['probabilities'])

    def test_cache_is_read_only_expired_data_and_wrong_horizon_are_not_reused(self):
        with patch.object(event_outcome_data, 'collect', side_effect=AssertionError('GET never collects')):
            self.assertEqual(f.forecast(**context(), now=NOW)['status'], 'RESEARCH_NOT_PREPARED')
            self.assertEqual(list(self.root.iterdir()), [])
            f._atomic_model(f._path('us-volatility', '30 days'), self.build())
            before = f._path('us-volatility', '30 days').read_bytes()
            self.assertEqual(f.forecast(**context(), now=NOW+timedelta(hours=24))['status'], 'RESEARCH_NOT_PREPARED')
            self.assertEqual(f.forecast(**context(horizon='7 days'), now=NOW)['status'], 'RESEARCH_NOT_PREPARED')
            self.assertEqual(f._path('us-volatility', '30 days').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
