"""
Rebuild data/base_year_reference.json from real sources.

    P0  = mean base-year economy fare per route
          <- data/kaggle/*.csv   (Kaggle 'Flight Price Prediction (India)')
    Q0  = base-year domestic passengers per city-pair (both directions)
          <- data/dgca/domestic_city_pair.csv   (DGCA, via Vonter/india-aviation-traffic)
             NOT scraped — official statistic.

Whichever inputs are present get refreshed; the other half is kept from the
existing file. Nothing is invented.

    python -m scripts.build_base_reference                 # refresh what's available, write
    python -m scripts.build_base_reference --base-year 2023
    python -m scripts.build_base_reference --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from config import REPO_ROOT, settings
from pipeline.geo import route_key as _route
from pipeline.geo import undirected as _undirected

KAGGLE_DIR = REPO_ROOT / "data" / "kaggle"
DGCA_CSV = REPO_ROOT / "data" / "dgca" / "domestic_city_pair.csv"


# --------------------------------------------------------------------------
#  P0  (Kaggle)
# --------------------------------------------------------------------------
def build_p0(base_year: int) -> dict[str, float]:
    csvs = sorted(KAGGLE_DIR.glob("*.csv"))
    if not csvs:
        print(f"  P0: no CSVs in {KAGGLE_DIR} — keeping existing P0")
        return {}
    frames = []
    for c in csvs:
        df = pd.read_csv(c, low_memory=False)
        df.columns = [str(x).lower().strip() for x in df.columns]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    src = _col(df, "source_city", "source", "from", "origin")
    dst = _col(df, "destination_city", "destination", "to", "dest")
    price = _col(df, "price", "fare")
    cls = _col(df, "class")
    if not (src and dst and price):
        print(f"  P0: missing source/dest/price columns in {list(df.columns)[:12]}")
        return {}

    if cls:
        df = df[df[cls].astype(str).str.lower().str.contains("eco", na=False)]
    df[price] = pd.to_numeric(df[price], errors="coerce")
    df = df.dropna(subset=[price])
    df["route"] = [_route(s, d) for s, d in zip(df[src], df[dst])]
    df = df.dropna(subset=["route"])
    df["route"] = df["route"].map(_undirected)

    # median, not mean — must match the Pt aggregator in pipeline/laspeyres.py so
    # the index reads ~100 when current fares equal base-year fares.
    p0 = df.groupby("route")[price].median().round(0)
    print(f"  P0: {len(p0)} routes from {len(df):,} economy rows (Kaggle, median)")
    return {r: float(v) for r, v in p0.items()}


# --------------------------------------------------------------------------
#  Q0  (DGCA city-pair)
# --------------------------------------------------------------------------
def build_q0(base_year: int) -> dict[str, float]:
    if not DGCA_CSV.exists():
        print(f"  Q0: {DGCA_CSV.name} not found — keeping existing Q0")
        return {}
    df = pd.read_csv(DGCA_CSV)
    df.columns = [str(x).strip() for x in df.columns]
    df = df[pd.to_numeric(df["Year"], errors="coerce") == base_year]
    if df.empty:
        print(f"  Q0: no {base_year} rows in DGCA CSV")
        return {}

    to_c2 = pd.to_numeric(df["PaxToCity2"], errors="coerce").fillna(0)
    from_c2 = pd.to_numeric(df["PaxFromCity2"], errors="coerce").fillna(0)
    df = df.assign(pax=to_c2 + from_c2)
    df["route"] = [_route(a, b) for a, b in zip(df["City1"], df["City2"])]
    df = df.dropna(subset=["route"])
    df["route"] = df["route"].map(_undirected)

    q0 = df.groupby("route")["pax"].sum().round(0)
    q0 = q0[q0 > 0]
    print(f"  Q0: {len(q0)} routes from DGCA {base_year} ({len(df):,} monthly rows)")
    return {r: float(v) for r, v in q0.items()}


# --------------------------------------------------------------------------
def _col(df: pd.DataFrame, *names: str) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    for n in names:
        for c in df.columns:
            if n in c:
                return c
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-year", type=int, default=int(settings.base_period))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = Path(settings.base_reference)
    existing = json.loads(out.read_text())
    routes: dict[str, dict] = {k: dict(v) for k, v in existing.get("routes", {}).items()}

    print(f"base year: {args.base_year}")
    p0 = build_p0(args.base_year)
    q0 = build_q0(args.base_year)

    if not p0 and not q0:
        print("\nno usable inputs — file unchanged.")
        return

    # p0/q0 are keyed undirected ("BOM-DEL"); the app uses directed corridors, so
    # write both directions. Pair passenger totals are already summed both ways;
    # economy fares are ~symmetric — good enough for a fixed base-year weight.
    def directed(u: str) -> tuple[str, str]:
        a, b = u.split("-")
        return f"{a}-{b}", f"{b}-{a}"

    undirected_keys = {_undirected(r) for r in routes} | set(p0) | set(q0)
    merged: dict[str, dict] = {}
    for u in sorted(undirected_keys):
        d1, d2 = directed(u)
        prev = routes.get(d1) or routes.get(d2) or {}
        P0 = p0.get(u) or prev.get("P0")
        Q0 = q0.get(u) or prev.get("Q0")
        if P0 and Q0:
            for d in (d1, d2):
                merged[d] = {"P0": round(float(P0), 0), "Q0": round(float(Q0), 0)}

    dropped = sorted(undirected_keys - {_undirected(r) for r in merged})
    payload = {
        "base_period": str(args.base_year),
        "provenance": {
            "P0": "Kaggle 'Flight Price Prediction' — mean economy fare per route"
            if p0 else existing.get("provenance", {}).get("P0", "seed"),
            "Q0": f"DGCA domestic city-pair passengers, {args.base_year}, both directions"
            if q0 else existing.get("provenance", {}).get("Q0", "seed"),
            "generated_by": "scripts/build_base_reference.py",
        },
        "routes": merged,
    }

    print(f"\n{len(merged)} routes with both P0 and Q0")
    if dropped:
        print(f"  dropped (missing one side): {', '.join(dropped)}")
    if args.dry_run:
        print("\n--dry-run — not writing.\n")
        print(json.dumps(payload, indent=2)[:1200])
        return
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote -> {out}")


if __name__ == "__main__":
    main()
