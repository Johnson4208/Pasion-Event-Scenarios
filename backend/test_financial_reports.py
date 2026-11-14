import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import financial_reports as reports
import public_financials as public
import sec_filings

FIXTURES = Path(__file__).parent / 'fixtures' / 'public_financials'


class ExpandedStatementsTests(unittest.TestCase):
    def setUp(self):
        self.data = {key: json.loads((FIXTURES / ('fpt-' + key + '.json')).read_text(encoding='utf-8'))
                     for key in ('summary', 'balance', 'cash', 'income')}

    def result(self):
        return public.normalize('FPT', self.data['summary'], self.data['balance'], self.data['cash'], self.data['income'])

    def test_all_statement_rows_and_annual_periods_are_retained(self):
        result = self.result()
        self.assertEqual(result['statement_row_count'], 195)
        self.assertEqual(len(result['statements']), 6)
        self.assertTrue(all(len(t['periods']) == 4 for t in result['statements']))
        income = result['statements'][0]
        self.assertEqual(next(r for r in income['rows'] if r['code'] == '70')['unit'], 'currency/share')
        # New property-sale row did not exist in the 2025 template: missing, not zero.
        self.assertIsNone(next(r for r in income['rows'] if r['code'] == '21')['values']['2025:HK'])
        self.assertEqual(next(r for r in income['rows'] if r['code'] == '27')['values']['2025:HK'], '658024835314')

    def test_2026_template_does_not_mislabel_old_financial_income_and_interest(self):
        m = self.result()['financials']['metrics']
        self.assertEqual(m['financial_income']['value'], '2977156356773')
        self.assertEqual(m['interest_expense']['value'], '809759601156')
        self.assertEqual(m['ebit']['value'], '13853392434953')
        self.assertEqual(m['gross_margin']['value'], '36.9241')
        self.assertEqual(m['common_equity']['value'], '36482943944772')
        self.assertIsNone(m['capex']['value'])
        self.assertGreaterEqual(len(m), 60)

    def test_full_statement_cross_issuer_is_rejected(self):
        self.data['income']['value']['data'][0]['symbol'] = 'HPG'
        with self.assertRaisesRegex(public.Unavailable, 'ENTITY_MISMATCH'):
            self.result()

    def test_sec_preserves_unknown_tags_units_zeroes_and_conflicts(self):
        f = {'accn': '0000000001-25-000001', 'end': '2025-12-31', 'start': '2025-01-01', 'form': '10-K'}
        point = {'accn': f['accn'], 'end': f['end'], 'form': '10-K', 'val': 0}
        data = {'facts': {'us-gaap': {'NewReportedTag': {'label': 'A new tag', 'units': {'USD': [point]}},
                                    'Conflict': {'units': {'shares': [point, {**point, 'val': 1}]}}}}}
        table = sec_filings.statement_tables(data, [f], 1)[0]
        self.assertEqual(table['rows'][0]['values'][table['periods'][0]['id']], '0')
        self.assertIsNone(table['rows'][1]['values'][table['periods'][0]['id']])
        self.assertEqual(len(table['rows'][1]['conflicting_periods']), 1)


class FilingArchiveTests(unittest.TestCase):
    def row(self, filename='FPT_2025.pdf', title='Báo cáo tài chính hợp nhất năm 2025 (đã kiểm toán)'):
        return f'<tr><td>{title}</td><td>CN/2025</td><td><a href="https://cafefnew.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{filename}">PDF</a></td></tr>'

    def test_catalog_rejects_wrong_issuer_and_unapproved_hosts(self):
        html = self.row() + self.row('HPG_2025.pdf') + self.row().replace('cafefnew.mediacdn.vn', 'localhost')
        rows = reports.parse_vietnam(html, 'FPT', 'https://cafef.vn/source')
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['annual']); self.assertTrue(rows[0]['audited'])
        self.assertEqual(rows[0]['scope'], 'consolidated')
        for url in ('http://cafef.vn/a', 'https://cafef.vn@localhost/a', 'https://localhost/a', 'file:///tmp/a'):
            self.assertFalse(reports.valid_url(url))

    def test_download_validates_pdf_and_caches_original_bytes(self):
        row = reports.parse_vietnam(self.row(), 'FPT', 'https://cafef.vn/source')[0]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with patch.object(reports, 'read_public', return_value=b'<html>blocked</html>'):
                with self.assertRaisesRegex(reports.ReportError, 'INVALID_PDF'):
                    reports.save_pdf(directory, row)
            with patch.object(reports, 'read_public', return_value=b'%PDF-1.7\noriginal filing') as fetch:
                path = reports.save_pdf(directory, row)
                self.assertEqual(path.read_bytes(), b'%PDF-1.7\noriginal filing')
                reports.save_pdf(directory, row)
                self.assertEqual(fetch.call_count, 1)

    def test_automatic_download_uses_consolidated_not_parent_only_report(self):
        rows = reports.parse_vietnam(self.row('FPT_parent_2025.pdf', 'Báo cáo tài chính công ty mẹ năm 2025') + self.row(), 'FPT', 'https://cafef.vn/source')
        with tempfile.TemporaryDirectory() as tmp, patch.object(reports, 'vietnam_catalog', return_value=(rows, [])), patch.object(reports, 'read_public', return_value=b'%PDF-1.7\noriginal') as fetch:
            result = reports.catalog(Path(tmp), 'FPT', 'VN', 2025)
            self.assertEqual(result['reports'][0]['download_status'], 'AVAILABLE')
            self.assertEqual(result['reports'][1]['download_status'], 'SAVED')
            reports.catalog(Path(tmp), 'FPT', 'VN', 2025)
            self.assertEqual(fetch.call_count, 1)
            with self.assertRaises(reports.ReportError):
                reports.download(Path(tmp), 'FPT', 'VN', '../../secret')


if __name__ == '__main__':
    unittest.main()
