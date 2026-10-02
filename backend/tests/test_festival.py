"""Festival flag engine — verify against a real 2026 calendar (deep-dive §7.2)."""

from datetime import date

import pytest

from pipeline.festival import build_festival_dates, flag, flag_festivals
from tests.conftest import rec


def test_2026_has_the_major_festivals():
    names = {n for n, _ in build_festival_dates([2026])}
    assert "Diwali" in names
    assert "Holi" in names
    assert "Christmas Day" in names


def test_diwali_2026_is_early_november():
    dts = {n: d for n, d in build_festival_dates([2026])}
    assert dts["Diwali"].year == 2026
    assert dts["Diwali"].month in (10, 11)


def test_record_in_diwali_window_is_flagged():
    diwali = {n: d for n, d in build_festival_dates([2026])}["Diwali"]
    on_day = rec(5000, ts=f"{diwali.isoformat()}T06:15:00+05:30", fno="A")
    plus6 = rec(5000, ts=f"{date(diwali.year, diwali.month, min(diwali.day + 6, 28)).isoformat()}T06:15:00+05:30", fno="B")
    recs, count, breakdown = flag_festivals([on_day, plus6], build_festival_dates([2026]), window_days=7)
    assert on_day.is_festival_season == 1
    assert on_day.festival_matched == "Diwali"
    assert count == 2
    assert breakdown.get("Diwali") == 2


def test_off_season_record_not_flagged():
    june = rec(5000, ts="2026-06-15T06:15:00+05:30", fno="C")
    recs, count, _ = flag([june], window_days=7)
    assert june.is_festival_season == 0
    assert count == 0


def test_window_boundary_is_exclusive_beyond_7_days():
    diwali = {n: d for n, d in build_festival_dates([2026])}["Diwali"]
    far = rec(5000, ts=f"{date(diwali.year, 12, 25).isoformat()}T06:15:00+05:30", fno="D")
    _, _, breakdown = flag_festivals([far], [("Diwali", diwali)], window_days=7)
    assert far.is_festival_season == 0
