"""
One-shot cache pruner.

`cache.write()` now prunes as it goes, but this cleans up the backlog from
before that existed (or after a burst of testing).

    python -m scripts.prune_cache            # keep the configured default per (source, corridor)
    python -m scripts.prune_cache --keep 1   # keep only the newest of each
"""

from __future__ import annotations

import argparse

from config import settings
from pipeline.scrape import cache


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=settings.cache_keep_per_source,
                    help=f"snapshots to keep per (source, corridor) [default {settings.cache_keep_per_source}]")
    args = ap.parse_args()

    before = list(settings.cache_path.glob("*.json"))
    n_before = len(before)
    mb_before = sum(f.stat().st_size for f in before) / 1_048_576

    deleted = cache.prune_all(keep=args.keep)

    after = list(settings.cache_path.glob("*.json"))
    mb_after = sum(f.stat().st_size for f in after) / 1_048_576
    print(f"cache: {n_before} files ({mb_before:.1f} MB) → {len(after)} files "
          f"({mb_after:.1f} MB) · deleted {deleted}, keep={args.keep}")


if __name__ == "__main__":
    main()
