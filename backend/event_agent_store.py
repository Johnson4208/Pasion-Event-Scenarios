"""Isolated, auditable event-intelligence memory.

Only PUBLIC research configurations and source snapshots go in this SQLite DB.
No account, email, personal memory, trade, session, or portfolio tables.
The API reads it with SQLite mode=ro; the independent agent owns all writes.
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime,timezone,timedelta
from pathlib import Path

VERSION="event-agent-store-v1"
DEFAULT_PATH=Path(__file__).resolve().parents[1]/"event-agent-state"/"intelligence.sqlite3"
WATCHES=[
 ("Economy","Inflation","World","30 days"),
 ("Economy","Inflation","Vietnam","30 days"),
 ("Economy","Inflation","United States","180 days"),
 ("Economy","GDP growth","Asia","180 days"),
 ("Energy","Oil supply","World","30 days"),
 ("Energy","Oil supply","Asia","180 days"),
 ("Geopolitics","Conflict risk","Asia","30 days"),
 ("Geopolitics","Conflict risk","World","180 days"),
 ("Banking & Credit","Central bank policy","United States","30 days"),
 ("Technology","Semiconductor supply","Asia","180 days"),
]

def location():
    raw=os.environ.get("PASION_EVENT_AGENT_DB")
    path=Path(raw).expanduser().resolve() if raw else DEFAULT_PATH.resolve()
    if path.name in ("accounts.sqlite3","finance.sqlite3","documents.sqlite3"):
        raise ValueError("Event agent data may not share a main application database.")
    return path

def key(category,factor,focus,horizon):
    return hashlib.sha256(json.dumps([category,factor,focus.casefold().strip(),horizon],ensure_ascii=False).encode()).hexdigest()[:24]

def connect(write=False):
    path=location()
    if write:path.parent.mkdir(parents=True,exist_ok=True)
    elif not path.is_file():return None
    db=sqlite3.connect(str(path) if write else path.as_uri()+"?mode=ro",uri=not write,timeout=8)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA busy_timeout=8000")
    if write:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
    return db

def init():
    with connect(True) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS watches(
          id TEXT PRIMARY KEY,category TEXT NOT NULL,factor TEXT NOT NULL,
          focus TEXT NOT NULL,horizon TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,UNIQUE(category,factor,focus,horizon));
        CREATE TABLE IF NOT EXISTS versions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,watch_id TEXT NOT NULL REFERENCES watches(id),
          created_at TEXT NOT NULL,content_hash TEXT NOT NULL,
          snapshot_json TEXT NOT NULL,change_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS versions_watch ON versions(watch_id,id DESC);
        CREATE TABLE IF NOT EXISTS polls(
          id INTEGER PRIMARY KEY AUTOINCREMENT,watch_id TEXT NOT NULL REFERENCES watches(id),
          checked_at TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,
          version_id INTEGER);
        CREATE INDEX IF NOT EXISTS polls_watch ON polls(watch_id,id DESC);
        CREATE TABLE IF NOT EXISTS lease(
          name TEXT PRIMARY KEY,holder TEXT NOT NULL,until_epoch REAL NOT NULL);
        """)
        for category,factor,focus,horizon in WATCHES:
            add(db,category,factor,focus,horizon)

def add(db,category,factor,focus,horizon):
    import event_news_preview as preview
    if factor not in preview._TOPICS.get(category,{}):raise ValueError("Unsupported event factor")
    if horizon not in ("7 days","30 days","90 days","180 days"):raise ValueError("Invalid horizon")
    import event_feed_sources as feeds
    feeds.geography(focus)
    if not isinstance(focus,str) or not focus.strip():raise ValueError("Focus required")
    ident=key(category,factor,focus,horizon)
    db.execute("""INSERT OR IGNORE INTO watches(id,category,factor,focus,horizon,created_at)
       VALUES(?,?,?,?,?,?)""",(ident,category,factor,focus,horizon,datetime.now(timezone.utc).isoformat()))
    return ident

def watches():
    db=connect(False)
    if db is None:return []
    try:return [dict(x) for x in db.execute("SELECT * FROM watches WHERE enabled=1 ORDER BY category,factor,focus,horizon")]
    finally:db.close()

def lease(holder,now):
    with connect(True) as db:
        db.execute("DELETE FROM lease WHERE name='poller' AND until_epoch<?",(now,))
        changed=db.execute("INSERT OR IGNORE INTO lease VALUES ('poller',?,?)",(holder,now+900))
        return changed.rowcount==1

def unlease(holder):
    with connect(True) as db:db.execute("DELETE FROM lease WHERE name='poller' AND holder=?",(holder,))

