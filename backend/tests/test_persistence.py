"""Persistence — Postgres -> SQLite WAL failover (deep-dive §7.5)."""

import sqlite3

from pipeline.persistence import fetch_run, fetch_runs, persist_run

ROW = {
    "run_id": "test-run-0001",
    "corridor": "DEL-BOM",
    "index_value": 118.75,
    "index_ex_festival": 116.4,
    "k_factor_used": 1.5,
    "base_period": "2022",
    "records_ingested": 412,
    "festival_flagged_count": 38,
    "festival_breakdown": {"Diwali": 31, "Christmas Day": 7},
    "anomalies_excluded_count": 2,
    "ingestion_source": "cache",
    "tiers_used": ["live_scrape", "cache"],
}


def test_writes_to_sqlite_when_postgres_disabled(tmp_sqlite):
    target = persist_run(ROW)
    assert target == "sqlite_fallback"
    assert tmp_sqlite.exists()

    conn = sqlite3.connect(tmp_sqlite)
    (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
    assert mode.lower() == "wal"
    row = conn.execute("SELECT db_target, index_value FROM audit_runs WHERE run_id=?",
                       (ROW["run_id"],)).fetchone()
    conn.close()
    assert row == ("sqlite_fallback", 118.75)


def test_json_columns_roundtrip(tmp_sqlite):
    persist_run(ROW)
    got = fetch_run(ROW["run_id"])
    assert got is not None
    assert '"Diwali": 31' in got["festival_breakdown"]


def test_fetch_runs_newest_first(tmp_sqlite):
    persist_run({**ROW, "run_id": "r1", "created_at": "2026-01-01T00:00:00Z"})
    persist_run({**ROW, "run_id": "r2", "created_at": "2026-02-01T00:00:00Z"})
    rows = fetch_runs(corridor="DEL-BOM", limit=10)
    assert [r["run_id"] for r in rows][:2] == ["r2", "r1"]
