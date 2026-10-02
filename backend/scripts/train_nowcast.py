"""
Train the Nowcasting / Imputation model  ->  models/nowcast_v1.joblib

Goal: given the fares we DID scrape on a run, estimate a route we missed, from
correlated routes' current prices + calendar features. Imputation of a missing
*observed* route-day — never a future forecast.

Training data = a route x day matrix built from cache snapshots + Kaggle history.
For each (route, day) we hold that route out and learn to reconstruct it from the
other routes that day. Residual std -> the confidence band.

    python -m scripts.train_nowcast
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import REPO_ROOT, settings
from pipeline.contract import normalise_many
from pipeline.ml.nowcast import PeerFeatureBuilder  # defined there so unpickle resolves

KAGGLE_DIR = REPO_ROOT / "data" / "kaggle"


def _matrix() -> pd.DataFrame:
    rows = []
    for snap in settings.cache_path.glob("*.json"):
        data = json.loads(snap.read_text())
        recs, _ = normalise_many(data.get("records", []))
        for r in recs:
            rows.append({"route": r.route, "day": r.departure_ts[:10], "price": r.price})
    for csv in KAGGLE_DIR.glob("*.csv"):
        df = pd.read_csv(csv, dtype=str, keep_default_na=False)
        recs, _ = normalise_many(df.to_dict("records"))
        for r in recs:
            rows.append({"route": r.route, "day": r.departure_ts[:10], "price": r.price})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.pivot_table(index="day", values="price", columns="route", aggfunc="median")


def main() -> None:
    from sklearn.ensemble import GradientBoostingRegressor

    mat = _matrix()
    if mat.empty or mat.shape[1] < 2:
        print("not enough route coverage to train nowcast. Seed more corridors first.")
        return
    print(f"matrix: {mat.shape[0]} day(s) x {mat.shape[1]} route(s)")

    routes = list(mat.columns)
    global_mean = float(np.nanmean(mat.values))

    X_rows, y_rows = [], []
    for _, day_row in mat.iterrows():
        vals = day_row.to_dict()
        for target in routes:
            if np.isnan(vals[target]):
                continue
            peers = [v for k, v in vals.items() if k != target and not np.isnan(v)]
            if not peers:
                continue
            X_rows.append([np.mean(peers), np.median(peers), len(peers),
                           np.std(peers) if len(peers) > 1 else 0.0,
                           hash(target) % 1000 / 1000.0])
            y_rows.append(vals[target])

    if len(X_rows) < 20:
        print(f"only {len(X_rows)} training samples — need more historical days. Skipping.")
        return

    X = np.array(X_rows)
    y = np.array(y_rows)
    cut = int(len(X) * 0.8)
    model = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=7)
    model.fit(X[:cut], y[:cut])

    pred = model.predict(X[cut:])
    resid = y[cut:] - pred
    mae = float(np.mean(np.abs(resid)))
    resid_std = float(np.std(resid) / max(np.mean(y[cut:]), 1))
    within = float(np.mean(np.abs(resid) <= 1.2816 * resid_std * np.mean(y[cut:])))
    print(f"eval  MAE={mae:.1f}  ~80%-band coverage={within:.2f}")

    bundle = {
        "model": model,
        "feature_builder": PeerFeatureBuilder(global_mean),
        "resid_std": resid_std,
        "version": "v1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "eval": {"mae": mae, "band_coverage": within},
        "global_mean": global_mean,
    }
    out = settings.path(settings.nowcast_model_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(bundle, out)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
