"""
Festival Flag Engine — pipeline/festival.py

Marks every fare that departs within +/- `window_days` of a major Indian
festival, so the index can be computed both `index_all` and `index_ex_festival`.
Lunar dates come from the `holidays` package (offline, maintained upstream) —
never hardcoded from memory.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import holidays

from pipeline.contract import FareRecord

# The festivals that move airfare demand. `holidays` emits many minor observances;
# we keep only these. Names must match the library's output exactly.
MAJOR_FESTIVALS: frozenset[str] = frozenset(
    {
        "Diwali",
        "Holi",
        "Dussehra",
        "Christmas Day",
        "Guru Nanak Jayanti",
        "Eid al-Fitr",
        "Eid al-Adha",
        "Makar Sankranti / Pongal",
        "Raksha Bandhan (Rakhi)",
    }
)


def build_festival_dates(years: Iterable[int]) -> list[tuple[str, date]]:
    """
    -> sorted list of (festival_name, date) for the given years, filtered to
    MAJOR_FESTIVALS. `holidays` names are sometimes suffixed ("Diwali*"); we
    match on a normalised prefix.
    """
    years = sorted(set(years))
    ind = holidays.India(years=years)
    out: list[tuple[str, date]] = []
    for d, raw_name in ind.items():
        for part in str(raw_name).split(";"):
            name = part.strip().rstrip("*").strip()
            matched = _match(name)
            if matched:
                out.append((matched, d))
    return sorted(set(out), key=lambda t: t[1])


def _match(name: str) -> str | None:
    if name in MAJOR_FESTIVALS:
        return name
    for fest in MAJOR_FESTIVALS:
        if name.startswith(fest) or fest.startswith(name):
            return fest
    return None


def _to_date(ts: str) -> date | None:
    try:
        return datetime.fromisoformat(ts).date()
    except ValueError:
        try:
            return datetime.strptime(ts[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def flag_festivals(
    records: list[FareRecord],
    festival_dates: list[tuple[str, date]],
    window_days: int = 7,
) -> tuple[list[FareRecord], int, dict[str, int]]:
    """
    Annotates records in place with `is_festival_season` (0/1) and
    `festival_matched` (name | None).

    Returns (records, flagged_count, breakdown) where breakdown is
    {festival_name: count} for festivals that actually matched — festivals whose
    window contains no fares do not appear.
    """
    breakdown: dict[str, int] = {}
    flagged = 0
    for r in records:
        dep = _to_date(r.departure_ts)
        r.is_festival_season = 0
        r.festival_matched = None
        if dep is None:
            continue
        for name, fdate in festival_dates:
            if abs((dep - fdate).days) <= window_days:
                r.is_festival_season = 1
                r.festival_matched = name
                breakdown[name] = breakdown.get(name, 0) + 1
                flagged += 1
                break
    return records, flagged, breakdown


def flag(
    records: list[FareRecord], *, window_days: int = 7
) -> tuple[list[FareRecord], int, dict[str, int]]:
    """
    Convenience wrapper: derives the year set from the records themselves.
    """
    years: set[int] = set()
    for r in records:
        d = _to_date(r.departure_ts)
        if d:
            years.add(d.year)
    if not years:
        years = {datetime.now().year}
    # widen by one year each side so a window straddling Jan 1 still resolves
    span = range(min(years) - 1, max(years) + 2)
    return flag_festivals(records, build_festival_dates(span), window_days)
