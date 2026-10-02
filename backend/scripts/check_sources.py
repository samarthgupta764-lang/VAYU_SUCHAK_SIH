"""
Scraper health check — run this before a demo.

Hits every adapter live for one route/date and prints a status table. Never
raises; a source that is blocked / robots-disallowed / recon-pending is reported,
not treated as a failure. This is how you know, on the day, which sources are
contributing live vs from cache.

    python -m scripts.check_sources
    python -m scripts.check_sources --corridor BLR-DEL --days 2
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta

from pipeline.scrape.base import get_adapters


async def check(corridor: str, n_days: int) -> None:
    start = date.today() + timedelta(days=14)
    days = [start + timedelta(days=i) for i in range(n_days)]
    adapters = get_adapters()

    print(f"\n  route {corridor}  ·  {days[0]} … {days[-1]}  ·  {len(adapters)} adapters\n")
    print(f"  {'source':<14} {'status':<12} {'fares':>6}  {'path':<5} detail")
    print("  " + "-" * 78)

    async def run(a):
        try:
            return a.name, await asyncio.wait_for(a.scrape(corridor, days), timeout=150)
        except asyncio.TimeoutError:
            return a.name, None

    results = await asyncio.gather(*(run(a) for a in adapters))
    live = degraded = 0
    for name, out in results:
        if out is None:
            print(f"  {name:<14} {'timeout':<12} {'—':>6}")
            degraded += 1
            continue
        s = out.status
        mark = "✓" if s.status == "ok" else " "
        print(f"  {name:<14} {s.status:<12} {len(out.records):>6}  {s.extraction_path:<5} {s.detail[:44]} {mark}")
        if s.status == "ok":
            live += 1
        else:
            degraded += 1

    print("  " + "-" * 78)
    print(f"  {live} live · {degraded} degraded/unavailable "
          f"(the pipeline runs on any 1 live source + Travelpayouts + cache)\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridor", default="DEL-BOM")
    ap.add_argument("--days", type=int, default=1)
    args = ap.parse_args()
    asyncio.run(check(args.corridor.upper(), args.days))


if __name__ == "__main__":
    main()
