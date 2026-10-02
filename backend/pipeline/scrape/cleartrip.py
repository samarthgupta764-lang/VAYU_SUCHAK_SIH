"""
Cleartrip adapter — COMPLETE.

Recon (2026-09, DEL->BOM; re-verified 2026-09-10 against a fresh HAR, depart
02/10/2026): Cleartrip's SPA loads its fare list from its own JSON endpoint —
plain GET, 200, no Authorization, no Cookie:

    GET https://www.cleartrip.com/flight/search/v2
        ?from=DEL&source_header=DEL&to=BOM&destination_header=BOM
        &depart_date=02%2F10%2F2026&class=Economy&adults=1&childs=0&infants=0
        &responseType=jsonV3&source=DESKTOP&utm_currency=INR&intl=n
        &multiFare=true&filterVersion=v2&isWP=true
        (SPA also tacks on mobileApp=true&isFFSC=true&cfw=false&return_date=
         &carrier= — we don't build this URL, we intercept the response, so
         the exact param set doesn't matter)

Returns every itinerary card incl. 1-stop connections (stops = segments - 1),
same as the airindia / akasa / yatra / googleflights adapters — no nonstop
filter. Downstream (index_engine) takes an IQR-trimmed median, so connecting
outliers wash out there, not here.

Response shape:
    cards.J1[]            one per itinerary card
      .summary.flights[0] {airlineCode, flightNumber}
      .summary.firstDeparture.airport.time   ISO 8601
      .summary.totalDuration {hh, mm}
      .summary.stops
      .subTravelOptionIds[0]  -> key into subTravelOptions
    subTravelOptions[stoid].cabinClassSummary.ECONOMY.minCabinPrice   <- INR fare

The base adapter intercepts the response during page load; parse_xhr maps it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.scrape.base import SourceAdapter


class CleartripAdapter(SourceAdapter):
    name = "cleartrip"
    base_domain = "www.cleartrip.com"
    results_ready_selector = "[data-testid='flight-card'], [class*='SearchResult'], main"

    def search_url(self, corridor: str, day: date) -> str:
        o, d = corridor.upper().split("-")
        dd = day.strftime("%d/%m/%Y")
        return (
            f"https://www.cleartrip.com/flights/results?adults=1&childs=0&infants=0"
            f"&class=Economy&depart_date={dd}&from={o}&to={d}&intl=n"
        )

    def is_fare_xhr(self, url: str, content_type: str) -> bool:
        return "/flight/search/v2" in url and "cleartrip.com" in url

    def parse_xhr(self, payload: Any, corridor: str, day: date) -> list[dict]:  # noqa: ARG002
        if not isinstance(payload, dict):
            return []
        cards = (payload.get("cards") or {}).get("J1") or []
        stos = payload.get("subTravelOptions") or {}
        rows: list[dict] = []
        for c in cards:
            summary = c.get("summary") or {}
            flights = summary.get("flights") or []
            if not flights:
                continue
            first = flights[0]

            price = None
            has_option = False
            for stoid in c.get("subTravelOptionIds") or []:
                sto = stos.get(stoid) or {}
                has_option = has_option or bool(sto)
                cabin = (sto.get("cabinClassSummary") or {}).get("ECONOMY") or {}
                p = cabin.get("minCabinPrice")
                if p:
                    price = p if price is None else min(price, p)

            # a card with itinerary + fare options but no economy price is a
            # shown-but-unavailable flight — keep it as a sold-out signal
            sold_out = price is None and has_option
            if price is None and not sold_out:
                continue

            dep = ((summary.get("firstDeparture") or {}).get("airport") or {}).get("time")
            dur = summary.get("totalDuration") or {}
            rows.append(
                {
                    "route": corridor,
                    "airline": first.get("airlineCode") or "NA",
                    "flight_no": f"{first.get('airlineCode', '')}-{first.get('flightNumber', '')}".strip("-"),
                    "price": price or 0,
                    "is_sold_out": 1 if sold_out else 0,
                    "departure_ts": dep or day.isoformat(),
                    "duration_minutes": int(dur.get("hh", 0)) * 60 + int(dur.get("mm", 0)) or None,
                    "stops": summary.get("stops"),
                    "source": self.name,
                }
            )
        return rows
