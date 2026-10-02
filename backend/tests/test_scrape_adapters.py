"""
Parser tests for the completed adapters, against payload shapes captured from
the real sites (2026-09, DEL->BOM).
"""

import json
from datetime import date
from pathlib import Path

from pipeline.scrape.airindia import parse_air_bounds
from pipeline.scrape.akasa import parse_availability
from pipeline.scrape.cleartrip import CleartripAdapter
from pipeline.scrape.googleflights import _parse_label
from pipeline.scrape.indigo import parse_search_response
from pipeline.scrape.ixigo import IxigoAdapter
from pipeline.scrape.yatra import parse_get_fare

DAY = date(2026, 9, 25)
FIXTURES = Path(__file__).parent / "fixtures"


# --- Cleartrip: real cards.J1 / subTravelOptions shape ----------------------
CLEARTRIP_PAYLOAD = {
    "cards": {
        "J1": [
            {
                "travelOptionId": "6E-322-DEL-BOM-1",
                "summary": {
                    "flights": [{"airlineCode": "6E", "flightNumber": "322"}],
                    "firstDeparture": {"airport": {"time": "2026-09-25T23:30:00.000+05:30"}},
                    "totalDuration": {"hh": 2, "mm": 15},
                    "stops": 0,
                },
                "subTravelOptionIds": ["sto-1"],
            },
            {
                "travelOptionId": "AI-441-DEL-BOM-2",
                "summary": {
                    "flights": [{"airlineCode": "AI", "flightNumber": "441"}],
                    "firstDeparture": {"airport": {"time": "2026-09-25T05:20:00.000+05:30"}},
                    "totalDuration": {"hh": 2, "mm": 10},
                    "stops": 0,
                },
                "subTravelOptionIds": ["sto-2"],
            },
        ]
    },
    "subTravelOptions": {
        "sto-1": {"cabinClassSummary": {"ECONOMY": {"minCabinPrice": 6530}}},
        "sto-2": {"cabinClassSummary": {"ECONOMY": {"minCabinPrice": 7450}}},
    },
}


def test_cleartrip_parse_xhr():
    rows = CleartripAdapter().parse_xhr(CLEARTRIP_PAYLOAD, "DEL-BOM", DAY)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["airline"] == "6E"
    assert r0["flight_no"] == "6E-322"
    assert r0["price"] == 6530
    assert r0["departure_ts"].startswith("2026-09-25T23:30")
    assert r0["duration_minutes"] == 135
    assert r0["stops"] == 0


def test_cleartrip_parse_real_capture():
    """Trimmed slice of a real /flight/search/v2 body (DEL->BOM, depart 02/10/2026,
    Economy, 1 adult). Ground truth that day: nonstop economy fares 6368-13307."""
    payload = json.loads((FIXTURES / "cleartrip_search_v2.json").read_text())
    rows = CleartripAdapter().parse_xhr(payload, "DEL-BOM", date(2026, 10, 2))

    assert len(rows) == 216
    assert {r["source"] for r in rows} == {"cleartrip"}
    # every carrier flying the pair that day shows up
    assert {"AI", "6E", "IX", "QP", "SG"} <= {r["airline"] for r in rows}

    nonstop = sorted(r["price"] for r in rows if r["stops"] == 0)
    assert nonstop[0] == 6368.0
    assert nonstop[-1] == 13307.0
    # connecting itineraries are kept too (consistent with the other adapters)
    assert any(r["stops"] and r["stops"] > 0 for r in rows)


def test_cleartrip_ignores_unpriced_cards():
    payload = {"cards": {"J1": [CLEARTRIP_PAYLOAD["cards"]["J1"][0]]}, "subTravelOptions": {}}
    assert CleartripAdapter().parse_xhr(payload, "DEL-BOM", DAY) == []


# --- Google Flights: real aria-label sentence -----------------------------
GF_LABEL = (
    "From 6,314 Indian rupees. Nonstop flight with Air India. Leaves Indira Gandhi "
    "International Airport at 5:00 AM on Friday, September 25 and arrives at Chhatrapati "
    "Shivaji Maharaj International Airport Mumbai at 7:20 AM on Friday, September 25. "
    "Total duration 2 hr 20 min.   Select flight"
)
GF_LABEL_1STOP = (
    "From 9,120 Indian rupees. 1 stop flight with IndiGo. Leaves ... at 6:05 AM on Friday, "
    "September 25 ... Total duration 5 hr 40 min. Select flight"
)


def test_googleflights_parse_label():
    r = _parse_label(GF_LABEL, "DEL-BOM", DAY)
    assert r["price"] == 6314
    assert r["airline"] == "Air India"
    assert r["stops"] == 0
    assert r["departure_ts"].startswith("2026-09-25T05:00")
    assert r["duration_minutes"] == 140
    assert r["flight_no"] is None


def test_googleflights_parse_label_with_stop():
    r = _parse_label(GF_LABEL_1STOP, "DEL-BOM", DAY)
    assert r["price"] == 9120
    assert r["stops"] == 1
    assert r["duration_minutes"] == 340


def test_googleflights_rejects_non_fare_label():
    assert _parse_label("Some tooltip about baggage", "DEL-BOM", DAY) is None


# --- Ixigo: secondary-text classifier still works -----------------------
def test_ixigo_classify_secondary():
    from pipeline.scrape.ixigo import _classify_secondary

    dur, stops = _classify_secondary(["2h 35m", "Non-stop", "DEL → BOM"])
    assert dur == 155
    assert stops == 0


# --- Air India: real air-bounds payload -------------------------------------
OCT2 = date(2026, 10, 2)


def _airindia_payload():
    return json.loads((FIXTURES / "airindia_air_bounds.json").read_text())


