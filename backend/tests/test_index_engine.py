"""Real-time index engine + base reference + CPI loader + back-test."""

from datetime import datetime, timezone

import pytest


@pytest.fixture
def index_db(tmp_path, monkeypatch):
    import json
    from config import settings
    monkeypatch.setattr(settings, "sqlite_fallback_path", str(tmp_path / "ix.sqlite"))
    monkeypatch.setattr(settings, "pg_dsn", "")

    # a synthetic 2-route base reference: P0 = 2022 fare, Q0 = passenger weight
    ref = tmp_path / "base.json"
    ref.write_text(json.dumps({"base_period": "2022", "routes": {
        "DEL-BOM": {"P0": 6000, "Q0": 600},
        "DEL-BLR": {"P0": 5000, "Q0": 400},
    }}))
    from pipeline import base_reference
    monkeypatch.setattr(base_reference, "_REF", ref)
    base_reference.clear_cache()

    def _q(route, price, day, carrier="6E", win="T+7", festival=0):
        from pipeline.contract import normalise
        dep = {"T+7": 7, "T+30": 30}[win]
        from datetime import date, timedelta
        d = date.fromisoformat(day)
        r = normalise({"route": route, "price": price, "airline": carrier,
                       "flight_no": f"{carrier}-{price}", "cabin": "eco",
                       "departure_ts": (d + timedelta(days=dep)).isoformat() + "T06:00:00+05:30",
                       "source": "test"},
                      ingestion_source="live_scrape",
                      collected_at=day + "T06:00:00+00:00")
        r.is_festival_season = festival
        return r

    yield settings, _q
    base_reference.clear_cache()


def _store(quotes):
    from pipeline.quotes import store_quotes
    store_quotes(quotes, collection_run_id="t")


def test_index_is_100_in_base_month(index_db):
    _settings, q = index_db
    _store([q("DEL-BOM", 6000, "2026-10-01"), q("DEL-BLR", 5000, "2026-10-01"),
            q("DEL-BOM", 6000, "2026-10-02"), q("DEL-BLR", 5000, "2026-10-02")])
    from pipeline.index_engine import latest
    p = latest("overall")
    assert p.index_value == 100.0
    assert p.routes_matched == 2


def test_index_moves_with_price(index_db):
    _settings, q = index_db
    # base month: two days at the base level
    _store([q("DEL-BOM", 6000, "2026-10-01"), q("DEL-BLR", 5000, "2026-10-01"),
            q("DEL-BOM", 6000, "2026-10-02"), q("DEL-BLR", 5000, "2026-10-02")])
    # a later day, DEL-BOM fares +20%
    _store([q("DEL-BOM", 7200, "2026-11-05"), q("DEL-BLR", 5000, "2026-11-05")])
    from pipeline.index_engine import series
    pts = {p.period: p for p in series("daily", "overall")}
    nov = pts["2026-11-05"]
    # DEL-BOM weight 600, +20%; DEL-BLR weight 400, flat
    # index = (7200*600 + 5000*400) / (6000*600 + 5000*400) * 100 = 112.7
    assert 112 < nov.index_value < 113.5
    assert nov.provisional is False   # 3 distinct days >= min_days(2)


def test_ex_festival_and_windows(index_db):
    _settings, q = index_db
    _store([
        q("DEL-BOM", 6000, "2026-10-01", win="T+7"),
        q("DEL-BOM", 9000, "2026-10-01", win="T+30", festival=1),
        q("DEL-BLR", 5000, "2026-10-01", win="T+7"),
        q("DEL-BOM", 6000, "2026-10-02", win="T+7"),
        q("DEL-BLR", 5000, "2026-10-02", win="T+7"),
    ])
    from pipeline.index_engine import series, elasticity
    oct1 = next(p for p in series("daily", "overall") if p.period == "2026-10-01")
    # the festival quote (9000) lifts Pt above the ex-festival Pt
    assert oct1.index_ex_festival is not None
    assert oct1.index_ex_festival < oct1.index_value
    assert oct1.festival_component > 0
    el = elasticity("DEL-BOM")
    windows = {e["window"] for e in el}
    assert "T+7" in windows and "T+30" in windows


