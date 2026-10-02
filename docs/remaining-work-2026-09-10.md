# VAYU-SUCHAK — Remaining Work

**Snapshot date:** 2026-09-10 · **SIH26056 · Team Chakravyuh**
**Branch:** `feat/phase-0-fare-quote-db` (7 commits ahead of `main`, not yet pushed)
**Tests:** 68 passing · **Collection:** day 1 of 30 banked (1,464 quotes, 48 routes, 7 carriers)

This document is the full list of what is left, after re-reading the official SIH
problem statement. It supersedes the informal status updates. Read alongside
`docs/backend-feature-list.html` (original spec) and the problem statement.

---

## 1. Where the project is today

### Done and working
- **Fare-quote database** (`fare_quotes`, `collection_runs`, `index_values`) — the
  de-duplicated airfare DB the problem statement asks for. Collection and index
  computation are now separate concerns.
- **Advance-purchase-window dimension** (T+1 / T+7 / T+15 / T+30 / T+45) end to end
  — every quote tagged, the collector scrapes exactly those departure dates.
- **Fare decomposition** — base fare / taxes / UDF captured where the source
  provides it (Air India, Akasa, Yatra).
- **5 live sources**, all robots-compliant: Cleartrip, Google Flights, Air India,
  Akasa, Yatra. Yatra returns the cheapest fare per carrier per day for **all 5
  airlines** including IndiGo / SpiceJet / Air India Express (whose own sites
  robots.txt disallows).
- **Route basket from DGCA** — `scripts/build_basket.py` ranks city-pairs by 2025
  passenger traffic → 24 pairs / 48 directed routes + real Q0 weights.
- **Index engine** (`pipeline/index_engine.py`) — Laspeyres APIx from the DB, at
  daily / weekly / monthly frequency, with sub-indices per route / carrier /
  window, an ex-festival variant, and lead-time elasticity curves.
- **Back-test module** (`pipeline/backtest.py`) — APIx vs MoSPI CPI item
  "Air Fare (normal): Economy Class (adult)". Live version fills in as collection
  accumulates; a historical 2022 version runs now (flagged method-demo-only).
- **CPI series wired** — real MoSPI data (`data/mospi/`), not a placeholder.
- **Daily collector** — macOS `launchd` job, installed and running. `collector_status`
  + `backup_db.sh` scripts.
- **Public API** — `GET /api/apix`, `/api/apix/latest`, `/api/elasticity/{route}`,
  `/api/cpi`, `/api/backtest` (the NSO/RBI-consumable surface), plus the original
  `/api/execute-audit`, `/api/runs`, `/api/report`, `/api/import-csv`, `/api/corridors`.
- Festival flag engine, IQR purifier, weighted Laspeyres, rule-based explain
  annotator — all golden-tested (118.75 etc.).

---

## 2. What we are NO LONGER using from the original design

