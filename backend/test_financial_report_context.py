import unittest
import financial_report_context as p
import financial_auto_index as idx

class UsVnReportRecognitionTests(unittest.TestCase):
 def test_explicit_us_basis_scope_and_issuer(self):
  d={"sections":[{"id":"s1","kind":"text","text":"Consolidated financial statements\nPrepared under accounting principles generally accepted in the United States\nNASDAQ: AAPL\nStatements of Operations"}]}
  result=p.detect_profile(d)
  self.assertEqual(result["standard"]["value"],"US_GAAP")
  self.assertEqual(result["scope"]["value"],"CONSOLIDATED")
  self.assertEqual(result["issuer"]["value"],"US:AAPL")
  self.assertIn("income_statement",result["statement_types"])
 def test_explicit_vietnam_basis_and_separate(self):
  d={"sections":[{"id":"s1","kind":"text","text":"Báo cáo tài chính riêng\nChuẩn mực kế toán Việt Nam\nHOSE: VNM"}]}
  r=p.detect_profile(d)
  self.assertEqual(r["standard"]["value"],"VAS")
  self.assertEqual(r["scope"]["value"],"SEPARATE")
  self.assertEqual(r["issuer"]["value"],"VN:VNM")
 def test_conflicting_scope_is_not_selected(self):
  d={"sections":[{"id":"a","kind":"text","text":"Consolidated financial statements\nSeparate financial statements"}]}
  self.assertEqual(p.detect_profile(d)["scope"]["status"],"CONFLICT")
  self.assertIsNone(p.detect_profile(d)["scope"]["value"])
 def test_quarter_and_ytd_headers(self):
  self.assertEqual(p.period_header("Q2 2025")["period_type"],"Q")
  self.assertEqual(p.period_header("Lũy kế 6 tháng 2025")["period_type"],"YTD")
  self.assertEqual(p.period_header("FY2025")["period_type"],"FY")
  self.assertEqual(p.period_header("2025")["period_type"],"YEAR_UNSPECIFIED")
  self.assertIsNone(p.date_end("09/10/2025"))
 def test_document_candidates_keep_period_unknowns(self):
  d={"sections":[{"id":"t","kind":"table","page":2,"title":"Statement of Operations","table":[["Metric","Q2 2025","FY2024"],["Revenue","100","400"]]}]}
  r=idx.scan(d)
  self.assertEqual(r["candidate_count"],2)
  self.assertEqual([x["period_type"] for x in r["candidates"]],["Q","FY"])
  self.assertEqual(r["report_profile"]["standard"]["status"],"UNKNOWN")
  self.assertTrue(all(x["normalized_value"] is None for x in r["candidates"]))
if __name__=="__main__":unittest.main()
