"""CSV sanitiser — the original scraper cleaning logic, now behind /api/import-csv."""

from pipeline.clean import clean_duration, clean_price, clean_stops, sanitize_rows


def test_field_cleaners():
    assert clean_price("₹4,820") == 4820
    assert clean_price("4380") == 4380
    assert clean_duration("2h 35m") == 155
    assert clean_duration("45m") == 45
    assert clean_stops("Non-stop") == 0
    assert clean_stops("1 stop") == 1


def test_sanitize_rows_end_to_end():
    rows = [
        {"airline": "IndiGo", "flight_no": "6E-2341", "route": "DEL-BOM",
         "departure_ts": "2026-11-08T06:15", "fare": "₹4,820"},
        {"airline": "Air India", "flight_no": "AI-887", "route": "DEL-BOM",
         "departure_ts": "2026-11-08T09:00", "fare": "5230"},
        {"airline": "IndiGo", "flight_no": "6E-090", "route": "DEL-BOM",
         "departure_ts": "2026-11-29T23:30", "fare": "0"},            # null-as-0 -> invalid
        {"airline": "IndiGo", "flight_no": "6E-2341", "route": "DEL-BOM",
         "departure_ts": "2026-11-08T06:15", "fare": "4820"},          # duplicate flight_id
        {"airline": "", "flight_no": "", "route": "not-a-route",
         "departure_ts": "2026-11-08T06:15", "fare": "5000"},          # bad route -> rejected
    ]
    records, report, rejected = sanitize_rows(rows)
    ids = {r.flight_id for r in records}
    assert len(records) == 2
    assert report.rows_in if hasattr(report, "rows_in") else True
    d = report.to_dict()
    assert d["rows_in"] == 5
    assert d["records_out"] == 2
    assert d["removed_invalid_values"] == 1     # the 0 fare
    assert d["removed_duplicates"] == 1
    assert d["removed_missing_required"] == 1   # bad route
