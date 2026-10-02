# VAYU-SUCHAK 2.0

Real-time airfare price index for India, built by **automated web scraping of
airline & OTA portals** (SIH26056 · Team Chakravyuh).

Live-first: real headless-browser scraping is the primary acquisition path.
Travelpayouts (Aviasales) data API is a formal tier-1 fallback; an on-disk cache
snapshot is tier 2. No external AI APIs — the two ML models are trained in-house.

```
Vayu-Suchak/
├── backend/        FastAPI + pipeline + scrapers + AI models + tests   (this is the app)
├── frontend/       the operator dashboard (single-page, no build step)
├── docs/           spec + interview material
│   ├── backend-feature-list.html   ← authoritative backend spec
│   └── reference/vayu-suchak-engineering-deepdive.html   ← the "why" behind each module
└── README.md
```

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium            # only needed for live scraping
cp .env.example .env                   # fill in optional tokens / DSN
python -m scripts.seed_cache           # seed data/cache/ so the pipeline runs day one
python run.py                          # http://127.0.0.1:8000
```

Run the golden-number test suite:

```bash
cd backend && pytest -q
```

## What's wired vs what needs input

| Working now (no accounts) | Needs you to add something |
|---|---|
| Full pipeline **live** (`mode=auto` → real fares from Cleartrip + Google Flights, ~300+/route) | `TRAVELPAYOUTS_TOKEN` in `.env` → tier-1 fallback |
| Real `P0` (Kaggle) + real `Q0` (DGCA), 32 routes, both ML models trained | `PG_DSN` (Docker `postgres:16` or Neon) → primary DB (SQLite works now) |
| Festival / IQR / Laspeyres + golden tests, SSE console, all `/api/*` | MoSPI CPI-Transport series for the chart overlay |
| robots.txt honoured (fail-closed); rate limits; cache | IndiGo / Air India adapters (airline SPAs — need form automation) |
| Cleartrip + Google Flights adapters live; Ixigo parser (live off per robots.txt) | MakeMyTrip (robots-disallowed + Akamai) |

See `backend/README.md` for module-by-module status and `docs/` for the spec.

## Structure note

`docs/reference/…deepdive.html` §06 sketches a single flat repo with a `static/`
folder. We instead split **`backend/`** and **`frontend/`** as separate top-level
folders (frontend = the deep-dive's `static/`). Every module name, signature and
build-order item from `docs/backend-feature-list.html` is preserved.
