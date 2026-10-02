"""
robots.txt handling — the ethical guard rail.

Verifies we DON'T fail open on a malformed-but-restrictive file (the exact bug
that let the original Ixigo scraper crawl a disallowed path).
"""

from pipeline.scrape.ratelimit import RobotsRules, _normalise_robots

# Ixigo's real robots.txt: a blank line sits between `User-agent: *` and its
# first Disallow. urllib.robotparser drops the rules; we must not.
IXIGO_STYLE = """# a friendly comment

User-agent: *

Disallow: /search/result/
Disallow: /flights/search
Disallow: /api/

User-agent: Yandex
Disallow: /
"""

CLEARTRIP_STYLE = """User-agent: *
Disallow: /flights/search*
Disallow: /hotels/info*
"""


def test_blank_line_after_user_agent_still_blocks():
    r = RobotsRules(IXIGO_STYLE)
    assert r.allowed("https://www.ixigo.com/search/result/flight?from=DEL") is False
    assert r.allowed("https://www.ixigo.com/api/x") is False


def test_permitted_paths_allowed():
    r = RobotsRules(IXIGO_STYLE)
    assert r.allowed("https://www.ixigo.com/flights/delhi-mumbai") is True


def test_wildcard_disallow():
    r = RobotsRules(CLEARTRIP_STYLE)
    assert r.allowed("https://www.cleartrip.com/flights/search?x=1") is False
    # singular /flight/search/v2 is a different path — not matched by /flights/search*
    assert r.allowed("https://www.cleartrip.com/flight/search/v2?from=DEL") is True
    assert r.allowed("https://www.cleartrip.com/flights/results?from=DEL") is True


def test_no_robots_file_means_allowed():
    assert RobotsRules("").allowed("https://example.com/anything") is True


def test_normalise_drops_intra_record_blank_lines():
    out = _normalise_robots(IXIGO_STYLE)
    assert "\n\n" not in out
    assert out.splitlines()[0].lower().startswith("user-agent")
