"""
Fallback chain — live pool empty -> Travelpayouts skipped (no token) -> cache.
Each tier is logged in `notes`. (feature list 1.15-1.21, test 11.5)
"""

import pytest

from pipeline import ingest
from pipeline.contract import FareRecord
from pipeline.scrape import cache
from pipeline.scrape.pool import PoolResult


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "travelpayouts_token", "")
    return tmp_path


def _fake_record(price, i):
    return FareRecord(
        flight_id=f"6E-{i}-x", route="DEL-BOM", price=price, currency="INR",
        departure_ts="2026-11-08T06:15:00+05:30", airline="6E", source="cache",
        ingestion_source="cache",
    )


@pytest.mark.asyncio
async def test_falls_through_to_cache_when_pool_empty(cache_dir, monkeypatch):
    # seed a cache snapshot
    cache.write("ixigo", "DEL-BOM", [_fake_record(4800 + i * 10, i) for i in range(30)])

    async def empty_pool(corridor, days, **kwargs):
        return PoolResult(records=[], statuses=[], duplicates_dropped=0)

    monkeypatch.setattr(ingest, "scrape_pool", empty_pool)

    from datetime import date
    res = await ingest.fetch_fares("DEL-BOM", date(2026, 11, 1), date(2026, 11, 30), mode="auto")
    assert res.records
    assert res.ingestion_source == "cache"
    assert "cache" in res.tiers_used
    assert any("cache" in n for n in res.notes)


@pytest.mark.asyncio
async def test_cache_tops_up_a_thin_live_result(cache_dir, monkeypatch):
    """Most scrapers blocked -> a handful of live fares -> cache fills the rest,
    without discarding the live ones (feature 1.15-1.21)."""
    from config import settings
    monkeypatch.setattr(settings, "ingest_min_fares", 20)
    cache.write("ixigo", "DEL-BOM", [_fake_record(4800 + i * 10, i) for i in range(30)])

    live = [FareRecord(flight_id=f"6E-live-{i}", route="DEL-BOM", price=5200 + i, currency="INR",
                       departure_ts="2026-11-08T06:15:00+05:30", airline="6E", source="yatra",
                       ingestion_source="live_scrape") for i in range(4)]

    async def thin_pool(corridor, days, **kwargs):
        from pipeline.scrape.base import SourceStatus
        return PoolResult(records=list(live),
                          statuses=[SourceStatus(source="yatra", status="ok", fares=4),
                                    SourceStatus(source="airindia", status="blocked")],
                          duplicates_dropped=0)

    monkeypatch.setattr(ingest, "scrape_pool", thin_pool)
    from datetime import date
    res = await ingest.fetch_fares("DEL-BOM", date(2026, 11, 1), date(2026, 11, 30), mode="auto")
    assert "live_scrape" in res.tiers_used and "cache" in res.tiers_used
    assert any(r.ingestion_source == "live_scrape" for r in res.records)  # live kept
    assert any(r.ingestion_source == "cache" for r in res.records)        # cache added
    assert res.degraded is True


@pytest.mark.asyncio
async def test_cache_only_mode(cache_dir):
    cache.write("indigo", "DEL-BOM", [_fake_record(5000, i) for i in range(12)])
    from datetime import date
    res = await ingest.fetch_fares("DEL-BOM", date(2026, 11, 1), date(2026, 11, 30), mode="cache")
    assert res.ingestion_source == "cache"
    assert res.tiers_used == ["cache"]
    assert len(res.records) == 12


@pytest.mark.asyncio
async def test_date_window_excludes_out_of_range_fares(cache_dir):
    """A fare that departs outside [start, end] is not ingested (feature 0.4 / F8.1)."""
    from datetime import date
    in_window = [_fake_record(5000, i) for i in range(10)]            # depart 2026-11-08
    out_window = [
        FareRecord(flight_id=f"6E-far-{i}", route="DEL-BOM", price=5000, currency="INR",
                   departure_ts="2027-03-01T06:15:00+05:30", airline="6E", source="cache",
                   ingestion_source="cache")
        for i in range(10)
    ]
    cache.write("indigo", "DEL-BOM", in_window + out_window)
    res = await ingest.fetch_fares("DEL-BOM", date(2026, 11, 1), date(2026, 11, 30), mode="cache")
    assert len(res.records) == 10
    assert all(r.departure_ts.startswith("2026-11") for r in res.records)
