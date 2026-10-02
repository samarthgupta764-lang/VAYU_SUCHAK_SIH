"""
Shared base for the five not-yet-recon'd adapters.

Each concrete stub only needs to declare its domain and the URL/XHR hints it
already knows. `parse_xhr` returns [] until a real fare-JSON shape is filled in,
which makes the pool log the source as `degraded` (0 fares) and the ingest
fallback chain cover it from Travelpayouts / cache. Nothing crashes.

RECON CHECKLIST for turning a stub into a real adapter
-----------------------------------------------------
1. Open the site, search one route (e.g. DEL -> BOM), open DevTools > Network.
2. Filter to XHR/Fetch. Find the response that carries the fare list (JSON).
   -> copy its URL pattern into `is_fare_xhr`
   -> copy a sample response, map its fields in `parse_xhr`
3. Copy the browser's address-bar URL into `search_url` (parametrise from/to/date).
4. If the site has no clean fare JSON, implement `parse_dom` with CSS selectors
   instead (see ixigo.py for the pattern).
5. Delete the `RECON_PENDING = True` line.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.scrape.base import SourceAdapter


class StubAdapter(SourceAdapter):
    RECON_PENDING = True
    search_url_template = ""  # subclass fills, with {origin} {destination} {date}
    date_fmt = "%Y-%m-%d"
    xhr_hints: tuple[str, ...] = ()

    def search_url(self, corridor: str, day: date) -> str:
        origin, destination = corridor.upper().split("-")
        return self.search_url_template.format(
            origin=origin, destination=destination, date=day.strftime(self.date_fmt)
        )

    def is_fare_xhr(self, url: str, content_type: str) -> bool:
        if "json" not in content_type.lower():
            return False
        u = url.lower()
        return any(h in u for h in self.xhr_hints)

    def parse_xhr(self, payload: Any, corridor: str, day: date) -> list[dict]:  # noqa: ARG002
        # RECON PENDING — map the site's fare JSON here. See checklist above.
        return []
