"""Public synthetic records; these tests never access real application data."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import event_forecast_ledger as ledger
import event_forecasts
import event_outcome_data


NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class ForecastLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'outcomes.sqlite3'

    def snapshot(self, profile, when, rows, *, status='COLLECTED_NEEDS_OUTCOME_REVIEW'):
        observations = [{'key': day, 'period': day, 'value': value} for day, value in rows]
        payload = json.dumps(observations).encode()
        snapshot = {'profile_id': profile, 'profile': event_outcome_data.PROFILES[profile],
                    'retrieved_at': when.isoformat(), 'status': status,
                    'response_sha256': hashlib.sha256(payload).hexdigest(),
                    'source_urls': ['https://fred.stlouisfed.org/graph/fredgraph.csv?id=' + event_outcome_data.PROFILES[profile]['metric']],
                    'observations': observations, '_raw_responses': []}
        return event_outcome_data.persist(snapshot, self.path)

    def model(self, *, mortgages=False):
        profile = 'us-mortgages' if mortgages else 'us-volatility'
        baseline = 7.0 if mortgages else 20.0
        snapshot = self.snapshot(profile, NOW, [('2025-12-31', baseline)])
        ids = ['lower', 'little_change', 'higher'] if mortgages else ['large_decrease', 'decrease', 'little_change', 'increase', 'large_increase']
        cuts = [-.25, .25] if mortgages else [-.25, -.10, .10, .25]
        counts = dict(zip(ids, [10, 20, 10] if mortgages else [4, 8, 16, 8, 4]))
        holdout = dict(zip(ids, [3, 6, 3] if mortgages else [1, 2, 6, 2, 1]))
        probabilities, intervals = event_forecasts._estimate(counts, sum(counts.values()), 'END_STATE')
        observed = {ident: holdout[ident]/sum(holdout.values()) for ident in ids}
        return {'schema_version': 2, 'method': ledger.METHOD, 'status': 'RESEARCH_ESTIMATE_AVAILABLE',
                'family_id': profile + '-family', 'definition_version': 'series-v1', 'model_version': 'series-test-v1',
                'question': 'Synthetic source endpoint question',
                'context': {'category': 'Real Estate' if mortgages else 'Markets', 'factor': 'Mortgage rates' if mortgages else 'Equity volatility',
                            'focus': 'United States', 'horizon': '7 days', 'basis': 'END_STATE'},
                'as_of': NOW.isoformat(), 'forecast_origin_at': NOW.isoformat(), 'maturity_at': (NOW + timedelta(days=7)).isoformat(),
                'baseline': {'value': baseline, 'observation_at': '2025-12-31', 'unit': 'percent' if mortgages else 'index points'},
                'threshold_cuts': cuts, 'change_unit': 'PERCENTAGE_POINTS' if mortgages else 'RELATIVE_CHANGE',
                'scenarios': [{'id': ident, 'title': ident, 'resolution_rule': 'Synthetic exhaustive band',
                               'lower_bound': cuts[index - 1] if index else None,
                               'upper_bound': cuts[index] if index < len(cuts) else None}
                              for index, ident in enumerate(ids)],
                'probabilities': probabilities, 'intervals': intervals, 'interval_level': .95,
                'training_counts': counts, 'holdout_counts': holdout,
                'training_sample_count': sum(counts.values()), 'holdout_sample_count': sum(holdout.values()),
                'training_period_end': '2020-12-31', 'holdout_period_start': '2021-01-01', 'holdout_period_end': '2025-12-30',
                'validation': {'status': 'RETROSPECTIVE_HOLDOUT_ONLY', 'quality': 'LIMITED',
                               'brier_score': 1 + sum(value*value for value in probabilities.values()) - 2*sum(observed[ident]*probabilities[ident] for ident in ids),
                               'log_loss': -sum(observed[ident]*__import__('math').log(probabilities[ident]) for ident in ids),
                               'maximum_rate_error': max(abs(probabilities[ident]-observed[ident]) for ident in ids),
                               'point_in_time_validated': False, 'prospectively_calibrated': False},
                'news_adjusted': False, 'calibrated_probability': False, 'mutually_exclusive': True, 'exhaustive': True,
                'source': {'profile_id': profile, 'metric': 'MORTGAGE30US' if mortgages else 'VIXCLS', 'provider': 'FRED',
                           'snapshot_id': snapshot, 'retrieved_at': NOW.isoformat(),
                           'source_urls': ['https://fred.stlouisfed.org/graph/fredgraph.csv?id=' + ('MORTGAGE30US' if mortgages else 'VIXCLS')]}}

    def record(self, model=None):
        return ledger.record(model or self.model(), now=NOW, path=self.path)

    def database_snapshot(self):
        return self.path.read_bytes()

    def test_uninitialized_reads_do_not_create_store(self):
        self.assertEqual(ledger.summary(path=self.path)['status'], 'UNINITIALIZED')
        self.assertEqual(ledger.resolve_due(path=self.path)['resolved'], 0)
        self.assertFalse(self.path.exists())

    def test_record_is_idempotent_immutable_and_has_no_operator_or_account_fields(self):
        model = self.model()
        model['email'] = 'private-owner@example.invalid'
        model['source']['api_key'] = 'PRIVATE_API_KEY'
        model['baseline']['private_note'] = 'PRIVATE_NOTE'
        first = self.record(model)
        second = ledger.record(model, now=NOW + timedelta(minutes=3), path=self.path)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['recorded_at'], second['recorded_at'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM event_series_predictions').fetchone()[0], 1)
            payload, digest = db.execute('SELECT forecast_json,forecast_sha256 FROM event_series_predictions').fetchone()
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), digest)
        saved = json.loads(payload)
        self.assertEqual(saved['intervals'], model['intervals'])
        self.assertEqual(saved['validation']['brier_score'], model['validation']['brier_score'])
        self.assertEqual(saved['training_counts'], model['training_counts'])
        for secret in ('private-owner@example.invalid', 'PRIVATE_API_KEY', 'PRIVATE_NOTE'):
            self.assertNotIn(secret, payload)
        status = ledger.summary(now=NOW, path=self.path)
        self.assertEqual(status['pending_count'], 1)
        self.assertEqual(status['recent'][0]['intervals'], model['intervals'])
        self.assertIsNone(status['brier_score'])
        self.assertEqual(status['calibration_status'], 'NOT_ESTABLISHED')

    def test_past_matured_or_future_dated_forecasts_cannot_be_added(self):
        model = self.model()
        for now in (NOW - timedelta(seconds=1), NOW + timedelta(days=7), NOW + timedelta(days=8)):
            with self.subTest(now=now), self.assertRaises(ValueError):
                ledger.record(model, now=now, path=self.path)

    def test_incomplete_or_dishonest_families_are_rejected(self):
        original = self.model()
        edits = [lambda m: m['probabilities'].pop('increase'),
                 lambda m: m['probabilities'].update(increase=float('nan')),
                 lambda m: m['probabilities'].update(increase=.9),
                 lambda m: m['threshold_cuts'].reverse(),
                 lambda m: m.update(calibrated_probability=True),
                 lambda m: m['context'].update(focus='Vietnam'),
                 lambda m: m['source'].update(metric='OTHER'),
                 lambda m: m.update(maturity_at=(NOW + timedelta(days=8)).isoformat()),
                 lambda m: m['scenarios'][0].update(upper_bound=.9)]
        for edit in edits:
            model = deepcopy(original)
            edit(model)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.record(model)

    def test_a_real_matching_baseline_snapshot_is_required(self):
        model = self.model()
        for change in ({'value': 99.0}, {'observation_at': '2025-12-30'}):
            bad = deepcopy(model)
            bad['baseline'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.record(bad)
        model['source']['snapshot_id'] = 'absent'
        with self.assertRaises(ValueError):
            self.record(model)

    def test_does_not_resolve_before_maturity_even_with_a_later_snapshot(self):
        self.record()
        self.snapshot('us-volatility', NOW + timedelta(days=8), [('2025-12-31', 20), ('2026-01-08', 24)])
        status = ledger.resolve_due(now=NOW + timedelta(days=6), path=self.path)
        self.assertEqual(status['resolved'], 0)
        self.assertEqual(status['pending'], 1)

    def test_old_or_incomplete_source_never_becomes_zero_change(self):
        self.record()
        self.snapshot('us-volatility', NOW + timedelta(days=6), [('2025-12-31', 20), ('2026-01-06', 20)])
        self.snapshot('us-volatility', NOW + timedelta(days=8), [('2025-12-31', 20), ('2026-01-07', 20)])
        status = ledger.resolve_due(now=NOW + timedelta(days=9), path=self.path)
        self.assertEqual(status['resolved'], 0)
        self.assertEqual(ledger.summary(now=NOW + timedelta(days=9), path=self.path)['resolved_count'], 0)

    def test_first_adequate_later_source_resolves_and_is_never_overwritten(self):
        model = self.model()
        forecast = self.record(model)
        first = self.snapshot('us-volatility', NOW + timedelta(days=8),
                              [('2025-12-31', 20), ('2026-01-08', 24), ('2026-01-09', 25)])
        result = ledger.resolve_due(now=NOW + timedelta(days=8), path=self.path)
        self.assertEqual(result['resolved'], 1)
        status = ledger.summary(now=NOW + timedelta(days=8), path=self.path)
        self.assertEqual(status['recent'][0]['outcome_id'], 'increase')
        self.assertAlmostEqual(status['brier_score'], sum((value - int(ident == 'increase'))**2 for ident, value in model['probabilities'].items()))
        self.assertAlmostEqual(status['log_loss'], -__import__('math').log(model['probabilities']['increase']))
        self.assertEqual(status['calibration_status'], 'NOT_ESTABLISHED')
        with closing(sqlite3.connect(self.path)) as db:
            before = db.execute('SELECT resolution_json FROM event_series_resolutions WHERE forecast_id=?', (forecast['id'],)).fetchone()[0]
        resolution = json.loads(before)
        self.assertEqual(resolution['source_snapshot_id'], first)
        self.assertEqual(resolution['adjudication_status'], 'UNREVIEWED')
        self.assertFalse(resolution['point_in_time_release_archive'])
        self.snapshot('us-volatility', NOW + timedelta(days=10), [('2025-12-31', 20), ('2026-01-08', 2), ('2026-01-10', 25)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=10), path=self.path)['resolved'], 0)
        with closing(sqlite3.connect(self.path)) as db:
            after = db.execute('SELECT resolution_json FROM event_series_resolutions WHERE forecast_id=?', (forecast['id'],)).fetchone()[0]
        self.assertEqual(before, after)

    def test_weekly_endpoint_uses_last_value_before_target_and_waits_for_coverage(self):
        model = self.model(mortgages=True)
        self.record(model)
        self.snapshot('us-mortgages', NOW + timedelta(days=9),
                      [('2025-12-31', 7), ('2026-01-07', 6.75)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=9), path=self.path)['resolved'], 0)
        self.snapshot('us-mortgages', NOW + timedelta(days=15),
                      [('2025-12-31', 7), ('2026-01-07', 6.75), ('2026-01-14', 9)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=15), path=self.path)['resolved'], 1)
        status = ledger.summary(now=NOW + timedelta(days=15), path=self.path)
        # Lower-inclusive bands: exact -.25 belongs to the middle band.
        self.assertEqual(status['recent'][0]['outcome_id'], 'little_change')

    def test_future_or_unreviewable_snapshots_do_not_resolve_early(self):
        self.record()
        self.snapshot('us-volatility', NOW + timedelta(days=8), [('2025-12-31', 20), ('2026-01-08', 24)], status='FAILED')
        self.snapshot('us-volatility', NOW + timedelta(days=15), [('2025-12-31', 20), ('2026-01-08', 24), ('2026-01-09', 25)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=9), path=self.path)['resolved'], 0)

    def test_summary_is_read_only_and_can_filter_context(self):
        model = self.model()
        self.record(model)
        before = self.database_snapshot()
        self.assertEqual(ledger.summary(context=model['context'], now=NOW, path=self.path)['forecast_count'], 1)
        context = {**model['context'], 'horizon': '30 days'}
        self.assertEqual(ledger.summary(context=context, now=NOW, path=self.path)['forecast_count'], 0)
        self.assertEqual(before, self.database_snapshot())

    def test_uncertainty_counts_and_retrospective_validation_cannot_be_falsified(self):
        original = self.model()
        edits = [lambda m: m.pop('intervals'),
                 lambda m: m['intervals']['increase'].__setitem__(0, 0),
                 lambda m: m['training_counts'].update(increase=7),
                 lambda m: m['validation'].update(brier_score=0),
                 lambda m: m['validation'].update(prospectively_calibrated=True),
                 lambda m: m.update(holdout_period_start=m['training_period_end']),
                 lambda m: m.update(exhaustive=False),
                 lambda m: m.update(threshold_cuts=[-.3, -.1, .1, .25]),
                 lambda m: m['source'].update(source_urls=['https://fred.stlouisfed.org/graph/fredgraph.csv?id=OTHER'])]
        for edit in edits:
            model = deepcopy(original)
            edit(model)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.record(model)

    def test_declared_us_aliases_use_same_context_key(self):
        model = self.model()
        model['context']['focus'] = 'U.S.'
        self.record(model)
        context = {**model['context'], 'focus': 'United States'}
        self.assertEqual(ledger.summary(context=context, now=NOW, path=self.path)['forecast_count'], 1)

    def test_stale_baseline_or_source_after_origin_is_rejected(self):
        model = self.model()
        bad = deepcopy(model)
        bad['baseline']['observation_at'] = '2025-12-01'
        with self.assertRaises(ValueError):
            self.record(bad)
        bad = deepcopy(model)
        bad['source']['retrieved_at'] = (NOW + timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):
            ledger.record(bad, now=NOW + timedelta(seconds=2), path=self.path)

    def test_old_future_forecasts_do_not_starve_matured_short_forecast(self):
        # A long-horizon queue must not consume the resolution batch before
        # newer short-horizon forecasts that are already due.
        self.record()
        with closing(sqlite3.connect(self.path)) as db, db:
            payload = db.execute('SELECT forecast_json FROM event_series_predictions').fetchone()[0]
            for index in range(ledger.MAX_PENDING):
                db.execute('INSERT INTO event_series_predictions VALUES(?,?,?,?,?,?,?)',
                           ('future-' + str(index), (NOW - timedelta(days=1)).isoformat(), (NOW + timedelta(days=30)).isoformat(),
                            'us-volatility', 'synthetic', str(index), payload))
        self.snapshot('us-volatility', NOW + timedelta(days=8), [('2025-12-31', 20), ('2026-01-08', 24), ('2026-01-09', 25)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=8), path=self.path)['resolved'], 1)

    def test_first_adequate_snapshot_orders_actual_instants_across_utc_offsets(self):
        self.record()
        earliest = self.snapshot('us-volatility', (NOW + timedelta(days=8)).astimezone(timezone(timedelta(hours=14))),
                                 [('2025-12-31', 20), ('2026-01-08', 24), ('2026-01-09', 25)])
        self.snapshot('us-volatility', NOW + timedelta(days=8, hours=2),
                      [('2025-12-31', 20), ('2026-01-08', 2), ('2026-01-09', 25)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=9), path=self.path)['resolved'], 1)
        with closing(sqlite3.connect(self.path)) as db:
            selected = db.execute('SELECT source_snapshot_id FROM event_series_resolutions').fetchone()[0]
        self.assertEqual(selected, earliest)
        self.assertEqual(ledger.summary(now=NOW + timedelta(days=9), path=self.path)['recent'][0]['outcome_id'], 'increase')

    def test_malformed_source_snapshot_does_not_block_other_complete_vintages(self):
        self.record()
        broken = self.snapshot('us-volatility', NOW + timedelta(days=8),
                               [('2025-12-31', 20), ('2026-01-08', 2), ('2026-01-09', 25)])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE outcome_snapshots SET retrieved_at=? WHERE id=?', ('invalid-time', broken))
        self.snapshot('us-volatility', NOW + timedelta(days=9),
                      [('2025-12-31', 20), ('2026-01-08', 24), ('2026-01-09', 25)])
        self.assertEqual(ledger.resolve_due(now=NOW + timedelta(days=9), path=self.path)['resolved'], 1)


if __name__ == '__main__':
    unittest.main()
