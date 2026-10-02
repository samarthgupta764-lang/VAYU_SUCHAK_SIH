# backend/data/kaggle/

Drop the **Kaggle "Flight Price Prediction"** CSVs here:
https://www.kaggle.com/datasets/shubhambathwal/flight-price-prediction

Expected files (any subset works): `Clean_Dataset.csv`, `economy.csv`, `business.csv`.

Used for:
- `P0` — mean base-year (2022) economy fare per route → `scripts/build_base_reference.py`
- training corpus for both ML models → `scripts/train_integrity.py`, `scripts/train_nowcast.py`

Not committed to git (bulky). NOT scraped — a public research dataset.
