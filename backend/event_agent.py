"""Standalone PUBLIC event-intelligence poller, isolated from user memory.

Run: python backend/event_agent.py --once
Or:  python backend/event_agent.py --interval-minutes 30
Never imports server, sessions, accounts, portfolio or personal data.
"""
import argparse
import os
import sys
import time
import uuid
from datetime import datetime,timezone
import event_agent_store as store
import event_news_preview as research

def tick():
    store.init()
    identifier=str(uuid.uuid4())
    if not store.lease(identifier,time.time()):
        print("Another event intelligence poller holds the active lease.",flush=True)
        return 0
    count=0
    try:
        for watch in store.watches():
            now=datetime.now(timezone.utc).isoformat()
            try:
                # Historical engine's short cache does not replace durable
                # agent snapshots. Cache expiration controlled by 15m TTL.
                result=research.analyze(watch["category"],watch["factor"],watch["focus"],watch["horizon"])
                revision=store.write_result(watch["id"],result,now)
                print(f'{watch["category"]} / {watch["factor"]} / {watch["focus"]}: {result.get("status")}; version {revision}',flush=True)
            except (research.Unavailable,ValueError,OSError,TimeoutError,ArithmeticError) as exc:
                store.write_failure(watch["id"],type(exc).__name__+":"+str(exc)[:80],now)
                print(f'{watch["factor"]}: FETCH_FAILED ({type(exc).__name__})',flush=True)
            count+=1
    finally:store.unlease(identifier)
    return count

def main():
    parser=argparse.ArgumentParser(description="Independent public-event research scheduler")
    parser.add_argument("--once",action="store_true",help="Run one complete watchlist scan and exit")
    parser.add_argument("--interval-minutes",type=int,default=30,help="Polling cadence, 15–1440 minutes")
    args=parser.parse_args()
    if not 15<=args.interval_minutes<=1440:parser.error("Interval must be between 15 and 1440 minutes")
    if args.once:
        tick()
        return
    print("PASION Event Intelligence Agent started. Database:",store.location(),flush=True)
    while True:
        tick()
        time.sleep(args.interval_minutes*60)

if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:sys.exit(0)
