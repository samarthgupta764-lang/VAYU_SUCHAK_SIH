"""
Compute the APIx from the fare-quote database — scripts/compute_index.py

Reads fare_quotes, computes the index at daily / weekly / monthly frequency for
every scope (overall, per route, per carrier, per advance-purchase window), and
upserts the results into index_values. Run it after each collection cycle.

    python -m scripts.compute_index
    python -m scripts.compute_index --show           # print the overall series
"""

from __future__ import annotations

import argparse

from pipeline.base_reference import basket_routes, build_p0
from pipeline.index_engine import series
from pipeline.quotes import store_index_points

_CARRIERS = ["6E", "AI", "QP", "SG", "IX"]
_WINDOWS = ["T+1", "T+7", "T+15", "T+30", "T+45"]


def _scopes() -> list[str]:
    scopes = ["overall"]
    scopes += [f"route:{r}" for r in basket_routes()]
    scopes += [f"carrier:{c}" for c in _CARRIERS]
    scopes += [f"window:{w}" for w in _WINDOWS]
    return scopes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    base = build_p0()
    print(f"base month: {base.month or '—'}  "
          f"({'PROVISIONAL, ' + str(base.collection_days) + ' days' if base.provisional else 'final'})  "
          f"P0 for {len(base.by_route)} routes from {base.n_quotes:,} quotes")

    written = 0
    for scope in _scopes():
        for freq in ("daily", "weekly", "monthly"):
            pts = [p for p in series(freq, scope) if p.n_quotes]
            if pts:
                written += store_index_points(p.to_row() for p in pts)

    print(f"{written} index rows written")

    if args.show:
        print("\noverall APIx:")
        for p in series("daily", "overall"):
            if p.index_value:
                flag = " (provisional)" if p.provisional else ""
                print(f"  {p.period}  {p.index_value:>7.2f}   ex-fest {p.index_ex_festival}   "
                      f"{p.n_quotes} quotes / {p.routes_matched} routes{flag}")


if __name__ == "__main__":
    main()
