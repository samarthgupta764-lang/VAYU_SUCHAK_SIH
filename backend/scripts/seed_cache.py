"""
Seed data/cache/ so the pipeline runs on day one with zero live scraping.

Fare source, in priority order:
  1. data/kaggle/economy.csv  — real 2022 Indian economy fares w/ times & routes
  2. data/kaggle/*.csv         — any other Kaggle layout
  3. data/samples/*.csv        — the small hand-made extracts in the repo

Each corridor gets one snapshot per synthetic "source" (ixigo, makemytrip, ...)
so the pool's merge/dedupe and the fallback chain have realistic multi-source
input. Prices are lightly jittered per source so dedupe has something to do.

    python -m scripts.seed_cache                       # every corridor in base_year_reference
    python -m scripts.seed_cache --corridor DEL-BOM --rows 40
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta

import pandas as pd

from config import REPO_ROOT, settings
from pipeline.contract import ContractError, normalise, normalise_many
from pipeline.geo import city_to_iata
from pipeline.scrape import cache

SYNTHETIC_SOURCES = ["ixigo", "makemytrip", "cleartrip", "indigo", "airindia", "googleflights"]
SAMPLE_DIR = REPO_ROOT / "data" / "samples"
KAGGLE_DIR = REPO_ROOT / "data" / "kaggle"


# --------------------------------------------------------------------------
#  load a route -> [raw fare dict] index from the best available source
# --------------------------------------------------------------------------
def _from_economy_csv() -> dict[str, list[dict]]:
    path = KAGGLE_DIR / "economy.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    rng = random.Random(2026)
    # This snapshot represents "fares captured today for Q4 2026 travel". Scatter
    # departure dates across a realistic booking window — roughly 3 weeks to
    # ~4 months out — so every dashboard preset (Diwali +/-7d, Nov 2026, Q4 2026)
    # lands on real observations and festival flagging has something to flag.
    window_start = date.today()
    lead_min, lead_max = 21, 120
    out: dict[str, list[dict]] = {}
    for r in df.to_dict("records"):
        ia, ib = city_to_iata(r.get("from", "")), city_to_iata(r.get("to", ""))
        if not (ia and ib) or ia == ib:
            continue
        route = f"{ia}-{ib}"
        dep_day = window_start + timedelta(days=rng.randint(lead_min, lead_max))
        dep = _iso_on(dep_day, r.get("dep_time", ""))
        out.setdefault(route, []).append(
            {
                "route": route,
                "airline": r.get("ch_code") or r.get("airline") or "NA",
                "flight_no": f"{r.get('ch_code', '')}-{r.get('num_code', '')}".strip("-"),
                "price": r.get("price"),
                "departure_ts": dep,
                "stops": r.get("stop"),
                "duration": r.get("time_taken"),
                "source": "kaggle",
            }
        )
    return out


def _iso_on(day: date, time_str: str) -> str:
    t = time_str.strip() or "06:00"
    try:
        hh, mm = (int(x) for x in t.split(":")[:2])
    except ValueError:
        hh, mm = 6, 0
    return datetime(day.year, day.month, day.day, hh, mm).isoformat() + "+05:30"


def _from_generic_csvs(dirpath, tag: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for csv in sorted(dirpath.glob("*.csv")):
        if csv.name == "economy.csv":
            continue
        df = pd.read_csv(csv, dtype=str, keep_default_na=False)
        for raw in df.to_dict("records"):
            g = {k.lower().strip(): v for k, v in raw.items()}
            route = _route_of(g)
            if not route:
                continue
            g["route"] = route
            out.setdefault(route, []).append(g)
    if out:
        print(f"  {tag}: {sum(len(v) for v in out.values())} rows, {len(out)} routes")
    return out


def _route_of(g: dict) -> str | None:
    route = str(g.get("route") or g.get("corridor") or "").upper().replace("_", "-")
    if route:
        return route
    a = city_to_iata(g.get("source_city") or g.get("from") or g.get("source") or "")
    b = city_to_iata(g.get("destination_city") or g.get("to") or g.get("destination") or "")
    return f"{a}-{b}" if a and b and a != b else None


def load_fare_index() -> dict[str, list[dict]]:
    eco = _from_economy_csv()
    if eco:
        print(f"  kaggle economy.csv: {sum(len(v) for v in eco.values()):,} fares, {len(eco)} routes")
        return eco
    generic = _from_generic_csvs(KAGGLE_DIR, "kaggle")
    return generic or _from_generic_csvs(SAMPLE_DIR, "samples")


# --------------------------------------------------------------------------
def _jitter(raw: dict, rng: random.Random, *, wide: bool = False) -> dict:
    out = dict(raw)
    try:
        base = float(str(out.get("price") or out.get("fare") or "5000").replace("₹", "").replace(",", ""))
    except ValueError:
        base = 5000.0
    spread = 0.22 if wide else 0.05
    out["price"] = round(base * (1 + rng.uniform(-spread, spread)))
    out.pop("fare", None)
    return out


def seed(corridor: str, target_rows: int, fare_index: dict[str, list[dict]] | None = None,
         seed_val: int = 42) -> int:
    rng = random.Random(seed_val + hash(corridor) % 1000)
    fare_index = fare_index if fare_index is not None else load_fare_index()

    pool = fare_index.get(corridor) or fare_index.get(_flip(corridor)) or []
    if not pool:
        # last resort: borrow the busiest route's shape, relabel to this corridor
        donor = max(fare_index.items(), key=lambda kv: len(kv[1]), default=(None, []))[1]
        pool = [{**r, "route": corridor} for r in donor[:target_rows]]
        if pool:
            print(f"  {corridor}: no direct fares — shaped from donor route")
    if not pool:
        print(f"  {corridor}: no usable rows")
        return 0

    good = [r for r in pool if _ok(r)]
    rng.shuffle(good)
    good = good[: max(target_rows, 15)]

    written = 0
    for src in SYNTHETIC_SOURCES:
        bucket = [_jitter(r, rng) for r in good]
        while len(bucket) < min(target_rows, 15):
            bucket.append(_jitter(rng.choice(good), rng, wide=True))
        recs, _ = normalise_many(bucket, ingestion_source="cache")
        for r in recs:
            r.source = src
        path = cache.write(src, corridor, recs[:target_rows])
        written += len(recs[:target_rows])
    print(f"  {corridor:<9} {written:>4} fares  ({len(SYNTHETIC_SOURCES)} sources)")
    return written


def _flip(corridor: str) -> str:
    a, b = corridor.split("-")
    return f"{b}-{a}"


def _ok(raw: dict) -> bool:
    try:
        normalise(raw, ingestion_source="cache")
        return True
    except ContractError:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridor", default=None)
    ap.add_argument("--rows", type=int, default=settings.scrape_target_flights)
    args = ap.parse_args()

    base = json.loads(settings.base_reference.read_text())["routes"]
    corridors = [args.corridor.upper()] if args.corridor else list(base.keys())

    print("loading fare index...")
    fare_index = load_fare_index()
    total = 0
    for c in corridors:
        total += seed(c, args.rows, fare_index)
    print(f"\nseeded {total} fares across {len(corridors)} corridor(s) -> {settings.cache_dir}/")


if __name__ == "__main__":
    main()