def test_fare_decomposition(index_db, monkeypatch):
    _settings, q = index_db

    def qd(route, price, base, tax, udf, carrier, source):
        r = q(route, price, "2026-10-01", carrier=carrier)
        r.source = source
        r.base_fare, r.taxes, r.udf = base, tax, udf
        return r

    _store([
        qd("DEL-BOM", 6000, 4800, 900, 300, "QP", "akasa"),
        qd("DEL-BOM", 6200, 5000, 900, 300, "QP", "akasa"),
        qd("DEL-BOM", 7000, 5800, 1200, 0, "AI", "airindia"),
        # a Cleartrip row with no breakdown — counts toward priced, not toward split
        q("DEL-BOM", 6500, "2026-10-01", carrier="6E"),
    ])
    from pipeline.index_engine import fare_decomposition
    d = fare_decomposition("DEL-BOM")
    carriers = {c["carrier"]: c for c in d["carriers"]}
    assert set(carriers) == {"QP", "AI"}              # 6E had no base_fare
    assert carriers["QP"]["udf"] == 300
    assert carriers["QP"]["base"] == 4900
    # base + tax + udf + conv + other == total
    qp = carriers["QP"]
    assert round(qp["base"] + qp["taxes"] + qp["udf"] + qp["convenience_fee"] + qp["other"], 0) == qp["total"]
    assert d["coverage"]["quotes_with_breakdown"] == 3
    assert d["coverage"]["quotes_priced"] == 4


def test_iqr_k_widens_the_fence_and_drops_fewer(index_db):
    _settings, q = index_db
    _store([q("DEL-BOM", 6000, "2026-10-01"), q("DEL-BLR", 5000, "2026-10-01"),
            q("DEL-BOM", 6000, "2026-10-02"), q("DEL-BLR", 5000, "2026-10-02")])
    # a spread of realistic DEL-BOM fares + a mild high outlier (13k) + a hard one (90k)
    day = ([q("DEL-BOM", p, "2026-11-10") for p in
            (5200, 5600, 5900, 6100, 6400, 6800, 7300, 8100, 13000, 90000)]
           + [q("DEL-BLR", 5000, "2026-11-10")])
    _store(day)
    from pipeline.index_engine import series

    def at(k):
        return {p.period: p for p in series("daily", "route:DEL-BOM", k_factor=k)}["2026-11-10"]

    tight, loose = at(1.5), at(4.0)
    # widening k widens the fence and excludes no more than before
    assert loose.fences["upper_fence"] > tight.fences["upper_fence"]
    assert loose.anomalies_excluded <= tight.anomalies_excluded
    # the ₹90k decoy is caught at every sane k — it never reaches the index
    assert tight.anomalies_high >= 1 and loose.anomalies_high >= 1
    # tight k also trims the ₹13k, so its index sits lower
    assert tight.index_value <= loose.index_value
    assert tight.k_factor == 1.5


def test_p0_is_frozen_at_default_k(index_db):
    _settings, q = index_db
    _store([q("DEL-BOM", 6000, "2026-10-01"), q("DEL-BLR", 5000, "2026-10-01"),
            q("DEL-BOM", 6000, "2026-10-02"), q("DEL-BLR", 5000, "2026-10-02")])
    from pipeline.index_engine import latest
    # dragging k must not move the base-month index off 100 (Pt == P0)
    assert latest("overall", k_factor=1.5).index_value == 100.0
    assert latest("overall", k_factor=6.0).index_value == 100.0


def test_cpi_loader():
    from pipeline import cpi
    af = cpi.air_fare_series()
    assert len(af) > 100                       # 2014 -> 2025, monthly
    assert af[0]["month"] < af[-1]["month"]
    assert all("index" in p for p in af)
    reb = cpi.rebased(af, af[-1]["month"])
    assert reb[-1]["index"] == 100.0


def test_backtest_historical_runs():
    from pipeline.backtest import historical
    r = historical()
    # Kaggle economy.csv has Feb + Mar 2022
    assert r.n_months == 2
    assert r.months == ["2022-02", "2022-03"]
    assert "METHOD DEMONSTRATION ONLY" in r.note   # honest about the confound
