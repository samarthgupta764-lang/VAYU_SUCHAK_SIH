"""
Scraper pool — concurrent fan-out across the six adapters.

    scrape_pool(corridor, days) -> PoolResult

Runs adapters under a concurrency cap, writes each source's fares to the cache,
merges + dedupes, and returns per-source status. Never raises: a per-adapter
failure becomes a `degraded` / `blocked` status line and the run continues.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from config import settings
from pipeline.contract import FareRecord, dedupe
from pipeline.scrape import cache
from pipeline.scrape.base import ScrapeOutput, SourceAdapter, SourceStatus, get_adapters

OnSourceDone = Callable[[str, SourceStatus], None]


@dataclass
class PoolResult:
    records: list[FareRecord] = field(default_factory=list)
    statuses: list[SourceStatus] = field(default_factory=list)
    duplicates_dropped: int = 0

    @property
    def sources_ok(self) -> list[str]:
        return [s.source for s in self.statuses if s.status == "ok"]

    @property
    def sources_degraded(self) -> list[str]:
        return [s.source for s in self.statuses if s.status in ("degraded", "blocked", "error", "unavailable")]

    def to_dict(self) -> dict:
        return {
            "records": len(self.records),
            "duplicates_dropped": self.duplicates_dropped,
            "sources": {s.source: s.to_dict() for s in self.statuses},
            "sources_ok": self.sources_ok,
            "sources_degraded": self.sources_degraded,
        }


async def scrape_pool(
    corridor: str, days: list[date], *, skip: set[str] | None = None,
    on_done: OnSourceDone | None = None,
) -> PoolResult:
    """`on_done(source_name, status)` fires the instant each adapter resolves —
    lets a caller (the SSE orchestrator) report per-source progress live
    instead of waiting for the whole gather() to finish (Cleartrip's Playwright
    XHR capture is the slow one, ~10-20s vs low single digits for the others)."""
    adapters = [a for a in get_adapters() if not skip or a.name not in skip]
    sem = asyncio.Semaphore(settings.scrape_concurrency)

    async def _run(adapter, shared_browser):
        async with sem:
            try:
                coro = (
                    adapter.scrape(corridor, days, browser=shared_browser)
                    if isinstance(adapter, SourceAdapter)
                    else adapter.scrape(corridor, days)
                )
                out = await asyncio.wait_for(coro, timeout=settings.scrape_source_timeout_s)
            except asyncio.TimeoutError:
                out = ScrapeOutput(
                    [],
                    SourceStatus(
                        source=adapter.name,
                        status="degraded",
                        detail=f"timed out after {settings.scrape_source_timeout_s}s",
                    ),
                )
        if out.records:
            try:
                cache.write(adapter.name, corridor, out.records)
            except OSError:
                pass
        if on_done:
            try:
                on_done(adapter.name, out.status or SourceStatus(source=adapter.name))
            except Exception:  # noqa: BLE001 — a bad callback must never break the scrape
                pass
        return out

    # one shared Chromium for every Playwright adapter this run actually
    # needs (Cleartrip, Google Flights) instead of each paying its own
    # ~200-500ms launch/close — a Browser safely hosts many concurrent
    # contexts, which is exactly what each adapter's own new_context() per
    # attempt already does. Falls back to per-adapter launch (unchanged
    # behaviour) if nothing needs one, or if the shared launch itself fails.
    needs_browser = any(
        isinstance(a, SourceAdapter)
        and not getattr(a, "ROBOTS_DISALLOWED", False)
        and not getattr(a, "RECON_PENDING", False)
        for a in adapters
    )
    shared_browser = None
    async with contextlib.AsyncExitStack() as stack:
        if needs_browser:
            with contextlib.suppress(Exception):  # ImportError, launch failure — degrade to per-adapter
                from playwright.async_api import async_playwright

                p = await stack.enter_async_context(async_playwright())
                shared_browser = await p.chromium.launch(headless=settings.scrape_headless)
                stack.push_async_callback(shared_browser.close)

        outputs = await asyncio.gather(*(_run(a, shared_browser) for a in adapters), return_exceptions=True)

    merged: list[FareRecord] = []
    statuses: list[SourceStatus] = []
    for adapter, out in zip(adapters, outputs):
        if isinstance(out, Exception):
            statuses.append(
                SourceStatus(source=adapter.name, status="error", detail=str(out))
            )
            continue
        merged.extend(out.records)
        statuses.append(out.status or SourceStatus(source=adapter.name))

    unique, dropped = dedupe(merged)
    return PoolResult(records=unique, statuses=statuses, duplicates_dropped=dropped)
