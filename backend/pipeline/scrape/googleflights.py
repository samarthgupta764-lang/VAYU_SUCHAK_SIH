"""
Google Flights adapter — COMPLETE (DOM extraction).

Google Flights has no clean public fare JSON (results arrive via an obfuscated
`batchexecute` RPC), so this adapter reads the rendered result list. Recon
(2026-09, DEL->BOM): each result is a `<li>` inside `[role="main"]` carrying a
child element whose aria-label is a full sentence:

    "From 6314 Indian rupees. Nonstop flight with Air India. Leaves Indira
     Gandhi International Airport at 5:00 AM on Friday, September 25 and arrives
     ... Total duration 2 hr 20 min. Select flight"

Everything we need is in that string. Google Flights does not expose flight
numbers in the list, so `flight_number` is left None (flight_id falls back to
airline+price+date). Matches the `gflights` source already in data/samples/.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pipeline.scrape.base import SourceAdapter

_PRICE = re.compile(r"From\s+([\d,]+)\s+Indian rupees", re.I)
_AIRLINE = re.compile(r"flight with ([A-Za-z0-9 ().'-]+?)\.\s", re.I)
_STOPS = re.compile(r"(Nonstop|(\d+)\s+stop)", re.I)
_DEP = re.compile(r"Leaves .*? at (\d{1,2}:\d{2}\s*[AP]M) on", re.I)
_ARR_NEXTDAY = re.compile(r"arrives .*? on \w+, \w+ (\d+)", re.I)
_DUR = re.compile(r"Total duration (\d+)\s*hr(?:\s*(\d+)\s*min)?", re.I)


class GoogleFlightsAdapter(SourceAdapter):
    name = "googleflights"
    base_domain = "www.google.com"
    results_ready_selector = "[role='main'] li"

    def search_url(self, corridor: str, day: date) -> str:
        o, d = corridor.upper().split("-")
        return (
            "https://www.google.com/travel/flights?q="
            f"Flights%20from%20{o}%20to%20{d}%20on%20{day.isoformat()}%20oneway"
        )

    def is_fare_xhr(self, url: str, content_type: str) -> bool:  # noqa: ARG002
        return False  # DOM-only

    def parse_xhr(self, payload: Any, corridor: str, day: date) -> list[dict]:  # noqa: ARG002
        return []

    async def parse_dom(self, page: Any, corridor: str, day: date) -> list[dict]:
        sel = "[role='main'] [aria-label*='Select flight']"
        try:
            await page.wait_for_selector(sel, timeout=15000)
        except Exception:  # noqa: BLE001
            return []
        labels: list[str] = await page.eval_on_selector_all(
            sel, "els => els.map(e => e.getAttribute('aria-label'))"
        )
        seen: set[tuple] = set()
        rows: list[dict] = []
        for text in labels:
            row = _parse_label(text or "", corridor, day)
            if not row:
                continue
            key = (row["airline"], row["price"], row["departure_ts"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        return rows


def _parse_label(text: str, corridor: str, day: date) -> dict | None:
    text = re.sub(r"\s+", " ", text or "").strip()  # collapse narrow/no-break spaces
    pm = _PRICE.search(text)
    if not pm:
        return None
    price = int(pm.group(1).replace(",", ""))

    am = _AIRLINE.search(text)
    airline = am.group(1).strip() if am else "NA"

    sm = _STOPS.search(text)
    stops = 0 if (sm and sm.group(1).lower() == "nonstop") else (int(sm.group(2)) if sm and sm.group(2) else None)

    dm = _DEP.search(text)
    dep_iso = day.isoformat()
    if dm:
        try:
            t = datetime.strptime(dm.group(1).replace(" ", ""), "%I:%M%p")
            dep_iso = datetime(day.year, day.month, day.day, t.hour, t.minute).isoformat() + "+05:30"
        except ValueError:
            pass

    um = _DUR.search(text)
    dur_min = (int(um.group(1)) * 60 + int(um.group(2) or 0)) if um else None

    return {
        "route": corridor,
        "airline": airline,
        "flight_no": None,
        "price": price,
        "departure_ts": dep_iso,
        "duration_minutes": dur_min,
        "stops": stops,
        "source": "googleflights",
    }
