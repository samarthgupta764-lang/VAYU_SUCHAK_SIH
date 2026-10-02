"""The fare-record contract — carrier / cabin normalisation, fare decomposition,
advance-purchase-window derivation (pipeline/contract.py)."""

from datetime import datetime, timezone

from pipeline.contract import normalise

COLLECTED = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc).isoformat()


def _n(**over):
    base = {
        "route": "DEL-BOM", "price": 6880, "airline": "Air India",
        "flight_no": "AI-2951", "departure_ts": "2026-10-08T13:30:00+05:30",
        "source": "airindia",
    }
    base.update(over)
    return normalise(base, ingestion_source="live_scrape", collected_at=COLLECTED)


def test_carrier_name_collapses_to_iata():
    assert _n(airline="Air India").airline == "AI"
    assert _n(airline="IndiGo").airline == "6E"
    assert _n(airline="Akasa Air").airline == "QP"
    assert _n(airline="SpiceJet").airline == "SG"
    assert _n(airline="Air India Express").airline == "IX"
    assert _n(airline="6E").airline == "6E"


def test_cabin_normalisation():
    assert _n(cabin="eco").fare_class == "economy"
    assert _n(cabin="Economy").fare_class == "economy"
    assert _n(cabin="ecoPremium").fare_class == "premium_economy"
    assert _n(cabin="Premium Economy").fare_class == "premium_economy"
    assert _n(cabin="Business").fare_class == "business"
    assert _n().fare_class == "economy"          # default


def test_advance_purchase_window_from_collected_at():
    r = _n(departure_ts="2026-10-08T13:30:00+05:30")   # collected 2026-10-01 -> 7 days
    assert r.advance_purchase_days == 7
    assert r.apw_bucket == "T+7"
    r2 = _n(departure_ts="2026-10-31T09:00:00+05:30")  # 30 days
    assert r2.apw_bucket == "T+30"
    r3 = _n(departure_ts="2026-10-13T09:00:00+05:30")  # 12 days -> between windows
    assert r3.apw_bucket is None


def test_fare_decomposition_fields():
    r = _n(base_fare=5093, taxes=1487, udf=299)
    assert r.base_fare == 5093
    assert r.taxes == 1487
    assert r.udf == 299
    assert r.price == 6880          # total unchanged


def test_sold_out_flag():
    assert _n(is_sold_out=True).is_sold_out == 1
    assert _n().is_sold_out == 0


def test_sold_out_row_may_have_no_price():
    r = _n(is_sold_out=True, price=None)
    assert r.is_sold_out == 1 and r.price == 0.0
    # a normal row with no price is still a hard error
    import pytest
    from pipeline.contract import ContractError
    with pytest.raises(ContractError):
        _n(price=None)
