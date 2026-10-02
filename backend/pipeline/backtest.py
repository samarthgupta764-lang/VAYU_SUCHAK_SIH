"""
Back-test — pipeline/backtest.py

The problem statement: *"demonstrate at least 30 days of back-tested results
against publicly available DGCA monthly average-fare data."* We validate the
VAYU-SUCHAK APIx against MoSPI's CPI item **"Air Fare (normal): Economy Class
(adult)"** — MoSPI's own airfare index, built the way DGCA collects fares.

Two modes:
  live        — our monthly APIx (from index_values / index_engine) vs the CPI
                series, on overlapping months. Fills in as collection accumulates.
  historical  — reconstruct a monthly APIx from the Kaggle 2022 fare corpus
                (~Feb–Mar 2022, ~50 days) and compare to CPI Air Fare for those
                months. Demonstrates the method on real historical data now.

Comparison metrics: Pearson correlation of month-over-month % changes, and the
share of months where both series moved the same direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from config import REPO_ROOT, settings
from pipeline import cpi
from pipeline.geo import route_key, undirected

KAGGLE_DIR = REPO_ROOT / "data" / "kaggle"


@dataclass
class BacktestResult:
    mode: str
    months: list[str] = field(default_factory=list)
    apix: list[float] = field(default_factory=list)          # rebased, first month = 100
    cpi_air_fare: list[float] = field(default_factory=list)   # rebased, first month = 100
    mom_correlation: float | None = None
    direction_agreement: float | None = None
    n_months: int = 0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "mode": self.mode, "months": self.months,
            "apix": self.apix, "cpi_air_fare": self.cpi_air_fare,
            "mom_correlation": self.mom_correlation,
            "direction_agreement": self.direction_agreement,
            "n_months": self.n_months, "note": self.note,
        }


# --------------------------------------------------------------------------
def _mom_pct(series: list[float]) -> list[float]:
    return [(series[i] - series[i - 1]) / series[i - 1] * 100
            for i in range(1, len(series)) if series[i - 1]]


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return round(cov / (va * vb), 3) if va and vb else None


def _rebase(series: list[float]) -> list[float]:
    b = series[0] if series else None
    return [round(100 * v / b, 2) for v in series] if b else series


def _compare(months: list[str], apix: list[float], cpi_idx: list[float], mode: str, note: str) -> BacktestResult:
    r = BacktestResult(mode=mode, months=months, note=note, n_months=len(months))
    r.apix = _rebase(apix)
    r.cpi_air_fare = _rebase(cpi_idx)
    da = _mom_pct(apix)
    dc = _mom_pct(cpi_idx)
    r.mom_correlation = _pearson(da, dc)
    if da and dc:
        same = sum(1 for x, y in zip(da, dc) if (x >= 0) == (y >= 0))
        r.direction_agreement = round(same / min(len(da), len(dc)), 3)
    return r


# --------------------------------------------------------------------------
#  live
# --------------------------------------------------------------------------
def live() -> BacktestResult:
    from pipeline.index_engine import series as index_series

    monthly = [p for p in index_series("monthly", "overall") if p.index_value]
    cpi_af = {p["month"]: p["index"] for p in cpi.air_fare_series()}
    overlap = [p for p in monthly if p.period in cpi_af]
    if len(overlap) < 2:
        r = BacktestResult(mode="live", n_months=len(overlap))
        r.note = (f"{len(overlap)} month(s) of overlapping data — the 30-day "
                  f"back-test needs the collector to run through at least one "
                  f"full calendar month that CPI also covers.")
        r.months = [p.period for p in overlap]
        r.apix = _rebase([p.index_value for p in overlap])
        r.cpi_air_fare = _rebase([cpi_af[p.period] for p in overlap])
        return r
    months = [p.period for p in overlap]
    return _compare(months, [p.index_value for p in overlap],
                    [cpi_af[m] for m in months], "live",
                    "VAYU-SUCHAK monthly APIx vs MoSPI CPI Air Fare, overlapping months.")


# --------------------------------------------------------------------------
#  historical (Kaggle 2022)
# --------------------------------------------------------------------------
def _kaggle_monthly_pt() -> dict[str, dict[str, float]]:
    """{'YYYY-MM': {route: median economy fare}} from the Kaggle 2022 corpus.

    Uses only files that carry a real flight date + city pair (economy.csv);
    business.csv is skipped, Clean_Dataset.csv has no date column."""
    try:
        import pandas as pd
    except ImportError:
        return {}

    out: dict[str, dict[str, list]] = {}
    for csv_path in sorted(KAGGLE_DIR.glob("*.csv")):
        if "business" in csv_path.name.lower():
            continue
        df = pd.read_csv(csv_path, low_memory=False)
        df.columns = [str(x).lower().strip().lstrip("﻿") for x in df.columns]

        price = next((x for x in ("price", "fare") if x in df.columns), None)
        src = next((x for x in ("from", "source_city", "source") if x in df.columns), None)
        dst = next((x for x in ("to", "destination_city", "destination") if x in df.columns), None)
        dcol = next((x for x in ("date", "flight_date") if x in df.columns), None)
        if not (price and src and dst and dcol):
            continue
        if "class" in df.columns:  # keep economy only where a class column exists
            df = df[df["class"].astype(str).str.lower().str.contains("eco", na=True)]

        df[price] = pd.to_numeric(
            df[price].astype(str).str.replace(",", "").str.replace("₹", ""),
            errors="coerce")
        df = df.dropna(subset=[price])
        df["month"] = pd.to_datetime(df[dcol], dayfirst=True, errors="coerce").dt.strftime("%Y-%m")
        df["route"] = [route_key(a, b) for a, b in zip(df[src], df[dst])]
        df = df.dropna(subset=["route", "month"])
        df["route"] = df["route"].map(undirected)

        for (m, r), g in df.groupby(["month", "route"]):
            out.setdefault(m, {}).setdefault(r, []).extend(g[price].tolist())

    import statistics
    return {m: {r: float(statistics.median(v)) for r, v in routes.items()}
            for m, routes in out.items()}


def historical() -> BacktestResult:
    from pipeline.base_reference import q0_table

    pt_by_month = _kaggle_monthly_pt()
    months = sorted(pt_by_month)
    if len(months) < 2:
        return BacktestResult(mode="historical", n_months=len(months),
                              note="Kaggle corpus has < 2 months — cannot back-test.")

    weights = q0_table()
    # undirected weights: sum both directions once
    w_undir: dict[str, float] = {}
    for r, q in weights.items():
        w_undir[undirected(r)] = q
    base_month = months[0]
    p0 = pt_by_month[base_month]

    apix = []
    for m in months:
        pt = pt_by_month[m]
        routes = [r for r in pt if r in p0 and r in w_undir and p0[r] and w_undir[r]]
        if not routes:
            apix.append(None)
            continue
        num = sum(pt[r] * w_undir[r] for r in routes)
        den = sum(p0[r] * w_undir[r] for r in routes)
        apix.append(round(100 * num / den, 2) if den else None)

    cpi_af = {p["month"]: p["index"] for p in cpi.air_fare_series()}
    keep = [(m, a) for m, a in zip(months, apix) if a and m in cpi_af]
    if len(keep) < 2:
        return BacktestResult(mode="historical", months=[m for m, _ in keep], n_months=len(keep),
                              note="No overlap between the Kaggle months and the CPI Air Fare series.")
    mm = [m for m, _ in keep]
    r = _compare(mm, [a for _, a in keep], [cpi_af[m] for m in mm], "historical",
                 f"Monthly APIx reconstructed from the Kaggle 2022 fare corpus "
                 f"({', '.join(mm)}) vs MoSPI CPI Air Fare. METHOD DEMONSTRATION ONLY — "
                 f"the 2022 dataset does not record the scrape date, so booking-window "
                 f"mix is confounded with travel month; magnitudes are unreliable. The "
                 f"live back-test (which controls for advance-purchase window) is the "
                 f"real validation.")
    r.mom_correlation = None   # not meaningful on 2 confounded points
    return r


def report() -> dict:
    return {"live": live().to_dict(), "historical": historical().to_dict()}
