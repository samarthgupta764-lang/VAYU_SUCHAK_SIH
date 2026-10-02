"""
FastAPI app — app/main.py

One process, one port. Serves the static dashboard and the API. Async, so the
SSE stream and the scrape run concurrently inside one request.
"""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import REPO_ROOT, settings
from app.models import AuditParams, CorridorList
from app.orchestrator import run_audit, sse
from pipeline import festival, iqr, laspeyres
from pipeline.clean import sanitize_csv_bytes
from pipeline.persistence import fetch_run, fetch_runs, persist_run

app = FastAPI(title="VAYU-SUCHAK 2.0", version="2.0.0")

# frontend lives in a sibling folder:  Vayu-Suchak/frontend/  ·  backend/ is REPO_ROOT
STATIC_DIR = REPO_ROOT.parent / "frontend"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@app.get("/")
@app.head("/")
def dashboard() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(503, "static/index.html not found")
    return FileResponse(index)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/corridors", response_model=CorridorList)
def corridors() -> CorridorList:
    base_ref, base_period = laspeyres.load_base_reference(settings.base_reference)
    return CorridorList(corridors=sorted(base_ref.keys()), base_period=base_period)


@app.get("/api/execute-audit")
async def execute_audit(
    corridor: str, start: str, end: str,
    k_factor: float | None = None, mode: str = "auto",
) -> StreamingResponse:
    """Validate the params inside the stream so a bad request shows up as an
    error line in the dashboard console, not an opaque 'backend unreachable'."""
    async def _stream():
        try:
            params = AuditParams(
                corridor=corridor, start=start, end=end,
                k_factor=k_factor if k_factor and k_factor > 0 else settings.k_factor_default,
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError et al.
            msg = str(exc).split("\n")[1].strip() if "\n" in str(exc) else str(exc)
            yield sse("SYSTEM", f"invalid audit parameters — {msg}", done=True, error=True)
            return
        async for line in run_audit(params):
            yield line

    return StreamingResponse(
        _stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@app.get("/api/runs")
def runs(corridor: str | None = None, limit: int = 20) -> list[dict]:
    rows = fetch_runs(corridor=corridor, limit=min(limit, 200))
    for r in rows:
        for col in ("festival_breakdown", "scrape_sources", "tiers_used"):
            if isinstance(r.get(col), str):
                try:
                    r[col] = json.loads(r[col])
                except (ValueError, TypeError):
                    pass
    return rows


@app.get("/api/report/{run_id}")
def report(run_id: str) -> dict:
    row = fetch_run(run_id)
    if not row:
        raise HTTPException(404, f"run {run_id} not found")
    return row


@app.get("/api/apix")
def apix(scope: str = "overall", freq: str = "daily", k: float | None = None,
         limit: int = 400) -> list[dict]:
    """The Airfare Price Index time-series for the NSO / RBI to consume.
    scope: overall | route:DEL-BOM | carrier:6E | window:T+7   ·   freq: daily|weekly|monthly
    k: Tukey-fence multiplier for the IQR purifier (default from config); pass it
    to recompute live off the stored quotes (the dashboard k-slider).

    Always computed live from `fare_quotes` against the frozen 2022 base so it
    can never disagree with /api/apix/latest (the stored `index_values` cache
    is written by the daily collector and used only for history beyond the
    quote-retention window)."""
    from pipeline.index_engine import series
    return [p.to_row() for p in series(freq, scope, k_factor=k) if p.n_quotes]


@app.get("/api/apix/latest")
def apix_latest(scope: str = "overall", k: float | None = None) -> dict:
    from pipeline.index_engine import latest
    p = latest(scope, k_factor=k)
    if p is None:
        raise HTTPException(404, "no fare data collected yet")
    return {**p.to_row(), "per_route": p.per_route, "fences": p.fences}


@app.get("/api/elasticity/{route}")
def elasticity(route: str, k: float | None = None) -> dict:
    """Average fare by advance-purchase window — the lead-time elasticity curve."""
    from pipeline.index_engine import elasticity as _el
    return {"route": route.upper(), "curve": _el(route.upper(), k_factor=k)}


@app.get("/api/fare-decomposition")
def fare_decomposition(route: str | None = None) -> dict:
    """Average rupee split of a fare — base / taxes / UDF / convenience / other —
    per carrier. Only quotes that carry a real breakdown count (Air India, Akasa,
    Yatra populate it; Cleartrip and Google Flights don't) — see `coverage`."""
    from pipeline.index_engine import fare_decomposition as _fd
    return _fd(route)


@app.get("/api/cpi")
def cpi_series() -> dict:
    from pipeline import cpi
    return {
        "air_fare": cpi.air_fare_series(),
        "transport": cpi.transport_series(),
        "note": "MoSPI CPI, base 2012=100. air_fare = item 'Air Fare (normal): Economy Class (adult)'.",
    }


@app.get("/api/backtest")
def backtest() -> dict:
    from pipeline.backtest import report
    return report()


@app.get("/api/routes")
def routes() -> dict:
    """The index route basket + base-year P0/Q0 (base_year_reference.json)."""
    from pipeline.base_reference import base_period, indexed_routes, p0_table, q0_table
    return {"routes": indexed_routes(), "base_period": base_period(),
            "p0": p0_table(), "q0": q0_table()}


@app.get("/api/collector/status")
def collector_status() -> dict:
    from pipeline.quotes import collector_status as _s
    return _s()


@app.get("/api/ml/status")
def ml_status() -> dict:
    """Static training-time metrics for the two in-house sklearn models —
    version, when trained, on how many rows, and the held-out eval (integrity:
    precision/recall; nowcast: MAE + 80% confidence-band coverage). Read from
    the saved model bundle, not recomputed — for the dashboard's AI-models
    panel, not a scoring call."""
    from pipeline.ml.integrity import model_info as integrity_info
    from pipeline.ml.nowcast import model_info as nowcast_info
    return {"integrity": integrity_info(), "nowcast": nowcast_info()}


@app.get("/api/quotes")
def quotes(route: str | None = None, carrier: str | None = None,
           apw: str | None = None, date: str | None = None, limit: int = 800) -> list[dict]:
    from pipeline.quotes import fetch_quotes
    return fetch_quotes(route=route, carrier=carrier, apw_bucket=apw,
                        collected_from=date, collected_to=date, limit=min(limit, 5000))


@app.post("/api/import-csv")
async def import_csv(file: UploadFile = File(...), k_factor: float | None = None) -> dict:
    """
    Upload a pre-scraped fare extract -> run the index pipeline on it.
    Synchronous (not SSE): returns the whole result as one JSON body.
    """
    blob = await file.read()
    try:
        records, sreport, rejected = sanitize_csv_bytes(blob)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"could not parse CSV: {exc}") from exc
    if not records:
        raise HTTPException(422, {"message": "no valid rows", "report": sreport.to_dict()})

    k = k_factor if k_factor and k_factor > 0 else settings.k_factor_default
    records, fcount, breakdown = festival.flag(records, window_days=settings.festival_window_days)
    iqr_res = iqr.apply_iqr_filter(records, k)
    base_ref, base_period = laspeyres.load_base_reference(settings.base_reference)
    idx = laspeyres.compute_index(iqr_res.clean, base_ref, base_period=base_period)

    import uuid
    from datetime import datetime, timezone

    run_id = str(uuid.uuid4())
    row = {
        "run_id": run_id,
        "corridor": records[0].route,
        "index_value": idx.index,
        "index_ex_festival": idx.index_ex_festival,
        "festival_component": idx.festival_component,
        "k_factor_used": k,
        "base_period": base_period,
        "records_ingested": len(records),
        "festival_flagged_count": fcount,
        "festival_breakdown": breakdown,
        "anomalies_excluded_count": iqr_res.excluded_total,
        "routes_matched": idx.routes_matched,
        "ingestion_source": "imported_csv",
        "tiers_used": ["imported_csv"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        row["db_target"] = persist_run(row)
    except Exception:  # noqa: BLE001
        row["db_target"] = "none"

    return {
        "run_id": run_id,
        "badge": "imported csv",
        "sanitize_report": sreport.to_dict(),
        "rejected_sample": rejected[:10],
        # flat fields so the dashboard can drive its choreography the same way
        # it does off the /api/execute-audit SSE 'done' frame
        "index": idx.index,
        "index_ex_festival": idx.index_ex_festival,
        "festival_component": idx.festival_component,
        "festival_flagged": fcount,
        "routes_matched": idx.routes_matched,
        "records_ingested": len(records),
        "anomalies": iqr_res.excluded_total,
        "excluded_low": iqr_res.excluded_low,
        "excluded_high": iqr_res.excluded_high,
        "fences": iqr_res.fences.to_dict(),
        "clean_prices": [r.price for r in iqr_res.clean],
        "anomaly_prices": [r.price for r in iqr_res.anomalies],
        "anomaly_rows": [
            {"airline": r.airline, "flight": r.flight_number, "price": r.price,
             "reason": r.exclusion_reason, "source": r.source}
            for r in iqr_res.anomalies[:40]
        ],
        "index_detail": idx.to_dict(),
        "festival": {"flagged": fcount, "breakdown": breakdown},
        "db_target": row["db_target"],
    }
