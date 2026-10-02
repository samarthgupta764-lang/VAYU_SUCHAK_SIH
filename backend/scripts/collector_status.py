"""
Collector status — scripts/collector_status.py

    python -m scripts.collector_status

Shows how the daily fare collector is doing: last few runs, quotes in the
database, per-carrier / per-window coverage, and how many distinct collection
days you have (the 30-day back-test needs 30).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date

from config import settings
from pipeline.quotes import fetch_quotes, quote_stats


def _runs(limit: int = 7) -> list[dict]:
    path = settings.sqlite_path
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _distinct_collection_days() -> list[str]:
    path = settings.sqlite_path
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT collected_date FROM fare_quotes ORDER BY collected_date"
        ).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def main() -> None:
    s = quote_stats()
    days = _distinct_collection_days()
    n_days = len(days)

    print("\n  VAYU-SUCHAK · collector status\n  " + "-" * 46)
    print(f"  fare quotes in DB   : {s.get('total', 0):,}")
    print(f"  routes / carriers   : {s.get('routes', 0)} / {s.get('carriers', 0)}")
    print(f"  collection days     : {n_days}"
          + (f"  ({days[0]} … {days[-1]})" if days else "")
          + f"   [30-day back-test: {min(n_days, 30)}/30]")

    recent = fetch_quotes(limit=20000)
    today = date.today().isoformat()
    todays = [r for r in recent if r["collected_date"] == today]
    if todays:
        by_src = Counter(r["source"] for r in todays)
        by_car = Counter(r["carrier"] for r in todays)
        by_apw = Counter(r["apw_bucket"] for r in todays)
        print(f"\n  today ({today}): {len(todays)} quotes")
        print("    sources :  " + "  ".join(f"{k}:{v}" for k, v in by_src.most_common()))
        print("    carriers:  " + "  ".join(f"{k}:{v}" for k, v in by_car.most_common()))
        print("    windows :  " + "  ".join(f"{k}:{v}" for k, v in sorted(by_apw.items(), key=str)))
    else:
        print(f"\n  no quotes collected today ({today}) yet")

    runs = _runs()
    if runs:
        print("\n  recent runs")
        for r in runs:
            print(f"    {str(r['started_at'])[:16]}  {r.get('status', '?'):8} "
                  f"{r.get('quotes_written', 0):>5} quotes  "
                  f"{r.get('routes_count', 0)} routes  ({r.get('trigger', '?')})")
    print()


if __name__ == "__main__":
    main()
