# backend/ — VAYU-SUCHAK 2.0

FastAPI, one process, port 8000. Serves the frontend (`../frontend/index.html`)
and the API. `pipeline/` is pure functions; `app/` is the only layer that knows
about HTTP / streaming / DB / logging.

## Layout ↔ spec (docs/backend-feature-list.html)

| Path | Feature-list § | Status |
|---|---|---|
| `config.py` | 0.3 config layer (`pydantic-settings`) | done |
| `app/models.py` → `AuditParams` | 0.4 boundary validation (422) | done |
| `app/orchestrator.py` → `run_audit` | 0.5 async SSE orchestrator | done |
| `app/main.py` | 09 API contract (`/`, `/api/corridors`, `/api/execute-audit`, `/api/runs`, `/api/import-csv`, `/api/report/{id}`) | done |
| `pipeline/contract.py` | 1.6 normalise contract, 1.7 merge+dedupe | done |
| `pipeline/scrape/base.py` | 1.1–1.14 adapter ABC, browser pool, XHR intercept, CSS fallback, retry/backoff, block detection | done |
| `pipeline/scrape/cleartrip.py` | per-source adapter (JSON: `/flight/search/v2`) | **done · live · ~230 fares/route** |
| `pipeline/scrape/googleflights.py` | per-source adapter (DOM aria-labels) | **done · live · ~60–110 fares/route** |
| `pipeline/scrape/ixigo.py` | per-source adapter (parser kept) | **parser done · live DISABLED — robots.txt disallows `/search/result/`** |
| `pipeline/scrape/makemytrip.py` | per-source adapter | stub — robots-disallowed + Akamai bot wall (docstring) |
| `pipeline/scrape/{indigo,airindia}.py` | per-source adapters | stub — airline SPA, need form-submit automation (docstring) |
| `pipeline/scrape/ratelimit.py` | 1.8 rate limiter, 1.9 robots.txt (hardened — fail-closed), 1.10 rotating UA | done |
| `pipeline/scrape/travelpayouts.py` | 1.15–1.16 tier-1 fallback | done (needs token to fire) |
| `pipeline/scrape/cache.py` | 1.17–1.18 tier-2 cache | done |
| `pipeline/ingest.py` | 1.20–1.21 fallback tagging + graceful degradation | done |
| `pipeline/festival.py` | 02 festival flag engine | done |
| `pipeline/iqr.py` | 03 two-tailed IQR purifier | done |
| `pipeline/ml/integrity.py` | 04 IsolationForest integrity model | code done · artifact needs Kaggle |
| `pipeline/ml/nowcast.py` | 05 gradient-boost nowcast/imputation | code done · artifact needs Kaggle |
| `pipeline/laspeyres.py` | 06 weighted Laspeyres + festival decomposition | done |
| `pipeline/explain.py` | 07 rule-based explainability annotator | done |
| `pipeline/persistence.py` + `db/schema.sql` | 08 Postgres→SQLite WAL failover | done (Postgres path needs `PG_DSN`) |
| `scripts/seed_cache.py` | 1.19 cache seed | done |
| `scripts/build_base_reference.py` | 10.1–10.3 P0/Q0 build | done (needs source CSVs) |
| `scripts/train_{integrity,nowcast}.py` | 4.3 / 5.5 self-training | done (needs Kaggle corpus) |
| `tests/` | 11 golden-number + e2e + fallback tests | 23 passing |

## Build-order position (feature-list "Build order")

Stages **1–9** are implemented. Stage **7** (live scraper pool): **2 sources
scrape live today** (Cleartrip, Google Flights → ~300+ fares/route combined),
the framework is complete, and the pipeline runs live end-to-end (`mode=auto` →
`tier=live_scrape`). Stage **9** (AI models): trained artifacts present
(`models/*.joblib`); retrain from `scripts/` when more data lands.

### Ethics / responsible scraping

- **robots.txt is honoured and fail-closed.** `ratelimit.py` normalises the file
  first because `urllib.robotparser` silently drops rules after a blank line
  (Ixigo's file does this) — that bug would have let us crawl a disallowed path.
- **Ixigo live scraping is OFF** — their robots.txt disallows `/search/result/`
  and `/flights/search`. `ROBOTS_DISALLOWED = True` on the adapter; data comes
  from Travelpayouts / cache instead. The parser is retained for robots-permitted
  pages or a future data-sharing agreement.
- 1 request / `RATE_LIMIT_PER_DOMAIN_SEC` per domain, rotating realistic UA,
  responses cached so re-runs don't re-hit sites. No CAPTCHA solving, no
  bot-detection evasion — a block → back off to the fallback chain.
- DGCA volume weights are downloaded, never scraped (official statistic).

## Turning a stub adapter into a real one

1. `python -m scripts.check_sources` to see current status.
2. Search a route on the site with DevTools → Network → XHR; find the fare-list
   JSON → put its URL fragment in `is_fare_xhr`, map fields in `parse_xhr`
   (see `cleartrip.py`). No clean JSON → implement `parse_dom` (see
   `googleflights.py` / `ixigo.py`).
3. Put the results URL in `search_url`.
4. Remove `RECON_PENDING` / `ROBOTS_DISALLOWED` (the latter only with permission).
