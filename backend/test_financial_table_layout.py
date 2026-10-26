import unittest
import financial_table_layout as layout
import financial_auto_index as idx

class LayoutTests(unittest.TestCase):
 def test_multirow_fiscal_columns(self):
  grid=[["Metric","2025","2024"],["","Q2","FY"],["Revenue","120","400"]]
  cols,last,issues=layout.headers(grid)
  self.assertEqual(last,1)
  self.assertEqual(cols[1]["period_type"],"Q")
  self.assertEqual(cols[1]["quarter"],2)
  self.assertEqual(cols[2]["period_type"],"FY")
  self.assertEqual(idx.scan({"sections":[{"id":"s","page":1,"kind":"table","table":grid}]})["candidate_count"],2)
 def test_conflicting_year_column(self):
  cols,last,issues=layout.headers([["Metric","2025"],["","2024"],["Revenue","123"]])
  self.assertEqual(cols,{})
  self.assertTrue(any(x.get("code")=="MULTIPLE_YEARS_IN_COLUMN" for x in issues))
 def test_do_not_map_gross_sales_to_net_revenue(self):
  self.assertIsNone(idx.exact_metric("Doanh thu bán hàng và cung cấp dịch vụ"))
  self.assertEqual(idx.exact_metric("Doanh thu thuần"),"revenue")
if __name__=="__main__":unittest.main()