def test_airindia_parse_air_bounds():
    rows = parse_air_bounds(_airindia_payload(), "DEL-BOM", OCT2)
    # 3 pure DEL-BOM groups + 1 DEL-NMI (Navi Mumbai == BOM metro) = 4
    assert len(rows) == 4
    r = min(rows, key=lambda x: x["price"])
    assert r["airline"] == "AI"
    assert r["flight_no"].startswith("AI-")
    assert r["price"] == 6979          # cheapest economy total in the fixture
    assert r["departure_ts"].startswith("2026-10-02T")
    assert r["stops"] == 0
    assert r["source"] == "airindia"


def test_airindia_captures_fare_decomposition():
    rows = parse_air_bounds(_airindia_payload(), "DEL-BOM", OCT2)
    r = min(rows, key=lambda x: x["price"])
    assert r["base_fare"] == 5093
    assert r["taxes"] == 1487
    assert r["cabin"] == "economy"
    # base + taxes (+ fees) reconciles to the total
    assert abs(r["base_fare"] + r["taxes"] - r["price"]) < 500


def test_airindia_excludes_business_and_premium():
    rows = parse_air_bounds(_airindia_payload(), "DEL-BOM", OCT2)
    # every kept price is an economy fare — the 31k/44k business buckets are gone
    assert max(r["price"] for r in rows) < 15000


def test_airindia_rejects_wrong_route():
    assert parse_air_bounds(_airindia_payload(), "BLR-CCU", OCT2) == []
    assert parse_air_bounds({}, "DEL-BOM", OCT2) == []


# --- IndiGo: real flight/search payload (parser kept; live scrape off) ------
def _indigo_payload():
    return json.loads((FIXTURES / "indigo_flight_search.json").read_text())


def test_indigo_parse_search_response():
    rows = parse_search_response(_indigo_payload(), "DEL-BOM", OCT2)
    assert rows  # some pure DEL-BOM journeys in the fixture
    assert all(r["source"] == "indigo" for r in rows)
    assert all(r["airline"] == "6E" for r in rows)
    r = rows[0]
    assert r["flight_no"].startswith("6E-")
    assert r["price"] > 0
    assert r["departure_ts"].startswith("2026-10-02")


def test_indigo_groups_alt_airports_to_the_metro():
    # fixture has DXN (Noida) -> BOM and HDO -> NMI journeys — Noida/Hindon are
    # the Delhi catchment, Navi Mumbai is Mumbai, so these ARE DEL-BOM fares.
    rows = parse_search_response(_indigo_payload(), "DEL-BOM", OCT2)
    assert len(rows) >= 3
    assert all(r["airline"] == "6E" and r["price"] > 0 for r in rows)


def test_indigo_rejects_a_genuinely_different_route():
    assert parse_search_response(_indigo_payload(), "BLR-CCU", OCT2) == []


def test_indigo_adapter_is_robots_disallowed():
    from pipeline.scrape.indigo import IndiGoAdapter

    assert IndiGoAdapter().ROBOTS_DISALLOWED is True


# --- Yatra: real get-fare payload (all carriers, base/total split) ---------
def _yatra_payload():
    return json.loads((FIXTURES / "yatra_get_fare.json").read_text())


def test_yatra_parse_get_fare_covers_all_carriers():
    rows = parse_get_fare(_yatra_payload(), "DEL-BOM")
    # 5 dates × 5 carriers in the fixture
    assert len(rows) == 25
    carriers = {r["carrier"] for r in rows}
    assert carriers == {"6E", "AI", "QP", "SG", "IX"}
    assert all(r["source"] == "yatra" for r in rows)


def test_yatra_keeps_base_total_split_and_stops():
    rows = parse_get_fare(_yatra_payload(), "DEL-BOM")
    r = next(x for x in rows if x["carrier"] == "6E")   # IndiGo routes via AMD in the fixture
    assert r["price"] == 6090
    assert r["base_fare"] == 4521
    assert r["taxes"] == r["price"] - r["base_fare"]
    assert r["stops"] == 1
    assert r["departure_ts"].startswith("2026-10-0")
    qp = next(x for x in rows if x["carrier"] == "QP")
    assert qp["stops"] == 0                             # Akasa nonstop


def test_yatra_rejects_error_and_wrong_route():
    assert parse_get_fare({"isError": True, "day": {}}, "DEL-BOM") == []
    assert parse_get_fare(_yatra_payload(), "MAA-CCU") == []


# --- Akasa: real Navitaire availability payload ---------------------------
def _akasa_payload():
    return json.loads((FIXTURES / "akasa_availability.json").read_text())


def test_akasa_parse_availability():
    rows = parse_availability(_akasa_payload(), "DEL-BOM", OCT2)
    # DEL|BOM (6) + DEL|NMI (3) + DXN|NMI (1) — all Delhi↔Mumbai metro
    assert len(rows) == 10
    assert all(r["carrier"] == "QP" and r["source"] == "akasa" for r in rows)
    r = min(rows, key=lambda x: x["price"])
    assert r["flight_no"].startswith("QP-")
    assert r["price"] > 0
    assert any(x["stops"] == 0 for x in rows)      # at least one nonstop


def test_akasa_breaks_out_udf():
    rows = parse_availability(_akasa_payload(), "DEL-BOM", OCT2)
    r = next(x for x in rows if x["base_fare"] and x["udf"])
    assert r["base_fare"] > 0
    assert r["udf"] > 0
    # base + taxes + udf reconciles to the total
    assert r["base_fare"] + r["taxes"] + r["udf"] == r["price"]


def test_akasa_rejects_wrong_route():
    assert parse_availability(_akasa_payload(), "BLR-CCU", OCT2) == []
    assert parse_availability({}, "DEL-BOM", OCT2) == []
