"""
Acquisition entry point + 3-tier fallback chain — pipeline/ingest.py

    fetch_fares(corridor, days, mode=...) -> IngestResult

Tier 0  live scrape pool          (the differentiator)
Tier 1  Travelpayouts data API    (a route is blocked / empty)
Tier 2  newest on-disk cache      (fully offline)

Every record and the run itself is tagged with `ingestion_source`. The chain
never raises for a recoverable condition — worst case it returns whatever the
cache holds with `ingestion_source="cache"` and `degraded=True`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from config import settings
from pipeline.contract import FareRecord, dedupe
from pipeline.scrape import cache
from pipeline.scrape.pool import OnSourceDone, PoolResult, scrape_pool
from pipeline.scrape.travelpayouts import TravelpayoutsError, fetch as tp_fetch

Mode = Literal["auto", "live", "cache"]


@dataclass
class IngestResult:
    records: list[FareRecord]
    ingestion_source: str                     # dominant tier used
    tiers_used: list[str] = field(default_factory=list)
    pool: PoolResult | None = None
    notes: list[str] = field(default_factory=list)
    degraded: bool = False

    def summary(self) -> str:
        return (
            f"{len(self.records)} fares · tier={self.ingestion_source}"
            + (f" · via {'+'.join(self.tiers_used)}" if self.tiers_used else "")
        )

    def to_dict(self) -> dict:
        return {
            "records": len(self.records),
            "ingestion_source": self.ingestion_source,
            "tiers_used": self.tiers_used,
            "degraded": self.degraded,
            "notes": self.notes,
            "pool": self.pool.to_dict() if self.pool else None,
        }


def _dep_date(ts: str | None) -> date | None:
    """Departure calendar date from an ISO timestamp; None if unparseable."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).date()
    except ValueError:
        try:
            return datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _within_window(
    records: list[FareRecord], start: date, end: date
) -> tuple[list[FareRecord], int]:
    """
    Keep only fares that depart inside [start, end]. Records with no parseable
    departure date are kept (conservative) rather than silently dropped.
    -> (kept, dropped_count)
    """
    kept: list[FareRecord] = []
    dropped = 0
    for r in records:
        d = _dep_date(r.departure_ts)
        if d is None or start <= d <= end:
            kept.append(r)
        else:
            dropped += 1
    return kept, dropped


async def fetch_fares(
    corridor: str, start: date, end: date, *, mode: Mode = "auto",
    on_source_done: OnSourceDone | None = None,
) -> IngestResult:
    corridor = corridor.upper()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    notes: list[str] = []
    tiers: list[str] = []

    # ---- Tier 2 only -------------------------------------------------------
    if mode == "cache":
        recs, stamps = cache.newest_any(corridor)
        held = len(recs)
        recs, _ = _within_window(recs, start, end)
        return IngestResult(
            records=recs,
            ingestion_source="cache",
            tiers_used=["cache"],
            notes=[
                f"cache-only mode · sources {sorted(stamps)}",
                f"window {start.isoformat()}..{end.isoformat()} · "
                f"{len(recs)}/{held} cached fares depart in range",
            ],
            degraded=not recs,
        )

    floor = settings.ingest_min_fares

    # ---- Tier 0 · live scrape pool --------------------------------------
    pool: PoolResult | None = None
    records: list[FareRecord] = []
    if mode in ("auto", "live"):
        # a monthly CPI input doesn't need every day live-scraped — sample up to
        # 3 evenly-spaced days from the window, keep the run to ~30s
        sample = days if len(days) <= 3 else [days[0], days[len(days) // 2], days[-1]]
        pool = await scrape_pool(corridor, sample, on_done=on_source_done)
        records = list(pool.records)
        tiers.append("live_scrape")
        blocked = pool.sources_degraded
        notes.append(
            f"live: {len(records)} fares from {pool.sources_ok or 'no source'}"
            + (f" · {len(blocked)} source(s) unavailable ({', '.join(blocked)})" if blocked else "")
        )

    # a thin live result — some sources blocked, or the network is down — is
    # topped up: Travelpayouts first (fresh, licensed), then the on-disk cache.
    thin = mode == "auto" and len(records) < floor

    # ---- Tier 1 · Travelpayouts fills the gap ------------------------
    if thin:
        try:
            tp_records, tp_note = await tp_fetch(corridor, days)
            records.extend(tp_records)
            tiers.append("travelpayouts")
            notes.append(tp_note)
        except TravelpayoutsError as exc:
            notes.append(f"travelpayouts skipped: {exc}")
        records, _ = dedupe(records)

    # ---- Tier 2 · on-disk cache tops up whatever is still missing -----
    if (mode == "auto" and len(records) < floor) or not records:
        cached, stamps = cache.newest_any(corridor)
        if cached:
            have = {(r.airline, r.flight_number or r.flight_id, r.departure_ts) for r in records}
            added = [r for r in cached if (r.airline, r.flight_number or r.flight_id, r.departure_ts) not in have]
            records.extend(added)
            tiers.append("cache")
            why = "no live/API fares" if not (pool and pool.sources_ok) else f"live below floor ({floor})"
            notes.append(
                f"cache top-up ({why}): +{len(added)} fares · newest snapshot per source "
                f"{ {s: t[:10] for s, t in stamps.items()} }"
            )

    # ---- date window: keep only fares that depart in [start, end] -----
    before = len(records)
    records, out_of_window = _within_window(records, start, end)
    if out_of_window:
        notes.append(
            f"window {start.isoformat()}..{end.isoformat()} · "
            f"{len(records)}/{before} fares depart in range"
        )

    records, dropped = dedupe(records)
    if dropped:
        notes.append(f"{dropped} cross-tier duplicates dropped")

    dominant = _dominant_tier(records)
    return IngestResult(
        records=records,
        ingestion_source=dominant,
        tiers_used=tiers,
        pool=pool,
        notes=notes,
        degraded=dominant != "live_scrape" or len(records) < floor,
    )


def _dominant_tier(records: list[FareRecord]) -> str:
    counts: dict[str, int] = {}
    for r in records:
        key = r.ingestion_source or "unknown"
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return "none"
    return max(counts, key=counts.get)
