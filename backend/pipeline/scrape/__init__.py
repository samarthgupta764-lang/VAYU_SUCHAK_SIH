"""
pipeline/scrape/ — the live acquisition layer.

One lightweight Playwright adapter per source. The pool fans out concurrently,
merges + dedupes, and reports per-source status. When a source is blocked the
ingest fallback chain (pipeline/ingest.py) takes over: Travelpayouts -> cache.

Only `ixigo` is a complete adapter today. The other five carry the full
browser / XHR-intercept plumbing but need their search-URL pattern and fare XHR
matcher filled in from a per-site DevTools recon — until then they return [].
"""

from pipeline.scrape.base import ADAPTERS, SourceAdapter, get_adapters

__all__ = ["ADAPTERS", "SourceAdapter", "get_adapters"]
