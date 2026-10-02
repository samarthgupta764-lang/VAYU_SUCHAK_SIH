"""Advance-purchase-window bucketing + target-date logic (pipeline/apw.py)."""

from datetime import date

from pipeline.apw import advance_purchase_days, apw_bucket, target_departure_dates


def test_bucket_snaps_to_nearest_window_within_tolerance():
    assert apw_bucket(1) == "T+1"
    assert apw_bucket(0) == "T+1"
    assert apw_bucket(7) == "T+7"
    assert apw_bucket(6) == "T+7"
    assert apw_bucket(8) == "T+7"
    assert apw_bucket(15) == "T+15"
    assert apw_bucket(30) == "T+30"
    assert apw_bucket(45) == "T+45"


def test_bucket_none_when_between_windows():
    assert apw_bucket(11) is None      # 4 off T+7, 4 off T+15
    assert apw_bucket(22) is None
    assert apw_bucket(60) is None
    assert apw_bucket(-3) is None
    assert apw_bucket(None) is None


def test_advance_purchase_days():
    assert advance_purchase_days(date(2026, 10, 8), date(2026, 10, 1)) == 7
    assert advance_purchase_days(date(2026, 10, 1), date(2026, 10, 1)) == 0


def test_target_departure_dates():
    t = target_departure_dates(date(2026, 10, 1))
    assert t["T+1"] == date(2026, 10, 2)
    assert t["T+7"] == date(2026, 10, 8)
    assert t["T+45"] == date(2026, 11, 15)
    assert list(t) == ["T+1", "T+7", "T+15", "T+30", "T+45"]
