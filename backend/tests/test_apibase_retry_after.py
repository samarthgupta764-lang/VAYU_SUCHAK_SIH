"""
Retry-After handling — pipeline/scrape/apibase.py

A 429 is a request to slow down, not a block: it should be retried (within
the existing attempt budget) after honouring the site's Retry-After header,
not treated the same as a 403 / captcha (which gives up immediately). See
[[vayu-suchak-build-status]] "scraper hardening".
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from config import settings
from pipeline.scrape import ratelimit
from pipeline.scrape.apibase import ApiSourceAdapter, _parse_retry_after
from pipeline.scrape.base import Blocked, RateLimited


class _Adapter(ApiSourceAdapter):
    name = "testsrc"
    base_domain = "example.test"

    async def fetch_raw(self, client, corridor, day):  # noqa: ARG002
        resp = await client.get("https://example.test/fares")
        self._raise_if_blocked(resp)
        return resp.json()


@pytest.fixture(autouse=True)
def _no_real_rate_limit_wait(monkeypatch):
    # the retry test already sleeps for the (tiny, test-supplied) Retry-After
    # value on purpose — this just removes the *unrelated* per-domain
    # politeness gap so the test doesn't also pay rate_limit_per_domain_sec.
    async def _instant(_url: str) -> None:
        return None

    monkeypatch.setattr(ratelimit, "acquire", _instant)


@pytest.mark.asyncio
async def test_429_is_retried_and_succeeds_after_retry_after():
    calls = {"n": 0}

    def handler(request):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json=[{"ok": True}])

    adapter = _Adapter()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await adapter._one_day(client, "DEL-BOM", date(2026, 11, 1))

    assert rows == [{"ok": True}]
    assert calls["n"] == 2  # one 429, one real retry — not blocked, not exhausted


@pytest.mark.asyncio
async def test_403_is_not_retried_unlike_429():
    calls = {"n": 0}

    def handler(request):  # noqa: ARG001
        calls["n"] += 1
        return httpx.Response(403)

    adapter = _Adapter()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Blocked):
            await adapter._one_day(client, "DEL-BOM", date(2026, 11, 1))

    assert calls["n"] == 1  # gave up immediately, exactly the pre-existing behaviour


@pytest.mark.asyncio
async def test_429_exhausting_every_retry_raises_rate_limited_not_blocked():
    """After settings.scrape_retries retries all still 429, _one_day gives up
    with RateLimited (scrape()'s own except RateLimited branch — plain code,
    not worth a heavier integration test — then maps that to status=degraded,
    distinct from the immediate status=blocked a real 403 gets)."""
    def handler(request):  # noqa: ARG001
        return httpx.Response(429, headers={"retry-after": "0"})

    adapter = _Adapter()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimited):
            await adapter._one_day(client, "DEL-BOM", date(2026, 11, 1))


def test_parse_retry_after_seconds_form():
    resp = httpx.Response(429, headers={"retry-after": "5"}, request=httpx.Request("GET", "https://x.test/"))
    assert _parse_retry_after(resp) == 5.0


def test_parse_retry_after_caps_a_very_long_wait():
    resp = httpx.Response(
        429, headers={"retry-after": "9999"}, request=httpx.Request("GET", "https://x.test/")
    )
    assert _parse_retry_after(resp) == settings.scrape_retry_after_cap_s


def test_parse_retry_after_missing_header_uses_cap():
    resp = httpx.Response(429, request=httpx.Request("GET", "https://x.test/"))
    assert _parse_retry_after(resp) == settings.scrape_retry_after_cap_s
