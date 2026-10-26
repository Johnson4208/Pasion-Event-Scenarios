"""Test isolated public SEC calculation example without touching app databases."""
import unittest
import public_filing_demo

class PublicFilingDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=public_filing_demo.calculate()

    def test_example_calculates_from_finance_core(self):
        d=self.output
        self.assertEqual(d['ticker'],'AAPL')
        self.assertEqual(d['engine'],'finance_core.company')
        self.assertEqual(d['execution_mode'],'ISOLATED_TEMPORARY_DATABASE_RECOMPUTED_ON_REQUEST')
        rows={r['id']:r for r in d['metrics']}
        self.assertEqual(rows['revenue']['value'],'416161000000')
        self.assertAlmostEqual(float(rows['net_margin']['value']),26.915,places=2)
        self.assertEqual(rows['ebitda']['status'],'UNAVAILABLE')
        self.assertEqual(rows['roe']['status'],'UNAVAILABLE')
        self.assertTrue(rows['revenue']['inputs'][0]['source_url'].startswith('https://www.sec.gov/'))

if __name__=='__main__':
    unittest.main()
