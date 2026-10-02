"""
Fare-quote store — pipeline/quotes.py

Writes the de-duplicated airfare database (`fare_quotes`) and the collection-run
log (`collection_runs`). Same resilience contract as pipeline/persistence.py:
Postgres first (short connect timeout), SQLite WAL fallback, never raise for a
recoverable condition.

The index engine reads fares from HERE, not from a live scrape — collection and
index construction are separate concerns.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from config import settings
from pipeline.contract import FareRecord

from pipeline.schema import RAW as _SCHEMA, statements as _ddl_statements

_QUOTE_COLS = [
    "quote_id", "collection_run_id", "collected_at", "collected_date",
    "source", "source_type", "route", "origin", "destination", "carrier",
    "flight_number", "departure_ts", "departure_date", "advance_purchase_days",
    "apw_bucket", "fare_class", "stops", "duration_minutes",
    "base_fare", "taxes", "udf", "convenience_fee", "total_fare", "currency",
    "is_sold_out", "is_festival_season", "festival_matched", "ingestion_source",
]
_RUN_COLS = [
    "run_id", "started_at", "finished_at", "trigger", "routes_count",
    "apw_windows", "quotes_written", "quotes_seen", "sources_summary",
    "status", "notes",
]
_INDEX_COLS = [
    "period_type", "period", "scope", "index_value", "index_ex_festival",
    "festival_component", "n_quotes", "routes_matched", "k_factor",
    "anomalies_excluded", "base_month", "provisional", "computed_at",
]

_SOURCE_TYPE = {
    "airindia": "airline", "akasa": "airline", "indigo": "airline",
    "spicejet": "airline", "airindiaexpress": "airline",
    "cleartrip": "ota", "yatra": "ota", "makemytrip": "ota", "ixigo": "ota",
    "googleflights": "aggregator",
    "travelpayouts": "api", "amadeus": "api", "cache": "cache",
}


# --------------------------------------------------------------------------
#  row shaping
# --------------------------------------------------------------------------
def quote_id(r: FareRecord, collected_date: str) -> str:
    """Deterministic id from the natural unique key — a re-scrape of the same
    flight on the same day overwrites rather than duplicates."""
    fn = r.flight_number or f"px{int(r.price)}"
    key = "|".join([
        r.source or "?", r.route, (r.airline or "?"), fn,
        r.departure_ts, r.fare_class, collected_date,
    ])
    return hashlib.sha1(key.encode()).hexdigest()[:20]


def _quote_row(r: FareRecord, collection_run_id: str | None) -> dict[str, Any]:
    collected = r.collected_at or datetime.now(timezone.utc).isoformat()
    collected_date = collected[:10]
    origin, _, destination = r.route.partition("-")
    return {
        "quote_id": quote_id(r, collected_date),
        "collection_run_id": collection_run_id,
        "collected_at": collected,
        "collected_date": collected_date,
        "source": r.source or "unknown",
        "source_type": r.source_type or _SOURCE_TYPE.get(r.source or "", None),
        "route": r.route,
        "origin": origin,
        "destination": destination,
        "carrier": r.airline or "NA",
        "flight_number": r.flight_number,
        "departure_ts": r.departure_ts,
        "departure_date": str(r.departure_ts)[:10],
        "advance_purchase_days": r.advance_purchase_days,
        "apw_bucket": r.apw_bucket,
        "fare_class": r.fare_class,
        "stops": r.stops,
        "duration_minutes": r.duration_minutes,
        "base_fare": r.base_fare,
        "taxes": r.taxes,
        "udf": r.udf,
        "convenience_fee": r.convenience_fee,
        "total_fare": r.price,
        "currency": r.currency or "INR",
        "is_sold_out": int(r.is_sold_out or 0),
        "is_festival_season": int(r.is_festival_season or 0),
        "festival_matched": r.festival_matched,
        "ingestion_source": r.ingestion_source,
    }


# --------------------------------------------------------------------------
#  Postgres / SQLite writers
# --------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _engine_for(dsn: str):
    """One pooled SQLAlchemy engine per DSN, reused for the life of the
    process. THE canonical Postgres engine factory — persistence.py imports
    this too, rather than each module minting its own. Previously every
    caller (every _read()/_try_postgres()/_read_postgres() call — and
    index_engine.py calls _read() once per compute_point(), i.e. once per
    day per scope) called create_engine() fresh and never disposed it; each
    engine opens its own pool (default 5 connections) that's never closed,
    so a day of normal use leaked well past Postgres's max_connections and
    every read/write silently fell back to a stale SQLite mirror with no
    error surfaced anywhere. Keyed by dsn (not a bare maxsize=1) so a
    settings change mid-process — tests monkeypatching pg_dsn between
    cases — still gets the right engine, not a stale cached one."""
    from sqlalchemy import create_engine

    return create_engine(
        dsn, connect_args={"connect_timeout": settings.pg_connect_timeout}, pool_pre_ping=True,
    )


def _pg_engine():
    if not settings.postgres_enabled:
        return None
    try:
        return _engine_for(settings.pg_dsn)
    except Exception:  # noqa: BLE001
        return None


def _sqlite() -> sqlite3.Connection:
    path = settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _upsert_sql(table: str, cols: list[str], conflict: str, pg: bool) -> str:
    ph = ", ".join(f":{c}" for c in cols) if pg else ", ".join(["?"] * len(cols))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != conflict)
    return (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    )


def store_quotes(
    records: Iterable[FareRecord], *, collection_run_id: str | None = None
) -> int:
    """Upsert fare quotes. Returns the number of rows written. Postgres → SQLite."""
    rows = [_quote_row(r, collection_run_id) for r in records]
    if not rows:
        return 0

    engine = _pg_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            from sqlalchemy.exc import DBAPIError, OperationalError
            with engine.begin() as conn:
                for stmt in _ddl_statements():
                    conn.execute(text(stmt))
                conn.execute(text(_upsert_sql("fare_quotes", _QUOTE_COLS, "quote_id", pg=True)), rows)
            return len(rows)
        except (OperationalError, DBAPIError, OSError, TimeoutError):
            pass

    conn = _sqlite()
    try:
        sql = _upsert_sql("fare_quotes", _QUOTE_COLS, "quote_id", pg=False)
        conn.executemany(sql, [[r[c] for c in _QUOTE_COLS] for r in rows])
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def store_index_points(points: Iterable[dict[str, Any]]) -> int:
    """Upsert APIx time-series rows into index_values (PG -> SQLite)."""
    rows = [{c: p.get(c) for c in _INDEX_COLS} for p in points]
    if not rows:
        return 0
    engine = _pg_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            from sqlalchemy.exc import DBAPIError, OperationalError
            with engine.begin() as conn:
                for stmt in _ddl_statements():
                    conn.execute(text(stmt))
                conn.execute(text(_upsert_sql(
                    "index_values", _INDEX_COLS, "period_type, period, scope", pg=True)), rows)
            return len(rows)
        except (OperationalError, DBAPIError, OSError, TimeoutError):
            pass
    conn = _sqlite()
    try:
        conn.executemany(
            _upsert_sql("index_values", _INDEX_COLS, "period_type, period, scope", pg=False),
            [[r[c] for c in _INDEX_COLS] for r in rows])
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def fetch_index_series(
    scope: str = "overall", period_type: str = "daily", limit: int = 400
) -> list[dict[str, Any]]:
    sql = ("SELECT * FROM index_values WHERE scope = :s AND period_type = :pt "
           "ORDER BY period ASC LIMIT :lim")
    params = {"s": scope, "pt": period_type, "lim": limit}
    engine = _pg_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
        except Exception:  # noqa: BLE001
            pass
    p = settings.sqlite_path
    if not p.exists():
        return []
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def record_collection_run(run: dict[str, Any]) -> None:
    """Write one collection_runs row (best-effort)."""
    row = {c: run.get(c) for c in _RUN_COLS}
    for j in ("apw_windows", "sources_summary"):
        if row.get(j) is not None and not isinstance(row[j], str):
            row[j] = json.dumps(row[j], default=str)

    engine = _pg_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            from sqlalchemy.exc import DBAPIError, OperationalError
            with engine.begin() as conn:
                conn.execute(text(_upsert_sql("collection_runs", _RUN_COLS, "run_id", pg=True)), row)
            return
        except (OperationalError, DBAPIError, OSError, TimeoutError):
            pass
    conn = _sqlite()
    try:
        conn.execute(_upsert_sql("collection_runs", _RUN_COLS, "run_id", pg=False),
                     [row[c] for c in _RUN_COLS])
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
#  reads
# --------------------------------------------------------------------------
def fetch_quotes(
    *,
    route: str | None = None,
    carrier: str | None = None,
    apw_bucket: str | None = None,
    fare_class: str | None = None,
    collected_from: str | None = None,
    collected_to: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    clauses, params = [], {}
    for col, val in [
        ("route", route), ("carrier", carrier), ("apw_bucket", apw_bucket),
        ("fare_class", fare_class),
    ]:
        if val:
            clauses.append(f"{col} = :{col}")
            params[col] = val
    if collected_from:
        clauses.append("collected_date >= :cfrom"); params["cfrom"] = collected_from
    if collected_to:
        clauses.append("collected_date <= :cto"); params["cto"] = collected_to
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params["limit"] = min(limit, 50000)
    sql = f"SELECT * FROM fare_quotes {where} ORDER BY collected_date DESC, total_fare ASC LIMIT :limit"

    engine = _pg_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
        except Exception:  # noqa: BLE001
            pass

    path = settings.sqlite_path
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:  # sqlite3 supports :name placeholders with a dict natively
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _read(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Run a read query against Postgres if reachable, else SQLite, else []."""
    params = params or {}
    engine = _pg_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
        except Exception:  # noqa: BLE001
            pass
    path = settings.sqlite_path
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def quote_stats() -> dict[str, Any]:
    rows = _read(
        "SELECT COUNT(*) total, COUNT(DISTINCT route) routes, "
        "COUNT(DISTINCT carrier) carriers, MAX(collected_date) latest, "
        "COUNT(DISTINCT collected_date) days FROM fare_quotes"
    )
    return rows[0] if rows else {"total": 0, "routes": 0, "carriers": 0, "latest": None, "days": 0}


