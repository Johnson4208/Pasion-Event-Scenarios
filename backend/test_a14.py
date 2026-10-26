import unittest
from datetime import datetime, timezone
from distribution import engine

class AdmissionTests(unittest.TestCase):
    def test_missing_verified_context_fails_closed(self):
        reasons = engine.context_gates({}, None, None, datetime.now(timezone.utc))
        self.assertIn('QUOTE_IANA_TIMEZONE_REQUIRED', reasons)
        self.assertIn('VERIFIED_LIQUIDITY_CAPACITY_REQUIRED', reasons)
        self.assertIn('VERIFIED_NAME_SECTOR_CURRENCY_EXPOSURE_POLICY_UNAVAILABLE', reasons)

    def test_nonfinite_and_future_origin_rejected(self):
        for value in ('NaN', 'Infinity', True):
            with self.assertRaises(ValueError): engine.finite(value)
        reasons = engine.context_gates({'utility':'1','decision_origin':'2999-01-01T00:00:00Z'}, {}, {}, datetime.now(timezone.utc))
        self.assertIn('FINITE_UTILITY_AND_VALID_DECISION_ORIGIN_REQUIRED', reasons)

    def test_no_forced_lower_utility_substitute(self):
        base = dict(shadow_gate_passed=True, utility_status='READY', horizon='30 sessions',
                    utility_definition='net payoff', utility_version='1', utility_model='frozen')
        candidates = [dict(base,id='best',utility='10'),dict(base,id='worse',utility='3')]
        self.assertEqual(engine.near_equivalent(candidates, '1'), ['best'])
        candidates[1]['horizon']='60 sessions'
        with self.assertRaises(ValueError): engine.near_equivalent(candidates, '1')
        self.assertEqual(engine.near_equivalent([], '0'), [])
