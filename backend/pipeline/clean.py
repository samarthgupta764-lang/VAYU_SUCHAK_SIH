"""
CSV sanitiser — pipeline/clean.py

The cleaning logic from the original `sanitize_csv` scraper script, lifted into
the pipeline and pointed at `/api/import-csv`. Takes a raw pre-scraped fare
extract (any of the column layouts we've produced), runs the format + validity
checks, and returns records in the FareRecord contract plus a rejection report.

Pure: no file I/O here — the API layer hands us parsed rows, we hand back
records. (A thin `sanitize_csv_file` helper is kept for CLI / test use.)
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from pipeline.contract import ContractError, FareRecord, normalise

# --- field-level cleaners (from the original script) -------------------------


def clean_price(value: Any) -> int | None:
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def clean_duration(value: Any) -> int:
    """'2h 35m' -> 155 (minutes). Missing -> 0."""
    s = str(value)
    h = re.search(r"(\d+)h", s)
    m = re.search(r"(\d+)m", s)
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


def clean_stops(value: Any) -> int | None:
    s = str(value).lower()
    if "non-stop" in s or "nonstop" in s:
        return 0
    match = re.search(r"(\d+)\s*stop", s)
    if match:
        return int(match.group(1))
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# --- report -----------------------------------------------------------------


@dataclass(slots=True)
class SanitizeReport:
    started: int
    missing_required: int
    duplicates: int
    invalid_values: int
    final: int

    def to_dict(self) -> dict[str, int]:
        return {
            "rows_in": self.started,
            "removed_missing_required": self.missing_required,
            "removed_duplicates": self.duplicates,
            "removed_invalid_values": self.invalid_values,
            "records_out": self.final,
        }


REQUIRED = ("route", "airline", "price", "departure_ts")
MAX_PRICE = 200_000
MAX_DURATION_MIN = 1_440


def sanitize_rows(rows: list[dict[str, Any]]) -> tuple[list[FareRecord], SanitizeReport, list[dict]]:
    """
    rows: list of raw dicts from a parsed CSV.
    -> (records, report, rejected)
    """
    started = len(rows)
    rejected: list[dict] = []
    staged: list[FareRecord] = []
    seen_ids: set[str] = set()
    missing = dupes = invalid = 0

    for raw in rows:
        try:
            rec = normalise(raw, ingestion_source="imported_csv")
        except ContractError as exc:
            missing += 1
            rejected.append({"row": raw, "reason": str(exc)})
            continue

        # invalid-value check (a sold-out row is allowed to have price 0 — it's
        # an availability signal, not a fare, and never reaches the index)
        if (rec.price <= 0 and not rec.is_sold_out) or rec.price > MAX_PRICE:
            invalid += 1
            rejected.append({"row": raw, "reason": f"price out of range: {rec.price}"})
            continue
        if rec.duration_minutes is not None and (
            rec.duration_minutes < 0 or rec.duration_minutes > MAX_DURATION_MIN
        ):
            invalid += 1
            rejected.append({"row": raw, "reason": f"duration out of range: {rec.duration_minutes}"})
            continue

        # duplicate check (first occurrence wins)
        if rec.flight_id in seen_ids:
            dupes += 1
            continue
        seen_ids.add(rec.flight_id)
        staged.append(rec)

    report = SanitizeReport(started, missing, dupes, invalid, len(staged))
    return staged, report, rejected


def sanitize_csv_bytes(blob: bytes) -> tuple[list[FareRecord], SanitizeReport, list[dict]]:
    df = pd.read_csv(io.BytesIO(blob), dtype=str, keep_default_na=False)
    return sanitize_rows(df.to_dict(orient="records"))


def sanitize_csv_file(path: str) -> tuple[list[FareRecord], SanitizeReport, list[dict]]:
    with open(path, "rb") as fh:
        return sanitize_csv_bytes(fh.read())
