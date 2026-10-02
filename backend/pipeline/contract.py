"""
The fare-record contract.

Every acquisition path — live scrape, Travelpayouts API, on-disk cache, CSV
import — must emit records in this exact shape before anything downstream
(festival flagging, IQR, Laspeyres) touches them. If you change this, you change
the whole pipeline, so it lives alone in one small file.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from pipeline.apw import advance_purchase_days, apw_bucket

ROUTE_RE = re.compile(r"^[A-Z]{3}-[A-Z]{3}$")

# where a record came from — tagged on every row and every run
INGESTION_SOURCES = ("live_scrape", "travelpayouts", "cache", "imported_csv")

# canonical cabin classes — every adapter's raw label maps to one of these
FARE_CLASSES = ("economy", "premium_economy", "business", "first")

# carrier labels vary by source ("Air India" from Google Flights, "AI" from the
# airline API) — collapse to the IATA code so dedupe + per-carrier index agree.
_CARRIER_ALIASES = {
    "indigo": "6E", "6e": "6E",
    "air india express": "IX", "airindia express": "IX", "aix": "IX", "ix": "IX",
    "air india": "AI", "airindia": "AI", "ai": "AI",
    "akasa air": "QP", "akasa": "QP", "qp": "QP",
    "spicejet": "SG", "spice jet": "SG", "sg": "SG",
    "vistara": "UK", "uk": "UK",
    "alliance air": "9I", "9i": "9I",
    "star air": "S5", "s5": "S5",
}


def _norm_carrier(raw: Any) -> str:
    s = str(raw or "").strip()
    return _CARRIER_ALIASES.get(s.lower(), s.upper()[:3] or "NA")


def _norm_fare_class(raw: Any) -> str:
    s = str(raw or "").strip().lower().replace("-", " ").replace("_", " ")
    if not s or s in {"eco", "economy", "y", "coach", "main"}:
        return "economy"
    if "premium" in s and ("eco" in s or "economy" in s):
        return "premium_economy"
    if s in {"ecopremium", "premium"}:
        return "premium_economy"
    if "business" in s or s in {"biz", "c", "j"}:
        return "business"
    if "first" in s or s == "f":
        return "first"
    return "economy"


@dataclass(slots=True)
class FareRecord:
    flight_id: str            # e.g. "6E-2341-20261108"  (airline-flightno-date)
    route: str                # "DEL-BOM"
    price: float              # INR, plain number
    currency: str             # always "INR" after normalisation
    departure_ts: str         # ISO 8601, e.g. "2026-11-08T06:15:00+05:30"
    airline: str              # IATA code, e.g. "6E"
    source: str               # "ixigo" | "makemytrip" | ... | "cache" | "csv"

    # optional / filled by later stages -------------------------------------
    flight_number: str | None = None
    duration_minutes: int | None = None
    stops: int | None = None
    ingestion_source: str | None = None       # one of INGESTION_SOURCES

    # collection metadata + fare decomposition (feature list §01, §07) ------
    collected_at: str | None = None           # ISO ts — when this quote was captured
    source_type: str | None = None            # airline | ota | api | cache
    fare_class: str = "economy"               # one of FARE_CLASSES
    advance_purchase_days: int | None = None  # departure_date − collected_date
    apw_bucket: str | None = None             # "T+1" | "T+7" | "T+15" | "T+30" | "T+45"
    base_fare: float | None = None            # fare before tax + statutory fees
    taxes: float | None = None                # GST + other taxes
    udf: float | None = None                  # user-development fee (airport)
    convenience_fee: float | None = None      # OTA / payment convenience charge
    is_sold_out: int = 0                      # 1 = flight shown but no seats / fare

    # stage annotations (set in place, never dropped) ----------------------
    is_festival_season: int = 0
    festival_matched: str | None = None
    exclusion_reason: str | None = None       # set by IQR / integrity model
    integrity_score: float | None = None
    ml_flag: int = 0
    imputed: int = 0

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContractError(ValueError):
    """Raised when a record cannot be coerced into the contract."""


def _clean_price(value: Any) -> float:
    """'₹4,820' / '4820' / 4820.0 -> 4820.0 . Raises on non-numeric."""
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    if not digits:
        raise ContractError(f"price has no digits: {value!r}")
    return float(digits)


def _normalise_ts(value: Any) -> str:
    """Accept a datetime or a parseable string; emit ISO 8601."""
    if isinstance(value, datetime):
        return value.isoformat()
    s = str(value).strip()
    # tolerate a bare "YYYY-MM-DDTHH:MM"
    try:
        return datetime.fromisoformat(s).isoformat()
    except ValueError:
        return s  # leave as-is; downstream festival flag parses defensively


def _to_day(ts: str) -> date | None:
    try:
        return datetime.fromisoformat(str(ts)).date()
    except ValueError:
        try:
            return datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def normalise(
    raw: dict[str, Any],
    *,
    ingestion_source: str | None = None,
    collected_at: str | None = None,
) -> FareRecord:
    """
    Coerce one loosely-shaped dict into a FareRecord.

    Required keys (any casing / synonyms handled): route, price, airline,
    departure_ts | departure | date. Everything else is best-effort.

    `collected_at` is when the quote was captured (ISO). Defaults to now.
    Used to derive the advance-purchase window; pass the original scrape time
    when re-normalising cached rows.
    """
    g = {k.lower().strip(): v for k, v in raw.items()}

    route = str(g.get("route") or g.get("corridor") or "").upper().replace("_", "-")
    if not ROUTE_RE.match(route):
        raise ContractError(f"bad route {route!r} (want e.g. DEL-BOM)")

    airline = _norm_carrier(g.get("airline") or g.get("carrier") or "")
    flight_number = g.get("flight_number") or g.get("flight_no") or g.get("flightnum")
    ts = g.get("departure_ts") or g.get("departure") or g.get("dep_ts") or g.get("date")
    if ts is None:
        raise ContractError("missing departure timestamp")

    sold_out = 1 if g.get("is_sold_out") or g.get("sold_out") else 0
    raw_price = g.get("price") if g.get("price") is not None else g.get("fare")
    if sold_out and (raw_price in (None, "", 0, "0")):
        # a flight shown with no bookable fare — kept as an availability signal,
        # priced 0, and filtered out of every index (is_sold_out = 0 guard)
        price = 0.0
    else:
        price = _clean_price(raw_price)

    dep_iso = _normalise_ts(ts)
    date_tag = re.sub(r"[^\d]", "", dep_iso[:10]) or "na"
    flight_id = str(
        g.get("flight_id")
        or (f"{airline}-{flight_number}-{date_tag}" if flight_number else f"{airline}-{int(price)}-{date_tag}")
    )

    collected = collected_at or datetime.now(timezone.utc).isoformat()
    dep_day, coll_day = _to_day(dep_iso), _to_day(collected)
    apd = advance_purchase_days(dep_day, coll_day) if dep_day and coll_day else None

    def _num(*keys: str) -> float | None:
        for k in keys:
            v = g.get(k)
            if v not in (None, ""):
                try:
                    return float(str(v).replace("₹", "").replace(",", ""))
                except ValueError:
                    return None
        return None

    return FareRecord(
        flight_id=flight_id,
        route=route,
        price=price,
        currency="INR",
        departure_ts=dep_iso,
        airline=airline or "NA",
        source=str(g.get("source") or "unknown"),
        flight_number=str(flight_number) if flight_number else None,
        duration_minutes=_maybe_int(g.get("duration_minutes")),
        stops=_maybe_int(g.get("stops") if g.get("stops") is not None else g.get("stops_count")),
        ingestion_source=ingestion_source,
        collected_at=collected,
        source_type=(str(g["source_type"]) if g.get("source_type") else None),
        fare_class=_norm_fare_class(g.get("fare_class") or g.get("cabin") or g.get("class")),
        advance_purchase_days=apd,
        apw_bucket=apw_bucket(apd) if apd is not None else None,
        base_fare=_num("base_fare", "base", "base_amount", "bf"),
        taxes=_num("taxes", "tax", "tax_amount", "total_tax"),
        udf=_num("udf", "user_development_fee"),
        convenience_fee=_num("convenience_fee", "convenience", "conv_fee"),
        is_sold_out=sold_out,
    )


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalise_many(
    rows: Iterable[dict[str, Any]], *, ingestion_source: str | None = None
) -> tuple[list[FareRecord], list[dict[str, Any]]]:
    """Returns (good_records, rejected_rows_with_reason)."""
    good: list[FareRecord] = []
    bad: list[dict[str, Any]] = []
    for row in rows:
        try:
            good.append(normalise(row, ingestion_source=ingestion_source))
        except ContractError as exc:
            bad.append({"row": row, "reason": str(exc)})
    return good, bad


def dedupe(records: list[FareRecord]) -> tuple[list[FareRecord], int]:
    """
    Merge key = airline + flight_number (or flight_id) + departure_ts.
    Keeps the first occurrence; returns (unique, dropped_count).
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[FareRecord] = []
    for r in records:
        key = (r.airline, r.flight_number or r.flight_id, r.departure_ts)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out, len(records) - len(out)
