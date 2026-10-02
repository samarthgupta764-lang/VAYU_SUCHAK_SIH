"""
Build the route basket from DGCA passenger traffic — scripts/build_basket.py

The problem statement: a basket of representative city-pairs *"selected on the
basis of DGCA passenger-traffic data"*. This script does exactly that — no hand
picking:

    data/dgca/domestic_city_pair.csv   (DGCA monthly city-pair passengers)
        -> rank undirected city-pairs by total passengers in the most recent
           complete year
        -> keep the top N that cover ~`--coverage` of all domestic pax and
           whose city names both resolve to IATA codes we can scrape
        -> write data/route_basket.json  { base_dgca_year, routes[], q0{} }

`config.collection_routes` and the index engine read this file.

    python -m scripts.build_basket
    python -m scripts.build_basket --top 30
    python -m scripts.build_basket --year 2025 --coverage 0.80
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from config import REPO_ROOT, settings
from pipeline.geo import route_key, undirected

DGCA_CSV = REPO_ROOT / "data" / "dgca" / "domestic_city_pair.csv"
OUT = REPO_ROOT / "data" / "route_basket.json"


def _latest_complete_year(df: pd.DataFrame) -> int:
    by_year = df.groupby("Year")["Month"].nunique()
    complete = by_year[by_year >= 12]
    return int(complete.index.max()) if len(complete) else int(df["Year"].max())


def build(top: int, coverage: float, year: int | None) -> dict:
    df = pd.read_csv(DGCA_CSV)
    df.columns = [c.strip() for c in df.columns]
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["Month"] = pd.to_numeric(df["Month"], errors="coerce")

    yr = year or _latest_complete_year(df)
    d = df[df["Year"] == yr].copy()
    pax = pd.to_numeric(d["PaxToCity2"], errors="coerce").fillna(0) + \
        pd.to_numeric(d["PaxFromCity2"], errors="coerce").fillna(0)
    d = d.assign(pax=pax)
    d["route"] = [route_key(a, b) for a, b in zip(d["City1"], d["City2"])]
    d = d.dropna(subset=["route"])
    d["pair"] = d["route"].map(undirected)

    ranked = d.groupby("pair")["pax"].sum().sort_values(ascending=False)
    ranked = ranked[ranked > 0]
    total = ranked.sum()

    chosen: list[str] = []
    q0: dict[str, float] = {}
    cum = 0.0
    for pair, p in ranked.items():
        if len(chosen) >= top or (chosen and cum / total >= coverage):
            break
        a, b = pair.split("-")
        chosen.append(pair)
        q0[f"{a}-{b}"] = round(float(p))
        q0[f"{b}-{a}"] = round(float(p))   # directed; pair pax is both-ways already
        cum += p

    directed = sorted(q0.keys())
    payload = {
        "base_dgca_year": yr,
        "generated": datetime.now(timezone.utc).isoformat(),
        "provenance": "DGCA City-Pair wise Monthly Domestic Passenger Traffic",
        "coverage_of_domestic_pax": round(cum / total, 3),
        "pairs": chosen,
        "routes": directed,
        "q0": q0,
    }
    print(f"DGCA {yr}: {len(chosen)} city-pairs "
          f"({len(directed)} directed routes) = {payload['coverage_of_domestic_pax']:.0%} of domestic pax")
    for pr in chosen:
        print(f"  {pr:<26} {q0[pr.split('-')[0] + '-' + pr.split('-')[1]]:>12,.0f}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30, help="max city-pairs")
    ap.add_argument("--coverage", type=float, default=0.75, help="stop once this pax share is covered")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    payload = build(args.top, args.coverage, args.year)
    if args.dry_run:
        print("\n--dry-run — not writing.")
        return
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote -> {OUT}")
    print("set config.collection_routes to route_basket.json's routes, or leave "
          "the collector to read it directly.")


if __name__ == "__main__":
    main()