| Original (backend-feature-list) | Now | Why it changed |
|---|---|---|
| **Frozen 2022 base year** — `base_year_reference.json`, P0 = Kaggle 2022 median, `base_period: "2022"`, frozen in-repo (6.2, 10.3) | Base period = **first full month of live collection**; P0 = mean fare *we collect* that month, per (route, window), from `fare_quotes` | Kaggle only covers 6 metros — can't extend a frozen 2022 base to the DGCA-ranked basket. A real-time index should anchor to a recent, self-consistent base. The 2022 P0 + 118.75 golden test survive as a **methodology-validation unit test only**. |
| **One "audit run"** = scrape + compute + store one index number in `audit_runs` (0.5, 8.4, 9.3) | **Collection and index computation split.** A scheduled collector fills `fare_quotes`; `index_engine` computes the APIx time-series from it. | The problem statement wants a database of quotes + daily/weekly/monthly frequencies, not one number per manual run. |
| **"Everything is live"** — 5 airline/OTA portals scraped directly (§01 intro) | 5 live sources, but **3 of the named airlines (IndiGo, SpiceJet, Air India Express) are robots.txt-disallowed** — their fares come via Yatra (permitted OTA meta-feed) + Google Flights | The problem statement requires robots.txt + ToS compliance. Pitch becomes "everything robots-permitted is live; blocked carriers via permitted aggregators." |
| **Per-source Playwright adapter for all** (1.1, 1.2) | Cleartrip + Google Flights use Playwright; **Air India + Akasa + Yatra use direct httpx API calls**. The Chromium "pool" with instance reuse was never built. | Direct API is faster, lighter, more polite where the site allows it — and is the spec's own stated primary method ("capture the site's own fare JSON"). |
| **APScheduler in-process** for off-peak pre-scrape (1.12) | **macOS `launchd`** job runs the collector daily | Survives sleep/wake on a laptop; simpler; no long-running process. APScheduler still in `requirements.txt`, unused. |
| **CPI "Transport" sub-group** as the overlay (10.7) | CPI **item** "Air Fare (normal): Economy Class (adult)" as the primary reference + back-test target; Transport sub-group is a secondary line | The item-level series is airfare-specific — a real validation target, not a broad basket. |
| **`normalise` contract** = `{flight_id, route, price, currency, departure_ts, airline, source}` (1.6) | Same + `collected_at, advance_purchase_days, apw_bucket, fare_class, base_fare, taxes, udf, convenience_fee, is_sold_out, source_type` | Expanded (not dropped) for the new requirements. |
| **k_factor slider as a headline control** + IQR purifier as the showcase (0.3, 3.x) | The new `index_engine` uses a plain **median** (outlier-robust) and does not expose `k`. IQR + the slider only run in the **old** `/api/execute-audit` path. | **This is a gap to fix, not an intentional drop** — see §3.1. |
| **pywebview desktop shell** (stretch) | Not built; web dashboard served locally | Deprioritised; problem statement doesn't require a native shell. |
| Vision-LLM extractor · free LLM API key · explainability LLM | Removed (already gone in the feature-list itself, pre-this-session) | No external AI APIs anywhere. Still true. |

### Added since the original design (not in backend-feature-list)
`fare_quotes` / `collection_runs` / `index_values` tables · APW dimension · fare
decomposition · daily/weekly/monthly frequencies · per-carrier & per-window
sub-indices · lead-time elasticity · back-test module · DGCA-traffic route basket
(`build_basket.py`) · daily scheduled collector + status + backup · public
NSO/RBI API endpoints · Akasa + Yatra adapters · `geo.same_metro()` (Navi Mumbai
→ Mumbai) · domestic-carrier filter.

---

## 3. Remaining work

Effort = focused engineering days. **Owner: "me" = coding; "you" = the item genuinely needs you.**

### 3.1 Unify the index engine — HIGH PRIORITY
The APIx computed by `index_engine.py` is currently *simpler* than the spec's
pipeline. Fold in:

| Task | Effort | Owner |
|---|---|---|
| Run the **IQR purifier** on the quote set before aggregating (report anomalies, keep the k control) — spec §03, 4.6 | 1.5d | me |
| Run the **integrity ML** pass as a second filter — spec §04, 4.6 | 1d | me |
| Run **nowcast imputation** for sparse route-days and carry the confidence band to the index — spec §05, **fixes the 5.8 bug** | 2d | me |
| Run the **explain annotator** on the new daily/monthly points — spec §07 | 0.5d | me |
| **Retire or repoint** the old `/api/execute-audit` so there is ONE index definition, not two that disagree | 1d | me |

### 3.2 AI models — make them real
| Task | Effort | Owner |
|---|---|---|
| **Integrity model** — recall is 0.29 (poor) and it flags 0 on real data. Rebuild the synthetic-injection eval, improve features, verify it catches decoys (4.7) | 1.5d | me |
| **Retrain both models** on the accumulating collected corpus, with APW / carrier / fare-class features — spec 4.3, 5.5 | 1d (recurring) | me |
| **Surface eval metrics** (precision/recall, MAE/CI-coverage) in the API + dashboard — spec 11.6 | 0.5d | me |

### 3.3 Sold-out / cancelled flights — spec (problem statement)
| Task | Effort | Owner |
|---|---|---|
| Detect "flight shown, no seats/fare" in each adapter → set `is_sold_out` (schema field already exists) | 1d | me |
| Feed sold-out route-days into the nowcast imputation as gaps | 0.5d | me |

### 3.4 Fallback tiers — prove them
| Task | Effort | Owner |
|---|---|---|
| **Travelpayouts** — add the token, wire it into the collector's fallback path, test the chain (1.15–1.16, 10.5) | 0.5d | **you** (token) + me |
| **Amadeus** — optional 2nd licensed API tier | 1d | you (signup) + me |
| **Postgres** — add `docker-compose.yml`, run once so `db_target: postgres` is real (8.1) | 1d | me (+ Docker on your machine) |

