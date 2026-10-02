"""
pipeline/ml/ — the two self-trained models + shared feature engineering.

No external AI API. Both models are scikit-learn, trained offline by the scripts
in `scripts/` on a Kaggle historical corpus + accumulated scrape data, saved as
versioned joblib artifacts under `models/`.

Inference is a pure function. When the artifact is missing the function is a
transparent pass-through — the IQR filter and Laspeyres index still work, the
run is just tagged `ml: model not loaded`.
"""
