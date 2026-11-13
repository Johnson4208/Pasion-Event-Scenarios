"""Local source configuration; public catalog never exposes the SEC contact."""
import json
import os
import re
import tempfile
from pathlib import Path

def directory(root):
    return Path(root) / 'private-financial-sources'

def settings(root):
    env = os.environ.get('PASION_SEC_USER_AGENT', '').strip()
    if env:
        return env, 'environment'
    try:
        data = json.loads((directory(root) / 'config.json').read_text(encoding='utf-8'))
        agent = data.get('sec_user_agent', '')
        return (agent, 'local') if valid_agent(agent) else ('', 'none')
    except (OSError, ValueError, TypeError, AttributeError):
        return '', 'none'

def valid_agent(value):
    return (isinstance(value, str) and len(value) <= 180 and
            all(32 <= ord(c) < 127 for c in value) and
            re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) is not None)

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def configure(root, email):
    if not isinstance(email, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()):
        raise ValueError('Enter a valid contact email.')
    agent = 'Pasion Research ' + email.strip()
    if not valid_agent(agent):
        raise ValueError('Use an ASCII contact email of at most 160 characters.')
    if os.environ.get('PASION_SEC_USER_AGENT', '').strip():
        raise ValueError('SEC is configured by PASION_SEC_USER_AGENT. Update that environment variable instead.')
    atomic_json(directory(root) / 'config.json', {'sec_user_agent': agent})

def catalog(root, can_configure=False):
    agent, origin = settings(root)
    return {'version': 1, 'can_configure': can_configure,
            'sec_configured': valid_agent(agent), 'configuration_origin': origin,
            'sources': [
                {'id': 'cafef', 'market': 'VN', 'kind': 'PUBLIC_FINANCIAL_SNAPSHOTS', 'url': 'https://cafef.vn/du-lieu/'},
                {'id': 'sec', 'market': 'US', 'kind': 'API', 'url': 'https://www.sec.gov/search-filings/edgar-application-programming-interfaces'},
                {'id': 'ssc', 'market': 'VN', 'kind': 'OFFICIAL_DOCUMENTS', 'url': 'https://congbothongtin.ssc.gov.vn/'},
                {'id': 'hnx', 'market': 'VN', 'kind': 'OFFICIAL_DOCUMENTS', 'url': 'https://hnx.vn/'},
                {'id': 'fiingroup', 'market': 'VN', 'kind': 'EXTERNAL_SERVICE_NOT_CONNECTED', 'url': 'https://dff.fiingroup.vn/ApiDataFeed?lang=vi-vn'}]}
