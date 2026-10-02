"""
Weighted Laspeyres Engine — pipeline/laspeyres.py

    Index = [ Sum(Pt * Q0) / Sum(P0 * Q0) ] * 100

Pt = current per-route fare (median — outlier-robust) after IQR cleaning
P0 = base-year per-route fare        (base_year_reference.json)
Q0 = base-year per-route passenger volume, fixed weight (DGCA, data.gov.in)

Weights are frozen at the base year, so period-to-period moves reflect price
change only — the same construction CPI uses. Vectorised, no loops, no random
seeds: same input -> same output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from pipeline.contract import FareRecord

Aggregator = Literal["median", "mean"]


@dataclass(slots=True)
class IndexResult:
    index: float                       # index_all
    index_ex_festival: float | None    # recomputed on non-festival fares only
    festival_component: float | None   # index - index_ex_festival, in index points
    routes_matched: int
    routes_unmatched: list[str]        # routes with fares but no base reference
    table: pd.DataFrame                # per-route Pt/P0/Q0/pt_q0/p0_q0
    base_period: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "index_ex_festival": self.index_ex_festival,
            "festival_component": self.festival_component,
            "routes_matched": self.routes_matched,
            "routes_unmatched": self.routes_unmatched,
            "base_period": self.base_period,
            "per_route": self.table.reset_index().to_dict(orient="records"),
        }


def load_base_reference(path: str | Path) -> tuple[dict[str, dict[str, float]], str]:
    """
    Reads base_year_reference.json -> ({route: {P0, Q0}}, base_period).
    Accepts both {"routes": {...}, "base_period": ...} and a bare {route: {...}}.
    """
    data = json.loads(Path(path).read_text())
    if "routes" in data:
        return data["routes"], str(data.get("base_period", "unknown"))
    return data, "unknown"


def _per_route_price(records: list[FareRecord], how: Aggregator) -> pd.Series:
    df = pd.DataFrame([{"route": r.route, "price": r.price} for r in records])
    if df.empty:
        return pd.Series(dtype=float, name="Pt")
    agg = df.groupby("route")["price"].median() if how == "median" else df.groupby("route")["price"].mean()
    return agg.rename("Pt")


def _index_from(pt: pd.Series, base: pd.DataFrame) -> tuple[float, pd.DataFrame, list[str]]:
    merged = base.join(pt, how="inner")
    unmatched = sorted(set(pt.index) - set(merged.index))
    if merged.empty:
        return float("nan"), merged, unmatched
    merged = merged.assign(
        pt_q0=merged["Pt"] * merged["Q0"],
        p0_q0=merged["P0"] * merged["Q0"],
    )
    index = 100.0 * merged["pt_q0"].sum() / merged["p0_q0"].sum()
    return round(float(index), 2), merged, unmatched


def compute_index(
    clean_records: list[FareRecord],
    base_reference: dict[str, dict[str, float]],
    *,
    base_period: str = "unknown",
    aggregator: Aggregator = "median",
) -> IndexResult:
    """
    Compute the Laspeyres index (and the ex-festival variant) from cleaned fares.
    """
    base = pd.DataFrame(base_reference).T
    base.index.name = "route"
    base = base[["P0", "Q0"]].astype(float)

    pt_all = _per_route_price(clean_records, aggregator)
    index_all, table, unmatched = _index_from(pt_all, base)

    non_fest = [r for r in clean_records if not r.is_festival_season]
    if len(non_fest) == len(clean_records) or not non_fest:
        index_exf = index_all if non_fest else None
    else:
        pt_exf = _per_route_price(non_fest, aggregator)
        index_exf, _, _ = _index_from(pt_exf, base)

    component = (
        round(index_all - index_exf, 2)
        if index_exf is not None and index_all == index_all  # not NaN
        else None
    )

    return IndexResult(
        index=index_all,
        index_ex_festival=index_exf,
        festival_component=component,
        routes_matched=len(table),
        routes_unmatched=unmatched,
        table=table,
        base_period=base_period,
    )
