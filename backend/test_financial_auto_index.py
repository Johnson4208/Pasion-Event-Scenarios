import unittest
import financial_auto_index as i

class FinancialAutoIndexTests(unittest.TestCase):
 def test_identifies_explicit_financial_table_cells(self):
  doc={"sections":[{"id":"s1","page":4,"title":"Consolidated income statement",
    "table":[["Metric","2025","2024"],["Revenue","1,250","1,100"],["Net income","220","180"],["Total assets","3,000","2,800"]]}]}
  result=i.scan(doc)
  self.assertEqual(result["status"],"CANDIDATES_FOUND")
  self.assertEqual(result["candidate_count"],6)
  values={(c["definition_id"],c["year"]):c["value"] for c in result["candidates"]}
  self.assertEqual(values[("revenue","2025")],"1250")
  self.assertEqual(values[("net_income","2024")],"180")
  self.assertEqual(values[("assets","2025")],"3000")
  self.assertEqual(result["candidates"][0]["row"],1)
 def test_no_autopromotion_of_ambiguous_period_or_ocr_numbers(self):
  doc={"sections":[{"id":"s","page":1,"text":"Revenue 120 million in 2025"},{
   "id":"t","page":2,"table":[["Metric","Q2 2025"],["Revenue","999"]]}]}
  classified=i.scan(doc)
  self.assertEqual(classified["candidate_count"],1)
  self.assertEqual(classified["candidates"][0]["period_type"],"Q")
  self.assertEqual(classified["candidates"][0]["period_candidate"]["status"],"PERIOD_CANDIDATE_REQUIRES_FISCAL_CALENDAR")
  self.assertIsNone(i.number("1,2O0"))
  self.assertIsNone(i.number("1.200,00"))
 def test_duplicate_metrics_marked_ambiguous(self):
  doc={"sections":[{"id":"x","page":1,"table":[["Metric","2025"],["Revenue","100"],["Revenue","150"]]}]}
  result=i.scan(doc)
  self.assertTrue(all(x["ambiguous"] for x in result["candidates"]))
 def test_zero_and_parentheses(self):
  self.assertEqual(i.number("0"),"0")
  self.assertEqual(i.number("(1,200)"),"-1200")

if __name__=="__main__":unittest.main()
