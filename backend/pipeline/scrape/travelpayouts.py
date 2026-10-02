"""
Tier-1 fallback — Travelpayouts (Aviasales) data API.

When a live scrape is blocked or returns nothing for a route, this fills that
route from `api.travelpayouts.com`, mapped into the FareRecord contract with
currency normalised to INR. Token lives in `.env`; if it's missing this whole
tier is skipped and ingest falls straight through to the on-disk cache.

Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163
Endpoint used: /aviasales/v3/prices_for_dates  (cheapest fare per date)
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from config import settings
from pipeline.contract import FareRecord, normalise_many

_BASE = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


class TravelpayoutsError(RuntimeError):
    pass


async def fetch(corridor: str, days: list[date]) -> tuple[list[FareRecord], str]:
    """
    -> (records, note). Raises TravelpayoutsError on hard failure so the caller
    can drop to the cache tier.
    """
    if not settings.travelpayouts_enabled:
        raise TravelpayoutsError("no TRAVELPAYOUTS_TOKEN configured")

    origin, destination = corridor.upper().split("-")
    params = {
        "origin": origin,
        "destination": destination,
        "currency": "inr",
        "token": settings.travelpayouts_token,
        "unique": "false",
        "sorting": "price",
        "limit": 1000,
    }
    if days:
        params["departure_at"] = min(days).strftime("%Y-%m")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TravelpayoutsError(f"request failed: {exc}") from exc

    if not body.get("success", True):
        raise TravelpayoutsError(f"api error: {body.get('error', 'unknown')}")

    wanted = {d.isoformat() for d in days} if days else None
    rows: list[dict[str, Any]] = []
    for item in body.get("data", []):
        dep = str(item.get("departure_at", ""))[:10]
        if wanted and dep not in wanted:
            continue
        rows.append(
            {
                "route": corridor,
                "airline": item.get("airline", "NA"),
                "flight_no": item.get("flight_number"),
                "price": item.get("price"),
                "departure_ts": item.get("departure_at") or dep,
                "source": "travelpayouts",
            }
        )

    records, _ = normalise_many(rows, ingestion_source="travelpayouts")
    return records, f"travelpayouts: {len(records)} fares for {corridor}"
