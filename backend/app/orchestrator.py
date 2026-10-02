"""
The orchestrator — app/orchestrator.py

`run_audit(params)` is an async generator. It runs every pipeline stage and
yields exactly one SSE line after each, with a small pause so the console
visibly streams. This is the ONLY file that imports the pipeline modules
together, talks to the DB, and knows about the wire format.

Pipeline functions never log, never stream, never persist — that all happens
here, between stages.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from config import settings
from pipeline import festival, iqr, laspeyres
from pipeline.explain import annotate
from pipeline.ingest import fetch_fares
from pipeline.ml.integrity import score_integrity
from pipeline.ml.nowcast import impute_gaps
from pipeline.persistence import fetch_runs, persist_run

_PAUSE = 0.2


def sse(stage: str, message: str, **extra: Any) -> str:
    payload = {"stage": stage, "message": message, **extra}
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _sample(values: list[float], cap: int = 600) -> list[float]:
    """Cap a price list for the SSE payload (histogram only needs the shape)."""
    vals = [round(float(v), 2) for v in values]
    if len(vals) <= cap:
        return vals
    step = len(vals) / cap
    return [vals[int(i * step)] for i in range(cap)]


def _sample_rows(rows: list, cap: int = 120) -> list:
    """Evenly sample up to `cap` FareRecords for the SSE ticker payload."""
    if len(rows) <= cap:
        return list(rows)
    step = len(rows) / cap
    return [rows[int(i * step)] for i in range(cap)]


async def run_audit(params) -> AsyncIterator[str]:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    corridor = params.corridor

    yield sse("SYSTEM", f"Audit started · {corridor} · run {run_id[:8]}", run_id=run_id)
    await asyncio.sleep(_PAUSE)

    # ---- 1 · acquisition (3-tier fallback chain) -----------------------
    # scrape_pool's adapters resolve independently (Cleartrip's Playwright XHR
    # capture is ~10-20s vs low single digits for the httpx-direct sources) —
    # run fetch_fares as a task and drain a queue of per-source completions so
    # the console/scrape-monitor updates live instead of freezing until the
    # slowest source (or the whole gather()) finishes.
    source_events: asyncio.Queue = asyncio.Queue()

    def _on_source_done(name: str, status) -> None:
        source_events.put_nowait((name, status))

    fetch_task = asyncio.ensure_future(
        fetch_fares(corridor, params.start, params.end, mode=params.mode,
                    on_source_done=_on_source_done)
    )
    try:
        while not fetch_task.done():
            try:
                name, status = await asyncio.wait_for(source_events.get(), timeout=0.4)
            except asyncio.TimeoutError:
                continue
            yield sse("SOURCE", f"{name}: {status.status}", source=name, status=status.status,
                      latency_ms=status.latency_ms, fares=status.fares, detail=status.detail,
                      block_reason=status.block_reason)
        while not source_events.empty():
            name, status = source_events.get_nowait()
            yield sse("SOURCE", f"{name}: {status.status}", source=name, status=status.status,
                      latency_ms=status.latency_ms, fares=status.fares, detail=status.detail,
                      block_reason=status.block_reason)
        ingest = fetch_task.result()
    except Exception as exc:  # noqa: BLE001
        yield sse("INGEST", f"acquisition failed: {exc}", done=True, error=True)
        return
    records = ingest.records
    yield sse(
        "INGEST",
        ingest.summary(),
        fares=len(records),
        ingestion_source=ingest.ingestion_source,
        tiers=ingest.tiers_used,
        sources=ingest.pool.to_dict()["sources"] if ingest.pool else {},
    )
    await asyncio.sleep(_PAUSE)

    if not records:
        yield sse("SYSTEM", "no fares from any tier — nothing to index", done=True, error=True)
        return

    # ---- 2 · festival flagging ---------------------------------------
    records, fcount, breakdown = festival.flag(records, window_days=settings.festival_window_days)
    top = ", ".join(f"{k}: {v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1]))
    yield sse("FESTIVAL", f"window=±{settings.festival_window_days}d · {fcount} flagged"
              + (f" ({top})" if top else ""), flagged=fcount, breakdown=breakdown)
    await asyncio.sleep(_PAUSE)

    # ---- 3 · dynamic IQR purifier ----------------------------------
    iqr_res = iqr.apply_iqr_filter(records, params.k_factor)
    f = iqr_res.fences
    yield sse(
        "IQR",
        f"k={params.k_factor} · Q1={f.q1:.0f} Q3={f.q3:.0f} · fences "
        f"[{f.lower:.0f}, {f.upper:.0f}] · {iqr_res.excluded_total} excluded "
        f"({iqr_res.excluded_low} low, {iqr_res.excluded_high} high)",
        fences=f.to_dict(),
        anomalies=iqr_res.excluded_total,
        excluded_low=iqr_res.excluded_low,
        excluded_high=iqr_res.excluded_high,
        clean_prices=_sample([r.price for r in iqr_res.clean]),
        anomaly_prices=_sample([r.price for r in iqr_res.anomalies]),
        anomaly_rows=[
            {"airline": r.airline, "flight": r.flight_number, "price": r.price,
             "reason": r.exclusion_reason, "source": r.source}
            for r in iqr_res.anomalies[:40]
        ],
        # a sample of the kept fares for the dashboard ticker (this corridor only)
        clean_rows=[
            {"airline": r.airline, "flight": r.flight_number, "price": r.price, "source": r.source}
            for r in _sample_rows(iqr_res.clean, 120)
        ],
    )
    await asyncio.sleep(_PAUSE)

    # ---- 4 · AI integrity model (second pass on the clean set) ------
    integ = score_integrity(iqr_res.clean)
    clean = [r for r in integ.records if not r.ml_flag]
    yield sse(
        "INTEGRITY",
        f"{integ.flagged_count} flagged · {integ.note}",
        ml_flagged=integ.flagged_count,
        model_loaded=integ.loaded,
    )
    await asyncio.sleep(_PAUSE)

    # ---- 5 · weighted Laspeyres -----------------------------------
    base_ref, base_period = laspeyres.load_base_reference(settings.base_reference)
    idx = laspeyres.compute_index(clean, base_ref, base_period=base_period)

    # ---- 6 · nowcast imputation for missing route-days ----------
    observed_pt = {row["route"]: row["Pt"] for row in idx.table.reset_index().to_dict("records")}
    nowcast = impute_gaps(observed_pt, list(base_ref.keys()), context={"corridor": corridor})
    if nowcast.imputed_count:
        idx = laspeyres.compute_index(clean, base_ref, base_period=base_period)  # base index
        yield sse("NOWCAST", nowcast.note, imputed=nowcast.imputed_count, model_loaded=nowcast.loaded)
    else:
        yield sse("NOWCAST", nowcast.note, imputed=0, model_loaded=nowcast.loaded)
    await asyncio.sleep(_PAUSE)

    per_route = idx.to_dict()["per_route"]
    corridor_row = next((r for r in per_route if r.get("route") == corridor), None)
    yield sse(
        "LASPEYRES",
        f"{idx.routes_matched} routes · Index = {idx.index} · "
        f"ex-festival = {idx.index_ex_festival} (base {base_period} = 100)",
        index=idx.index,
        index_ex_festival=idx.index_ex_festival,
        festival_component=idx.festival_component,
        base_period=base_period,
        routes_matched=idx.routes_matched,
        per_route=per_route,
        corridor_row=corridor_row,
    )
    await asyncio.sleep(_PAUSE)

    # ---- 7 · persistence (Postgres -> SQLite WAL) --------------
    run_row = _assemble_row(
        run_id, params, ingest, fcount, breakdown, iqr_res, integ, idx, nowcast, started
    )
    try:
        target = persist_run(run_row)
    except Exception as exc:  # noqa: BLE001
        target = "none"
        yield sse("DB", f"persist failed: {exc}", error=True)
    else:
        yield sse("DB", f"commit OK -> {target}", db_target=target)
    await asyncio.sleep(_PAUSE)

    # ---- 8 · explainability annotation --------------------------
    run_row["db_target"] = target
    prev = fetch_runs(corridor=corridor, limit=2)
    prev_run = next((r for r in prev if r.get("run_id") != run_id), None)
    note = annotate({**run_row, **idx.to_dict(), "festival_breakdown": breakdown}, prev_run)
    yield sse("EXPLAIN", note.summary, drivers=note.drivers, delta_pct=note.delta_pct)
    await asyncio.sleep(_PAUSE)

    # ---- done ---------------------------------------------------
    yield sse(
        "SYSTEM",
        f"Audit complete — Index = {idx.index}",
        done=True,
        run_id=run_id,
        index=idx.index,
        index_ex_festival=idx.index_ex_festival,
        festival_component=idx.festival_component,
        anomalies=iqr_res.excluded_total,
        ml_flagged=integ.flagged_count,
        imputed=nowcast.imputed_count,
        ingestion_source=ingest.ingestion_source,
        tiers=ingest.tiers_used,
        db_target=target,
        annotation=note.summary,
        fences=f.to_dict(),
        festival_flagged=fcount,
        festival_breakdown=breakdown,
        routes_matched=idx.routes_matched,
        per_route=per_route,
        corridor_row=corridor_row,
        records_ingested=len(ingest.records),
        elapsed_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
    )


def _assemble_row(run_id, params, ingest, fcount, breakdown, iqr_res, integ, idx, nowcast, started) -> dict:
    return {
        "run_id": run_id,
        "corridor": params.corridor,
        "date_range_start": params.start.isoformat(),
        "date_range_end": params.end.isoformat(),
        "index_value": idx.index,
        "index_ex_festival": idx.index_ex_festival,
        "festival_component": idx.festival_component,
        "k_factor_used": params.k_factor,
        "base_period": idx.base_period,
        "records_ingested": len(ingest.records),
        "festival_flagged_count": fcount,
        "festival_breakdown": breakdown,
        "anomalies_excluded_count": iqr_res.excluded_total,
        "ml_flagged_count": integ.flagged_count,
        "imputed_route_days": nowcast.imputed_count,
        "routes_matched": idx.routes_matched,
        "scrape_sources": ingest.pool.to_dict()["sources"] if ingest.pool else {},
        "ingestion_source": ingest.ingestion_source,
        "tiers_used": ingest.tiers_used,
        "sources_degraded": len(ingest.pool.sources_degraded) if ingest.pool else 0,
        "degraded_sources": ingest.pool.sources_degraded if ingest.pool else [],
        "created_at": started.isoformat(),
    }
