"""Golden-number test for the IQR purifier (engineering deep-dive §7.3)."""

from pipeline.iqr import apply_iqr_filter
from tests.conftest import rec

PRICES = [4200, 4500, 4800, 5000, 5200, 5500, 5800, 6000, 9000, 15000]


def _records(prices):
    return [rec(p, fno=f"F{i}") for i, p in enumerate(prices)]


def test_quartiles_match_hand_calc():
    res = apply_iqr_filter(_records(PRICES), k_factor=1.5)
    assert res.fences.q1 == 4850
    assert res.fences.q3 == 5950
    assert res.fences.iqr == 1100


def test_k_1_5_excludes_two():
    res = apply_iqr_filter(_records(PRICES), k_factor=1.5)
    assert round(res.fences.upper) == 7600
    assert res.excluded_total == 2
    assert res.excluded_high == 2
    assert {r.price for r in res.anomalies} == {9000, 15000}


def test_k_3_0_excludes_one():
    res = apply_iqr_filter(_records(PRICES), k_factor=3.0)
    assert round(res.fences.upper) == 9250
    assert res.excluded_total == 1
    assert {r.price for r in res.anomalies} == {15000}


def test_lower_fence_catches_glitch_low():
    res = apply_iqr_filter(_records(PRICES + [1]), k_factor=1.5)
    assert res.excluded_low == 1
    low = [r for r in res.anomalies if r.price == 1][0]
    assert low.exclusion_reason == "below_lower_fence"


def test_nothing_deleted():
    recs = _records(PRICES)
    res = apply_iqr_filter(recs, k_factor=1.5)
    assert len(res.clean) + len(res.anomalies) == len(recs)
