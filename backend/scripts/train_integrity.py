"""
Train the Data-Integrity model  ->  models/integrity_v1.joblib

IsolationForest over engineered fare features. Trained on the real fare corpus
(cache snapshots + data/kaggle/*.csv), evaluated against a labelled
synthetic-injection set (decoy lows, absurd highs, broken price-per-km) so we can
print precision / recall — the numbers the feature list asks for.

    python -m scripts.train_integrity
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import REPO_ROOT, settings
from pipeline.contract import FareRecord, normalise_many
from pipeline.ml.features import build_matrix, route_medians

RNG = random.Random(7)
KAGGLE_DIR = REPO_ROOT / "data" / "kaggle"


def _load_corpus() -> list[FareRecord]:
    records: list[FareRecord] = []
    for snap in settings.cache_path.glob("*.json"):
        data = json.loads(snap.read_text())
        recs, _ = normalise_many(data.get("records", []), ingestion_source="cache")
        records.extend(recs)
    for csv in KAGGLE_DIR.glob("*.csv"):
        df = pd.read_csv(csv, dtype=str, keep_default_na=False)
        recs, _ = normalise_many(df.to_dict("records"), ingestion_source="cache")
        records.extend(recs)
    return records


def _inject_anomalies(records: list[FareRecord], frac: float = 0.12) -> tuple[list[FareRecord], np.ndarray]:
    out = [FareRecord(**r.to_dict()) for r in records]
    labels = np.zeros(len(out) + int(len(out) * frac), dtype=int)
    extra: list[FareRecord] = []
    med = route_medians(records)
    for _ in range(int(len(out) * frac)):
        base = RNG.choice(records)
        d = base.to_dict()
        kind = RNG.choice(["decoy_low", "absurd_high", "ppk_break"])
        if kind == "decoy_low":
            d["price"] = RNG.choice([1, 2, 10, 0.0]) or 1
        elif kind == "absurd_high":
            d["price"] = med.get(base.route, 5000) * RNG.uniform(6, 15)
        else:
            d["price"] = med.get(base.route, 5000) * RNG.uniform(0.9, 1.1)
            d["route"] = "DEL-GAU" if base.route != "DEL-GAU" else "BOM-BLR"
        extra.append(FareRecord(**d))
    combined = out + extra
    labels[len(out):] = 1
    return combined, labels


def main() -> None:
    from sklearn.ensemble import IsolationForest

    corpus = _load_corpus()
    if len(corpus) < 30:
        print(f"corpus too small ({len(corpus)}). Run `python -m scripts.seed_cache` first.")
        return
    print(f"corpus: {len(corpus)} real fares")

    combined, labels = _inject_anomalies(corpus)
    X = build_matrix(combined, route_median=route_medians(corpus))
    feature_cols = list(X.columns)

    # split
    idx = np.arange(len(combined))
    RNG_np = np.random.default_rng(7)
    RNG_np.shuffle(idx)
    cut = int(len(idx) * 0.75)
    tr, te = idx[:cut], idx[cut:]

    model = IsolationForest(
        n_estimators=200,
        contamination=settings.integrity_contamination,
        random_state=7,
    )
    model.fit(X.iloc[tr])

    pred = (model.predict(X.iloc[te]) == -1).astype(int)
    truth = labels[te]
    tp = int(((pred == 1) & (truth == 1)).sum())
    fp = int(((pred == 1) & (truth == 0)).sum())
    fn = int(((pred == 0) & (truth == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    print(f"eval  precision={precision:.3f}  recall={recall:.3f}  (tp={tp} fp={fp} fn={fn})")

    bundle = {
        "model": model,
        "feature_cols": feature_cols,
        "version": "v1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(corpus),
        "contamination": settings.integrity_contamination,
        "eval": {"precision": precision, "recall": recall},
    }
    out = settings.path(settings.integrity_model_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(bundle, out)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
