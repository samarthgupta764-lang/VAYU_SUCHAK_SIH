"""
Ixigo adapter — parser kept, LIVE SCRAPING DISABLED (robots.txt).

Ixigo's robots.txt disallows `/search/result/` and `/flights/search` — exactly
the fare-search pages this adapter (and the original standalone script) used. We
honour that: `ROBOTS_DISALLOWED = True` makes the pool skip Ixigo live and serve
it from cache / Travelpayouts instead. (Python's `urllib.robotparser` actually
fails *open* on Ixigo's malformed file — a blank line after `User-agent: *` — so
pipeline/scrape/ratelimit.py hardens the check.)

The DOM/XHR parsers below are retained: they still work against Ixigo's
robots-permitted public fare pages (`/flights/<city-a>-<city-b>`), and are ready
if MoSPI formalises access. Flip `ROBOTS_DISALLOWED` off only with permission.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from config import settings
from pipeline.scrape.base import SourceAdapter

_DURATION_RE = re.compile(r"\d+h(\s*\d+m)?\b|\b\d+m\b")
_HHMM_RE = re.compile(r"(\d{1,2}):(\d{2})")


class IxigoAdapter(SourceAdapter):
    name = "ixigo"
    base_domain = "www.ixigo.com"
    results_ready_selector = '[data-testid="pricing"]'
    ROBOTS_DISALLOWED = True  # /search/result/ is Disallow-ed — see module docstring

    # ------------------------------------------------------------------ URL
    def search_url(self, corridor: str, day: date) -> str:
        origin, destination = corridor.upper().split("-")
        d = day.strftime("%d%m%Y")  # ixigo wants DDMMYYYY
        return (
            "https://www.ixigo.com/search/result/flight?"
            f"from={origin}&to={destination}&date={d}"
            "&adults=1&children=0&infants=0&class=e&source=Search+Form"
        )

    # ------------------------------------------------------------------ XHR
    def is_fare_xhr(self, url: str, content_type: str) -> bool:
        if "json" not in content_type.lower():
            return False
        u = url.lower()
        return "ixigo.com" in u and any(
            k in u for k in ("/search/", "/flight", "fare", "result", "listing")
        )

    def parse_xhr(self, payload: Any, corridor: str, day: date) -> list[dict]:
        """
        Best-effort walk of an Ixigo fare payload. Returns [] on an unrecognised
        shape so the driver falls through to parse_dom.
        """
        items = _find_flight_list(payload)
        rows: list[dict] = []
        for it in items:
            price = _dig(it, "fare", "price", "totalFare", "displayFare", "amount")
            if price is None:
                continue
            airline = _dig(it, "airlineCode", "airline", "carrier") or "NA"
            fno = _dig(it, "flightNumber", "flightNo", "number")
            dep = _dig(it, "departTime", "departureTime", "departure", "depTime")
            rows.append(
                {
                    "route": corridor,
                    "airline": str(airline),
                    "flight_no": str(fno) if fno else None,
                    "price": price,
                    "departure_ts": _iso(day, str(dep)) if dep else day.isoformat(),
                    "source": self.name,
                }
            )
        return rows

    # ------------------------------------------------------------------ DOM
    async def parse_dom(self, page: Any, corridor: str, day: date) -> list[dict]:
        seen: dict[str, dict] = {}
        empty_rounds = 0
        max_rounds = 60

        for round_num in range(max_rounds):
            cards = await page.query_selector_all(".shadow-card")
            new_this_round = 0

            for card in cards:
                price_el = await card.query_selector('[data-testid="pricing"]')
                if not price_el:
                    continue
                price_txt = await price_el.inner_text()

                airline_el = await card.query_selector(".airlineTruncate")
                airline = (await airline_el.inner_text()) if airline_el else "NA"

                fno_el = await card.query_selector(
                    "xpath=.//p[contains(@class,'airlineTruncate')]/following-sibling::p[1]"
                )
                flight_no = (await fno_el.inner_text()).strip() if fno_el else None

                key = flight_no or f"{airline}-{price_txt}-{round_num}"
                if key in seen:
                    continue

                time_els = await card.query_selector_all("h6.font-medium")
                dep_time = (await time_els[0].inner_text()) if len(time_els) > 0 else ""

                sec_els = await card.query_selector_all("p.text-secondary")
                sec_texts = [(await el.inner_text()).strip() for el in sec_els]
                duration, stops = _classify_secondary(sec_texts)

                seen[key] = {
                    "route": corridor,
                    "airline": airline.strip(),
                    "flight_no": flight_no,
                    "price": price_txt,
                    "departure_ts": _iso(day, dep_time),
                    "duration_minutes": duration,
                    "stops": stops,
                    "source": self.name,
                }
                new_this_round += 1

            if len(seen) >= settings.scrape_target_flights:
                break
            empty_rounds = empty_rounds + 1 if new_this_round == 0 else 0
            if empty_rounds >= 5:
                break

            if cards:
                await cards[-1].scroll_into_view_if_needed()
                await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(1800)

        return list(seen.values())


# --------------------------------------------------------------------------
#  helpers (module-level, pure)
# --------------------------------------------------------------------------
def _classify_secondary(texts: list[str]) -> tuple[int | None, int | None]:
    duration = stops = None
    for t in texts:
        low = t.lower()
        if _DURATION_RE.search(t):
            h = re.search(r"(\d+)h", t)
            m = re.search(r"(\d+)m", t)
            duration = (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)
        elif "non-stop" in low or "nonstop" in low:
            stops = 0
        elif "stop" in low:
            n = re.search(r"(\d+)\s*stop", low)
            stops = int(n.group(1)) if n else 1
    return duration, stops


def _iso(day: date, dep_time: str) -> str:
    """Combine the search day with a rendered 'HH:MM' into ISO 8601 (+05:30)."""
    m = _HHMM_RE.search(dep_time or "")
    if not m:
        return day.isoformat()
    hh, mm = int(m.group(1)), int(m.group(2))
    return datetime(day.year, day.month, day.day, hh, mm).isoformat() + "+05:30"


def _dig(obj: Any, *keys: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj and obj[k] not in (None, ""):
            return obj[k]
    return None


def _find_flight_list(payload: Any) -> list[dict]:
    """Depth-first search for the first list-of-dicts that looks like fares."""
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list) and cur and isinstance(cur[0], dict):
            keys = set(cur[0])
            if keys & {"fare", "price", "totalFare", "displayFare", "airlineCode", "flightNumber"}:
                return cur
            stack.extend(cur)
        elif isinstance(cur, dict):
            stack.extend(cur.values())
    return []
