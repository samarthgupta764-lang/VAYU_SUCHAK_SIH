"""
IndiGo (goindigo.in) adapter — parser kept, LIVE SCRAPING DISABLED (robots.txt).

Recon (2026-09, DEL->BOM HAR): IndiGo's SPA loads fares from its own JSON API,
`POST https://api-prod-flight-skyplus6e.goindigo.in/v2/flight/search`, with a
per-session `user_key` token minted behind Akamai Bot Manager on the booking
pages. Response shape:

    data.trips[0].journeysAvailable[]
      .stops, .flightType
      .designator {origin, destination, departure, arrival}
      .segments[0].identifier {identifier: "353", carrierCode: "6E"}
      .passengerFares[] {FareClass: "Economy"|"Business", totalFareAmount}

BUT `www.goindigo.in/robots.txt` has `Disallow: /book/*` and `Disallow:
/search.html` — the results flow. We honour that: `ROBOTS_DISALLOWED = True`
keeps the pool from scraping IndiGo live; it is served from cache /
Travelpayouts, and IndiGo *carrier* fares still enter the index via the
Cleartrip and Google Flights adapters (both robots-permitted, both list 6E
flights). `parse_search_response` below is retained and unit-tested so the
adapter is ready if MoSPI formalises access — flip the flag only with
permission.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.geo import same_metro
from pipeline.scrape._stub import StubAdapter


class IndiGoAdapter(StubAdapter):
    name = "indigo"
    base_domain = "www.goindigo.in"
    search_url_template = "https://www.goindigo.in/book/flight-select.html"
    date_fmt = "%Y-%m-%d"
    xhr_hints = ("/v2/flight/search",)
    ROBOTS_DISALLOWED = True  # /book/* and /search.html are Disallow-ed

    def parse_xhr(self, payload: Any, corridor: str, day: date) -> list[dict]:
        return parse_search_response(payload, corridor, day)


# --------------------------------------------------------------------------
#  pure parser — unit-tested against a captured payload
# --------------------------------------------------------------------------
def parse_search_response(payload: Any, corridor: str, day: date) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or {}
    trips = data.get("trips") or []
    if not trips:
        return []

    o_want, d_want = corridor.upper().split("-")
    rows: list[dict] = []
    for journey in trips[0].get("journeysAvailable") or []:
        desg = journey.get("designator") or {}
        if not (same_metro(desg.get("origin", ""), o_want)
                and same_metro(desg.get("destination", ""), d_want)):
            continue  # keep DXN/HDO (Delhi-area) & NMI (Mumbai) as the metro

        econ = [
            pf.get("totalFareAmount")
            for pf in journey.get("passengerFares") or []
            if pf.get("FareClass") == "Economy" and pf.get("totalFareAmount")
        ]
        if not econ:
            continue

        seg0 = (journey.get("segments") or [{}])[0]
        ident = seg0.get("identifier") or {}
        carrier = ident.get("carrierCode") or "6E"
        num = ident.get("identifier")
        rows.append(
            {
                "route": corridor,
                "airline": carrier,
                "flight_no": f"{carrier}-{num}" if num else None,
                "price": min(econ),
                "departure_ts": desg.get("departure") or day.isoformat(),
                "stops": journey.get("stops"),
                "source": "indigo",
            }
        )
    return rows
