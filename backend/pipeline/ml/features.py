"""
Shared feature engineering for both models.

Turns a list[FareRecord] into a numeric DataFrame. Deterministic, no fitting
here — encoders that need vocabulary (airline, source) are hashed so train and
inference never disagree on column layout.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from pipeline.contract import FareRecord
from pipeline.geo import route_km as _haversine_proxy  # noqa: F401 (kept name)

AIRLINE_BUCKETS = 12
SOURCE_BUCKETS = 8


def _hash_bucket(value: str, n: int) -> int:
    return (hash(value) % n + n) % n


def _to_dt(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=None)  # compare against naive as_of
    except ValueError:
        return None


def build_matrix(
    records: list[FareRecord],
    *,
    route_median: dict[str, float] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    as_of = as_of or datetime.now()
    route_median = route_median or {}
    rows = []
    for r in records:
        dt = _to_dt(r.departure_ts)
        med = route_median.get(r.route)
        dist_km = _haversine_proxy(r.route)
        rows.append(
            {
                "price": r.price,
                "price_per_km": r.price / dist_km if dist_km else np.nan,
                "dev_from_route_median": (r.price - med) / med if med else 0.0,
                "days_to_departure": (dt - as_of).days if dt else np.nan,
                "hour_of_day": dt.hour if dt else np.nan,
                "day_of_week": dt.weekday() if dt else np.nan,
                "is_festival_season": r.is_festival_season,
                "stops": r.stops if r.stops is not None else 0,
                "duration_minutes": r.duration_minutes or 0,
                "airline_bucket": _hash_bucket(r.airline or "NA", AIRLINE_BUCKETS),
                "source_bucket": _hash_bucket(r.source or "NA", SOURCE_BUCKETS),
            }
        )
    df = pd.DataFrame(rows)
    return df.replace([np.inf, -np.inf], np.nan).fillna(df.median(numeric_only=True)).fillna(0.0)


def route_medians(records: list[FareRecord]) -> dict[str, float]:
    if not records:
        return {}
    df = pd.DataFrame([{"route": r.route, "price": r.price} for r in records])
    return df.groupby("route")["price"].median().to_dict()


# _haversine_proxy is pipeline.geo.route_km (imported above) — one distance table.
