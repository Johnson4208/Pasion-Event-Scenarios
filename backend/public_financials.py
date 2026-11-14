"""On-demand public financial snapshots. Never writes accepted facts or valuations.

CafeF endpoints are the JSON feeds used by its public financial statement page.
Amounts in statement feeds are VND (the page divides by 1e9 to display billions).
Fiscal year labels are retained; a December year-end is NOT inferred from a year.
"""
import copy
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import financial_sources
import sec_filings

VERSION = 1
CACHE_VERSION = 2
TTL = 6 * 3600
CACHE = {}
ATTEMPTS = {}
PREPARE_LOCKS = [threading.Lock() for _ in range(32)]
FETCH_LOCK = threading.Lock()
LAST_FETCH = 0.0
MAX_BYTES = 4 * 1024 * 1024
BASE = 'https://apiweb.cafef.vn/api/'
FEEDS = {
    'summary': BASE + 'v1/BCTC/GetReportSummary',
    'balance': BASE + 'v2/BCTC/GetReportCDKT',
    'cash': BASE + 'v1/BCTC/GetReportLCTT',
    'income': BASE + 'v1/BCTC/GetReportDetail',
}


class Unavailable(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def fetch_json(url):
    global LAST_FETCH
    with FETCH_LOCK:
        delay = .35 - (time.monotonic() - LAST_FETCH)
        if delay > 0:
            time.sleep(delay)
        LAST_FETCH = time.monotonic()
    try:
        request = Request(url, headers={'User-Agent': 'Pasion Financial Research/1.0',
                                       'Accept': 'application/json', 'Accept-Encoding': 'identity'})
        with urlopen(request, timeout=12) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise Unavailable('PROVIDER_RESPONSE_TOO_LARGE')
        return json.loads(raw, parse_float=Decimal)
    except HTTPError as exc:
        raise Unavailable('PROVIDER_RATE_LIMITED' if exc.code == 429 else 'PROVIDER_UNAVAILABLE') from exc
    except (OSError, TimeoutError, ValueError, UnicodeError) as exc:
        raise Unavailable('PROVIDER_UNAVAILABLE') from exc


def number(value):
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def plain(value):
    text = unicodedata.normalize('NFKD', str(value).casefold()).replace('đ', 'd')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


def grouped_payload(payload):
    """Adapt the detailed income endpoint, including its documented 2026 code migration."""
    if not isinstance(payload, dict) or not isinstance(payload.get('value'), dict):
        return payload
    value = payload['value']
    templates = value.get('templace') or []
    if not templates or 'data' in templates[0]:
        return payload
    result = copy.deepcopy(payload)
    value = result['value']
    labels = {str(r.get('code', '')).strip(): plain(r.get('name', '')) for r in templates}
    industrial_2026 = ('lai lo cua hoat dong ban thanh ly bat dong san dau tu' in labels.get('21', '') and
                       'doanh thu hoat dong tai chinh' in labels.get('22', '') and
                       'chi phi lai vay' in labels.get('24', ''))
    periods = value.get('data', [])
    if industrial_2026:
        mapping = {'22': '21', '23': '22', '24': '23', '27': '24'}
        for period in periods:
            if type(period.get('year')) is int and period['year'] <= 2025:
                original = {str(c.get('code', '')).strip(): c for c in period.get('data', [])}
                converted = []
                for template in templates:
                    code = str(template['code']).strip()
                    if code == '21':  # New property-disposal line has no old-form counterpart.
                        continue
                    old_code = mapping.get(code, code)
                    if old_code in original:
                        converted.append({**original[old_code], 'code': code, 'source_code': old_code})
                period['data'] = converted
    kind = value.get('type', 'KQKD')
    value['templace'] = [{'code': kind, 'name': 'Kết quả hoạt động kinh doanh', 'data': templates}]
    value['data'] = [{'code': kind, 'data': periods}]
    return result


def groups(payload, ticker):
    """Validate identity and template, retain period + report basis for every cell."""
    if not isinstance(payload, dict) or payload.get('isSuccess') is not True:
        raise Unavailable('INVALID_PROVIDER_RESPONSE')
    payload = grouped_payload(payload)
    value = payload.get('value')
    if not isinstance(value, dict) or not isinstance(value.get('data'), list):
        raise Unavailable('INVALID_PROVIDER_RESPONSE')
    templates = {str(g['code']): g for g in value.get('templace', []) if isinstance(g, dict) and 'data' in g}
    result = {}
    for group in value['data']:
        code = str(group.get('code', ''))
        template = templates.get(code)
        if not template:
            continue
        labels = {str(row['code']).strip(): row['name'] for row in template['data']}
        periods = {}
        for period in group.get('data', []):
            if period.get('symbol', '').upper() != ticker:
                raise Unavailable('PROVIDER_ENTITY_MISMATCH')
            year = period.get('year')
            if (type(year) is not int or not 1990 <= year <= date.today().year or
                    period.get('quater') != 0 or str(period.get('time')) != str(year) or not period.get('type')):
                continue
            key = (year, period['type'])
            cells = {}
            for cell in period.get('data', []):
                tag = str(cell.get('code', '')).strip()
                if tag not in labels:
                    continue
                val = number(cell.get('value'))
                if val is not None:
                    if tag in cells and cells[tag]['value'] != val:
                        raise Unavailable('CONFLICTING_PROVIDER_VALUES')
                    cells[tag] = {'value': val, 'label': labels[tag], 'tag': code + ':' + str(cell.get('source_code', tag)),
                                  'year': year, 'report_type': period['type']}
            if key in periods and cells != periods[key]:
                raise Unavailable('CONFLICTING_PROVIDER_PERIODS')
            periods[key] = cells
        result[code] = periods
    return result


def statement_tables(ticker, payload, category, only=None):
    """Keep every published template line, including missing cells and actual zeroes."""
    if not payload:
        return []
    payload = grouped_payload(payload)
    validated = groups(payload, ticker)
    tables = []
    for template in payload['value']['templace']:
        code = str(template['code'])
        if only and code not in only:
            continue
        periods = validated.get(code, {})
        if not periods:
            continue
        metadata = next((g for g in payload['value']['data'] if str(g.get('code')) == code), {})
        labels = {(p.get('year'), p.get('type')): p.get('content', '') for p in metadata.get('data', [])}
        keys = sorted(periods, reverse=True)
        rows = []
        for row in template['data']:
            tag = str(row['code']).strip()
            name = ' '.join(str(row['name']).split())
            if not tag:
                continue
            eps = 'co phieu' in plain(name) and ('lai co ban' in plain(name) or 'lai suy giam' in plain(name))
            rows.append({'id': code + ':' + tag, 'code': tag, 'label': name,
                         'unit': 'currency/share' if eps else 'currency', 'currency': 'VND',
                         'values': {str(year) + ':' + basis: str(periods[(year, basis)][tag]['value'])
                                    if tag in periods[(year, basis)] else None for year, basis in keys}})
        tables.append({'id': category + '-' + code, 'category': category, 'title': template.get('name', code),
                       'periods': [{'id': str(year) + ':' + basis, 'label': 'FY ' + str(year),
                                    'year': year, 'basis': basis, 'description': labels.get((year, basis), '')}
                                   for year, basis in keys], 'rows': rows, 'provider': 'CafeF',
                       'source_url': 'https://cafef.vn/du-lieu/' + ticker.lower() + '/bao-cao-tai-chinh.chn'})
    return tables


def select(cells, tag, label_fragment):
    cell = cells.get(tag)
    return cell if cell and plain(label_fragment) in plain(cell['label']) else None


def normalize(ticker, summary, balance=None, cash=None, income_detail=None):
    root = groups(summary, ticker)
    income, sheet = root.get('KQKD', {}), root.get('CDKT', {})
    eligible = set(income) & set(sheet)
    if not eligible:
        raise Unavailable('NO_PUBLIC_FINANCIALS')
    newest = max(year for year, _ in eligible)
    bases = [basis for year, basis in eligible if year == newest]
    if len(bases) != 1:
        raise Unavailable('AMBIGUOUS_REPORT_BASIS')
    basis = bases[0]
    current = (newest, basis)
    prior = (newest - 1, basis)
    inc, bs, opening = income[current], sheet[current], sheet.get(prior, {})
    detail = groups(balance, ticker) if balance else {}
    flow = groups(cash, ticker) if cash else {}
    full_income = groups(income_detail, ticker) if income_detail else {}
    nv = detail.get('NV', {}).get(current, {})
    operating = flow.get('HDKD', {}).get(current, {})
    investing = flow.get('HDDT', {}).get(current, {})
    url = 'https://cafef.vn/du-lieu/' + ticker.lower() + '/bao-cao-tai-chinh.chn'
    metrics = {}

    def put(key, cells, calculate=lambda v: v[0], unit='currency', formula=None, reason='MISSING_SOURCE_INPUTS'):
        result = {'definition_id': key, 'status': 'UNAVAILABLE', 'value': None, 'unit': unit,
                  'currency': 'VND', 'period_type': 'FY', 'period_end': str(newest),
                  'period_label': 'FY ' + str(newest), 'provider': 'CafeF', 'source_url': url,
                  'origin': 'PUBLIC_PROVIDER' if formula is None else 'DERIVED',
                  'report_type': basis, 'human_reviewed': False, 'reason_codes': [reason],
                  'source_ids': [], 'inputs': [], 'formula': formula}
        if cells and all(cell is not None for cell in cells):
            result['inputs'] = [{**c, 'value': str(c['value'])} for c in cells]
            result['source_ids'] = [ticker + ':' + str(c['year']) + ':' + c['tag'] for c in cells]
            try:
                value = calculate([c['value'] for c in cells])
                if value is not None and value.is_finite():
                    result.update(status='READY', value=format(value.quantize(Decimal('.0001')), 'f').rstrip('0').rstrip('.') if unit in ('%', 'x') else str(value), reason_codes=[])
                    if result['value'] in ('', '-0'):
                        result['value'] = '0'
            except (ArithmeticError, ValueError):
                result['reason_codes'] = ['INVALID_DENOMINATOR_OR_SIGN']
        metrics[key] = result
        return cells[0] if len(cells) == 1 and cells[0] is not None else None

    def ratio(a, b):
        if b <= 0:
            raise ValueError('Positive denominator required')
        return a / b

    bank = select(inc, 'KQKD_2', 'Thu nhập lãi thuần') is not None
    rev = put('revenue', [select(inc, 'KQKD_2', 'Doanh thu thuần')])
    profit = put('net_income', [select(inc, 'KQKD_13', 'Lợi nhuận sau thuế')])
    parent = put('net_income_common', [select(inc, 'KQKD_14', 'Lợi nhuận sau thuế của cổ đông')])
    put('eps', [select(inc, 'KQKD_15', 'Lãi cơ bản trên cổ phiếu')], unit='currency/share')
    assets = put('assets', [select(bs, 'CDKT_29' if bank else 'CDKT_27', 'Tổng cộng tài sản')])
    equity = put('equity', [select(bs, 'CDKT_38' if bank else 'CDKT_31', 'Vốn và các quỹ' if bank else 'Vốn chủ sở hữu')])
    ca = put('current_assets', [select(bs, 'CDKT_17', 'Tài sản ngắn hạn')])
    cl = put('current_liabilities', [select(bs, 'CDKT_29', 'Nợ ngắn hạn')])
    put('net_margin', [profit, rev], lambda v: ratio(*v) * 100, '%', 'Net income / revenue × 100')
    put('current_ratio', [ca, cl], lambda v: ratio(*v), 'x', 'Current assets / current liabilities')
    put('roa', [profit, select(opening, 'CDKT_29' if bank else 'CDKT_27', 'Tổng cộng tài sản'), assets],
        lambda v: ratio(v[0], (v[1] + v[2]) / 2) * 100, '%', 'Net income / average total assets × 100')
    # Match profit attributable to owners with equity excluding non-controlling interests.
    nci = select(bs, 'CDKT_35', 'Lợi ích của cổ đông thiểu số')
    old_nci = select(opening, 'CDKT_35', 'Lợi ích của cổ đông thiểu số')
    old_equity = select(opening, 'CDKT_31', 'Vốn chủ sở hữu')
    put('common_equity', [equity, nci], lambda v: v[0] - v[1], formula='Equity − non-controlling interests')
    put('roe', [parent, old_equity, old_nci, equity, nci],
        lambda v: ratio(v[0], (v[1] - v[2] + v[3] - v[4]) / 2) * 100, '%',
        'Profit attributable to owners / average equity attributable to owners × 100')
    if bank:
        # Bank equity template lists owners' capital and reserves separately from NCI.
        put('common_equity', [equity])
        put('roe', [parent, select(opening, 'CDKT_38', 'Vốn và các quỹ'), equity],
            lambda v: ratio(v[0], (v[1] + v[2]) / 2) * 100, '%',
            'Profit attributable to bank owners / average capital and reserves × 100')
    short_debt = select(nv, '320', 'Vay và nợ thuê tài chính')
    long_debt = select(nv, '338', 'Vay và nợ thuê tài chính dài hạn')
    put('debt_equity', [short_debt, long_debt, equity], lambda v: ratio(v[0] + v[1], v[2]), 'x',
        '(Short-term + long-term borrowings and leases) / equity')
    cfo = put('cfo', [select(operating, 'HDKD_20', 'Lưu chuyển tiền thuần từ hoạt động kinh doanh')])
    capex = select(investing, 'HDDT_22', 'Tiền chi để mua sắm xây dựng TSCĐ')
    investment_total = select(investing, 'HDDT_29', 'Lưu chuyển tiền thuần từ hoạt động đầu tư')
    investment_parts = [investing.get('HDDT_' + str(i)) for i in range(22, 29)]
    # This public feed sometimes encodes a missing capex line as zero. Its cash
    # bridge must reconcile before a zero can be used as genuine expenditure.
    cash_reconciles = (investment_total is not None and all(investment_parts) and
                       abs(sum(c['value'] for c in investment_parts) - investment_total['value']) <= 1)
    if not cash_reconciles:
        capex = None
    def free_cash(v):
        if v[1] > 0:
            raise ValueError('Cash expenditure must be negative in this feed')
        return v[0] + v[1]
    put('free_cash_flow', [cfo, capex], free_cash, formula='Operating cash flow + signed payments for fixed and other long-term assets',
        reason='CASH_FLOW_RECONCILIATION_REQUIRED' if not cash_reconciles else 'MISSING_SOURCE_INPUTS')
    put('ebitda_margin', [], unit='%', reason='EBITDA_EXPENSE_RECONCILIATION_REQUIRED')
    put('revenue_growth', [rev, select(income.get(prior, {}), 'KQKD_2', 'Doanh thu thuần')],
        lambda v: (ratio(*v) - 1) * 100, '%', 'Revenue / previous fiscal-year revenue − 1')
    # Expanded direct observations and ratios. All operands retain the same annual
    # report basis. Bank templates are handled separately, never as industrials.
    income_full = full_income.get('KQKD', {}).get(current, {})
    financing = flow.get('HDTC', {}).get(current, {})
    cash_balance = put('cash', [select(bs, 'CDKT_18', 'Tiền và các khoản tương đương tiền')])
    inventory = put('inventories', [select(bs, 'CDKT_21', 'Hàng tồn kho')])
    receivables = put('receivables', [select(bs, 'CDKT_20', 'Các khoản phải thu ngắn hạn')])
    liabilities = put('liabilities', [select(bs, 'CDKT_28', 'Nợ phải trả')])
    gross_profit = put('gross_profit', [select(inc, 'KQKD_4', 'Lợi nhuận gộp')])
    cogs = put('cost_of_revenue', [select(inc, 'KQKD_3', 'Giá vốn hàng bán')])
    operating_profit = put('operating_profit', [select(inc, 'KQKD_9', 'Lợi nhuận thuần từ hoạt động kinh doanh')])
    pretax = put('pretax_income', [select(inc, 'KQKD_12', 'Tổng lợi nhuận kế toán trước thuế')])
    interest = put('interest_expense', [select(income_full, '24', 'Chi phí lãi vay')])
    for key, source, tag, label in [
            ('financial_income', inc, 'KQKD_5', 'Doanh thu hoạt động tài chính'),
            ('financial_expense', inc, 'KQKD_6', 'Chi phí tài chính'),
            ('selling_expense', inc, 'KQKD_7', 'Chi phí bán hàng'),
            ('administrative_expense', inc, 'KQKD_8', 'Chi phí quản lý doanh nghiệp'),
            ('noncurrent_assets', bs, 'CDKT_23', 'Tài sản dài hạn'),
            ('fixed_assets', bs, 'CDKT_24', 'Tài sản cố định'),
            ('short_investments', bs, 'CDKT_19', 'Các khoản đầu tư tài chính ngắn hạn'),
            ('long_liabilities', bs, 'CDKT_30', 'Nợ dài hạn'),
            ('retained_earnings', bs, 'CDKT_34', 'Lợi nhuận sau thuế chưa phân phối'),
            ('payables', nv, '311', 'Phải trả người bán ngắn hạn'),
            ('investing_cash_flow', investing, 'HDDT_29', 'Lưu chuyển tiền thuần từ hoạt động đầu tư'),
            ('financing_cash_flow', financing, 'HDTC_38', 'Lưu chuyển tiền thuần từ hoạt động tài chính'),
            ('cash_change', financing, 'HDTC_39', 'Lưu chuyển tiền thuần trong kỳ'),
            ('dividends_paid', financing, 'HDTC_36', 'Cổ tức, lợi nhuận đã trả'),
            ('current_tax', income_full, '51', 'Chi phí thuế TNDN hiện hành'),
            ('deferred_tax', income_full, '52', 'Chi phí thuế TNDN hoãn lại')]:
        put(key, [select(source, tag, label)])
    put('eps_diluted', [select(income_full, '71', 'Lãi suy giảm')], unit='currency/share')
    put('debt', [short_debt, long_debt], lambda v: sum(v), formula='Short-term + long-term borrowings and leases')
    put('short_debt', [short_debt]); put('long_debt', [long_debt])
    put('net_debt', [short_debt, long_debt, cash_balance], lambda v: v[0] + v[1] - v[2], formula='Borrowings and leases − cash and equivalents')
    put('working_capital', [ca, cl], lambda v: v[0] - v[1], formula='Current assets − current liabilities')
    put('capex', [capex], lambda v: -v[0], formula='Absolute cash payments for fixed and other long-term assets',
        reason='CASH_FLOW_RECONCILIATION_REQUIRED' if not cash_reconciles else 'MISSING_SOURCE_INPUTS')
    for key, numerator, denominator, formula in [
            ('gross_margin', gross_profit, rev, 'Gross profit / revenue × 100'),
            ('operating_margin', operating_profit, rev, 'Source operating profit / revenue × 100'),
            ('pretax_margin', pretax, rev, 'Pretax income / revenue × 100'),
            ('liabilities_assets', liabilities, assets, 'Total liabilities / assets × 100'),
            ('equity_assets', equity, assets, 'Equity / assets × 100'),
            ('cfo_margin', cfo, rev, 'Operating cash flow / revenue × 100')]:
        put(key, [numerator, denominator], lambda v: ratio(*v) * 100, '%', formula)
    put('quick_ratio', [ca, inventory, cl], lambda v: ratio(v[0] - v[1], v[2]), 'x', '(Current assets − inventory) / current liabilities')
    put('cash_ratio', [cash_balance, cl], lambda v: ratio(*v), 'x', 'Cash and equivalents / current liabilities')
    put('cfo_net_income', [cfo, profit], lambda v: ratio(*v), 'x', 'Operating cash flow / net income')
    put('cfo_current_liabilities', [cfo, cl], lambda v: ratio(*v), 'x', 'Operating cash flow / current liabilities')
    put('asset_turnover', [rev, select(opening, 'CDKT_27', 'Tổng cộng tài sản'), assets],
        lambda v: ratio(v[0], (v[1] + v[2]) / 2), 'x', 'Revenue / average total assets')
    put('inventory_turnover', [cogs, select(opening, 'CDKT_21', 'Hàng tồn kho'), inventory],
        lambda v: ratio(v[0], (v[1] + v[2]) / 2), 'x', 'Cost of revenue / average inventory')
    put('net_income_growth', [profit, select(income.get(prior, {}), 'KQKD_13', 'Lợi nhuận sau thuế')],
        lambda v: (ratio(*v) - 1) * 100, '%', 'Net income / previous annual net income − 1')
    put('ebit', [pretax, interest], lambda v: v[0] + v[1], formula='Pretax income + interest expense')
    put('interest_coverage', [pretax, interest], lambda v: ratio(v[0] + v[1], v[1]), 'x',
        '(Pretax income + interest expense) / interest expense')
    if bank:
        for key in ('revenue', 'revenue_growth', 'net_margin', 'ebitda_margin', 'current_ratio', 'debt_equity', 'free_cash_flow'):
            metrics[key].update(status='UNAVAILABLE', value=None, reason_codes=['BANK_METRIC_NOT_APPLICABLE'])
    if not any(m['status'] == 'READY' for m in metrics.values()):
        raise Unavailable('UNSUPPORTED_REPORT_TEMPLATE')
    tables = (statement_tables(ticker, income_detail or summary, 'income', {'KQKD'}) +
              statement_tables(ticker, balance or summary, 'balance', None if balance else {'CDKT'}) +
              statement_tables(ticker, cash, 'cash_flow'))
    return {'version': VERSION, 'ticker': ticker, 'market': 'VN', 'provider': 'CafeF', 'issuer': ticker,
            'period': 'FY', 'period_end': str(newest), 'source_url': url, 'report_type': basis,
            'source_status': 'PUBLIC_PROVIDER_NOT_HUMAN_REVIEWED', 'review_required_for_valuation': True,
            'statements': tables, 'statement_row_count': sum(len(table['rows']) for table in tables),
            'financials': {'version': 1, 'status': 'READY', 'company': {'ticker': ticker, 'name': ticker},
                           'period': 'FY', 'period_end': str(newest), 'metrics': metrics}}


def build_vietnam(ticker):
    def read(item):
        name, url = item
        try:
            return name, fetch_json(url), None
        except Unavailable as exc:
            return name, None, exc.reason
    endpoints = {name: url + '?symbol=' + ticker + '&pageIndex=1&pageSize=4&reportType=ALL&TypeTime=NAM'
                 for name, url in FEEDS.items()}
    endpoints['income'] = endpoints['income'].replace('reportType=ALL', 'reportType=KQKD')
    endpoints['identity'] = 'https://cafef.vn/du-lieu/Ajax/PageNew/CompanyIntro.ashx?Symbol=' + ticker
    endpoints['market'] = 'https://cafef.vn/du-lieu/Ajax/PageNew/ChiSoTaiChinh.ashx?Symbol=' + ticker
    endpoints['quote'] = 'https://cafef.vn/du-lieu/Ajax/PageNew/PriceRealTimeHeader.ashx?Symbol=' + ticker
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(read, endpoints.items()))
    data = {name: payload for name, payload, _ in rows}
    if data['summary'] is None:
        raise Unavailable(next(error for name, _, error in rows if name == 'summary'))
    warnings = [name + ': ' + error for name, _, error in rows if error]
    # Supplemental outages do not erase already downloaded financial statements.
    for name in ('balance', 'cash', 'income'):
        try:
            if data[name] is not None:
                groups(data[name], ticker)
        except Unavailable as exc:
            if exc.reason == 'PROVIDER_ENTITY_MISMATCH':
                raise
            warnings.append(name + ': ' + exc.reason)
            data[name] = None
    result = normalize(ticker, data['summary'], data['balance'], data['cash'], data['income'])
    identity = (data.get('identity') or {}).get('Data') or {}
    if identity.get('Symbol', '').upper() == ticker and identity.get('Name'):
        result['issuer'] = identity['Name']
        result['financials']['company']['name'] = identity['Name']
        market_rows = (data.get('market') or {}).get('Data', [])
        if isinstance(market_rows, list):
            mapped = {row.get('Code'): row for row in market_rows if isinstance(row, dict)}
            for key, tag, label, scale, unit in [('market_cap', 'VonHoaThiTruong', 'Vốn hóa thị trường', 1000000000, 'currency'),
                                                ('pe', 'P/E', 'P/E', 1, 'x'), ('pb', 'Beta', 'P/B', 1, 'x')]:
                row = mapped.get(tag, {})
                # The public feed calls P/B "Beta" internally: validate the visible label too.
                value = number(str(row.get('Value', '')).replace(',', ''))
                if value is None or value <= 0 or plain(label) not in plain(row.get('Text', '')):
                    continue
                result['financials']['metrics'][key] = {'definition_id': key, 'status': 'READY',
                    'value': str(value * scale), 'unit': unit, 'currency': 'VND', 'provider': 'CafeF',
                    'source_url': result['source_url'], 'period_label': 'Market snapshot',
                    'source_context': mapped.get('ThoiGian', {}).get('Value'), 'reason_codes': [],
                    'origin': 'PUBLIC_PROVIDER', 'human_reviewed': False}
        quote = (data.get('quote') or {}).get('Data') or {}
        stamp = re.fullmatch(r'/Date\((\d{13})\)/', str(quote.get('ThoiGian', '')))
        price = number(quote.get('Gia'))
        if stamp and price is not None and price > 0:
            quote_time = int(stamp[1]) / 1000
            # Price payload uses thousands of VND, as declared by CafeF's page.
            if 0 <= time.time() - quote_time <= 7 * 86400:
                result['quote'] = {'status': 'READY', 'price': str(price * 1000), 'currency': 'VND',
                    'as_of': datetime.fromtimestamp(quote_time, timezone.utc).isoformat(),
                    'provider': 'CafeF', 'source_url': result['source_url'], 'verified_for_valuation': False}
    elif identity.get('Symbol'):
        raise Unavailable('PROVIDER_ENTITY_MISMATCH')
    result['warnings'] = warnings
    return result


