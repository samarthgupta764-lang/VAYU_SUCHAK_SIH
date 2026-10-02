"""
Advance-purchase-window (APW) logic — pipeline/apw.py

Airfares in India move 200–400% for the *same* flight depending on how far
ahead you book. The problem statement fixes the collection windows at
**T+1, T+7, T+15, T+30, T+45 days** before departure. Every fare quote is
tagged with the window it belongs to, and the collector scrapes exactly those
departure dates each day.

Pure date arithmetic — no config import here so `pipeline.contract` can use it
without a cycle. The window list itself is a config value, passed in.
"""

from __future__ import annotations

from datetime import date, timedelta

# default windows (days before departure) — overridden from settings.apw_windows
DEFAULT_WINDOWS: tuple[int, ...] = (1, 7, 15, 30, 45)

# a quote whose advance-purchase days is within this many days of a window
# still counts as that window (scrapes can land a day off, flights shift)
DEFAULT_TOLERANCE = 2


def advance_purchase_days(departure: date, collected: date) -> int:
    """Whole days between the collection date and the departure date."""
    return (departure - collected).days


def apw_bucket(
    apd: int | None,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    tolerance: int = DEFAULT_TOLERANCE,
) -> str | None:
    """
    Nearest window label ("T+7") for an advance-purchase-days value, or None
    when it is not close enough to any window. Ties go to the smaller window.
    """
    if apd is None or apd < 0:
        return None
    best: int | None = None
    best_gap = tolerance + 1
    for w in sorted(windows):
        gap = abs(apd - w)
        if gap < best_gap:
            best, best_gap = w, gap
    return f"T+{best}" if best is not None else None


def target_departure_dates(
    collected: date, windows: tuple[int, ...] = DEFAULT_WINDOWS
) -> dict[str, date]:
    """
    For one collection day, the exact departure date to scrape for each window.
    -> {"T+1": date, "T+7": date, ...}
    """
    return {f"T+{w}": collected + timedelta(days=w) for w in sorted(windows)}


def window_label(w: int) -> str:
    return f"T+{w}"
