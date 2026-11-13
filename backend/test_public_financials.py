import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import public_financials as public

FIXTURES = Path(__file__).parent / 'fixtures' / 'public_financials'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class PublicFinancialTests(unittest.TestCase):
    def setUp(self):
        self.summary = load('fpt-summary.json')
        self.balance = load('fpt-balance.json')
        self.cash = load('fpt-cash.json')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        public.CACHE.clear()
        public.ATTEMPTS.clear()

    def tearDown(self):
        self.temp.cleanup()

    def result(self):
        return public.normalize('FPT', self.summary, self.balance, self.cash)

    def test_observed_fpt_values_and_units(self):
        result = self.result()
        m = result['financials']['metrics']
        self.assertEqual(m['revenue']['value'], '70112825100710')
        self.assertEqual(m['net_income']['value'], '11232339450734')
        self.assertEqual(m['revenue']['currency'], 'VND')
        self.assertEqual(m['net_margin']['value'], '16.0204')
        self.assertEqual(m['roa']['value'], '14.028')
        self.assertEqual(m['roe']['value'], '28.2937')
        self.assertEqual(m['debt_equity']['value'], '0.4817')
        self.assertEqual(m['current_ratio']['value'], '1.4001')
        self.assertEqual(result['period'], 'FY')
        self.assertEqual(result['period_end'], '2025')  # Not an invented calendar year-end.
        self.assertFalse(m['roe']['human_reviewed'])
        self.assertIn('average equity attributable', m['roe']['formula'])

    def test_cash_flow_missing_zero_does_not_become_free_cash_flow(self):
        metric = self.result()['financials']['metrics']['free_cash_flow']
        self.assertIsNone(metric['value'])
        self.assertIn('CASH_FLOW_RECONCILIATION_REQUIRED', metric['reason_codes'])

    def test_reconciled_cash_flow_can_be_calculated(self):
        investing = self.cash['value']['data'][1]['data'][0]['data']
        total = next(c['value'] for c in investing if c['code'] == 'HDDT_29')
        others = sum(c['value'] for c in investing if c['code'] not in ('HDDT_21', 'HDDT_22', 'HDDT_29'))
        next(c for c in investing if c['code'] == 'HDDT_22')['value'] = total - others
        metric = self.result()['financials']['metrics']['free_cash_flow']
        self.assertEqual(metric['status'], 'READY')
        self.assertEqual(int(metric['value']), 10136043915911 + total - others)

    def test_real_zero_profit_survives_and_negative_equity_is_not_a_return(self):
        income = self.summary['value']['data'][0]['data'][0]['data']
        next(c for c in income if c['code'] == 'KQKD_13')['value'] = 0
        m = self.result()['financials']['metrics']
        self.assertEqual(m['net_margin']['value'], '0')
        self.assertEqual(m['net_margin']['status'], 'READY')

    def test_no_cross_issuer_or_period_mix(self):
        self.balance['value']['data'][1]['data'][0]['symbol'] = 'HPG'
        with self.assertRaisesRegex(public.Unavailable, 'ENTITY_MISMATCH'):
            self.result()
        self.balance = load('fpt-balance.json')
        self.balance['value']['data'][1]['data'][0]['year'] = 2024
        m = self.result()['financials']['metrics']
        self.assertIsNone(m['debt_equity']['value'])

    def test_partial_sources_keep_available_metrics_and_do_not_guess_ebitda(self):
        m = public.normalize('FPT', self.summary)['financials']['metrics']
        self.assertEqual(m['revenue']['status'], 'READY')
        self.assertEqual(m['roa']['status'], 'READY')
        self.assertIsNone(m['debt_equity']['value'])
        self.assertIsNone(m['ebitda_margin']['value'])

    def test_missing_opening_balance_does_not_use_closing_only_roe(self):
        self.summary['value']['data'][1]['data'] = self.summary['value']['data'][1]['data'][:1]
        m = self.result()['financials']['metrics']
        self.assertIsNone(m['roe']['value'])
        self.assertIsNone(m['roa']['value'])

    def test_template_change_does_not_reuse_numerical_code(self):
        self.summary['value']['templace'][0]['data'][0]['name'] = 'An unrelated value'
        self.assertIsNone(self.result()['financials']['metrics']['revenue']['value'])

    def test_different_company_and_bank_templates(self):
        hpg = public.normalize('HPG', load('hpg-summary.json'))
        self.assertNotEqual(hpg['financials']['metrics']['revenue']['value'], self.result()['financials']['metrics']['revenue']['value'])
        bank = public.normalize('VCB', load('vcb-summary.json'))['financials']['metrics']
        self.assertEqual(bank['net_income']['value'], '35197940000000')
        self.assertEqual(bank['roe']['status'], 'READY')
        self.assertEqual(bank['roa']['status'], 'READY')
        self.assertEqual(bank['revenue']['reason_codes'], ['BANK_METRIC_NOT_APPLICABLE'])
        self.assertIsNone(bank['current_ratio']['value'])

    def test_persistent_cache_and_stale_outage(self):
        with patch.object(public, 'build_vietnam', return_value={**self.result(), 'warnings': []}) as build:
            first = public.research(self.root, 'FPT', 'VN')
            self.assertEqual(first['cache_status'], 'LIVE')
            public.CACHE.clear()
            second = public.research(self.root, 'FPT', 'VN')
            self.assertEqual(second['cache_status'], 'FRESH')
            self.assertEqual(build.call_count, 1)
        path = public.financial_sources.directory(self.root) / 'cafef-FPT.json'
        saved = json.loads(path.read_text())
        saved['timestamp'] = time.time() - public.TTL - 1
        path.write_text(json.dumps(saved))
        public.CACHE.clear(); public.ATTEMPTS.clear()
        with patch.object(public, 'build_vietnam', side_effect=public.Unavailable('PROVIDER_UNAVAILABLE')):
            stale = public.research(self.root, 'FPT', 'VN')
        self.assertEqual(stale['cache_status'], 'STALE')
        self.assertEqual(stale['refresh_error'], 'PROVIDER_UNAVAILABLE')
        self.assertFalse((self.root / 'finance.sqlite3').exists())

    def test_bad_cache_is_not_trusted_and_failure_is_throttled(self):
        path = public.financial_sources.directory(self.root) / 'cafef-FPT.json'
        path.parent.mkdir();path.write_text('{broken')
        with patch.object(public, 'build_vietnam', side_effect=public.Unavailable('PROVIDER_UNAVAILABLE')) as build:
            with self.assertRaises(public.Unavailable): public.research(self.root, 'FPT', 'VN')
            with self.assertRaisesRegex(public.Unavailable, 'REFRESH_COOLDOWN'): public.research(self.root, 'FPT', 'VN')
            self.assertEqual(build.call_count, 1)

    def test_automatic_us_never_substitutes_apple_example(self):
        with patch.object(public.financial_sources, 'settings', return_value=('', 'none')):
            with self.assertRaisesRegex(public.Unavailable, 'SEC_USER_AGENT_NOT_CONFIGURED'):
                public.research(self.root, 'AAPL', 'US')

    def test_invalid_market_and_ticker_do_not_fetch(self):
        with patch.object(public, 'fetch_json') as fetch:
            for ticker, market in [('../FPT', 'VN'), ('FPT', 'GB'), ('FPT?x=1', 'VN')]:
                with self.assertRaises(public.Unavailable): public.research(self.root, ticker, market)
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
