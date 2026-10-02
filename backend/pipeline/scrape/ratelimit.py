"""
Per-domain politeness — token-bucket rate limiter + robots.txt honouring.

Shared across all adapters so concurrent scrapes of the same domain still
respect one request every `rate_limit_per_domain_sec`.

robots.txt handling is deliberately CONSERVATIVE / fail-closed on the important
case: `urllib.robotparser` silently drops rules when a site puts a blank line
between `User-agent:` and its first `Disallow:` (Ixigo does exactly this), which
would let us crawl a path the site disallows. We normalise the file first and,
as a second guard, run a raw prefix scan of the `User-agent: *` block.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from config import settings

_locks: dict[str, asyncio.Lock] = {}
_last_hit: dict[str, float] = {}
_robots_cache: dict[str, "RobotsRules"] = {}

# a robots.txt fetched successfully is reused from disk for this long, so a
# transient edge 403 / stream-reset on a re-fetch never flips a permitted site
# to blocked (feature 1.9: "fetch, cache, respect disallow").
_ROBOTS_DISK_TTL_S = 24 * 3600

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
]


def _robots_disk_path() -> Path:
    p = settings.cache_path / "robots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _robots_disk_read(host: str) -> str | None:
    f = _robots_disk_path() / f"{host}.json"
    try:
        blob = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    age = time.time() - blob.get("epoch", 0)
    if age > _ROBOTS_DISK_TTL_S:
        return None
    return blob.get("text", "")


def _robots_disk_write(host: str, text: str) -> None:
    f = _robots_disk_path() / f"{host}.json"
    try:
        f.write_text(json.dumps(
            {"host": host, "fetched_at": datetime.now(timezone.utc).isoformat(),
             "epoch": time.time(), "text": text}
        ))
    except OSError:
        pass


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


# --------------------------------------------------------------------------
#  robots.txt
# --------------------------------------------------------------------------
class RobotsRules:
    """A parsed robots.txt plus a raw disallow list for the `*` group."""

    def __init__(self, text: str):
        self._rp = urllib.robotparser.RobotFileParser()
        self._star_disallows: list[str] = []
        self._fetched = bool(text)
        if text:
            self._rp.parse(_normalise_robots(text).splitlines())
            self._star_disallows = _raw_star_disallows(text)

    def allowed(self, url: str, user_agent: str = "*") -> bool:
        if not self._fetched:
            return True  # no robots.txt served -> allowed
        path = urlparse(url).path + (f"?{urlparse(url).query}" if urlparse(url).query else "")
        # conservative raw guard first
        for rule in self._star_disallows:
            if _raw_match(rule, path):
                return False
        return self._rp.can_fetch(user_agent, url)


def _normalise_robots(text: str) -> str:
    """
    Drop comments and blank lines *inside* a record so a stray blank line after
    `User-agent:` doesn't orphan the rules that follow. `User-agent:` lines stay
    as the only record boundary.
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        out.append(line)
    return "\n".join(out)


def _raw_star_disallows(text: str) -> list[str]:
    rules: list[str] = []
    in_star = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("user-agent:"):
            in_star = line.split(":", 1)[1].strip() == "*"
        elif in_star and low.startswith("disallow:"):
            val = line.split(":", 1)[1].strip()
            if val:
                rules.append(val)
    return rules


def _raw_match(rule: str, path: str) -> bool:
    """Minimal robots pattern match: supports leading path, `*` wildcard, `$` end."""
    if rule == "/":
        return True
    pattern = re.escape(rule).replace(r"\*", ".*")
    if pattern.endswith(r"\$"):
        pattern = pattern[:-2] + "$"
    anchored = "^" + pattern if rule.startswith("/") else ".*" + pattern
    return re.search(anchored, path) is not None


class RobotsUnavailable(RuntimeError):
    """robots.txt could not be fetched after retries — caller decides policy."""


async def _load_rules(url: str) -> RobotsRules:
    d = _domain(url)
    cached = _robots_cache.get(d)
    if cached is not None:
        return cached
    robots_url = f"{urlparse(url).scheme}://{d}/robots.txt"

    # a recent successful fetch on disk wins — edges throttle repeat /robots.txt
    # hits, and a permitted site must not flip to blocked on a transient reset.
    disk = _robots_disk_read(d)
    if disk is not None:
        rules = RobotsRules(disk)
        _robots_cache[d] = rules
        return rules

    text: str | None = None
    for attempt in range(3):
        try:
            # http2: several airline edges (Akamai) hang or 403 plain HTTP/1.1
            # clients, which would make a served robots.txt look "unreachable"
            # and trip the fail-closed path for a site that actually allows us.
            async with httpx.AsyncClient(
                timeout=12, follow_redirects=True, http2=True,
                headers={
                    "User-Agent": pick_user_agent(attempt),
                    "Accept": "text/plain,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ) as client:
                resp = await client.get(robots_url)
            text = resp.text if resp.status_code == 200 else ""  # 404 == no rules
            break
        except (httpx.HTTPError, OSError):
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))

    if text is None:
        # genuinely unreachable. RFC 9309 says assume allowed, but we don't want
        # a flaky network to silently unblock a site — cache nothing, raise so
        # the caller can be conservative.
        raise RobotsUnavailable(robots_url)

    _robots_disk_write(d, text)
    rules = RobotsRules(text)
    _robots_cache[d] = rules
    return rules


async def allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    if not settings.respect_robots_txt:
        return True
    try:
        rules = await _load_rules(url)
    except RobotsUnavailable:
        # can't confirm — refuse the fetch rather than risk crawling a
        # disallowed path. The fallback chain (Travelpayouts / cache) covers it.
        return False
    return rules.allowed(url, user_agent)


# --------------------------------------------------------------------------
#  rate limiting
# --------------------------------------------------------------------------
async def acquire(url: str) -> None:
    """Block until it is polite to hit `url`'s domain again."""
    d = _domain(url)
    lock = _locks.setdefault(d, asyncio.Lock())
    min_gap = settings.rate_limit_per_domain_sec
    async with lock:
        wait = min_gap - (time.monotonic() - _last_hit.get(d, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        _last_hit[d] = time.monotonic()


def pick_user_agent(seed: int = 0) -> str:
    return USER_AGENTS[seed % len(USER_AGENTS)]
