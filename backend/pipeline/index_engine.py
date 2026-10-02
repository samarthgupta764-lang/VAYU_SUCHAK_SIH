"""
Real-time Airfare Price Index (APIx) — pipeline/index_engine.py

Computes the index FROM the fare_quotes database (collection and index
construction are separate concerns — this never scrapes).

    Index = Sum(Pt . Q0) / Sum(P0 . Q0) x 100

  Pt  current per-route fare  = median (outlier-robust) of the economy quotes
      in the period, per route
  P0  base per-route fare     = pipeline/base_reference.build_p0()  (base month)
  Q0  fixed weight            = DGCA passengers per city-pair

Frequencies: a point per collection **day**, rolled up to ISO **week** and
calendar **month**. Sub-indices by route / carrier / advance-purchase window.
Every point is also computed ex-festival (drop is_festival_season quotes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from config import settings
from pipeline.base_reference import BaseP0, build_p0, q0_table
from pipeline.contract import FareRecord
from pipeline.iqr import filter_prices
from pipeline.ml.integrity import score_integrity
from pipeline.ml.nowcast import impute_gaps
from pipeline.quotes import _read

AGG = settings.index_aggregator


@dataclass
class IndexPoint:
    period_type: str            # daily | weekly | monthly
    period: str                 # 2026-10-05 | 2026-W41 | 2026-10
    scope: str                  # overall | route:DEL-BOM | carrier:6E | window:T+7
    index_value: float | None
    index_ex_festival: float | None
    festival_component: float | None
    n_quotes: int
    routes_matched: int
    base_month: str | None
    provisional: bool
    k_factor: float = settings.k_factor_default
    anomalies_excluded: int = 0
    anomalies_low: int = 0
    anomalies_high: int = 0
    fences: dict | None = None        # for a route-scoped point: that route's Tukey fence
    per_route: list[dict] = field(default_factory=list)
    ml_flagged: int = 0               # integrity model — structurally-odd fares excluded post-IQR
    ml_model_loaded: bool = False
    imputed_count: int = 0            # nowcast — route-days filled in (no live/clean quote, incl. all-sold-out)
    imputed_routes: list[str] = field(default_factory=list)
    # the nowcast model already computes an ~80% confidence band per imputed
    # route (pipeline/ml/nowcast.py) — it was being silently discarded here,
    # so an imputed number looked exactly as certain as a real one anywhere
    # this was consumed. {route: {value, lower, upper}}.
    imputed_bands: dict[str, dict] = field(default_factory=dict)
    nowcast_model_loaded: bool = False

    def to_row(self) -> dict:
        return {
            "period_type": self.period_type, "period": self.period, "scope": self.scope,
            "index_value": self.index_value, "index_ex_festival": self.index_ex_festival,
            "festival_component": self.festival_component, "n_quotes": self.n_quotes,
            "routes_matched": self.routes_matched, "base_month": self.base_month,
            "provisional": int(self.provisional), "k_factor": self.k_factor,
            "anomalies_excluded": self.anomalies_excluded,
            "ml_flagged": self.ml_flagged, "ml_model_loaded": self.ml_model_loaded,
            "imputed_count": self.imputed_count, "imputed_routes": self.imputed_routes,
            "imputed_bands": self.imputed_bands,
            "nowcast_model_loaded": self.nowcast_model_loaded,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }


def _agg(vals: list[float]) -> float:
    vals = sorted(vals)
    n = len(vals)
    if AGG == "mean":
        return sum(vals) / n
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def _laspeyres(pt: dict[str, float], p0: dict[str, float], weights: dict[str, float]):
    routes = [r for r in pt if r in p0 and r in weights and p0[r] and weights[r]]
    if not routes:
        return None, [], 0
    num = sum(pt[r] * weights[r] for r in routes)
    den = sum(p0[r] * weights[r] for r in routes)
    idx = 100.0 * num / den if den else None
    per = [{"route": r, "Pt": round(pt[r], 2), "P0": round(p0[r], 2),
            "Q0": weights[r], "rel": round(100 * pt[r] / p0[r], 1)} for r in sorted(routes)]
    return (round(idx, 2) if idx is not None else None), per, len(routes)


# --------------------------------------------------------------------------
def _quotes(collected_from: str, collected_to: str, scope: str) -> list[dict]:
    """Postgres if reachable, else the local SQLite fallback — via
    pipeline.quotes._read, the same dual-DB read every other read path in
    the app already goes through. (Previously this queried a hardcoded
    SQLite connection even when Postgres was primary, silently missing
    whatever the collector had written there — see [[vayu-suchak]] notes.)"""
    clauses = ["collected_date >= :f", "collected_date <= :t",
               "fare_class = 'economy'", "total_fare IS NOT NULL", "is_sold_out = 0"]
    params = {"f": collected_from, "t": collected_to}
    kind, _, val = scope.partition(":")
    if kind == "route":
        clauses.append("route = :route"); params["route"] = val
    elif kind == "carrier":
        clauses.append("carrier = :carrier"); params["carrier"] = val
    elif kind == "window":
        clauses.append("apw_bucket = :w"); params["w"] = val
    # quote_id/carrier/source/departure_ts/stops/duration_minutes are pulled
    # only so a purified row can become a FareRecord for the integrity model
    # (build_matrix needs them) — the aggregate index itself only uses
    # route/apw_bucket/total_fare/is_festival_season, same as before.
    sql = ("SELECT quote_id, route, apw_bucket, total_fare, is_festival_season, "
           "carrier, source, departure_ts, stops, duration_minutes "
           f"FROM fare_quotes WHERE {' AND '.join(clauses)}")
    return _read(sql, params)


def _row_to_record(r: dict) -> FareRecord:
    return FareRecord(
        flight_id=r["quote_id"], route=r["route"], price=r["total_fare"], currency="INR",
        departure_ts=r["departure_ts"], airline=r["carrier"], source=r["source"],
        stops=r["stops"], duration_minutes=r["duration_minutes"],
        apw_bucket=r["apw_bucket"], is_festival_season=r["is_festival_season"] or 0,
    )


def _purify_rows(rows, k: float):
    """
    Per (route x window) Tukey fence — a fare is an outlier relative to
    comparable fares, not to the whole DB. -> (rows_by_route, n_low, n_high,
    fence_by_route). Keeps the row (not just its price) so the surviving set
    can go on to the integrity model.
    """
    groups: dict[tuple[str, str], list] = {}
    for r in rows:
        groups.setdefault((r["route"], r["apw_bucket"] or "?"), []).append(r)

    by_route: dict[str, list] = {}
    fence_by_route: dict[str, object] = {}
    fence_n: dict[str, int] = {}
    low = high = 0
    for (route, _win), grp in groups.items():
        prices = [g["total_fare"] for g in grp]
        _clean_prices, lo, hi, f = filter_prices(prices, k)
        kept = [g for g in grp if f.lower <= g["total_fare"] <= f.upper] or grp  # never drop a whole group
        by_route.setdefault(route, []).extend(kept)
        low += lo
        high += hi
        # keep the widest-sample fence per route for the histogram
        if len(prices) > fence_n.get(route, 0):
            fence_by_route[route] = f
            fence_n[route] = len(prices)
    return by_route, low, high, fence_by_route


def compute_point(
    period_type: str, period: str, collected_from: str, collected_to: str,
    scope: str = "overall", *, base: BaseP0 | None = None,
    k_factor: float | None = None,
) -> IndexPoint:
    k = k_factor if k_factor and k_factor > 0 else settings.k_factor_default
    # P0 is the frozen base — always purified at the default k. Only the current
    # period's Pt responds to the k-slider, so dragging k shows real index
    # movement (and the anomaly count / fences) rather than shifting both baskets
    # together.
    base = base or build_p0()
    weights = q0_table()
    window = scope.split(":", 1)[1] if scope.startswith("window:") else None
    p0 = {r: base.p0(r, window) for r in weights if base.p0(r, window)}

    # A route-scoped query asks for THAT route's own price ratio, not a
    # 32-route Laspeyres blend — narrowing p0/weights to the one route here
    # means nowcast (below) can only ever impute that same one route, never
    # fabricate the other 31 and silently bake them into "the" index_value.
    # (Bug found 2026-09-11: scope=route:DEL-BOM was returning a full-basket
    # index with 31/32 routes nowcast-imputed, e.g. 208.57, while DEL-BOM's
    # own real ratio — sitting right there in per_route[0].rel — was 129.3.
    # Every route-scoped API caller, including the Analytics heatmap, was
    # silently getting that blended number instead.)
    scope_route = scope.split(":", 1)[1] if scope.startswith("route:") else None
    if scope_route:
        p0 = {scope_route: p0[scope_route]} if scope_route in p0 else {}
        weights = {scope_route: weights[scope_route]} if scope_route in weights else {}

    point = IndexPoint(period_type, period, scope, None, None, None, 0, 0,
                       base.month, base.provisional, k_factor=k)
    rows = _quotes(collected_from, collected_to, scope)
    if not rows:
        return point
    point.n_quotes = len(rows)

    rows_by_route, low, high, fences = _purify_rows(rows, k)
    point.anomalies_low, point.anomalies_high = low, high
    point.anomalies_excluded = low + high

    if scope_route and scope_route in fences:
        point.fences = fences[scope_route].to_dict()

    # ---- integrity model — second pass on the IQR-clean set, same as the
    # /api/execute-audit orchestrator, so the two index paths agree ---------
    iqr_clean_records = [_row_to_record(r) for rs in rows_by_route.values() for r in rs]
    integ = score_integrity(iqr_clean_records)
    clean_records = [r for r in integ.records if not r.ml_flag]
    point.ml_flagged, point.ml_model_loaded = integ.flagged_count, integ.loaded

    def _pt_from(records: list[FareRecord]) -> dict[str, float]:
        by_route: dict[str, list[float]] = {}
        for r in records:
            by_route.setdefault(r.route, []).append(r.price)
        return {rt: _agg(v) for rt, v in by_route.items() if v}

    # ---- nowcast — fill any route in the base basket this period has no
    # clean quote for (never scraped, or every quote for it was sold-out) ---
    pt_observed = _pt_from(clean_records)
    nowcast = impute_gaps(pt_observed, list(p0.keys()), context={"scope": scope, "period": period})
    point.imputed_count = nowcast.imputed_count
    point.imputed_routes = [cell.route for cell in nowcast.imputed]
    point.imputed_bands = {
        cell.route: {"value": cell.value, "lower": cell.lower, "upper": cell.upper}
        for cell in nowcast.imputed
    }
    point.nowcast_model_loaded = nowcast.loaded

    idx, per, matched = _laspeyres(nowcast.per_route_price, p0, weights)
    point.index_value, point.per_route, point.routes_matched = idx, per, matched
    # thread imputed + its band onto the per-route rows too, since that's
    # what most callers (heatmap, carrier comparison) actually read —
    # imputed_routes/imputed_bands above stay as the point-level summary.
    for row in per:
        if row["route"] in point.imputed_bands:
            row["imputed"] = True
            row["band"] = point.imputed_bands[row["route"]]

    exf_records = [r for r in clean_records if not r.is_festival_season]
    if exf_records:
        pt_exf = _pt_from(exf_records)
        exf, _, _ = _laspeyres(pt_exf, p0, weights)
        point.index_ex_festival = exf
        if idx is not None and exf is not None:
            point.festival_component = round(idx - exf, 2)
    return point


# --------------------------------------------------------------------------
#  frequency series
# --------------------------------------------------------------------------
def _collection_days() -> list[str]:
    return [r["d"] for r in _read("SELECT DISTINCT collected_date d FROM fare_quotes ORDER BY d")]


def series(
    period_type: str, scope: str = "overall", *, k_factor: float | None = None
) -> list[IndexPoint]:
    days = _collection_days()
    if not days:
        return []
    k = k_factor if k_factor and k_factor > 0 else settings.k_factor_default
    base = build_p0()          # frozen base — default k

    if period_type == "daily":
        return [compute_point("daily", d, d, d, scope, base=base, k_factor=k) for d in days]

    buckets: dict[str, list[str]] = {}
    for d in days:
        dt = date.fromisoformat(d)
        if period_type == "weekly":
            iso = dt.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
        else:  # monthly
            key = d[:7]
        buckets.setdefault(key, []).append(d)

    out = []
    for key, ds in sorted(buckets.items()):
        out.append(compute_point(period_type, key, min(ds), max(ds), scope, base=base, k_factor=k))
    return out


def latest(scope: str = "overall", *, k_factor: float | None = None) -> IndexPoint | None:
    daily = series("daily", scope, k_factor=k_factor)
    return daily[-1] if daily else None


def elasticity(route: str, k_factor: float | None = None) -> list[dict]:
    """Average IQR-purified fare by advance-purchase window — the lead-time curve."""
    k = k_factor if k_factor and k_factor > 0 else settings.k_factor_default
    rows = _read(
        "SELECT apw_bucket, total_fare FROM fare_quotes "
        "WHERE route = :route AND fare_class='economy' AND total_fare IS NOT NULL "
        "AND is_sold_out = 0 AND apw_bucket IS NOT NULL", {"route": route})
    by_w: dict[str, list[float]] = {}
    for r in rows:
        by_w.setdefault(r["apw_bucket"], []).append(r["total_fare"])
    order = ["T+1", "T+7", "T+15", "T+30", "T+45"]
    for w in list(by_w):
        clean, *_ = filter_prices(by_w[w], k)
        by_w[w] = clean or by_w[w]
    return [{"window": w, "avg_fare": round(_agg(by_w[w]), 0), "n": len(by_w[w])}
            for w in order if w in by_w]


def fare_decomposition(route: str | None = None) -> dict:
    """What a fare is made of — base / tax / UDF / convenience / other — as an
    average rupee split per carrier. Only rows that actually carry a breakdown
    (base_fare IS NOT NULL) count; Air India, Akasa and Yatra populate it,
    Cleartrip and Google Flights don't. -> {carriers:[...], coverage:{...}}."""
    clauses = ["fare_class = 'economy'", "is_sold_out = 0", "total_fare IS NOT NULL",
               "base_fare IS NOT NULL"]
    params: dict = {}
    if route:
        clauses.append("route = :route"); params["route"] = route.upper()
    rows = _read(
        "SELECT carrier, source, total_fare, base_fare, taxes, udf, convenience_fee "
        f"FROM fare_quotes WHERE {' AND '.join(clauses)}", params)
    priced_rows = _read(
        "SELECT COUNT(*) n FROM fare_quotes WHERE "
        + " AND ".join(clauses[:3]) + (" AND route = :route" if route else ""),
        params)
    priced = priced_rows[0] if priced_rows else None

    by_carrier: dict[str, list[dict]] = {}
    for r in rows:
        by_carrier.setdefault(r["carrier"], []).append(r)

    out = []
    for carrier, rs in sorted(by_carrier.items()):
        n = len(rs)
        base = _agg([x["base_fare"] for x in rs])
        tax = _agg([x["taxes"] or 0.0 for x in rs])
        udf = _agg([x["udf"] or 0.0 for x in rs])
        conv = _agg([x["convenience_fee"] or 0.0 for x in rs])
        total = _agg([x["total_fare"] for x in rs])
        other = max(0.0, round(total - base - tax - udf - conv, 2))
        out.append({
            "carrier": carrier, "n": n,
            "total": round(total, 2),
            "base": round(base, 2), "taxes": round(tax, 2),
            "udf": round(udf, 2), "convenience_fee": round(conv, 2),
            "other": other,
            "sources": sorted({x["source"] for x in rs}),
        })
    total_priced = (priced["n"] if priced else 0) or 0
    return {
        "route": route.upper() if route else "ALL",
        "carriers": out,
        "coverage": {
            "quotes_with_breakdown": len(rows),
            "quotes_priced": total_priced,
            "pct": round(100 * len(rows) / total_priced, 1) if total_priced else 0.0,
        },
    }
