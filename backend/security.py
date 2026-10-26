"""F01 policies and owner-scoped persistence; no client-supplied owner authority."""
import json
import time


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY, occurred_at REAL NOT NULL, actor TEXT, action TEXT NOT NULL, status INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS owned_data (owner TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE, namespace TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner, namespace, key))')


def permissions(is_admin):
    return {'research.read': True, 'portfolio.own': True,
            'finance.ingest': is_admin, 'documents.admin': is_admin,
            'distribution.admin': is_admin}


def route_policy(path):
    if path == '/api/admin' or path.startswith('/api/admin/'):
        return 'admin'
    if path == '/api/finance' or path.startswith('/api/finance/'):
        return 'admin'
    for prefix in ('/api/research', '/api/portfolio', '/api/trades'):
        if path == prefix or path.startswith(prefix + '/'):
            return 'member'
    return None


def audit(db, actor, action, status):
    # Only server-selected action names: never request bodies, cookies or query strings.
    db.execute('INSERT INTO audit_events (occurred_at, actor, action, status) VALUES (?, ?, ?, ?)',
               (time.time(), actor, action, status))


def put_owned(db, session, namespace, key, payload):
    owner = session['email'].casefold()
    db.execute('INSERT INTO owned_data VALUES (?, ?, ?, ?) ON CONFLICT(owner, namespace, key) DO UPDATE SET payload=excluded.payload',
               (owner, namespace, key, json.dumps(payload)))


def get_owned(db, session, namespace, key):
    row = db.execute('SELECT payload FROM owned_data WHERE owner=? AND namespace=? AND key=?',
                     (session['email'].casefold(), namespace, key)).fetchone()
    return json.loads(row[0]) if row else None
