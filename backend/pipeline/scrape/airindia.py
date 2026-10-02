"""
Air India (airindia.com) adapter — COMPLETE (direct API).

Recon (2026-09, DEL->BOM, HAR capture): Air India's booking front-end reads
fares from its own JSON API with no bot wall. Two calls:

  1. POST https://api.airindia.com/cbiz-booking/v2/prime/auth/token
     body {"originLocationCode","userToken":null,"clientId":"web-pb",
           "portalFacts":[{"key":"countryCode","value":"IN"}]}
     -> {"token": "<jwt>", "expiryDate", "journeyId"}   (guest, ~40 min TTL)

  2. POST https://api.airindia.com/cbiz-booking/v2/prime/search/air-bounds
     headers  Authorization: Bearer <jwt>   origincountrycode: IN
     body {"cabin":"ECONOMY","itineraries":[{"originLocationCode","destinationLocationCode",
           "departureDateTime":"YYYY-MM-DD","isRequestedBound":true}],
           "travelers":[{"passengerTypeCode":"ADT"}],"promotion":{"code":""}}

Response shape:
  responsePayload[0].airBoundGroups[]
    .boundDetails.segments[].flightId        -> key into dictionaries.flight
    .airBounds[]                              one per fare family
      .fareFamilyCode                         -> dictionaries.fareFamilyWithServices
      .prices.totalPrices[0].total            INR, incl. tax
  dictionaries.flight[flightId] {marketingAirlineCode, marketingFlightNumber,
     departure{locationCode,dateTime}, arrival{locationCode,dateTime}, duration}
  dictionaries.location[code].cityCode        -> maps NMI (Navi Mumbai) to BOM

We keep the cheapest ECONOMY fare per itinerary, match on *city* (so an
alternate airport serving the same metro still counts), and record stops.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from pipeline.scrape.apibase import ApiSourceAdapter

_HOST = "https://api.airindia.com"
_AUTH_URL = f"{_HOST}/cbiz-booking/v2/prime/auth/token"
_SEARCH_URL = f"{_HOST}/cbiz-booking/v2/prime/search/air-bounds"


class AirIndiaAdapter(ApiSourceAdapter):
    name = "airindia"
    base_domain = "api.airindia.com"
    # airindia.com/robots.txt disallows only /bin/, some DAM images and 3 named
    # pages — flight search is permitted. The API edge (api.airindia.com) serves
    # no usable robots.txt, so the www policy is authoritative.
    robots_policy_url = "https://www.airindia.com/in/en/book-flights.html"

    def __init__(self) -> None:
        self._token: str | None = None

    async def prepare(self, client: httpx.AsyncClient, corridor: str) -> None:
        origin = corridor.upper().split("-")[0].lower()
        resp = await client.post(
            _AUTH_URL,
            json={
                "originLocationCode": origin,
                "userToken": None,
                "clientId": "web-pb",
                "portalFacts": [{"key": "countryCode", "value": "IN"}],
            },
            headers={"content-type": "application/json", "origin": "https://www.airindia.com",
                     "referer": "https://www.airindia.com/"},
        )
        self._raise_if_blocked(resp)
        resp.raise_for_status()
        self._token = (resp.json() or {}).get("token")
        if not self._token:
            raise ValueError("air india: no guest token in auth response")

    async def fetch_raw(
        self, client: httpx.AsyncClient, corridor: str, day: date
    ) -> list[dict]:
        o, d = corridor.upper().split("-")
        resp = await client.post(
            _SEARCH_URL,
            json={
                "cabin": "ECONOMY",
                "itineraries": [
                    {
                        "originLocationCode": o.lower(),
                        "destinationLocationCode": d.lower(),
                        "departureDateTime": day.isoformat(),
                        "flexibility": None,
                        "isRequestedBound": True,
                    }
                ],
                "travelers": [{"passengerTypeCode": "ADT"}],
                "promotion": {"code": ""},
            },
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self._token}",
                "origincountrycode": "IN",
                "origin": "https://www.airindia.com",
                "referer": "https://www.airindia.com/",
            },
        )
        self._raise_if_blocked(resp)
        resp.raise_for_status()
        return parse_air_bounds(resp.json(), corridor, day)


# --------------------------------------------------------------------------
#  pure parser — unit-tested against a captured payload
# --------------------------------------------------------------------------
def parse_air_bounds(payload: Any, corridor: str, day: date) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    groups = _first(payload.get("responsePayload"), {}).get("airBoundGroups") or []
    dicts = payload.get("dictionaries") or {}
    flights = dicts.get("flight") or {}
    locations = dicts.get("location") or {}
    families = dicts.get("fareFamilyWithServices") or {}

    o_want, d_want = corridor.upper().split("-")

    def city(code: str) -> str:
        return (locations.get(code) or {}).get("cityCode") or code

    rows: list[dict] = []
    for g in groups:
        bd = g.get("boundDetails") or {}
        seg_ids = [s.get("flightId") for s in (bd.get("segments") or []) if s.get("flightId")]
        if not seg_ids:
            continue
        first = flights.get(seg_ids[0]) or {}
        last = flights.get(seg_ids[-1]) or {}
        if not first or not last:
            continue

        o_code = (first.get("departure") or {}).get("locationCode", "")
        d_code = (last.get("arrival") or {}).get("locationCode", "")
        if city(o_code) != o_want or city(d_code) != d_want:
            continue

        cheapest: dict | None = None
        for ab in g.get("airBounds") or []:
            ffc = ab.get("fareFamilyCode")
            fam = families.get(ffc) or {}
            avail = _first(ab.get("availabilityDetails"), {})
            # plain economy only — exclude "ecoPremium" (premium economy) and
            # "business" so the sample matches the base-year economy P0.
            cabin = fam.get("cabin") or avail.get("cabin")
            if cabin != "eco":
                continue
            tp = _first(ab.get("prices", {}).get("totalPrices"), {})
            total = tp.get("total")
            if total and (cheapest is None or total < cheapest["total"]):
                cheapest = tp
        if cheapest is None:
            continue

        airline = first.get("marketingAirlineCode") or "AI"
        num = first.get("marketingFlightNumber")
        dur = bd.get("duration") or first.get("duration")
        base = cheapest.get("base")
        total_taxes = cheapest.get("totalTaxes")
        total_fees = cheapest.get("totalFees")
        rows.append(
            {
                "route": corridor,
                "airline": airline,
                "flight_no": f"{airline}-{num}" if num else None,
                "base_fare": base,
                "taxes": total_taxes,
                "udf": total_fees,   # AI lumps UDF + statutory into totalFees
                "cabin": "economy",
                "price": cheapest["total"],
                "departure_ts": (first.get("departure") or {}).get("dateTime") or day.isoformat(),
                "duration_minutes": int(dur) // 60 if dur else None,
                "stops": max(0, len(seg_ids) - 1),
                "source": "airindia",
            }
        )
    return rows


def _first(seq: Any, default: Any) -> Any:
    return seq[0] if isinstance(seq, list) and seq else default
