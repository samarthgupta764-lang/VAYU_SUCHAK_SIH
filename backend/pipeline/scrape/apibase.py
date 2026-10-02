"""
ApiSourceAdapter — base for sources we read through their own JSON API rather
than a headless browser.

Some airline sites (Air India) expose the exact fare endpoint their own
front-end calls, with no bot wall — a direct `httpx` request is faster, lighter
and far more stable than driving Chromium. Such an adapter implements one
method, `fetch_raw(client, corridor, day) -> list[dict]`, and the base class
owns everything else the Playwright `SourceAdapter` also owns: robots.txt,
per-domain rate limiting, timeout + retry with backoff, HTTP/2, anti-bot
detection, and normalisation to `FareRecord`.

The pool treats an `ApiSourceAdapter` and a `SourceAdapter` identically — both
expose `name` and `async scrape(corridor, days) -> ScrapeOutput`.
"""

from __future__ import annotations

import abc
import asyncio
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from config import settings
from pipeline.contract import normalise_many
from pipeline.scrape import ratelimit
from pipeline.scrape.base import Blocked, RateLimited, ScrapeOutput, SourceStatus

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)

def _parse_retry_after(resp: httpx.Response) -> float:
    """RFC 9110 §10.2.3 — either delay-seconds or an HTTP-date. Falls back to
    the configured cap when the header is absent or malformed, so a site that
    sends a 429 with no guidance still gets a sane, bounded backoff rather
    than the old blind exponential one."""
    raw = resp.headers.get("retry-after")
    cap = settings.scrape_retry_after_cap_s
    if not raw:
        return cap
    raw = raw.strip()
    if raw.isdigit():
        return min(float(raw), cap)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, min((dt - datetime.now(timezone.utc)).total_seconds(), cap))
    except (TypeError, ValueError):
        return cap


# shared browser-shaped headers; an adapter merges its own on top
BASE_HEADERS: dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": _UA,
    "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


class ApiSourceAdapter(abc.ABC):
    name: str = "apibase"
    base_domain: str = ""            # host we actually call — the rate-limit key
    # URL whose host's robots.txt is the airline's published crawl policy. The
    # API is often on a separate CDN edge whose /robots.txt is a 404 or a bot
    # wall; the authoritative policy lives on the main www host. Defaults to
    # base_domain when a subclass doesn't set it.
    robots_policy_url: str = ""

    # ---- subclass responsibility ---------------------------------------
    @abc.abstractmethod
    async def fetch_raw(
        self, client: httpx.AsyncClient, corridor: str, day: date
    ) -> list[dict]:
        """One API round-trip for (corridor, day) -> loosely-shaped fare dicts."""

    async def fetch_all(
        self, client: httpx.AsyncClient, corridor: str, days: list[date]
    ) -> list[dict] | None:
        """
        Optional: fetch every requested day in ONE request (some endpoints take a
        date range). Return the rows, or None to fall back to per-day `fetch_raw`.
        Rows for departure dates not in `days` are filtered out by the caller.
        """
        return None

    async def prepare(self, client: httpx.AsyncClient, corridor: str) -> None:
        """Optional one-time setup per run (e.g. mint a guest session token)."""
        return

    # ---- driver -------------------------------------------------------
    async def scrape(self, corridor: str, days: list[date]) -> ScrapeOutput:
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        st = SourceStatus(source=self.name, extraction_path="api")

        policy = self.robots_policy_url or f"https://{self.base_domain}/"
        if not await ratelimit.allowed_by_robots(policy):
            st.status = "unavailable"
            st.detail = f"robots.txt policy ({policy}) disallows or is unverifiable"
            return ScrapeOutput([], st)

        raw: list[dict] = []
        try:
            async with httpx.AsyncClient(
                http2=True,
                timeout=httpx.Timeout(settings.scrape_page_timeout_ms / 1000),
                headers=BASE_HEADERS,
                follow_redirects=True,
            ) as client:
                await ratelimit.acquire(f"https://{self.base_domain}/")
                await self.prepare(client, corridor)
                await ratelimit.acquire(f"https://{self.base_domain}/")
                ranged = await self._fetch_all_with_retry(client, corridor, days)
                if ranged is not None:
                    wanted = {d.isoformat() for d in days}
                    raw = [r for r in ranged if str(r.get("departure_ts", ""))[:10] in wanted]
                else:
                    for day in days:
                        raw.extend(await self._one_day(client, corridor, day))
        except Blocked as exc:
            st.status = "blocked"
            st.detail = str(exc)
            return ScrapeOutput([], st)
        except RateLimited as exc:
            # every retry-after wait was honoured and it's still 429ing —
            # genuinely rate limited for this run, not a policy block.
            st.status = "degraded"
            st.detail = f"still rate-limited after retrying: {exc}"
            return ScrapeOutput([], st)
        except Exception as exc:  # noqa: BLE001 — degrade, never crash the run
            st.status = "error"
            st.detail = f"{type(exc).__name__}: {exc}"
            return ScrapeOutput([], st)

        records, _rejected = normalise_many(raw, ingestion_source="live_scrape")
        st.fares = len(records)
        st.latency_ms = int((loop.time() - t0) * 1000)
        st.status = "ok" if records else "degraded"
        if not records and not st.detail:
            st.detail = "0 fares — check fetch_raw mapping for this source"
        return ScrapeOutput(records, st)

    async def _fetch_all_with_retry(
        self, client: httpx.AsyncClient, corridor: str, days: list[date]
    ) -> list[dict] | None:
        """Same Retry-After courtesy as _one_day, for the ranged (fetch_all)
        path — a single extra attempt, since a ranged call already covers
        every day in one request so there's nothing to gain from more."""
        try:
            return await self.fetch_all(client, corridor, days)
        except RateLimited as exc:
            await asyncio.sleep(exc.retry_after)
            await ratelimit.acquire(f"https://{self.base_domain}/")
            return await self.fetch_all(client, corridor, days)

    async def _one_day(
        self, client: httpx.AsyncClient, corridor: str, day: date
    ) -> list[dict]:
        attempts = settings.scrape_retries + 1
        for attempt in range(attempts):
            await ratelimit.acquire(f"https://{self.base_domain}/")
            try:
                return await self.fetch_raw(client, corridor, day)
            except Blocked:
                raise
            except RateLimited as exc:
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(exc.retry_after)
            except (httpx.HTTPError, ValueError, KeyError):
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(2**attempt)
        return []

    @staticmethod
    def _raise_if_blocked(resp: httpx.Response) -> None:
        # 429 means "slow down", not "go away" — distinct from a real block
        # (403 / captcha) so the caller can retry instead of giving up on
        # the whole source for this run.
        if resp.status_code == 429:
            raise RateLimited(
                f"HTTP 429 from {resp.request.url.host}", retry_after=_parse_retry_after(resp)
            )
        if resp.status_code == 403 or (
            resp.status_code == 200
            and "captcha" in resp.text[:2000].lower()
        ):
            raise Blocked(f"HTTP {resp.status_code} from {resp.request.url.host}")
