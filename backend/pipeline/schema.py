"""
db/schema.sql loaded once, plus a comment-aware statement splitter.

SQLite's `executescript` understands `--` comments and multiple statements, but
SQLAlchemy / psycopg execute one statement at a time — a naive `split(";")`
breaks on a semicolon inside a comment. `statements()` strips comments first.
"""

from __future__ import annotations

import re
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
RAW: str = _PATH.read_text()


def statements() -> list[str]:
    no_comments = re.sub(r"--[^\n]*", "", RAW)
    return [s.strip() for s in no_comments.split(";") if s.strip()]
