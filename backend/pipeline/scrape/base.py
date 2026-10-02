"""
SourceAdapter — the uniform contract every scrape source implements.

A subclass supplies four things:
    name             : short source id  ("ixigo")
    search_url()      : build the fare-search URL for (corridor, date)
    is_fare_xhr()     : True if a captured response is the site's own fare JSON
    parse_xhr()       : that JSON  ->  list[dict] in the FareRecord shape

The base class owns everything else: the shared headless Chromium, per-page
timeout + retry with backoff, rate limiting, robots.txt, anti-bot detection,
CSS-selector fallback hook, and normalisation to FareRecord.

Playwright is imported lazily so the rest of the app (and the test suite) runs
even when browsers aren't installed.
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from config import settings
from pipeline.contract import FareRecord, normalise_many
from pipeline.scrape import ratelimit


class Blocked(RuntimeError):
    """Anti-bot / captcha / 403 detected — caller should trigger fallback."""


class RateLimited(RuntimeError):
    """HTTP 429 — the site is asking us to slow down, not refusing outright.
    Distinct from Blocked: retrying after the honoured wait is expected to
    succeed, so callers should back off and retry within their existing
    attempt budget rather than giving up immediately like they do for a real
    block (403 / captcha)."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(slots=True)
class SourceStatus:
    source: str
    status: str = "pending"        # ok | degraded | blocked | error | unavailable
    fares: int = 0
    latency_ms: int = 0
    extraction_path: str = "none"  # xhr | css | none
    detail: str = ""
    block_reason: str = ""         # robots | antibot | recon — why status == blocked/unavailable

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "fares": self.fares,
            "latency_ms": self.latency_ms,
            "extraction_path": self.extraction_path,
            "detail": self.detail,
            "block_reason": self.block_reason,
        }


@dataclass
class ScrapeOutput:
    records: list[FareRecord] = field(default_factory=list)
    status: SourceStatus | None = None


BLOCK_MARKERS = (
    "captcha",
    "unusual traffic",
    "are you a human",
    "access denied",
    "request blocked",
    "verify you are not a robot",
)


