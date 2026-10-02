"""
Base reference for the index — pipeline/base_reference.py

The APIx is a weighted Laspeyres index:  Index = Σ(Pt·Q0) / Σ(P0·Q0) × 100

  P0  base-year fare per route      ← data/base_year_reference.json  (2022,
      Kaggle median economy fare — frozen, feature 6.2 / 10.3)
  Q0  base-year passenger weight    ← same file (DGCA 2022 city-pair pax)

Both weights are fixed at the base period, so the index isolates pure price
change. The `/api/execute-audit` live scrape and the daily-collected time-series
use the SAME base, so they read as one consistent index.

Routes are the intersection of base_year_reference.json and whatever has been
collected — currently the 16 metro pairs (32 directed routes). Routes we
collect but have no 2022 P0 for are shown on the map / coverage panels but are
not in the headline index.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from config import settings

_REF = settings.base_reference


@lru_cache(maxsize=1)
def _ref() -> dict:
    try:
        data = json.loads(_REF.read_text())
    except (OSError, ValueError):
        return {"base_period": "2022", "routes": {}}
    if "routes" not in data:                       # bare {route: {P0, Q0}}
        return {"base_period": "unknown", "routes": data}
    return data


def base_period() -> str:
    return str(_ref().get("base_period", "2022"))


def indexed_routes() -> list[str]:
    """Routes that have a base-year P0 + Q0 — the index basket."""
    return sorted(_ref().get("routes", {}).keys())


# collector uses the same basket, so every collected route is in the index
def basket_routes() -> list[str]:
    return indexed_routes()


def q0(route: str) -> float | None:
    r = _ref().get("routes", {}).get(route)
    return r["Q0"] if r else None


def q0_table() -> dict[str, float]:
    return {k: v["Q0"] for k, v in _ref().get("routes", {}).items() if v.get("Q0")}


def p0_table() -> dict[str, float]:
    return {k: v["P0"] for k, v in _ref().get("routes", {}).items() if v.get("P0")}


# --------------------------------------------------------------------------
#  BaseP0 — kept as a struct so pipeline/index_engine.py is unchanged
# --------------------------------------------------------------------------
@dataclass
class BaseP0:
    month: str | None
    by_route_window: dict[tuple[str, str], float] = field(default_factory=dict)
    by_route: dict[str, float] = field(default_factory=dict)
    provisional: bool = False
    collection_days: int = 0
    n_quotes: int = 0

    def p0(self, route: str, window: str | None = None) -> float | None:
        return self.by_route.get(route)   # 2022 P0 is per route, not per window


def build_p0(aggregator: str | None = None, k_factor: float | None = None) -> BaseP0:
    """The frozen 2022 base — a static lookup, not computed from the DB."""
    return BaseP0(month=base_period(), by_route=p0_table(), provisional=False)


def base_month() -> str | None:
    return base_period()


def clear_cache() -> None:
    _ref.cache_clear()
