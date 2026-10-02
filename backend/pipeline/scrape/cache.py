"""
On-disk cache — tier-2 fallback and the day-one data source.

Every successful scrape / API response is written here, timestamped. When live
acquisition and Travelpayouts are both unreachable, the newest snapshot for
`source_corridor` serves. Files:

    data/cache/<source>__<CORRIDOR>__<YYYYMMDDTHHMMSS>.json
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from pipeline.contract import FareRecord, normalise

_TS_FMT = "%Y%m%dT%H%M%S"


def _dir() -> Path:
    p = settings.cache_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def _stem(source: str, corridor: str) -> str:
    return f"{source.lower()}__{corridor.upper()}"


def write(source: str, corridor: str, records: list[FareRecord]) -> Path:
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    path = _dir() / f"{_stem(source, corridor)}__{ts}.json"
    payload = {
        "source": source,
        "corridor": corridor.upper(),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "records": [r.to_dict() for r in records],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    prune(source, corridor)
    return path


def prune(source: str, corridor: str, keep: int | None = None) -> int:
    """Keep only the `keep` newest snapshots for one (source, corridor); delete
    the rest. The cache is a fallback, not an archive — old snapshots have no
    value once a fresher one exists. -> number of files deleted."""
    keep = settings.cache_keep_per_source if keep is None else keep
    if keep <= 0:
        return 0
    snaps = sorted(_dir().glob(f"{_stem(source, corridor)}__*.json"))
    stale = snaps[:-keep] if len(snaps) > keep else []
    for f in stale:
        with contextlib.suppress(OSError):
            f.unlink()
    return len(stale)


def prune_all(keep: int | None = None) -> int:
    """Prune every (source, corridor) pair in the cache. -> files deleted."""
    seen: set[tuple[str, str]] = set()
    total = 0
    for f in _dir().glob("*__*__*.json"):
        parts = f.name.split("__")
        if len(parts) != 3:
            continue
        key = (parts[0], parts[1])
        if key in seen:
            continue
        seen.add(key)
        total += prune(parts[0], parts[1], keep)
    return total


def newest(source: str, corridor: str) -> tuple[list[FareRecord], str | None]:
    """-> (records, scraped_at_iso) for the freshest snapshot, or ([], None)."""
    matches = sorted(_dir().glob(f"{_stem(source, corridor)}__*.json"))
    if not matches:
        return [], None
    data = json.loads(matches[-1].read_text())
    scraped_at = data.get("scraped_at")
    records = [
        normalise(row, ingestion_source="cache", collected_at=scraped_at)
        for row in data.get("records", [])
    ]
    return records, scraped_at


def newest_any(corridor: str) -> tuple[list[FareRecord], dict[str, str]]:
    """
    Union of the newest snapshot per source for a corridor.
    -> (records, {source: scraped_at})
    """
    out: list[FareRecord] = []
    stamps: dict[str, str] = {}
    for path in _dir().glob(f"*__{corridor.upper()}__*.json"):
        source = path.name.split("__", 1)[0]
        if source in stamps:
            continue
        recs, ts = newest(source, corridor)
        if recs:
            out.extend(recs)
            stamps[source] = ts or "unknown"
    return out, stamps


def has_any(corridor: str) -> bool:
    return any(_dir().glob(f"*__{corridor.upper()}__*.json"))