def _signature(result):
    # A changed wall clock or ordinary recency decay is NOT new evidence.
    # Source-title, URL, timestamp and direction changes do create a revision.
    items=sorted([(x.get("id"),x.get("title"),x.get("url"),x.get("published_at"),x.get("direction"))
                  for x in result.get("items",[])],key=lambda x:str(x))
    return hashlib.sha256(json.dumps(items,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def _movement(before,after):
    prior={x["id"]:x for x in (before or {}).get("dynamic_scenarios",{}).get("ranked_scenarios",[])}
    current=after.get("dynamic_scenarios",{}).get("ranked_scenarios",[])
    earlier={x.get("id") for x in (before or {}).get("items",[])}
    present={x.get("id") for x in after.get("items",[])}
    return {"added_source_ids":sorted(present-earlier),"removed_source_ids":sorted(earlier-present),
            "scenario_changes":[{"id":s["id"],"previous_rank":prior.get(s["id"],{}).get("rank"),
             "current_rank":s["rank"],"previous_support_index":prior.get(s["id"],{}).get("support_index"),
             "current_support_index":s.get("support_index")} for s in current],
            "change_type":"INITIAL_SNAPSHOT" if before is None else "SOURCE_EVIDENCE_REVISION"}

def write_result(watch_id,result,checked_at):
    """Append immutable revision only when the actual source snapshot changes."""
    with connect(True) as db:
        known=db.execute("SELECT id FROM watches WHERE id=?",(watch_id,)).fetchone()
        if not known:raise ValueError("Watch must be pre-registered by agent")
        if result.get("status")!="EVIDENCE_AVAILABLE":
            db.execute("INSERT INTO polls(watch_id,checked_at,status,reason) VALUES(?,?,?,?)",
                       (watch_id,checked_at,"INSUFFICIENT_EVIDENCE",str(result.get("reason_code","UNKNOWN"))[:120]))
            return None
        prev=db.execute("SELECT id,content_hash,snapshot_json FROM versions WHERE watch_id=? ORDER BY id DESC LIMIT 1",(watch_id,)).fetchone()
        digest=_signature(result)
        if prev and digest==prev["content_hash"]:
            db.execute("INSERT INTO polls(watch_id,checked_at,status,version_id) VALUES(?,?,?,?)",
                       (watch_id,checked_at,"UNCHANGED",prev["id"]))
            return prev["id"]
        previous=json.loads(prev["snapshot_json"]) if prev else None
        change=_movement(previous,result)
        # Snapshots are public research only: aggressively whitelist persisted fields.
        safe={name:result.get(name) for name in ("version","status","category","factor","focus","horizon",
             "outcomes","items","source_count","coverage","generated_at","model","probability_status",
             "bayesian_forecast","dynamic_scenarios")}
        cur=db.execute("""INSERT INTO versions(watch_id,created_at,content_hash,snapshot_json,change_json)
                     VALUES(?,?,?,?,?)""",(watch_id,checked_at,digest,json.dumps(safe,ensure_ascii=False),
                                          json.dumps(change,ensure_ascii=False)))
        db.execute("INSERT INTO polls(watch_id,checked_at,status,version_id) VALUES(?,?,?,?)",
                   (watch_id,checked_at,"NEW_REVISION",cur.lastrowid))
        return cur.lastrowid

def write_failure(watch_id,reason,checked_at):
    with connect(True) as db:
        db.execute("INSERT INTO polls(watch_id,checked_at,status,reason) VALUES(?,?,?,?)",
                   (watch_id,checked_at,"FETCH_FAILED",str(reason)[:120]))

def read(category,factor,focus,horizon,limit=12):
    """Read-only consumer; never initializes, migrates or writes the agent DB."""
    ident=key(category,factor,focus,horizon)
    try:db=connect(False)
    except (sqlite3.Error,OSError):db=None
    if db is None:return {"status":"AGENT_NOT_INITIALIZED","watch":None,"latest":None,"versions":[]}
    try:
        watch=db.execute("SELECT * FROM watches WHERE id=?",(ident,)).fetchone()
        if not watch:return {"status":"WATCH_NOT_CONFIGURED","watch":None,"latest":None,"versions":[]}
        poll=db.execute("SELECT checked_at,status,reason FROM polls WHERE watch_id=? ORDER BY id DESC LIMIT 1",(ident,)).fetchone()
        rows=db.execute("SELECT id,created_at,snapshot_json,change_json FROM versions WHERE watch_id=? ORDER BY id DESC LIMIT ?",(ident,min(25,max(1,int(limit))))).fetchall()
        versions=[{"id":x["id"],"created_at":x["created_at"],"snapshot":json.loads(x["snapshot_json"]),
          "changes":json.loads(x["change_json"])} for x in rows]
        return {"status":"TRACKING" if poll else "WAITING_FOR_FIRST_POLL",
                "watch":dict(watch),"last_poll":dict(poll) if poll else None,
                "latest":versions[0] if versions else None,
                "versions":versions,
                "data_scope":"PUBLIC_EVENT_INTELLIGENCE_ONLY",
                "storage_version":VERSION}
    except (sqlite3.Error,ValueError,KeyError) as exc:
        return {"status":"AGENT_STORAGE_UNAVAILABLE","watch":None,"latest":None,"versions":[]}
    finally:db.close()