def research(root, ticker, market, refresh=False):
    ticker = ticker.upper()
    if not re.fullmatch(r'[A-Z0-9.-]{1,16}', ticker) or market not in ('VN', 'US'):
        raise Unavailable('INVALID_MARKET_OR_TICKER')
    if market == 'US':
        # Automatic mode never silently substitutes the bundled historical Apple example.
        agent, _ = financial_sources.settings(root)
        if not financial_sources.valid_agent(agent):
            raise Unavailable('SEC_USER_AGENT_NOT_CONFIGURED')
        try:
            result = copy.deepcopy(sec_filings.research(ticker, refresh, root=root))
        except sec_filings.FilingUnavailable as exc:
            raise Unavailable(exc.reason) from exc
        result.update(market='US', provider='SEC', source_url=result.get('filing_url'))
        for metric in result['financials']['metrics'].values():
            metric.update(provider='SEC', source_url=result['source_url'], period_label='FY ' + result['period_end'])
        metrics = result['financials']['metrics']
        cfo, capex = metrics.get('cfo', {}), metrics.get('capex', {})
        if (cfo.get('status') == capex.get('status') == 'READY' and number(capex.get('value')) is not None and
                number(capex['value']) >= 0 and cfo.get('period_end') == capex.get('period_end')):
            metrics['free_cash_flow'] = {**cfo, 'definition_id': 'free_cash_flow', 'origin': 'DERIVED',
                'value': str(number(cfo['value']) - number(capex['value'])), 'formula': 'Operating cash flow − capital expenditure',
                'source_ids': cfo.get('source_ids', []) + capex.get('source_ids', [])}
        return result
    root = Path(root)
    key = (str(root.resolve()), ticker)
    path = financial_sources.directory(root) / ('cafef-' + ticker + '.json')
    # A slow old selection should not block another company's request.
    # Striped preparation locks bound memory while coalescing same-ticker loads.
    with PREPARE_LOCKS[hash(key) % len(PREPARE_LOCKS)]:
        now = time.time()
        previous = CACHE.get(key)
        if previous is None:
            try:
                entry = json.loads(path.read_text(encoding='utf-8'))
                stamp, result = entry['timestamp'], entry['result']
                if (entry.get('cache_version') == CACHE_VERSION and isinstance(stamp, (int, float)) and
                        0 <= now - stamp and result.get('ticker') == ticker and
                        result.get('market') == 'VN' and result.get('provider') == 'CafeF'):
                    previous = (stamp, result)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                pass
        def cached(error=None):
            return {**previous[1], 'cache_status': 'FRESH' if now - previous[0] < TTL else 'STALE', 'refresh_error': error}
        if previous and now - previous[0] < TTL and not refresh:
            return cached()
        if now - ATTEMPTS.get(key, 0) < 60:
            if previous:
                return cached('REFRESH_COOLDOWN')
            raise Unavailable('REFRESH_COOLDOWN')
        ATTEMPTS[key] = now
        try:
            result = build_vietnam(ticker)
        except Unavailable as exc:
            if previous:
                return cached(exc.reason)
            raise
        stamp = time.time()
        result['retrieved_at'] = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
        CACHE[key] = (stamp, result)
        if len(CACHE) > 256:
            CACHE.pop(next(iter(CACHE)), None)
        if len(ATTEMPTS) > 512:
            ATTEMPTS.pop(next(iter(ATTEMPTS)), None)
        try:
            financial_sources.atomic_json(path, {'cache_version': CACHE_VERSION, 'timestamp': stamp, 'result': result})
        except OSError:
            result['warnings'].append('CACHE_WRITE_FAILED')
        return {**result, 'cache_status': 'LIVE'}
