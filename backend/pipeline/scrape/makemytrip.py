"""
MakeMyTrip adapter — RECON DONE, blocked headless.

Recon (2026-09): a headless browser hitting the results URL gets Akamai Bot
Manager's soft wall — the page renders "NETWORK PROBLEM / We are unable to
connect to our systems from your device" and the fare XHR never fires. The
`GvuchP8I/...` requests in the trace are Akamai sensor-data POSTs.

To finish this adapter you need one of:
  * a residential-IP / non-headless run (MMT is far more lenient there), then
    capture the fare list call — it is under `/api/flights-search/...` returning
    JSON; map it in parse_xhr below.
  * the mobile web endpoint (m.makemytrip.com) which is lighter.
  * accept that the pool runs without MMT (it already has ixigo + cleartrip +
    googleflights live, and MMT from cache).

search_url + selectors are correct; only parse_xhr / anti-bot remain.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.scrape._stub import StubAdapter


class MakeMyTripAdapter(StubAdapter):
    name = "makemytrip"
    base_domain = "www.makemytrip.com"
    results_ready_selector = "[data-cy='listingCard'], .listingCard, .fli-list"
    search_url_template = (
        "https://www.makemytrip.com/flight/search?itinerary={origin}-{destination}-{date}"
        "&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E"
    )
    date_fmt = "%d/%m/%Y"
    xhr_hints = ("flights-search", "listing", "clientbackend/flight", "fare")
    RECON_PENDING = True  # blocked headless — see module docstring
