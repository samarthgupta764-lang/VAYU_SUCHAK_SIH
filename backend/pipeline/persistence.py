"""
Resilient persistence — pipeline/persistence.py

    persist_run(run_data) -> "postgres" | "sqlite_fallback"

Try Postgres (3s connect timeout). On any connection/operational error, write
the mirrored schema to a local SQLite file in WAL mode so a DB outage never
freezes the app. Every row is tagged `db_target` so the two stores can be
reconciled later.

If both fail the disk is gone — we raise and say so, rather than pretending an
in-memory retry queue exists.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

from pipeline.schema import RAW as _SCHEMA, statements as _ddl_statements

# columns in insertion order — must match db/schema.sql
_COLUMNS = [
    "run_id", "corridor", "date_range_start", "date_range_end",
    "index_value", "index_ex_festival", "festival_component",
    "k_factor_used", "base_period", "records_ingested",
    "festival_flagged_count", "festival_breakdown", "anomalies_excluded_count",
    "ml_flagged_count", "imputed_route_days", "routes_matched",
    "scrape_sources", "ingestion_source", "tiers_used", "sources_degraded",
    "annotation", "db_target", "created_at",
]
_JSON_COLUMNS = {"festival_breakdown", "scrape_sources", "tiers_used"}


class PersistenceError(RuntimeError):
    """Both Postgres and SQLite failed."""


def _row(run_data: dict[str, Any], db_target: str) -> dict[str, Any]:
    row = {c: run_data.get(c) for c in _COLUMNS}
    row["db_target"] = db_target
    row["created_at"] = run_data.get("created_at") or datetime.now(timezone.utc).isoformat()
    for c in _JSON_COLUMNS:
        if row.get(c) is not None and not isinstance(row[c], str):
            row[c] = json.dumps(row[c], default=str)
    return row


# --------------------------------------------------------------------------
#  Postgres
# --------------------------------------------------------------------------
def _try_postgres(run_data: dict[str, Any]) -> bool:
    if not settings.postgres_enabled:
        return False
    try:
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError, OperationalError
    except ImportError:
        return False

    from pipeline.quotes import _pg_engine  # the one cached, pooled engine — see its docstring

    row = _row(run_data, "postgres")
    try:
        engine = _pg_engine()
        if engine is None:
            return False
        with engine.begin() as conn:
            for stmt in _ddl_statements():
                conn.execute(text(stmt))
            placeholders = ", ".join(f":{c}" for c in _COLUMNS)
            conn.execute(
                text(f"INSERT INTO audit_runs ({', '.join(_COLUMNS)}) VALUES ({placeholders})"),
                row,
            )
        return True
    except (OperationalError, DBAPIError, OSError, TimeoutError):
        return False


# --------------------------------------------------------------------------
#  SQLite WAL fallback
# --------------------------------------------------------------------------
def _write_sqlite(run_data: dict[str, Any]) -> None:
    row = _row(run_data, "sqlite_fallback")
    path = settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        conn.execute(
            f"INSERT OR REPLACE INTO audit_runs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
            [row[c] for c in _COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()


def persist_run(run_data: dict[str, Any]) -> str:
    if _try_postgres(run_data):
        return "postgres"
    try:
        _write_sqlite(run_data)
        return "sqlite_fallback"
    except sqlite3.Error as exc:
        raise PersistenceError(f"postgres and sqlite both failed: {exc}") from exc


# --------------------------------------------------------------------------
#  reads (for /api/runs and the PDF report)
# --------------------------------------------------------------------------
def _read_sqlite(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    path = settings.sqlite_path
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _read_postgres(query: str, params: dict) -> list[dict[str, Any]] | None:
    if not settings.postgres_enabled:
        return None
    try:
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError, OperationalError
    except ImportError:
        return None

    from pipeline.quotes import _pg_engine  # the one cached, pooled engine — see its docstring

    try:
        engine = _pg_engine()
        if engine is None:
            return None
        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [dict(r) for r in rows]
    except (OperationalError, DBAPIError, OSError, TimeoutError):
        return None


def fetch_runs(corridor: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Newest runs first, Postgres if reachable else SQLite, else []."""
    where = "WHERE corridor = :corridor" if corridor else ""
    pg = _read_postgres(
        f"SELECT * FROM audit_runs {where} ORDER BY created_at DESC LIMIT :limit",
        {"corridor": corridor, "limit": limit},
    )
    if pg is not None:
        return pg
    where_s = "WHERE corridor = ?" if corridor else ""
    args = (corridor, limit) if corridor else (limit,)
    return _read_sqlite(
        f"SELECT * FROM audit_runs {where_s} ORDER BY created_at DESC LIMIT ?", args
    )


def fetch_run(run_id: str) -> dict[str, Any] | None:
    pg = _read_postgres("SELECT * FROM audit_runs WHERE run_id = :rid", {"rid": run_id})
    if pg:
        return pg[0]
    rows = _read_sqlite("SELECT * FROM audit_runs WHERE run_id = ?", (run_id,))
    return rows[0] if rows else None