### 3.5 Frontend / dashboard rebuild — THE LARGEST PIECE
The current screen is the old single-run console. Build the analytical dashboard:

| View | Effort |
|---|---|
| APIx time-series chart — daily/weekly/monthly toggle, CPI Air Fare + Transport + festival overlays | 1.5d |
| Sector-wise heatmap (routes × index / WoW change) | 1d |
| Lead-time elasticity curves (fare vs T+1…T+45, per route) | 1d |
| Fare-decomposition view (base / tax / UDF stacked) | 0.5d |
| Carrier comparison | 0.5d |
| Real collection-status panel (last run, quotes today, per-source health, sold-out rate) — replaces the fake tiles | 0.5d |
| Back-test view (APIx vs CPI Air Fare, correlation, direction agreement) | 1d |
| Filters (route / carrier / window / date range) + API-explorer page | 1d |
| Accessibility pass (aria-live, non-colour status, 1366×768 fit) | 1d |
| **Total** | **~8–9d** · owner: me · **you: review + feedback** |

### 3.6 Scraper hardening — spec §01 gaps
| Task | Effort | Owner |
|---|---|---|
| **Air India** — currently IP-blocked from testing. Gentle the token flow / add IP rotation, or wait for it to clear | 0.5d | me |
| Chromium **pool with instance reuse** (1.2) | 1d | me |
| **UA + viewport rotation** per session (1.10) | 0.5d | me |
| Honour **Retry-After** (1.9) | 0.5d | me |
| Collector speed — a 48-route API-only run is ~30 min (Akasa is slow); raise concurrency or trim | 0.5d | me |

### 3.7 Documentation — a stated deliverable
| Doc | Effort | Owner |
|---|---|---|
| **Methodology** — index construction, weights, base-period choice, "PSD routes/weights" justification | 1d | me |
| **API reference** — the NSO/RBI endpoints | 0.5d | me |
| **Scrape-target recon doc** (10.6) — per source: endpoint, response shape, robots verdict | 0.5d | me |
| **Back-test report** — 30-day results once collected | 0.5d | me |
| `SETUP.md` — clone → venv → data → `install_collector.sh` | 0.5d | me |

### 3.8 CSV import (9.5)
| Task | Effort | Owner |
|---|---|---|
| Wire the dashboard's Import CSV to `POST /api/import-csv` (currently client-side) | 0.5d | me |

### 3.9 Git / ship hygiene — before pushing today
| Task | Effort | Owner |
|---|---|---|
| Merge `feat/phase-0-fare-quote-db` → `main` | 5 min | me |
| DB-snapshot-to-git (weekly compressed snapshot so collected data is backed up on GitHub) | 0.5d | me |
| Create the GitHub repo + push | 5 min | **you** (create repo) |

---

## 4. The unavoidable wait

The 30-day back-test needs **29 more days** of collection. Day 1/30 is banked.
Nothing speeds this — the only requirement is the laptop being opened once a day
so the `launchd` job runs.

---

## 5. Critical path / suggested order

1. **Today:** git hygiene (§3.9) → push to GitHub.
2. **Week 1 (while collection runs):** unify the index engine (§3.1) + fix the AI
   models (§3.2) + Travelpayouts/Postgres (§3.4) + scraper hardening (§3.6).
3. **Weeks 2–3:** frontend rebuild (§3.5).
4. **Week 3–4:** sold-out handling (§3.3), documentation (§3.7), CSV import (§3.8).
5. **Day ~30:** run the real back-test, write the report, final polish.

**Total remaining engineering: ~20 working days**, almost none of it blocked on
you — the exceptions are the Travelpayouts token, Docker for Postgres, creating
the GitHub repo, and dashboard feedback.

---

## 6. What genuinely needs YOU — complete list

1. Keep the laptop opened once a day (collection).
2. Create the GitHub repo (5 min).
3. Travelpayouts: free signup → send token + marker.
4. (Optional) Amadeus signup for a 2nd API tier.
5. (Optional) Install Docker so Postgres can be demoed.
6. Later: review the dashboard and say what feels wrong.
7. (Done ✅) DGCA passenger data, Kaggle fares, MoSPI CPI Air Fare + Transport.
