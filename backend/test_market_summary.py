import unittest
from datetime import datetime, timezone
import market_summary


class MarketSummaryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
        self.quote = {'price': 100, 'change': 0, 'as_of': '2026-10-13T14:59:00Z',
                      'session_open': '2026-10-13T13:30:00Z', 'session_close': '2026-10-13T20:00:00Z',
                      'venue': 'US index', 'timezone': 'UTC', 'calendar': 'provider-session-v1',
                      'currency': 'USD', 'unit': 'Index points', 'max_age_seconds': 300}

    def run_quote(self, **overrides):
        return market_summary.summary('provider', self.now, {'verified': True, 'source': 'Test provider',
                                    'quotes': {'SPX': dict(self.quote, **overrides)}})

    def spx(self, result):
        return next(q for q in result['quotes'] if q['ticker'] == 'SPX')

    def test_sample_has_no_fabricated_clock(self):
        result = market_summary.summary('demo', self.now)
        self.assertTrue(all(q['origin'] == 'SAMPLE' and q['as_of'] is None for q in result['quotes']))
        self.assertEqual(result['provider_status'], 'NOT_CONNECTED')

    def test_ready_zero_change_and_partial_coverage(self):
        result = self.run_quote()
        self.assertEqual(self.spx(result)['change'], 0)
        self.assertEqual(result['coverage']['available'], 1)
        self.assertEqual(result['benchmark']['status'], 'READY')
        self.assertEqual(result['breadth']['status'], 'UNAVAILABLE')

    def test_future_stale_naive_and_outside_session_quotes_suppress_prices(self):
        for patch, status in [({'as_of': '2026-10-13T15:01:00Z'}, 'WITHHELD'),
                              ({'as_of': '2026-10-13T14:00:00Z'}, 'STALE'),
                              ({'as_of': '2026-10-13T14:59:00'}, 'WITHHELD'),
                              ({'as_of': '2026-10-13T12:00:00Z'}, 'WITHHELD'),
                              ({'price': float('nan')}, 'WITHHELD'),
                              ({'unit': 'USD'}, 'WITHHELD')]:
            quote = self.spx(self.run_quote(**patch))
            self.assertEqual(quote['status'], status)
            self.assertIsNone(quote['price'])
            self.assertIsNone(quote['change'])

    def test_bad_cache_never_falls_back_to_sample(self):
        for snapshot in [[], {}, {'verified': False}, {'verified': True, 'source': 'test', 'quotes': []}]:
            result = market_summary.summary('provider', self.now, snapshot)
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertEqual(result['quotes'], [])
