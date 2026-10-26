import unittest
from decimal import Decimal
import financial_locale as u
import financial_auto_index as idx

class UsVietnamFinancialLocaleTests(unittest.TestCase):
 def test_vietnam_million_dong(self):
  d={"sections":[{"id":"unit","kind":"text","page":1,"text":"Đơn vị tính: triệu đồng"},
   {"id":"table","kind":"table","page":1,"title":"Kết quả kinh doanh",
    "table":[["Chỉ tiêu","2025","2024"],["Doanh thu thuần","1.234,5","1.001,0"],["Lợi nhuận sau thuế","100,5","50,5"]]}]}
  result=idx.scan(d)
  self.assertEqual(result["candidate_count"],4)
  metric=next(x for x in result["candidates"] if x["definition_id"]=="revenue" and x["year"]=="2025")
  self.assertEqual((metric["currency"],metric["scale"],metric["value"],metric["normalized_value"]),("VND","1000000","1234.5","1234500000.0"))
 def test_usd_millions(self):
  d={"sections":[{"id":"source","kind":"text","page":2,"text":"(In millions of US dollars)"},
   {"id":"t","kind":"table","page":2,"table":[["Metric","2025"],["Revenue","1,234.50"],["Net income","220.75"]]}]}
  r=idx.scan(d)
  self.assertEqual(r["candidate_count"],2)
  self.assertEqual(r["candidates"][0]["currency"],"USD")
  self.assertEqual(r["candidates"][0]["scale"],"1000000")
  self.assertEqual(Decimal(r["candidates"][0]["normalized_value"]),Decimal("1234500000"))
 def test_conflicting_or_missing_units_withheld(self):
  d={"sections":[{"kind":"text","page":1,"text":"Đơn vị tính: triệu đồng\nUnit: USD millions"},
   {"kind":"table","page":1,"id":"t","table":[["Metric","2025"],["Revenue","1,200"]]}]}
  item=idx.scan(d)["candidates"][0]
  self.assertEqual(item["unit_status"],"CONFLICTING_UNIT_DECLARATIONS")
  self.assertIsNone(item["currency"])
  self.assertIsNone(item["normalized_value"])
 def test_currency_and_number_not_inferred_from_market(self):
  d={"sections":[{"kind":"table","page":1,"id":"t","table":[["Metric","2025"],["Revenue","1,200"]]}]}
  item=idx.scan(d)["candidates"][0]
  self.assertIsNone(item["scale"])
  self.assertIsNone(item["currency"])
  self.assertEqual(u.parse_number("1.234,5","US"),None)
  self.assertEqual(u.parse_number("1,234.5","VN"),None)
 def test_zero_parentheses_scale(self):
  self.assertEqual(u.parse_number("(1.234,5)","VN"),"-1234.5")
  self.assertEqual(u.parse_number("0","VN"),"0")

if __name__=="__main__":unittest.main()
