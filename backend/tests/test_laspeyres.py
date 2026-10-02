"""Golden-number test for the weighted Laspeyres engine (deep-dive §7.4) — 118.75."""

from pipeline.laspeyres import compute_index
from tests.conftest import rec

BASE = {
    "DEL-BOM": {"P0": 5000, "Q0": 1000},
    "DEL-GAU": {"P0": 6000, "Q0": 100},
}


def test_two_route_index_is_exactly_118_75():
    records = [
        rec(5500, route="DEL-BOM", fno="A"),
        rec(6000, route="DEL-BOM", fno="B"),   # median DEL-BOM = 5750
        rec(9000, route="DEL-GAU", fno="C"),   # median DEL-GAU = 9000
    ]
    res = compute_index(records, BASE, base_period="2022")
    assert res.index == 118.75
    assert res.routes_matched == 2


def test_volume_weighting_beats_naive_average():
    records = [rec(5750, route="DEL-BOM", fno="A"), rec(9000, route="DEL-GAU", fno="C")]
    res = compute_index(records, BASE)
    naive = 100 * ((5750 / 5000) + (9000 / 6000)) / 2
    assert res.index < naive          # 118.75 vs 132.5
    assert abs(naive - 132.5) < 1e-9


def test_unmatched_routes_reported_not_crashed():
    records = [rec(5750, route="DEL-BOM", fno="A"), rec(4000, route="XXX-YYY", fno="Z")]
    res = compute_index(records, BASE)
    assert res.routes_matched == 1
    assert "XXX-YYY" in res.routes_unmatched


def test_festival_decomposition():
    records = [
        rec(5000, route="DEL-BOM", fno="A", festival=0),
        rec(6500, route="DEL-BOM", fno="B", festival=1),
        rec(9000, route="DEL-GAU", fno="C", festival=0),
    ]
    res = compute_index(records, BASE)
    assert res.index_ex_festival is not None
    assert res.index != res.index_ex_festival
    assert res.festival_component == round(res.index - res.index_ex_festival, 2)
