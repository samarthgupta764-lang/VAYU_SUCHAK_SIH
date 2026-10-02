import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.contract import FareRecord  # noqa: E402


def rec(price, route="DEL-BOM", airline="6E", fno=None, ts="2026-11-08T06:15:00+05:30",
        source="ixigo", festival=0):
    r = FareRecord(
        flight_id=f"{airline}-{fno or int(price)}-{route}",
        route=route, price=float(price), currency="INR", departure_ts=ts,
        airline=airline, source=source, flight_number=fno,
        ingestion_source="cache",
    )
    r.is_festival_season = festival
    return r


@pytest.fixture
def make_rec():
    return rec


@pytest.fixture
def tmp_sqlite(tmp_path, monkeypatch):
    from config import settings
    path = tmp_path / "fallback.sqlite"
    monkeypatch.setattr(settings, "sqlite_fallback_path", str(path))
    monkeypatch.setattr(settings, "pg_dsn", "")
    return path
