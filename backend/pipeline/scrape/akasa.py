"""
Akasa Air (akasaair.com) adapter — COMPLETE (direct API).

Recon (2026-09, HAR): Akasa runs Navitaire, same family as IndiGo / SpiceJet.
Its booking front-end calls one endpoint, **no auth, no token**:

    POST https://prod-bl.qp.akasaair.com/api/ibe/availability/search
    body {"criteria":[{"stations":{"originStationCodes":["DEL"],
            "destinationStationCodes":["BOM"],"searchDestinationMacs":true,
            "searchOriginMacs":true},"dates":{"beginDate":"YYYY-MM-DDT00:00:00"},
          "filters":{"compressionType":1,"maxConnections":8,
            "productClasses":["NB","LB","EC","AV"],"fareTypes":["NB","LB","R","V"]}}],
          "passengers":{"types":[{"type":"ADT","count":1}],"residentCountry":""},
          "codes":{"currencyCode":"INR","currentSourceOrganization":"QPGGLEMETA",
            "promotionCode":""},"numberOfFaresPerJourney":10,"taxesAndFees":1}

Response:
  data.results[0].trips[].journeysAvailableByMarket[] -> {key:"DEL|NMI", value:[journeys]}
    journey.designator {origin,destination,departure}
    journey.segments[0].identifier {identifier, carrierCode}
    journey.fares[].fareAvailabilityKey  -> data.faresAvailable
  data.faresAvailable[]  {key, value.fares[].passengerFares[]}
    .fareAmount                                 total
    .serviceCharges[] type=FarePrice            base
                      type=Tax                  tax
                      type=TravelFee code=UDF|DUDF   user-development fee
                      (CUTE/RCS/WFE/ASF are other statutory fees)

robots.txt (`www.akasaair.com`): allow-all.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from pipeline.geo import same_metro
from pipeline.scrape.apibase import ApiSourceAdapter

_URL = "https://prod-bl.qp.akasaair.com/api/ibe/availability/search"


class AkasaAdapter(ApiSourceAdapter):
    name = "akasa"
    base_domain = "prod-bl.qp.akasaair.com"
    robots_policy_url = "https://www.akasaair.com/book-flight-tickets/flight-search"

    async def fetch_raw(
        self, client: httpx.AsyncClient, corridor: str, day: date
    ) -> list[dict]:
        o, d = corridor.upper().split("-")
        resp = await client.post(
            _URL,
            json={
                "criteria": [{
                    "stations": {
                        "originStationCodes": [o], "destinationStationCodes": [d],
                        "searchDestinationMacs": True, "searchOriginMacs": True,
                    },
                    "dates": {"beginDate": f"{day.isoformat()}T00:00:00"},
                    "filters": {
                        "compressionType": 1, "maxConnections": 8,
                        "productClasses": ["NB", "LB", "EC", "AV"],
                        "fareTypes": ["NB", "LB", "R", "V"],
                    },
                }],
                "passengers": {"types": [{"type": "ADT", "count": 1}], "residentCountry": ""},
                "codes": {
                    "currencyCode": "INR",
                    "currentSourceOrganization": "QPGGLEMETA",
                    "promotionCode": "",
                },
                "offerCode": None,
                "numberOfFaresPerJourney": 10,
                "taxesAndFees": 1,
            },
            headers={"content-type": "application/json",
                     "origin": "https://www.akasaair.com",
                     "referer": "https://www.akasaair.com/"},
        )
        self._raise_if_blocked(resp)
        resp.raise_for_status()
        return parse_availability(resp.json(), corridor, day)


# --------------------------------------------------------------------------
#  pure parser — unit-tested against a captured payload
# --------------------------------------------------------------------------
def _price_map(fares_available: Any) -> dict[str, dict]:
    """fareAvailabilityKey -> cheapest {total, base, taxes, udf}."""
    if isinstance(fares_available, list):
        pairs = [(e.get("key"), e.get("value")) for e in fares_available if isinstance(e, dict)]
    elif isinstance(fares_available, dict):
        pairs = list(fares_available.items())
    else:
        return {}

    out: dict[str, dict] = {}
    for key, val in pairs:
        best: dict | None = None
        for fare in (val or {}).get("fares") or []:
            for pf in fare.get("passengerFares") or []:
                total = pf.get("fareAmount")
                if not total:
                    continue
                base = udf = 0.0
                for sc in pf.get("serviceCharges") or []:
                    amt = sc.get("amount") or 0
                    if sc.get("type") == "FarePrice":
                        base += amt
                    elif sc.get("code") in ("UDF", "DUDF"):
                        udf += amt
                row = {
                    "total": round(total),
                    "base": round(base) or None,
                    "udf": round(udf) or None,
                    # everything that isn't base or UDF (Tax + CUTE/RCS/WFE/ASF)
                    "taxes": round(total - base - udf) if base else None,
                }
                if best is None or row["total"] < best["total"]:
                    best = row
        if best and key:
            out[key] = best
    return out


def parse_availability(payload: Any, corridor: str, day: date) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or {}
    prices = _price_map(data.get("faresAvailable"))
    o_want, d_want = corridor.upper().split("-")

    rows: list[dict] = []
    for result in data.get("results") or []:
        for trip in result.get("trips") or []:
            for market in trip.get("journeysAvailableByMarket") or []:
                for j in market.get("value") or []:
                    desg = j.get("designator") or {}
                    if not (same_metro(desg.get("origin", ""), o_want)
                            and same_metro(desg.get("destination", ""), d_want)):
                        continue
                    keys = [f.get("fareAvailabilityKey") for f in (j.get("fares") or [])]
                    priced = [prices[k] for k in keys if k in prices]
                    if not priced:
                        continue
                    cheapest = min(priced, key=lambda p: p["total"])

                    seg0 = (j.get("segments") or [{}])[0]
                    ident = seg0.get("identifier") or {}
                    carrier = ident.get("carrierCode") or "QP"
                    num = ident.get("identifier")
                    n_seg = len(j.get("segments") or [])
                    dep = desg.get("departure") or day.isoformat()
                    if len(dep) == 19 and "+" not in dep:   # naive IST -> tag it
                        dep += "+05:30"
                    rows.append({
                        "route": corridor,
                        "carrier": carrier,
                        "flight_no": f"{carrier}-{num}" if num else None,
                        "departure_ts": dep,
                        "price": cheapest["total"],
                        "base_fare": cheapest["base"],
                        "taxes": cheapest["taxes"],
                        "udf": cheapest["udf"],
                        "cabin": "economy",   # Akasa domestic is single-class
                        "stops": max(0, n_seg - 1),
                        "source": "akasa",
                        "source_type": "airline",
                    })
    return rows
