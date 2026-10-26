"""Synthetic cases exercise arithmetic and gates; never deploy these as data."""
import copy
import json
import math
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import event_forecasts as f

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def specification(basis='END_STATE', size=3):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = [f'outcome-{i}' for i in range(size)]
    cases = []
    for partition in (0, 1):
        for i in range(210):
            origin = start+timedelta(days=i if partition else i-500)
            maturity = origin+timedelta(days=30)
            row = dict(id=f'case-{partition}-{i}', group_id=f'independent-{partition}-{i}',
                       reviewed=True, origin_at=origin.isoformat(), maturity_at=maturity.isoformat(),
                       resolved_at=maturity.isoformat(), source_url='https://example.org/synthetic-resolution')
            if basis == 'END_STATE':
                row['outcome_id'] = ids[i % size]
            else:
                row['outcomes'] = {key: i % 10 < (7 if k == 0 else 6) for k, key in enumerate(ids)}
            cases.append(row)
    return {'context': {'category': 'Geopolitics', 'factor': 'Conflict risk', 'focus': 'Vietnam',
                        'horizon': '30 days', 'basis': basis},
            'model_version': 'synthetic-test-only-v1', 'family_id': 'synthetic-test-only',
            'definition_version': '1', 'question': 'Synthetic test question, never a real forecast',
            'sampling_policy': 'Synthetic independent groups used exclusively by automated tests.',
            'scenarios': [{'id': k, 'title': f'Synthetic outcome {k}', 'resolution_rule': f'Fixture rule for {k}'} for k in ids],
            'validation_start': start.isoformat(), 'expires_at': (NOW+timedelta(days=30)).isoformat(), 'cases': cases}


