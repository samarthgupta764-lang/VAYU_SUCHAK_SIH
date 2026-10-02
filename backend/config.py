"""
Typed configuration for VAYU-SUCHAK 2.0.

Loads `.env` (via pydantic-settings) into a single frozen `Settings` object.
Import `settings` anywhere; never read `os.environ` directly and never hardcode
a tunable — `k_factor`, dates, DSNs, rate limits and model paths all live here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # not frozen: the test suite overrides individual attributes via monkeypatch.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- pipeline defaults ---
    k_factor_default: float = Field(default=1.5, gt=0, le=10)
    festival_window_days: int = Field(default=7, ge=0, le=30)
    date_range_max_days: int = Field(default=100, ge=1, le=365)  # a full quarter preset = 92d
    base_period: str = "2022"

    # --- real-time index (pipeline/index_engine.py) ---
    # base month for the APIx (= 100). Blank -> the first calendar month that has
    # collected fares. P0 per (route, window) = mean fare collected that month.
    index_base_month: str = ""
    # collection days the base month needs before P0 is frozen; until then the
    # index runs on a provisional P0 (mean of everything collected so far).
    index_base_min_days: int = Field(default=20, ge=1)
    index_aggregator: str = Field(default="median", pattern=r"^(median|mean)$")

    # --- daily collection (scripts/collect.py + the launchd job) ---
    # advance-purchase windows (days before departure) the collector scrapes
    apw_windows: str = "1,7,15,30,45"
    # adapters the *scheduled* daily collector skips — the Playwright ones
    # (Cleartrip, Google Flights) drive a real browser and make a 48-route run
    # take ~40 min on a laptop. The fast httpx sources (Yatra covers all 5
    # carriers in one call; Air India + Akasa add per-flight depth) keep a full
    # run under ~10 min. Cleartrip + Google Flights still run for on-demand
    # /api/execute-audit and `collect --all-sources`.
    collection_skip_sources: str = "cleartrip,googleflights"
    # routes collected concurrently (API sources benefit; per-domain rate limits
    # still serialise same-host calls)
    collection_concurrency: int = Field(default=3, ge=1, le=8)
    # a route with fewer than this many live fares is topped up from Travelpayouts
    collection_tp_floor: int = Field(default=15, ge=0)
    # week-1 basket: the highest-traffic city pairs, both directions. Widen to
    # the full DGCA-ranked basket once recent DGCA passenger data is loaded.
    collection_routes: str = (
        "DEL-BOM,BOM-DEL,DEL-BLR,BLR-DEL,BOM-BLR,BLR-BOM,"
        "DEL-CCU,CCU-DEL,DEL-HYD,HYD-DEL,DEL-MAA,MAA-DEL,"
        "BLR-CCU,CCU-BLR,BLR-HYD,HYD-BLR,BOM-CCU,CCU-BOM,DEL-GAU,GAU-DEL"
    )

    @property
    def apw_window_list(self) -> tuple[int, ...]:
        return tuple(int(w) for w in self.apw_windows.split(",") if w.strip())

    @property
    def collection_route_list(self) -> list[str]:
        return [r.strip().upper() for r in self.collection_routes.split(",") if r.strip()]

    # --- persistence ---
    pg_dsn: str = ""
    pg_connect_timeout: int = 3
    sqlite_fallback_path: str = "db/fallback.sqlite"

    # --- live acquisition ---
    scrape_headless: bool = True
    scrape_concurrency: int = Field(default=3, ge=1, le=10)
    scrape_page_timeout_ms: int = 30_000
    scrape_retries: int = Field(default=2, ge=0, le=5)
    # hard wall-clock cap per source in scrape_pool — a source past this is
    # marked degraded/timeout and the run continues (fallback chain fills the gap)
    scrape_source_timeout_s: int = Field(default=40, ge=5, le=120)
    # a site's own Retry-After (HTTP 429) is honoured up to this many seconds —
    # capped so one slow retry can't eat the whole scrape_source_timeout_s budget
    scrape_retry_after_cap_s: float = Field(default=15.0, ge=1, le=60)
    scrape_target_flights: int = Field(default=50, ge=1)
    rate_limit_per_domain_sec: float = Field(default=3.0, ge=0)
    respect_robots_txt: bool = True
    # an /api/execute-audit run with fewer than this many live fares is topped
    # up first from Travelpayouts, then from the on-disk cache (each tier tagged
    # on the record, run marked degraded). 0 disables the top-up.
    ingest_min_fares: int = Field(default=20, ge=0)

    # --- tier-1 fallback: Travelpayouts ---
    travelpayouts_token: str = ""
    travelpayouts_marker: str = ""

    # --- AI models ---
    integrity_model_path: str = "models/integrity_v1.joblib"
    nowcast_model_path: str = "models/nowcast_v1.joblib"
    integrity_contamination: float = Field(default=0.05, gt=0, lt=0.5)

    # --- paths ---
    data_dir: str = "data"
    cache_dir: str = "data/cache"
    # the on-disk cache is a fallback, not an archive — keep only this many
    # snapshots per (source, corridor); older ones are deleted on write
    cache_keep_per_source: int = Field(default=3, ge=1, le=100)
    base_reference_path: str = "data/base_year_reference.json"
    # MoSPI CPI series live in data/mospi/*.csv, loaded directly by pipeline/cpi.py

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8000

    # ------------------------------------------------------------------ helpers
    def path(self, value: str) -> Path:
        """Resolve a configured relative path against the repo root."""
        p = Path(value)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def cache_path(self) -> Path:
        return self.path(self.cache_dir)

    @property
    def base_reference(self) -> Path:
        return self.path(self.base_reference_path)

    @property
    def sqlite_path(self) -> Path:
        return self.path(self.sqlite_fallback_path)

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.pg_dsn.strip())

    @property
    def travelpayouts_enabled(self) -> bool:
        return bool(self.travelpayouts_token.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
