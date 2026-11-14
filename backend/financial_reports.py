"""Download original public filings into an isolated, issuer-scoped archive.

The archive is not the accepted accounting database. Only URLs discovered on a
known reporting source can be downloaded; callers supply an issuer and report ID.
"""
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

import financial_sources
import sec_filings

MAX_PDF = 40 * 1024 * 1024
TTL = 6 * 3600
LOCKS = [threading.Lock() for _ in range(32)]
HOSTS = {'cafef.vn', 'cafefnew.mediacdn.vn', 'data.sec.gov', 'www.sec.gov', 'bctn2025.fpt.com'}


class ReportError(Exception):
    pass


def valid_url(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in HOSTS and p.port in (None, 443) and not p.username and not p.password


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not valid_url(newurl):
            raise ReportError('UNSUPPORTED_REPORT_HOST')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_public(url, limit=2 * 1024 * 1024, agent='Pasion Financial Research/1.0'):
    if not valid_url(url):
        raise ReportError('UNSUPPORTED_REPORT_HOST')
    try:
        request = Request(url, headers={'User-Agent': agent, 'Accept-Encoding': 'identity'})
        with build_opener(SafeRedirect()).open(request, timeout=15) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ReportError('REPORT_TOO_LARGE')
        return data
    except (OSError, ValueError) as exc:
        raise ReportError('REPORT_DOWNLOAD_UNAVAILABLE') from exc


def plain(text):
    s = unicodedata.normalize('NFKD', text.lower()).replace('đ', 'd')
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split())


class FilingRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.cell, self.links = [], None, None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.cells, self.links = [], []
        elif tag == 'td' and self.cells is not None:
            self.cell = ''
        elif tag == 'a' and self.cells is not None:
            self.links.append(attrs.get('href', ''))

    def handle_data(self, text):
        if self.cell is not None:
            self.cell += text

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.cells.append(' '.join(self.cell.split()))
            self.cell = None
        elif tag == 'tr' and self.cells is not None:
            self.rows.append((self.cells, self.links))
            self.cells = None


def parse_vietnam(html, ticker, source_url):
    parser = FilingRows()
    parser.feed(html)
    result = []
    for cells, links in parser.rows:
        if len(cells) < 2:
            continue
        title, period = cells[:2]
        label = plain(title)
        if 'bao cao tai chinh' not in label and 'bctc' not in label:
            continue
        for url in links:
            filename = unquote(urlparse(url).path).upper()
            if not valid_url(url) or not filename.endswith('.PDF'):
                continue
            # Do not attach another issuer's PDF just because it appeared in a feed.
            if not re.search(r'(^|[^A-Z0-9])' + re.escape(ticker) + r'([^A-Z0-9]|$)', filename):
                continue
            year = re.search(r'(20\d{2})', period)
            if not year or int(year[1]) > date.today().year:
                continue
            result.append({'id': hashlib.sha256(url.encode()).hexdigest()[:24], 'ticker': ticker,
                           'title': title, 'period': period, 'year': int(year[1]),
                           'scope': 'consolidated' if 'hop nhat' in label else 'separate',
                           'audited': 'kiem toan' in label, 'annual': period.upper().startswith('CN/'),
                           'url': url, 'source_url': source_url, 'format': 'PDF',
                           'provider': 'CafeF · original issuer filing'})
    return result


def archive_dir(root, market, ticker):
    if market not in ('VN', 'US') or not re.fullmatch(r'[A-Z0-9.-]{1,16}', ticker) or ticker in ('.', '..'):
        raise ReportError('INVALID_MARKET_OR_TICKER')
    return financial_sources.directory(root) / 'reports' / market / ticker


def vietnam_catalog(ticker, year):
    found, errors = {}, []
    # Current-year filings plus the annual base used in the financial dashboard.
    for selected in dict.fromkeys((date.today().year, year)):
        url = f'https://cafef.vn/du-lieu/Ajax/CongTy/BaoCaoTaiChinh.aspx?sym={ticker}&type=1&year={selected}'
        try:
            for row in parse_vietnam(read_public(url).decode('utf-8'), ticker, url):
                found[row['id']] = row
        except (ReportError, UnicodeError) as exc:
            errors.append(str(exc))
    # Issuer-published alternative for a broken CafeF annual-filing attachment.
    # This document contains FPT's audited consolidated statements and notes.
    if ticker == 'FPT' and year == 2025:
        url = 'https://bctn2025.fpt.com/wp-content/uploads/2026/04/BCTN-2025.pdf'
        identity = hashlib.sha256(url.encode()).hexdigest()[:24]
        found[identity] = {'id': identity, 'ticker': ticker,
            'title': 'Báo cáo thường niên 2025 · BCTC hợp nhất kiểm toán và thuyết minh',
            'period': 'CN/2025', 'year': 2025, 'scope': 'consolidated', 'audited': True,
            'annual': True, 'url': url, 'source_url': 'https://bctn2025.fpt.com/',
            'format': 'PDF', 'provider': 'FPT · issuer website', 'primary_source': True}
    return list(found.values()), errors


