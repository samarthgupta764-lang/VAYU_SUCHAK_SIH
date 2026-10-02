"""
AI · Nowcasting / Imputation Model — pipeline/ml/nowcast.py

Fills route-days a live scrape missed. This is IMPUTATION of missing *observed*
route-days, not forecasting — it never predicts a future price. (This is how
central banks nowcast GDP.)

    impute_gaps(route_day_matrix, expected_routes) -> NowcastResult

Gradient-boosted regressor + a simple residual band for the confidence interval.
Missing artifact -> pass-through (returns the matrix unchanged, nothing imputed,
`loaded=False`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from config import settings


class PeerFeatureBuilder:
    """
    Picklable feature builder stored inside the nowcast model bundle. Given the
    fares a run DID observe, produces the feature row used to impute a route it
    missed. Lives here (not in the train script) so unpickling always resolves.
    """

    def __init__(self, global_mean: float) -> None:
        self.global_mean = float(global_mean)

    def __call__(self, route: str, observed: dict[str, float], _ctx: dict) -> list[float]:
        peers = list(observed.values()) or [self.global_mean]
        std = float(np.std(peers)) if len(peers) > 1 else 0.0
        return [
            float(np.mean(peers)),
            float(np.median(peers)),
            len(peers),
            std,
            hash(route) % 1000 / 1000.0,
        ]


@dataclass
class ImputedCell:
    route: str
    value: float
    lower: float
    upper: float


@dataclass
class NowcastResult:
    per_route_price: dict[str, float]          # complete Pt map after imputation
    imputed: list[ImputedCell] = field(default_factory=list)
    loaded: bool = False
    note: str = ""

    @property
    def imputed_count(self) -> int:
        return len(self.imputed)

    def confidence_bands(self) -> dict[str, tuple[float, float]]:
        return {c.route: (c.lower, c.upper) for c in self.imputed}

    def to_dict(self) -> dict[str, Any]:
        return {
            "imputed_route_days": self.imputed_count,
            "model_loaded": self.loaded,
            "note": self.note,
            "imputed": [c.__dict__ for c in self.imputed],
        }


@lru_cache(maxsize=1)
def _load() -> Any | None:
    path = settings.path(settings.nowcast_model_path)
    if not path.exists():
        return None
    try:
        import joblib

        return joblib.load(path)
    except Exception:  # noqa: BLE001
        return None


def model_info() -> dict[str, Any]:
    """Static training-time metadata for the dashboard / API — no imputation."""
    bundle = _load()
    if bundle is None:
        return {"loaded": False, "path": str(settings.nowcast_model_path)}
    return {
        "loaded": True,
        "version": bundle.get("version") if isinstance(bundle, dict) else None,
        "trained_at": bundle.get("trained_at") if isinstance(bundle, dict) else None,
        "trained_rows": bundle.get("rows") if isinstance(bundle, dict) else None,
        "eval": bundle.get("eval") if isinstance(bundle, dict) else None,
    }


def impute_gaps(
    observed_price: dict[str, float],
    expected_routes: list[str],
    *,
    context: dict[str, Any] | None = None,
) -> NowcastResult:
    """
    observed_price : {route: Pt} the scrape actually produced
    expected_routes: routes the index needs (keys of base_year_reference)
    """
    missing = [r for r in expected_routes if r not in observed_price]
    if not missing:
        return NowcastResult(per_route_price=dict(observed_price), note="no gaps to impute")

    bundle = _load()
    if bundle is None:
        return NowcastResult(
            per_route_price=dict(observed_price),
            loaded=False,
            note=f"model not loaded ({settings.nowcast_model_path}) — "
            f"{len(missing)} route-day(s) left unfilled",
        )

    model = bundle["model"] if isinstance(bundle, dict) else bundle
    resid_std = bundle.get("resid_std", 0.0) if isinstance(bundle, dict) else 0.0
    feat = bundle.get("feature_builder") if isinstance(bundle, dict) else None

    complete = dict(observed_price)
    cells: list[ImputedCell] = []
    for route in missing:
        X = feat(route, observed_price, context or {}) if feat else _fallback_features(route, observed_price)
        yhat = float(model.predict([X])[0])
        band = 1.2816 * resid_std * yhat  # ~80% interval
        complete[route] = round(yhat, 2)
        cells.append(
            ImputedCell(route=route, value=round(yhat, 2),
                        lower=round(yhat - band, 2), upper=round(yhat + band, 2))
        )

    return NowcastResult(
        per_route_price=complete,
        imputed=cells,
        loaded=True,
        note=f"imputed {len(cells)} route-day(s)",
    )


def _fallback_features(route: str, observed: dict[str, float]) -> list[float]:
    peers = list(observed.values())
    mean_peer = sum(peers) / len(peers) if peers else 0.0
    return [mean_peer, len(peers), hash(route) % 1000 / 1000.0]
