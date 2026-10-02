"""
MoSPI CPI reference series — pipeline/cpi.py

Loads the two official Consumer Price Index series (base 2012 = 100) that the
dashboard overlays and the back-test compares against:

  air_fare_series()   CPI item "Air Fare (normal): Economy Class (adult)"
                      — MoSPI's own airfare index; the back-test target.
  transport_series()  CPI sub-group "Transport and Communication", All-India
                      Combined — the broader reference line.

Files live in data/mospi/ (see data/mospi/SOURCE.md). NOT scraped.
"""

from __future__ import annotations

import csv
from functools import lru_cache

from config import settings

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def _month_key(year: str, month_code: str, month_name: str) -> str | None:
    try:
        mc = int(month_code)
    except (TypeError, ValueError):
        mc = _MONTHS.get(str(month_name).strip().lower(), 0)
    if not (year and 1 <= mc <= 12):
        return None
    return f"{int(year):04d}-{mc:02d}"


@lru_cache(maxsize=2)
def air_fare_series() -> list[dict]:
    """[{month: 'YYYY-MM', index: float, inflation: float|None}], ascending."""
    path = settings.path("data/mospi/cpi_air_fare_item.csv")
    if not path.exists():
        return []
    out: dict[str, dict] = {}
    for row in csv.DictReader(path.open()):
        key = _month_key(row.get("year"), row.get("month_code"), row.get("month"))
        if not key or not row.get("index"):
            continue
        try:
            out[key] = {
                "month": key,
                "index": float(row["index"]),
                "inflation": float(row["inflation"]) if row.get("inflation") else None,
            }
        except ValueError:
            continue
    return [out[k] for k in sorted(out)]


@lru_cache(maxsize=2)
def transport_series(state: str = "All India", sector: str = "Combined") -> list[dict]:
    path = settings.path("data/mospi/cpi_transport_subgroup.csv")
    if not path.exists():
        return []
    out: dict[str, dict] = {}
    for row in csv.DictReader(path.open()):
        if row.get("state") != state or row.get("sector") != sector:
            continue
        key = _month_key(row.get("year"), row.get("month_code"), row.get("month"))
        if not key or not row.get("index"):
            continue
        try:
            out[key] = {"month": key, "index": float(row["index"]),
                        "inflation": float(row["inflation"]) if row.get("inflation") else None}
        except ValueError:
            continue
    return [out[k] for k in sorted(out)]


def rebased(series: list[dict], base_month: str) -> list[dict]:
    """Re-anchor a CPI series so `base_month` = 100 — for overlaying on the APIx."""
    base = next((p["index"] for p in series if p["month"] == base_month), None)
    if not base:
        base = series[0]["index"] if series else None
    if not base:
        return series
    return [{**p, "index": round(100 * p["index"] / base, 2)} for p in series]
