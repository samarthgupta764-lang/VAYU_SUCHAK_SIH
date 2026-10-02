"""
Off-peak cache warmer / scheduler  (feature-list 1.12).

Runs the live scraper pool across a set of corridors and a forward date window,
writing real fare snapshots to data/cache/. This is the demo-safety net: run it
before a presentation and the pipeline serves genuine recently-scraped fares
even if every source is blocked on stage — the fallback chain drops to these
snapshots and the index doesn't flinch.

    python -m scripts.warm_cache                        # one pass, default corridors
    python -m scripts.warm_cache --corridors DEL-BOM,BOM-BLR --days 3 --offset 14
    python -m scripts.warm_cache --daemon --every 6h    # APScheduler, keeps warming

Rate limiting + robots.txt are enforced by the adapters, so this is polite by
construction. Only the robots-permitted live sources (Cleartrip, Google Flights
today) actually hit the network; disabled/stub sources are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date, timedelta

from config import REPO_ROOT, settings
from pipeline.scrape.cache import write as cache_write
from pipeline.scrape.pool import scrape_pool

DEFAULT_CORRIDORS = ["DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", "BOM-BLR", "DEL-CCU", "DEL-HYD"]


def _load_corridors() -> list[str]:
    try:
        ref = json.loads(settings.base_reference.read_text())["routes"]
        return [c for c in DEFAULT_CORRIDORS if c in ref] or list(ref)[:8]
    except Exception:  # noqa: BLE001
        return DEFAULT_CORRIDORS


async def warm(corridors: list[str], days: int, offset: int, fresh: bool = False) -> dict:
    start = date.today() + timedelta(days=offset)
    window = [start + timedelta(days=i) for i in range(days)]
    summary: dict[str, dict] = {}

    for corridor in corridors:
        if fresh:
            for old in settings.cache_path.glob(f"*__{corridor.upper()}__*.json"):
                old.unlink()
        pool = await scrape_pool(corridor, window)
        live = {s.source: s.fares for s in pool.statuses if s.status == "ok"}
        # scrape_pool already writes per-source snapshots for sources that returned
        # fares; record what happened
        summary[corridor] = {
            "fares": len(pool.records),
            "live_sources": live,
            "degraded": pool.sources_degraded,
        }
        tag = ", ".join(f"{k}:{v}" for k, v in live.items()) or "none live"
        print(f"  {corridor:9} {len(pool.records):>4} fares  [{tag}]")

    return summary


def _parse_every(v: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([hm]?)", v.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError("use e.g. 6h or 90m")
    n = int(m.group(1))
    return n * 3600 if m.group(2) != "m" else n * 60


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridors", default=None, help="comma list; default = demo set")
    ap.add_argument("--days", type=int, default=3, help="date-window width")
    ap.add_argument("--offset", type=int, default=14, help="days ahead the window starts")
    ap.add_argument("--fresh", action="store_true", help="clear a corridor's old snapshots before scraping (no seed/real mixing)")
    ap.add_argument("--daemon", action="store_true", help="keep running on a schedule")
    ap.add_argument("--every", type=_parse_every, default=_parse_every("6h"))
    args = ap.parse_args()

    corridors = (
        [c.strip().upper() for c in args.corridors.split(",")]
        if args.corridors else _load_corridors()
    )

    async def one_pass():
        print(f"warming {len(corridors)} corridors · +{args.offset}d..+{args.offset + args.days}d")
        s = await warm(corridors, args.days, args.offset, fresh=args.fresh)
        total = sum(v["fares"] for v in s.values())
        print(f"done · {total} fares cached across {len(corridors)} corridors\n")

    if not args.daemon:
        asyncio.run(one_pass())
        return

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("apscheduler not installed — running a single pass instead")
        asyncio.run(one_pass())
        return

    sched = BlockingScheduler()
    sched.add_job(lambda: asyncio.run(one_pass()), "interval", seconds=args.every, next_run_time=None)
    asyncio.run(one_pass())  # warm immediately, then on the interval
    print(f"scheduler armed — every {args.every}s. Ctrl+C to stop.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nstopped.")


if __name__ == "__main__":
    main()