def sec_catalog(root, ticker):
    agent, _ = financial_sources.settings(root)
    if not financial_sources.valid_agent(agent):
        raise ReportError('SEC_USER_AGENT_NOT_CONFIGURED')
    try:
        cik, _ = sec_filings.ticker_cik(ticker, agent)
        data = sec_filings.fetch_json(f'https://data.sec.gov/submissions/CIK{cik:010d}.json', agent)
    except sec_filings.FilingUnavailable as exc:
        raise ReportError(exc.reason) from exc
    if str(data.get('cik', '')).lstrip('0') != str(cik):
        raise ReportError('SEC_ISSUER_MISMATCH')
    recent = data.get('filings', {}).get('recent', {})
    result = []
    for i, form in enumerate(recent.get('form', [])):
        if form not in ('10-K', '10-K/A', '10-Q', '20-F'):
            continue
        try:
            accn, document = recent['accessionNumber'][i], recent['primaryDocument'][i]
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accn) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.html?', document):
                continue
            end, filed = recent['reportDate'][i], recent['filingDate'][i]
            if date.fromisoformat(filed) > date.today():
                continue
            url = f'https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace("-", "")}/{document}'
            result.append({'id': hashlib.sha256(url.encode()).hexdigest()[:24], 'ticker': ticker,
                           'title': form + ' · ' + end, 'period': end, 'year': int(end[:4]),
                           'annual': form in ('10-K', '10-K/A', '20-F'), 'scope': 'issuer filing',
                           'url': url, 'source_url': url, 'format': 'HTML', 'provider': 'SEC',
                           'filed': filed, 'download_status': 'SOURCE_LINK'})
        except (IndexError, KeyError, TypeError, ValueError):
            continue
        if len(result) == 12:
            break
    return result, []


def save_pdf(directory, row):
    path = directory / (row['id'] + '.pdf')
    if path.is_file() and path.read_bytes()[:5] == b'%PDF-':
        row.update(download_status='SAVED', bytes=path.stat().st_size)
        return path
    if row.get('format') != 'PDF':
        raise ReportError('ORIGINAL_FORMAT_IS_HTML')
    data = read_public(row['url'], MAX_PDF)
    if not data.startswith(b'%PDF-'):
        raise ReportError('INVALID_PDF_RESPONSE')
    directory.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_bytes(data)
    os.replace(temp, path)
    row.update(download_status='SAVED', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
               downloaded_at=datetime.now(timezone.utc).isoformat())
    return path


def catalog(root, ticker, market, year=None, refresh=False):
    ticker = ticker.upper()
    directory = archive_dir(root, market, ticker)
    year = int(year or date.today().year - 1)
    if not 1990 <= year <= date.today().year:
        raise ReportError('INVALID_REPORT_YEAR')
    path = directory / 'catalog.json'
    with LOCKS[hash(str(directory)) % len(LOCKS)]:
        old = None
        try:
            old = json.loads(path.read_text(encoding='utf-8'))
            if old.get('ticker') != ticker or old.get('market') != market:
                old = None
        except (OSError, ValueError):
            pass
        age = time.time() - old.get('timestamp', 0) if old else float('inf')
        if old and age < (60 if refresh else TTL) and old.get('requested_year') == year:
            return old
        rows, warnings = vietnam_catalog(ticker, year) if market == 'VN' else sec_catalog(root, ticker)
        if not rows and old:
            return {**old, 'warnings': warnings + ['REPORT_CATALOG_REFRESH_UNAVAILABLE'], 'stale': True}
        # Download the newest consolidated filing and matching audited annual report.
        consolidated = [r for r in rows if r['scope'] == 'consolidated']
        annuals = [r for r in consolidated if r['annual'] and r['audited'] and r['year'] == year]
        annual = next((r for r in annuals if r.get('primary_source')), annuals[0] if annuals else None)
        selected = {r['id'] for r in [consolidated[0] if consolidated else None, annual] if r}
        for row in rows:
            row.setdefault('download_status', 'AVAILABLE')
            if row['id'] in selected:
                try:
                    save_pdf(directory, row)
                except ReportError as exc:
                    row.update(download_status='UNAVAILABLE', download_error=str(exc))
        result = {'version': 1, 'ticker': ticker, 'market': market, 'requested_year': year,
                  'reports': rows, 'warnings': warnings, 'timestamp': time.time()}
        financial_sources.atomic_json(path, result)
        return result


def download(root, ticker, market, identity):
    directory = archive_dir(root, market, ticker.upper())
    if not re.fullmatch(r'[a-f0-9]{24}', identity):
        raise ReportError('REPORT_NOT_FOUND')
    with LOCKS[hash(str(directory)) % len(LOCKS)]:
        try:
            data = json.loads((directory / 'catalog.json').read_text(encoding='utf-8'))
            row = next(r for r in data['reports'] if r['id'] == identity and r['ticker'] == ticker.upper())
        except (OSError, ValueError, KeyError, StopIteration):
            raise ReportError('REPORT_NOT_FOUND')
        path = save_pdf(directory, row)
        financial_sources.atomic_json(directory / 'catalog.json', data)
        return path, row
