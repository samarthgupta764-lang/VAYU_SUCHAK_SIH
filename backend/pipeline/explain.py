"""
Explainability Annotator — pipeline/explain.py

Rule-based, no model, no API. Tags each index movement with a cause drawn from
what the pipeline itself already knows: festival-window proximity, k_factor
change, source degradation, imputation share. Produces one human sentence.

    annotate(run, prev_run) -> Annotation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Annotation:
    summary: str
    drivers: list[str] = field(default_factory=list)
    delta_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "drivers": self.drivers, "delta_pct": self.delta_pct}


def _get(run: dict, *keys, default=None):
    for k in keys:
        if k in run and run[k] is not None:
            return run[k]
    return default


def annotate(run: dict[str, Any], prev_run: dict[str, Any] | None = None) -> Annotation:
    index = float(_get(run, "index_value", "index", default=0.0) or 0.0)
    drivers: list[str] = []

    # --- delta vs previous run for the same corridor ---
    delta_pct = None
    if prev_run:
        prev_index = float(_get(prev_run, "index_value", "index", default=0.0) or 0.0)
        if prev_index:
            delta_pct = round((index - prev_index) / prev_index * 100, 2)

    # --- festival component ---
    fest_component = _get(run, "festival_component")
    fest_flagged = int(_get(run, "festival_flagged_count", default=0) or 0)
    fest_breakdown = _get(run, "festival_breakdown", default={}) or {}
    if fest_component:
        top = ", ".join(f"{k} {v}" for k, v in sorted(fest_breakdown.items(), key=lambda x: -x[1]))
        sign = "+" if fest_component >= 0 else "−"
        drivers.append(
            f"festival demand {sign}{abs(fest_component):.2f} index pts "
            f"({fest_flagged} fares{': ' + top if top else ''})"
        )

    # --- k_factor change ---
    if prev_run is not None:
        k_now = _get(run, "k_factor_used", "k_factor")
        k_prev = _get(prev_run, "k_factor_used", "k_factor")
        if k_now is not None and k_prev is not None and k_now != k_prev:
            drivers.append(f"k_factor {k_prev} -> {k_now} ({_get(run, 'anomalies_excluded_count', default=0)} excluded)")

    # --- source degradation ---
    degraded = _get(run, "sources_degraded", default=0) or 0
    names = _get(run, "degraded_sources", "fallback_sources", default=[]) or []
    if degraded:
        drivers.append(
            f"{degraded} source(s) degraded"
            + (f" ({', '.join(names)})" if names else "")
        )

    # --- imputation share ---
    imputed = int(_get(run, "imputed_route_days", default=0) or 0)
    if imputed:
        drivers.append(f"{imputed} route-day(s) imputed (nowcast)")

    # --- ML integrity flags ---
    ml_flagged = int(_get(run, "ml_flagged_count", default=0) or 0)
    if ml_flagged:
        drivers.append(f"{ml_flagged} fare(s) flagged by integrity model")

    # --- assemble the sentence ---
    head = f"Index {index:.2f}"
    if delta_pct is not None:
        arrow = "+" if delta_pct >= 0 else ""
        head += f" ({arrow}{delta_pct:.2f}% vs last run)"
    body = " — " + "; ".join(drivers) if drivers else " — no notable drivers this run"
    return Annotation(summary=head + body, drivers=drivers, delta_pct=delta_pct)
