"""
Copy every row from the SQLite fallback DB into Postgres — scripts/migrate_to_pg.py

Run once after pointing PG_DSN at a Postgres instance, so the history collected
while on SQLite-only isn't left behind. Idempotent (upserts by primary key).

    python -m scripts.migrate_to_pg
"""

from __future__ import annotations

import sqlite3

from config import settings
from pipeline.schema import statements as _ddl

_TABLES = {
    "fare_quotes": "quote_id",
    "collection_runs": "run_id",
    "index_values": "period_type, period, scope",
    "audit_runs": "run_id",
}


def main() -> None:
    if not settings.postgres_enabled:
        print("PG_DSN not set — nothing to migrate to.")
        return
    src = settings.sqlite_path
    if not src.exists():
        print(f"no SQLite DB at {src} — nothing to migrate.")
        return

    from sqlalchemy import create_engine, text
    engine = create_engine(settings.pg_dsn, connect_args={"connect_timeout": 5})

    lite = sqlite3.connect(src)
    lite.row_factory = sqlite3.Row
    total = 0
    with engine.begin() as pg:
        for stmt in _ddl():
            pg.execute(text(stmt))
        for table, conflict in _TABLES.items():
            try:
                rows = [dict(r) for r in lite.execute(f"SELECT * FROM {table}").fetchall()]
            except sqlite3.Error:
                continue
            if not rows:
                print(f"  {table:<16} 0")
                continue
            cols = list(rows[0])
            ph = ", ".join(f":{c}" for c in cols)
            upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict.split(", "))
            sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
                   f"ON CONFLICT ({conflict}) DO UPDATE SET {upd}")
            pg.execute(text(sql), rows)
            total += len(rows)
            print(f"  {table:<16} {len(rows)}")
    lite.close()
    print(f"\nmigrated {total} rows -> Postgres")


if __name__ == "__main__":
    main()