class SourceAdapter(abc.ABC):
    name: str = "base"
    base_domain: str = ""
    results_ready_selector: str = "body"

    # ---- subclass responsibilities --------------------------------------
    @abc.abstractmethod
    def search_url(self, corridor: str, day: date) -> str: ...

    @abc.abstractmethod
    def is_fare_xhr(self, url: str, content_type: str) -> bool: ...

    @abc.abstractmethod
    def parse_xhr(self, payload: Any, corridor: str, day: date) -> list[dict]: ...

    # optional CSS-selector fallback; return [] if not implemented
    async def parse_dom(self, page: Any, corridor: str, day: date) -> list[dict]:  # noqa: ARG002
        return []

    # ---- driver --------------------------------------------------------
    async def scrape(self, corridor: str, days: list[date], browser: Any | None = None) -> ScrapeOutput:
        """`browser`, when given, is a Playwright Browser the pool already
        launched and owns the lifecycle of (see pool.py) — reused across
        every Playwright adapter in one scrape_pool() call instead of each
        adapter paying its own ~200-500ms launch/close. A browser supports
        many concurrent contexts safely (that's what new_context() is for),
        so two adapters sharing one instance is the intended usage, not a
        shortcut. Falls back to launching (and closing) its own when not
        given — standalone/test use unaffected."""
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        st = SourceStatus(source=self.name)

        if getattr(self, "ROBOTS_DISALLOWED", False):
            # the site's robots.txt Disallow-s fare-search paths: a policy block.
            # surfaced as "blocked" so the dashboard shows the graceful-degrade story.
            st.status = "blocked"
            st.block_reason = "robots"
            st.detail = "robots.txt disallows fare-search crawling — routed via Yatra meta-feed + cache"
            return ScrapeOutput([], st)

        if getattr(self, "RECON_PENDING", False):
            st.status = "blocked"
            st.block_reason = "antibot"
            st.detail = "anti-bot wall (Akamai) on headless — adapter recon pending, served from cache"
            return ScrapeOutput([], st)

        if browser is None:
            try:
                from playwright.async_api import async_playwright  # lazy
            except ImportError:
                st.status = "unavailable"
                st.detail = "playwright not installed"
                return ScrapeOutput([], st)

        raw_rows: list[dict] = []
        try:
            async with self._browser_ctx(browser) as active_browser:
                for day in days:
                    rows, path = await self._scrape_one_day(active_browser, corridor, day)
                    raw_rows.extend(rows)
                    if path != "none":
                        st.extraction_path = path
        except Blocked as exc:
            st.status = "blocked"
            st.detail = str(exc)
            return ScrapeOutput([], st)
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the run
            st.status = "error"
            st.detail = f"{type(exc).__name__}: {exc}"
            return ScrapeOutput([], st)

        records, _rejected = normalise_many(raw_rows, ingestion_source="live_scrape")
        st.fares = len(records)
        st.latency_ms = int((loop.time() - t0) * 1000)
        st.status = "ok" if records else "degraded"
        if not records and not st.detail:
            st.detail = "0 fares — check search_url / is_fare_xhr for this source"
        return ScrapeOutput(records, st)

    @staticmethod
    @contextlib.asynccontextmanager
    async def _browser_ctx(shared: Any | None):
        """Yield `shared` as-is (pool.py owns launching/closing it) or, when
        None, launch+close a private Chromium for the duration — the only
        difference between the pool-shared and standalone code paths."""
        if shared is not None:
            yield shared
            return
        from playwright.async_api import async_playwright  # lazy

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.scrape_headless)
            try:
                yield browser
            finally:
                await browser.close()

    async def _scrape_one_day(self, browser: Any, corridor: str, day: date) -> tuple[list[dict], str]:
        url = self.search_url(corridor, day)
        if not await ratelimit.allowed_by_robots(url):
            raise Blocked(f"robots.txt disallows {url}")

        attempts = settings.scrape_retries + 1
        for attempt in range(attempts):
            await ratelimit.acquire(url)
            ctx = await browser.new_context(user_agent=ratelimit.pick_user_agent(attempt))
            page = await ctx.new_page()
            captured: list[Any] = []  # asyncio tasks resolving to parsed JSON (or None)
            fare_seen = asyncio.Event()

            async def _grab(resp: Any) -> Any:
                # read the raw body straight away and decode it ourselves —
                # resp.json() is lazy and Playwright evicts large/late bodies
                # (Cleartrip's is ~2 MB) before a deferred read gets to them.
                try:
                    return json.loads(await resp.body())
                except Exception:  # noqa: BLE001
                    return None

            def _on_response(resp: Any) -> None:
                ct = resp.headers.get("content-type", "")
                if self.is_fare_xhr(resp.url, ct):
                    captured.append(asyncio.ensure_future(_grab(resp)))
                    fare_seen.set()

            page.on("response", _on_response)
            try:
                # SPAs stream ads/analytics forever — don't wait for "load"
                await page.goto(url, timeout=settings.scrape_page_timeout_ms, wait_until="domcontentloaded")

                # block detection: only trust a SHORT page (a challenge/interstitial,
                # not a results page that merely mentions "captcha" in a script)
                with contextlib.suppress(Exception):
                    visible = (await page.inner_text("body")).lower()
                    if len(visible) < 2500 and any(m in visible for m in BLOCK_MARKERS):
                        raise Blocked(f"{self.name}: block/challenge page")

                # give the fare XHR a chance to fire before we look
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        fare_seen.wait(),
                        timeout=min(settings.scrape_page_timeout_ms, 20000) / 1000,
                    )
                with contextlib.suppress(Exception):
                    await page.wait_for_selector(
                        self.results_ready_selector, timeout=settings.scrape_page_timeout_ms
                    )

                # FAST path — the site's own fare JSON. Await every capture task
                # (bodies are read in _grab); newest first so a re-fired XHR wins.
                if captured:
                    with contextlib.suppress(Exception):
                        await asyncio.wait(captured, timeout=15)
                for task in reversed(captured):
                    with contextlib.suppress(Exception):
                        payload = task.result() if task.done() else await task
                        if payload is None:
                            continue
                        rows = self.parse_xhr(payload, corridor, day)
                        if rows:
                            return rows, "xhr"

                # FALLBACK path — CSS selectors on the rendered DOM
                rows = await self.parse_dom(page, corridor, day)
                return rows, ("css" if rows else "none")

            except Blocked:
                raise
            except Exception:
                if attempt == attempts - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # exponential backoff
            finally:
                await ctx.close()
        return [], "none"


# --------------------------------------------------------------------------
#  adapter registry
# --------------------------------------------------------------------------
def get_adapters() -> list:
    """Every adapter, in fan-out order. Import here to avoid cycles.
    Mix of Playwright `SourceAdapter` and direct-API `ApiSourceAdapter` — the
    pool only needs `.name` and `async scrape(corridor, days)`."""
    from pipeline.scrape.airindia import AirIndiaAdapter
    from pipeline.scrape.akasa import AkasaAdapter
    from pipeline.scrape.cleartrip import CleartripAdapter
    from pipeline.scrape.googleflights import GoogleFlightsAdapter
    from pipeline.scrape.indigo import IndiGoAdapter
    from pipeline.scrape.ixigo import IxigoAdapter
    from pipeline.scrape.makemytrip import MakeMyTripAdapter
    from pipeline.scrape.yatra import YatraAdapter

    return [
        IxigoAdapter(),
        MakeMyTripAdapter(),
        CleartripAdapter(),
        IndiGoAdapter(),
        AirIndiaAdapter(),
        AkasaAdapter(),
        GoogleFlightsAdapter(),
        YatraAdapter(),
    ]


ADAPTERS = ("ixigo", "makemytrip", "cleartrip", "indigo", "airindia", "akasa",
            "googleflights", "yatra")
