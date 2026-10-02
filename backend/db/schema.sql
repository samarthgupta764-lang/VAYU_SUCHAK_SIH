-- VAYU-SUCHAK 2.0 — one DDL file, applied to both Postgres and the SQLite
-- fallback. TEXT timestamps keep the two stores byte-identical for reconciling.
-- Statements are split on the semicolon by the Python loaders, so keep every
-- statement terminated with one and do not put a bare semicolon in a comment.

CREATE TABLE IF NOT EXISTS audit_runs (
    run_id                      TEXT PRIMARY KEY,
    corridor                    TEXT NOT NULL,
    date_range_start            TEXT,
    date_range_end              TEXT,
    index_value                 REAL,
    index_ex_festival           REAL,
    festival_component          REAL,
    k_factor_used               REAL,
    base_period                 TEXT,
    records_ingested            INTEGER,
    festival_flagged_count      INTEGER,
    festival_breakdown          TEXT,      -- json: {"Diwali": 31, ...}
    anomalies_excluded_count    INTEGER,
    ml_flagged_count            INTEGER,
    imputed_route_days          INTEGER,
    routes_matched              INTEGER,
    scrape_sources              TEXT,      -- json: {"ixigo": {...}, ...}
    ingestion_source            TEXT,      -- live_scrape | travelpayouts | cache | imported_csv
    tiers_used                  TEXT,      -- json: ["live_scrape", "cache"]
    sources_degraded            INTEGER,
    annotation                  TEXT,      -- explainability one-liner
    db_target                   TEXT,      -- postgres | sqlite_fallback
    created_at                  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_runs_corridor_created
    ON audit_runs (corridor, created_at DESC);


-- ---------------------------------------------------------------------------
--  fare_quotes — the de-duplicated airfare database (Expected Solution b).
--  One row per (source, flight, fare-class) captured on a collection day.
--  Every downstream index is computed FROM this table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fare_quotes (
    quote_id              TEXT PRIMARY KEY,   -- deterministic hash of the unique key
    collection_run_id     TEXT,
    collected_at          TEXT NOT NULL,      -- ISO ts of capture
    collected_date        TEXT NOT NULL,      -- YYYY-MM-DD (de-dup + daily index key)
    source                TEXT NOT NULL,      -- yatra | cleartrip | airindia | akasa | googleflights | cache | ...
    source_type           TEXT,              -- airline | ota | api | cache
    route                 TEXT NOT NULL,      -- directed, e.g. DEL-BOM
    origin                TEXT NOT NULL,
    destination           TEXT NOT NULL,
    carrier               TEXT NOT NULL,      -- 6E | AI | QP | SG | IX
    flight_number         TEXT,
    departure_ts          TEXT NOT NULL,
    departure_date        TEXT NOT NULL,      -- YYYY-MM-DD
    advance_purchase_days  INTEGER,
    apw_bucket            TEXT,              -- T+1 | T+7 | T+15 | T+30 | T+45
    fare_class            TEXT NOT NULL DEFAULT 'economy',
    stops                 INTEGER,
    duration_minutes      INTEGER,
    base_fare             REAL,
    taxes                 REAL,
    udf                   REAL,
    convenience_fee       REAL,
    total_fare            REAL NOT NULL,     -- the number the index uses
    currency              TEXT DEFAULT 'INR',
    is_sold_out           INTEGER DEFAULT 0,
    is_festival_season    INTEGER DEFAULT 0,
    festival_matched      TEXT,
    ingestion_source      TEXT,
    created_at            TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_fq_route_apw_dep
    ON fare_quotes (route, apw_bucket, departure_date);
CREATE INDEX IF NOT EXISTS ix_fq_collected
    ON fare_quotes (collected_date);
CREATE INDEX IF NOT EXISTS ix_fq_carrier
    ON fare_quotes (carrier, collected_date);


-- ---------------------------------------------------------------------------
--  collection_runs — one row per scheduled/manual collection cycle.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_runs (
    run_id           TEXT PRIMARY KEY,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    trigger          TEXT,             -- scheduled | manual | api
    routes_count     INTEGER,
    apw_windows      TEXT,             -- json: [1, 7, 15, 30, 45]
    quotes_written   INTEGER,
    quotes_seen      INTEGER,
    sources_summary  TEXT,             -- json: {source: {status, fares, latency_ms}}
    status           TEXT,             -- ok | partial | failed
    notes            TEXT,
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_collection_runs_started
    ON collection_runs (started_at DESC);


-- ---------------------------------------------------------------------------
--  index_values — the APIx time-series computed from fare_quotes.
--  One row per (frequency, period, scope). Recomputed idempotently.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS index_values (
    period_type          TEXT NOT NULL,   -- daily | weekly | monthly
    period               TEXT NOT NULL,   -- 2026-10-05 | 2026-W41 | 2026-10
    scope                TEXT NOT NULL,   -- overall | route:DEL-BOM | carrier:6E | window:T+7
    index_value          REAL,
    index_ex_festival    REAL,
    festival_component   REAL,
    n_quotes             INTEGER,
    routes_matched       INTEGER,
    k_factor             REAL,
    anomalies_excluded   INTEGER,
    base_month           TEXT,
    provisional          INTEGER DEFAULT 1,
    computed_at          TEXT,
    PRIMARY KEY (period_type, period, scope)
);

CREATE INDEX IF NOT EXISTS ix_index_values_scope_period
    ON index_values (scope, period_type, period);
