"""
Dynamic IQR Purifier — pipeline/iqr.py

Two-tailed Tukey fence: Q1 - k*IQR and Q3 + k*IQR. Catches both glitch-low
(Rs 1, null-as-0, placeholder responses) and absurd-high fares before they
poison the per-route average.

Nothing is deleted. Anomalies are split out, tagged with a reason and the fence
they crossed, and returned — so any `k` choice is fully reversible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pipeline.contract import FareRecord


@dataclass(slots=True)
class Fences:
    q1: float
    q3: float
    iqr: float
    lower: float
    upper: float
    k_factor: float

    def to_dict(self) -> dict[str, float]:
        return {
            "Q1": round(self.q1, 2),
            "Q3": round(self.q3, 2),
            "IQR": round(self.iqr, 2),
            "lower_fence": round(self.lower, 2),
            "upper_fence": round(self.upper, 2),
            "k_factor": self.k_factor,
        }


@dataclass(slots=True)
class IQRResult:
    clean: list[FareRecord]
    anomalies: list[FareRecord]
    fences: Fences
    excluded_low: int
    excluded_high: int

    @property
    def excluded_total(self) -> int:
        return self.excluded_low + self.excluded_high


def tukey_fences(prices: list[float] | np.ndarray, k_factor: float) -> Fences:
    """Two-tailed Tukey fence for a plain price list (no FareRecord needed)."""
    if k_factor <= 0:
        raise ValueError("k_factor must be > 0")
    arr = np.asarray(prices, dtype=float)
    if arr.size == 0:
        return Fences(0, 0, 0, 0, 0, k_factor)
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1
    return Fences(q1, q3, iqr, q1 - k_factor * iqr, q3 + k_factor * iqr, k_factor)


def filter_prices(
    prices: list[float], k_factor: float
) -> tuple[list[float], int, int, Fences]:
    """
    Partition a price list by the Tukey fence.
    -> (clean_prices, n_below_lower, n_above_upper, fences)

    The index engine calls this per (route x advance-purchase window) group, so
    that legitimate booking-window spread is never mistaken for an outlier.
    """
    f = tukey_fences(prices, k_factor)
    if not prices:
        return [], 0, 0, f
    clean, low, high = [], 0, 0
    for p in prices:
        if p < f.lower:
            low += 1
        elif p > f.upper:
            high += 1
        else:
            clean.append(p)
    return clean, low, high, f


def apply_iqr_filter(records: list[FareRecord], k_factor: float) -> IQRResult:
    """
    Partition `records` into clean / anomalies by the two-tailed Tukey fence.

    Quartiles use numpy's linear interpolation (type-7), the same convention as
    the hand-worked example in tests/test_iqr.py.
    """
    if k_factor <= 0:
        raise ValueError("k_factor must be > 0")
    if not records:
        z = Fences(0, 0, 0, 0, 0, k_factor)
        return IQRResult([], [], z, 0, 0)

    prices = np.asarray([r.price for r in records], dtype=float)
    q1 = float(np.percentile(prices, 25))
    q3 = float(np.percentile(prices, 75))
    iqr = q3 - q1
    lower = q1 - k_factor * iqr
    upper = q3 + k_factor * iqr
    fences = Fences(q1, q3, iqr, lower, upper, k_factor)

    clean: list[FareRecord] = []
    anomalies: list[FareRecord] = []
    low = high = 0
    for r in records:
        if r.price < lower:
            r.exclusion_reason = "below_lower_fence"
            r.extra["fence_crossed"] = round(lower, 2)
            anomalies.append(r)
            low += 1
        elif r.price > upper:
            r.exclusion_reason = "above_upper_fence"
            r.extra["fence_crossed"] = round(upper, 2)
            anomalies.append(r)
            high += 1
        else:
            r.exclusion_reason = None
            clean.append(r)

    return IQRResult(clean, anomalies, fences, low, high)
