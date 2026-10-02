"""
AI · Data-Integrity Model — pipeline/ml/integrity.py

An IsolationForest that runs as a second, learned pass on top of the IQR filter.
It flags decoy / placeholder / bot-trap fares that sit inside the Tukey fence
(so IQR passes them) but are structurally odd — wrong price-per-km, impossible
time-to-departure for the price, airline/source combinations that never occur.

    score_integrity(records) -> IntegrityResult

Pure. Loads `models/integrity_v1.joblib` once. Missing artifact -> pass-through
(every record scored 0.0, nothing flagged, `loaded=False`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from config import settings
from pipeline.contract import FareRecord
from pipeline.ml.features import build_matrix, route_medians


@dataclass
class IntegrityResult:
    records: list[FareRecord]
    flagged_count: int = 0
    loaded: bool = False
    note: str = ""
    flagged_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ml_flagged_count": self.flagged_count,
            "model_loaded": self.loaded,
            "note": self.note,
            "flagged_ids": self.flagged_ids,
        }


@lru_cache(maxsize=1)
def _load() -> Any | None:
    path = settings.path(settings.integrity_model_path)
    if not path.exists():
        return None
    try:
        import joblib

        return joblib.load(path)
    except Exception:  # noqa: BLE001
        return None


def model_info() -> dict[str, Any]:
    """Static training-time metadata for the dashboard / API — no scoring."""
    bundle = _load()
    if bundle is None:
        return {"loaded": False, "path": str(settings.integrity_model_path)}
    return {
        "loaded": True,
        "version": bundle.get("version") if isinstance(bundle, dict) else None,
        "trained_at": bundle.get("trained_at") if isinstance(bundle, dict) else None,
        "trained_rows": bundle.get("rows") if isinstance(bundle, dict) else None,
        "eval": bundle.get("eval") if isinstance(bundle, dict) else None,
    }


def score_integrity(records: list[FareRecord]) -> IntegrityResult:
    if not records:
        return IntegrityResult(records=[], note="no records")

    bundle = _load()
    if bundle is None:
        for r in records:
            r.integrity_score = 0.0
            r.ml_flag = 0
        return IntegrityResult(
            records=records,
            loaded=False,
            note=f"model not loaded ({settings.integrity_model_path}) — IQR-only pass",
        )

    model = bundle["model"] if isinstance(bundle, dict) else bundle
    feature_cols = bundle.get("feature_cols") if isinstance(bundle, dict) else None

    X = build_matrix(records, route_median=route_medians(records))
    if feature_cols:
        X = X.reindex(columns=feature_cols, fill_value=0.0)

    # IsolationForest: decision_function > 0 inlier, < 0 outlier
    raw = model.decision_function(X)
    preds = model.predict(X)  # 1 inlier, -1 outlier

    flagged_ids: list[str] = []
    for r, score, pred in zip(records, raw, preds):
        r.integrity_score = round(float(score), 4)
        r.ml_flag = int(pred == -1)
        if r.ml_flag:
            r.exclusion_reason = r.exclusion_reason or "ml_integrity_flag"
            flagged_ids.append(r.flight_id)

    return IntegrityResult(
        records=records,
        flagged_count=len(flagged_ids),
        loaded=True,
        note=f"integrity model {bundle.get('version', 'v?')}"
        if isinstance(bundle, dict)
        else "integrity model",
        flagged_ids=flagged_ids,
    )