class HistoricalForecastTests(unittest.TestCase):
    def model(self, spec=None):
        return f.build(spec or specification(), 'automated synthetic fixture', NOW)

    def test_all_outcomes_have_one_coherent_distribution_and_intervals(self):
        model = self.model()
        result = f.estimate(model, model['context'], NOW)
        self.assertEqual(result['status'], 'REFERENCE_ESTIMATE_AVAILABLE')
        self.assertEqual(len(result['scenarios']), 3)
        self.assertAlmostEqual(sum(result['probabilities'].values()), 1)
        self.assertEqual(result['validation']['status'], 'PASSED_HOLDOUT_CHECK')
        self.assertFalse(result['news_adjusted'])
        for key, probability in result['probabilities'].items():
            lo, hi = result['intervals'][key]
            self.assertLess(lo, probability)
            self.assertGreater(hi, probability)
        self.assertAlmostEqual(result['validation']['brier_score'], 2/3)
        self.assertAlmostEqual(result['validation']['log_loss'], math.log(3))

    def test_order_and_names_cannot_bias_probabilities_or_force_a_winner(self):
        spec = specification()
        original = self.model(spec)
        spec['scenarios'].reverse()
        spec['cases'].reverse()
        spec['scenarios'][0]['title'] = 'A dramatic title does not change its rate'
        reordered = self.model(spec)
        a = f.estimate(original, original['context'], NOW)
        b = f.estimate(reordered, reordered['context'], NOW)
        self.assertEqual(a['probabilities'], b['probabilities'])
        self.assertEqual(len(set(a['probabilities'].values())), 1)

    def test_dynamic_families_do_not_assume_ten_paths_or_match_by_position(self):
        for size in (2, 5, 7, 21):
            model = self.model(specification(size=size))
            result = f.estimate(model, model['context'], NOW)
            self.assertEqual(len(result['probabilities']), size)
            self.assertAlmostEqual(sum(result['probabilities'].values()), 1)

    def test_overlapping_events_keep_marginals_and_never_normalize_to_100(self):
        model = self.model(specification('OCCURRENCE', 2))
        result = f.estimate(model, model['context'], NOW)
        self.assertFalse(result['mutually_exclusive'])
        self.assertGreater(sum(result['probabilities'].values()), 1.29)
        self.assertAlmostEqual(result['probabilities']['outcome-0'], 147.5/211)

    def test_duplicate_groups_and_unreviewed_or_future_labels_fail(self):
        for change in ('duplicate', 'unreviewed', 'future', 'wrong-horizon', 'unknown-outcome'):
            spec = specification()
            if change == 'duplicate':
                spec['cases'][-1]['group_id'] = spec['cases'][0]['group_id']
            elif change == 'unreviewed':
                spec['cases'][0]['reviewed'] = False
            elif change == 'future':
                spec['cases'][0]['resolved_at'] = (NOW+timedelta(days=1)).isoformat()
            elif change == 'wrong-horizon':
                spec['cases'][0]['maturity_at'] = spec['cases'][0]['origin_at']
            else:
                spec['cases'][0]['outcome_id'] = 'not-defined'
            with self.subTest(change=change), self.assertRaises(f.InvalidModel):
                self.model(spec)

    def test_partly_labeled_overlapping_events_fail_instead_of_becoming_zero(self):
        spec = specification('OCCURRENCE', 2)
        del spec['cases'][0]['outcomes']['outcome-1']
        with self.assertRaises(f.InvalidModel):
            self.model(spec)

    def test_insufficient_history_and_holdout_drift_withhold_the_entire_family(self):
        spec = specification()
        spec['cases'] = spec['cases'][:50]+spec['cases'][210:]
        with self.assertRaises(f.InvalidModel):
            self.model(spec)
        spec = specification()
        for row in spec['cases'][210:]:
            row['outcome_id'] = 'outcome-0'
        model = self.model(spec)
        self.assertEqual(model['validation']['status'], 'WITHHELD_HOLDOUT_CHECK_FAILED')
        with self.assertRaises(f.InvalidModel):
            f.estimate(model, model['context'], NOW)

    def test_embargo_prevents_resolved_training_outcomes_leaking_into_holdout(self):
        spec = specification()
        row = copy.deepcopy(spec['cases'][0])
        row.update(id='embargo', group_id='embargo', origin_at='2025-12-20T00:00:00Z',
                   maturity_at='2026-01-19T00:00:00Z', resolved_at='2026-01-19T00:00:00Z')
        spec['cases'].append(row)
        model = self.model(spec)
        self.assertEqual(model['embargoed_cases'], 1)
        self.assertEqual(model['training_sample_count'], 210)

    def test_tampered_incomplete_counts_wrong_query_expiry_and_false_metadata_fail(self):
        original = self.model()
        for change in ('missing-count', 'sum', 'bool', 'stale', 'leakage', 'forged-validation'):
            model = copy.deepcopy(original)
            if change == 'missing-count':
                del model['training_counts']['outcome-0']
            elif change == 'sum':
                model['training_counts']['outcome-0'] += 1
            elif change == 'bool':
                model['holdout_sample_count'] = True
            elif change == 'stale':
                model['expires_at'] = (NOW-timedelta(days=1)).isoformat()
            elif change == 'leakage':
                model['training_resolved_through'] = model['holdout_origin_from']
            else:
                model['holdout_counts'] = {'outcome-0': 210, 'outcome-1': 0, 'outcome-2': 0}
                model['validation']['status'] = 'PASSED_HOLDOUT_CHECK'
            with self.subTest(change=change), self.assertRaises(f.InvalidModel):
                f.estimate(model, model['context'], NOW)
        with self.assertRaises(f.InvalidModel):
            f.estimate(original, dict(original['context'], focus='Japan'), NOW)

    def test_catalog_is_local_scoped_and_ambiguous_models_do_not_cherry_pick(self):
        model = self.model()
        context = model['context']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'models.json'
            with patch.dict(os.environ, {'PASION_EVENT_MODELS_PATH': str(path)}):
                self.assertEqual(f.forecast(**context, now=NOW)['status'], 'UNAVAILABLE')
                path.write_text(json.dumps({'schema_version': 1, 'models': [model]}))
                self.assertEqual(f.forecast(**context, now=NOW)['status'], 'REFERENCE_ESTIMATE_AVAILABLE')
                self.assertEqual(f.forecast(**dict(context, basis='OCCURRENCE'), now=NOW)['status'], 'UNAVAILABLE')
                path.write_text(json.dumps({'schema_version': 1, 'models': [model, model]}))
                self.assertEqual(f.forecast(**context, now=NOW)['reason_code'], 'AMBIGUOUS_MODEL_FAMILY')

    def test_beta_quantiles_match_closed_form_uniform_and_symmetric_cases(self):
        self.assertAlmostEqual(f._quantile(.025, 1, 1), .025, places=10)
        self.assertAlmostEqual(f._quantile(.975, 1, 1), .975, places=10)
        self.assertAlmostEqual(f._quantile(.5, 2, 2), .5, places=10)
        self.assertAlmostEqual(f._beta_cdf(.5, 100, 100), .5, places=8)

    def test_new_models_and_expiry_are_rechecked_without_reusing_stale_news_probabilities(self):
        import event_news_preview as news
        spec = specification()
        article = {'title':'Vietnam conflict escalates','description':'Vietnam conflict security report',
                   'published_at':(NOW-timedelta(days=1)).isoformat(),'url':'https://example.org/test', 'source':'Synthetic fixture'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'catalog.json'
            with patch.dict(os.environ, {'PASION_EVENT_MODELS_PATH': str(path)}), patch.object(news.event_feed_sources,'retrieve',return_value=([article],{'feed_successes':1,'requests':1})) as retrieve:
                with news._lock:news._cache.clear()
                query = {k:v for k,v in spec['context'].items() if k != 'basis'}
                first = news.analyze(**query, now=NOW)
                self.assertEqual(first['scenario_forecast']['status'],'UNAVAILABLE')
                path.write_text(json.dumps({'schema_version':1,'models':[self.model(spec)]}))
                second = news.analyze(**query, now=NOW)
                self.assertEqual(second['scenario_forecast']['status'],'REFERENCE_ESTIMATE_AVAILABLE')
                self.assertEqual(retrieve.call_count,1)
                expired = news.analyze(**query, now=NOW+timedelta(days=31))
                self.assertEqual(expired['scenario_forecast']['status'],'UNAVAILABLE')
                with news._lock:news._cache.clear()


if __name__ == '__main__':
    unittest.main()
