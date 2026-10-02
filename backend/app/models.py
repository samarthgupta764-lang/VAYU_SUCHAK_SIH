"""
Request / response models — validated at the API boundary.

Bad input -> FastAPI 422 with a clear message before any pipeline code runs,
instead of a KeyError three modules deep.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field, field_validator, model_validator

from config import settings


class AuditParams(BaseModel):
    corridor: str = Field(pattern=r"^[A-Z]{3}-[A-Z]{3}$", examples=["DEL-BOM"])
    start: date
    end: date
    k_factor: float = Field(default_factory=lambda: settings.k_factor_default, gt=0, le=10)
    mode: str = Field(default="auto", pattern=r"^(auto|live|cache)$")

    @field_validator("corridor")
    @classmethod
    def _distinct_endpoints(cls, v: str) -> str:
        a, b = v.split("-")
        if a == b:
            raise ValueError("origin and destination must differ")
        return v

    @model_validator(mode="after")
    def _check_range(self):
        if self.end < self.start:
            raise ValueError("end date is before start date")
        if (self.end - self.start).days > settings.date_range_max_days:
            raise ValueError(f"date range exceeds {settings.date_range_max_days} days")
        return self

    def days(self) -> list[date]:
        n = (self.end - self.start).days
        return [self.start + timedelta(days=i) for i in range(n + 1)]


class RunSummary(BaseModel):
    run_id: str
    corridor: str
    index_value: float | None = None
    index_ex_festival: float | None = None
    k_factor_used: float | None = None
    ingestion_source: str | None = None
    db_target: str | None = None
    created_at: str | None = None


class CorridorList(BaseModel):
    corridors: list[str]
    base_period: str