def collector_status() -> dict[str, Any]:
    """Everything the dashboard's collection-health panel needs."""
    stats = quote_stats()
    d = stats.get("latest") or ""
    by = lambda col: _read(
        f"SELECT {col} k, COUNT(*) n FROM fare_quotes WHERE collected_date = :d "
        f"AND {col} IS NOT NULL GROUP BY {col} ORDER BY n DESC", {"d": d})
    sold = _read("SELECT COUNT(*) n FROM fare_quotes WHERE collected_date = :d AND is_sold_out = 1", {"d": d})
    runs = _read(
        "SELECT run_id, started_at, finished_at, trigger, routes_count, "
        "quotes_written, status FROM collection_runs ORDER BY started_at DESC LIMIT 10")
    days = _read("SELECT DISTINCT collected_date x FROM fare_quotes ORDER BY x")
    return {
        "total_quotes": stats["total"], "routes": stats["routes"], "carriers": stats["carriers"],
        "collection_days": [r["x"] for r in days],
        "days_toward_backtest": min(len(days), 30),
        "latest_date": stats.get("latest"),
        "latest": {
            "by_source": {r["k"]: r["n"] for r in by("source")},
            "by_carrier": {r["k"]: r["n"] for r in by("carrier")},
            "by_window": {r["k"]: r["n"] for r in by("apw_bucket")},
            "sold_out": sold[0]["n"] if sold else 0,
        },
        "recent_runs": runs,
    }
