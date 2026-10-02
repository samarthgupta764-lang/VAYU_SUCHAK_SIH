"""
One collection cycle — scripts/collect.py

For every route in the basket, scrape fares for each advance-purchase window
(T+1 … T+45 from today), tag them, and write them to the `fare_quotes`
database. Logs one `collection_runs` row.

This is the unit the daily scheduler (Phase 1) will call. Run it by hand now to
seed the database and to accumulate the back-test history.

    python -m scripts.collect                       # full basket, live
    python -m scripts.collect --routes DEL-BOM,BLR-DEL
    python -m scripts.collect --mode cache          # from the on-disk cache
    python -m scripts.collect --windows 7,30        # subset of APW windows
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import date, datetime, timezone

from config import settings
from pipeline import festival
from pipeline.apw import target_departure_dates
from pipeline.geo import is_domestic_carrier
from pipeline.scrape import cache as cache_mod
from pipeline.scrape.pool import scrape_pool
from pipeline.scrape.travelpayouts import TravelpayoutsError
from pipeline.scrape.travelpayouts import fetch as tp_fetch
from pipeline.quotes import record_collection_run, store_quotes


def _basket() -> list[str]:
    """The index basket — routes with a 2022 base price in base_year_reference.json
    (16 metro pairs / 32 directed routes). Every collected route is in the index."""
    from pipeline.base_reference import basket_routes
    return basket_routes() or settings.collection_route_list


async def _collect_route(
    route: str, days: list[date], mode: str, skip: set[str]
) -> tuple[list, dict]:
    if mode == "cache":
        recs, _ = cache_mod.newest_any(route)
        want = {d.isoformat() for d in days}
        recs = [r for r in recs if str(r.departure_ts)[:10] in want]
        summary = {"cache": {"status": "ok", "fares": len(recs)}}
    else:
        pool = await scrape_pool(route, days, skip=skip)
        recs = list(pool.records)
        summary = {s.source: {"status": s.status, "fares": s.fares,
                              "latency_ms": s.latency_ms} for s in pool.statuses}

        # tier-1 fallback: a thin route -> top it up from Travelpayouts (feature 1.15)
        if settings.travelpayouts_enabled and len(recs) < settings.collection_tp_floor:
            try:
                tp_recs, tp_note = await tp_fetch(route, days)
                recs.extend(tp_recs)
                summary["travelpayouts"] = {"status": "ok", "fares": len(tp_recs)}
            except TravelpayoutsError as exc:
                summary["travelpayouts"] = {"status": "error", "fares": 0, "detail": str(exc)}

    # domestic airfare index — drop foreign-carrier routings Google Flights mixes in
    recs = [r for r in recs if is_domestic_carrier(r.airline)]
    recs, _, _ = festival.flag(recs, window_days=settings.festival_window_days)
    return recs, summary


async def run(
    routes: list[str], windows: tuple[int, ...], mode: str,
    *, trigger: str = "manual", skip: set[str] | None = None,
) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    skip = skip or set()
    days = sorted(set(target_departure_dates(date.today(), windows).values()))
    print(f"\n=== {started.isoformat(timespec='seconds')} · collection {run_id[:8]} · "
          f"{len(routes)} routes · windows {list(windows)} · mode={mode}"
          + (f" · skip {sorted(skip)}" if skip else "") + " ===", flush=True)

    sem = asyncio.Semaphore(settings.collection_concurrency)
    written = seen = 0
    done = 0
    all_summary: dict = {}
    status = "ok"

    async def _one(route: str):
        nonlocal written, seen, done, status
        async with sem:
            try:
                recs, summary = await _collect_route(route, days, mode, skip)
            except Exception as exc:  # noqa: BLE001 — one route must not kill the cycle
                done += 1
                print(f"  [{done}/{len(routes)}] {route:<9} ERROR {type(exc).__name__}: {exc}", flush=True)
                status = "partial"
                return
        n = store_quotes(recs, collection_run_id=run_id)
        written += n
        seen += len(recs)
        for k, v in summary.items():
            agg = all_summary.setdefault(k, {"fares": 0})
            agg["fares"] += v.get("fares", 0)
            agg["status"] = v.get("status", agg.get("status"))
        by_apw: dict[str, int] = {}
        for r in recs:
            by_apw[r.apw_bucket or "—"] = by_apw.get(r.apw_bucket or "—", 0) + 1
        done += 1
        print(f"  [{done}/{len(routes)}] {route:<9} {n:>4} quotes  "
              + " ".join(f"{k}:{v}" for k, v in sorted(by_apw.items())), flush=True)

    await asyncio.gather(*(_one(r) for r in routes))

    finished = datetime.now(timezone.utc)
    record_collection_run({
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "trigger": trigger,
        "routes_count": len(routes),
        "apw_windows": list(windows),
        "quotes_written": written,
        "quotes_seen": seen,
        "sources_summary": all_summary,
        "status": status if written else "failed",
    })
    dur = (finished - started).total_seconds()
    print(f"\n{written} quotes written ({seen} seen) in {dur / 60:.1f} min · "
          f"sources {json.dumps(all_summary)}", flush=True)
    return {"run_id": run_id, "written": written}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", default=None, help="comma list; default = week-1 basket")
    ap.add_argument("--windows", default=None, help="comma list of days; default 1,7,15,30,45")
    ap.add_argument("--mode", choices=["auto", "live", "cache"], default="auto")
    ap.add_argument("--trigger", default="manual", help="scheduled | manual | api")
    ap.add_argument("--all-sources", action="store_true",
                    help="include the sources the scheduled run skips (e.g. Cleartrip)")
    args = ap.parse_args()

    routes = [r.strip().upper() for r in args.routes.split(",")] if args.routes else _basket()
    windows = (tuple(int(w) for w in args.windows.split(",")) if args.windows
               else settings.apw_window_list)
    skip = set() if args.all_sources else {
        s.strip() for s in settings.collection_skip_sources.split(",") if s.strip()
    }
    asyncio.run(run(routes, windows, args.mode, trigger=args.trigger, skip=skip))


if __name__ == "__main__":
    main()
