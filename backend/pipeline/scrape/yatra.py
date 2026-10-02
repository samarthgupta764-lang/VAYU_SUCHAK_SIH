"""
Yatra (yatra.com) adapter — COMPLETE (direct API, ranged).

Recon (2026-09, HAR): Yatra's search UI reads a compact "lowest fare per
carrier per date" feed:

    GET https://flight.yatra.com/lowest-fare-service/dom2/get-fare
        ?origin=DEL&destination=BOM&from=DD-MM-YYYY&to=DD-MM-YYYY
        &tripType=O&airlines=all&_i=<epoch-ms>&src=srp
    Referer: https://flight.yatra.com/air-search-ui/dom2/trigger?flex=0

The body is a JSON *string* (double-decode). Shape:

    { "day": { "2026-10-05": { "af": {
        "6E": { "tf": 6090, "bf": 4521, "ow": [
            { "dac":"DEL","aac":"BOM","fl":353,"ac":"6E","an":"IndiGo",
              "ddt":"2026-10-05 03:00","adt":"2026-10-05 05:20",
              "cabin":"Economy","rbd":"R" } ] } } } } }

One GET covers a whole date range and **every carrier** — including IndiGo,
SpiceJet and Air India Express, whose own sites we don't scrape. `tf` = total,
`bf` = base, so we get the base/total split too. It is the *cheapest* fare per
carrier per day, not every flight — the cleanest possible "what a traveller
pays" signal for the index.

robots.txt (`flight.yatra.com`): `Allow: /`; `/lowest-fare-service/` is not
disallowed.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any

import httpx

from pipeline.geo import same_metro
from pipeline.scrape.apibase import ApiSourceAdapter

_URL = "https://flight.yatra.com/lowest-fare-service/dom2/get-fare"


class YatraAdapter(ApiSourceAdapter):
    name = "yatra"
    base_domain = "flight.yatra.com"
    robots_policy_url = _URL

    async def fetch_all(
        self, client: httpx.AsyncClient, corridor: str, days: list[date]
    ) -> list[dict] | None:
        o, d = corridor.upper().split("-")
        lo, hi = min(days), max(days)
        resp = await client.get(
            _URL,
            params={
                "origin": o,
                "destination": d,
                "from": lo.strftime("%d-%m-%Y"),
                "to": hi.strftime("%d-%m-%Y"),
                "tripType": "O",
                "airlines": "all",
                "_i": str(int(time.time() * 1000)),
                "src": "srp",
            },
            headers={"referer": "https://flight.yatra.com/air-search-ui/dom2/trigger?flex=0"},
        )
        self._raise_if_blocked(resp)
        resp.raise_for_status()
        try:
            payload = json.loads(resp.json())          # body is a JSON string
        except (ValueError, TypeError):
            payload = json.loads(resp.text)
        return parse_get_fare(payload, corridor)

    async def fetch_raw(
        self, client: httpx.AsyncClient, corridor: str, day: date
    ) -> list[dict]:
        return await self.fetch_all(client, corridor, [day]) or []


# --------------------------------------------------------------------------
#  pure parser — unit-tested against a captured payload
# --------------------------------------------------------------------------
def _iso(ddt: str) -> str | None:
    """'2026-10-05 19:55' -> '2026-10-05T19:55:00+05:30'."""
    try:
        return datetime.strptime(ddt.strip(), "%Y-%m-%d %H:%M").isoformat() + "+05:30"
    except (ValueError, AttributeError):
        return None


def parse_get_fare(payload: Any, corridor: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("isError"):
        return []
    o_want, d_want = corridor.upper().split("-")
    rows: list[dict] = []
    for _date_str, info in (payload.get("day") or {}).items():
        for carrier_key, fare in (info.get("af") or {}).items():
            ow = fare.get("ow") or []
            if not ow:
                continue
            if not (same_metro(ow[0].get("dac", ""), o_want)
                    and same_metro(ow[-1].get("aac", ""), d_want)):
                continue  # a routing that isn't this city pair
            carrier = carrier_key or ow[0].get("ac") or "NA"
            total, base = fare.get("tf"), fare.get("bf")
            dep = _iso(ow[0].get("ddt", ""))
            if not (total and dep):
                continue
            fl = ow[0].get("fl")
            rows.append({
                "route": corridor,
                "carrier": carrier,
                "flight_no": f"{carrier}-{fl}" if fl else None,
                "departure_ts": dep,
                "price": total,
                "base_fare": base,
                # Yatra lumps taxes + statutory fees; store the remainder as taxes
                "taxes": round(total - base) if (base and total > base) else None,
                "cabin": ow[0].get("cabin") or "economy",
                "stops": max(0, len(ow) - 1),
                "source": "yatra",
                "source_type": "ota",
            })
    return rows
