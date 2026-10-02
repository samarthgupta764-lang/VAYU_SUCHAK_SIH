"""
End-to-end: seed cache -> run the orchestrator -> assert a full SSE transcript
and a persisted row. Exercises every stage on real-shaped data, no network.
"""

import json
from datetime import date

import pytest


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(settings, "sqlite_fallback_path", str(tmp_path / "fallback.sqlite"))
    monkeypatch.setattr(settings, "pg_dsn", "")
    monkeypatch.setattr(settings, "travelpayouts_token", "")

    from scripts.seed_cache import seed
    written = seed("DEL-BOM", target_rows=40)
    assert written > 0
    return settings


@pytest.mark.asyncio
async def test_full_pipeline_streams_and_persists(seeded, monkeypatch):
    from app.models import AuditParams
    from app.orchestrator import run_audit
    from pipeline import ingest
    from pipeline.scrape.pool import PoolResult

    async def cache_only_pool(corridor, days, **kwargs):
        return PoolResult(records=[], statuses=[], duplicates_dropped=0)

    monkeypatch.setattr(ingest, "scrape_pool", cache_only_pool)

    params = AuditParams(corridor="DEL-BOM", start=date(2026, 11, 1), end=date(2026, 11, 30), k_factor=1.5)

    stages, final = [], None
    async for line in run_audit(params):
        assert line.startswith("data: ")
        payload = json.loads(line[6:])
        stages.append(payload["stage"])
        if payload.get("done"):
            final = payload

    for expected in ["SYSTEM", "INGEST", "FESTIVAL", "IQR", "INTEGRITY", "LASPEYRES", "NOWCAST", "DB", "EXPLAIN"]:
        assert expected in stages, f"missing stage {expected}"

    assert final is not None
    assert final["index"] > 0
    assert final["db_target"] == "sqlite_fallback"

    from pipeline.persistence import fetch_runs
    rows = fetch_runs(corridor="DEL-BOM", limit=1)
    assert rows and rows[0]["run_id"] == final["run_id"]


def test_reproducible_index(seeded, monkeypatch):
    """Same seeded input -> identical index twice (pure pipeline, no RNG)."""
    from pipeline import festival, iqr, laspeyres
    from pipeline.scrape import cache

    recs1, _ = cache.newest_any("DEL-BOM")
    recs2, _ = cache.newest_any("DEL-BOM")
    base, bp = laspeyres.load_base_reference(seeded.base_reference)

    def run(recs):
        recs, *_ = festival.flag(recs)
        res = iqr.apply_iqr_filter(recs, 1.5)
        return laspeyres.compute_index(res.clean, base, base_period=bp).index

    assert run(recs1) == run(recs2)
