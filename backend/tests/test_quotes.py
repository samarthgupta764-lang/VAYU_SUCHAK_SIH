"""Fare-quote store — write / upsert / read / stats (pipeline/quotes.py)."""

from datetime import datetime, timezone

import pytest


@pytest.fixture
def quote_db(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "sqlite_fallback_path", str(tmp_path / "q.sqlite"))
    monkeypatch.setattr(settings, "pg_dsn", "")
    return settings


COLLECTED = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc).isoformat()


def _rec(**over):
    from pipeline.contract import normalise
    base = {
        "route": "DEL-BOM", "price": 6880, "airline": "QP", "flight_no": "QP-1833",
        "departure_ts": "2026-10-08T06:50:00+05:30", "source": "akasa", "cabin": "eco",
        "base_fare": 5640, "taxes": 288, "udf": 152,
    }
    base.update(over)
    return normalise(base, ingestion_source="live_scrape", collected_at=COLLECTED)


def test_store_and_fetch(quote_db):
    from pipeline.quotes import store_quotes, fetch_quotes
    n = store_quotes([_rec(), _rec(airline="6E", flight_no="6E-353", price=6305)],
                     collection_run_id="run-1")
    assert n == 2
    rows = fetch_quotes(route="DEL-BOM")
    assert len(rows) == 2
    qp = next(r for r in rows if r["carrier"] == "QP")
    assert qp["apw_bucket"] == "T+7"
    assert qp["base_fare"] == 5640
    assert qp["udf"] == 152
    assert qp["total_fare"] == 6880
    assert qp["source_type"] == "airline"


def test_upsert_is_idempotent(quote_db):
    from pipeline.quotes import store_quotes, fetch_quotes
    store_quotes([_rec()], collection_run_id="run-1")
    store_quotes([_rec(price=7100)], collection_run_id="run-1")   # same flight, new price, same day
    rows = fetch_quotes(route="DEL-BOM")
    assert len(rows) == 1
    assert rows[0]["total_fare"] == 7100      # overwritten, not duplicated


def test_same_flight_different_day_is_a_new_row(quote_db):
    from pipeline.quotes import store_quotes, fetch_quotes
    store_quotes([_rec()], collection_run_id="run-1")
    later = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc).isoformat()
    store_quotes([_rec(collected_at=later) if False else _rec()], collection_run_id="run-2")
    from pipeline.contract import normalise
    r2 = normalise({"route": "DEL-BOM", "price": 6900, "airline": "QP", "flight_no": "QP-1833",
                    "departure_ts": "2026-10-08T06:50:00+05:30", "source": "akasa", "cabin": "eco"},
                   ingestion_source="live_scrape", collected_at=later)
    store_quotes([r2], collection_run_id="run-2")
    rows = fetch_quotes(route="DEL-BOM")
    assert len(rows) == 2      # one per collection day
    assert {r["collected_date"] for r in rows} == {"2026-10-01", "2026-10-02"}


def test_filters_and_stats(quote_db):
    from pipeline.quotes import store_quotes, fetch_quotes, quote_stats
    store_quotes(
        [_rec(), _rec(airline="6E", flight_no="6E-1", price=5000),
         _rec(route="BLR-DEL", airline="AI", flight_no="AI-9", price=4200,
              departure_ts="2026-10-31T09:00:00+05:30")],
        collection_run_id="run-1",
    )
    assert len(fetch_quotes(carrier="6E")) == 1
    assert len(fetch_quotes(apw_bucket="T+30")) == 1
    s = quote_stats()
    assert s["total"] == 3
    assert s["routes"] == 2
    assert s["latest"] == "2026-10-01"


def test_record_collection_run(quote_db):
    from pipeline.quotes import record_collection_run
    record_collection_run({
        "run_id": "cr-1", "started_at": COLLECTED, "trigger": "manual",
        "routes_count": 2, "apw_windows": [1, 7, 15, 30, 45],
        "quotes_written": 10, "status": "ok",
    })  # must not raise
