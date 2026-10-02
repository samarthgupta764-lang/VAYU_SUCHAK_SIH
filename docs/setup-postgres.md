# Postgres (primary persistence tier) + the wake schedule

The app writes to **Postgres first** and falls back to **SQLite (WAL)** on any
connection/operational error — every row is tagged `db_target` so the two can be
reconciled. Blank `PG_DSN` = SQLite only.

## Local Postgres — Homebrew (what this machine uses)

```bash
brew install postgresql@17
brew services start postgresql@17          # auto-starts on login
createuser -s vayu                         # or: psql postgres -c "CREATE ROLE vayu LOGIN PASSWORD 'vayu'"
createdb -O vayu vayu
```

Then in `backend/.env`:
```
PG_DSN=postgresql+psycopg://vayu:vayu@localhost:5432/vayu
```

Bring the history collected while on SQLite across:
```bash
cd backend && .venv/bin/python -m scripts.migrate_to_pg
```

The app creates its own schema on the first write — nothing else to run.

## Local Postgres — Docker (alternative)

```bash
docker compose -f deploy/docker-compose.yml up -d
```
Same `PG_DSN` and `migrate_to_pg` step.

## Verifying the failover (for the demo)

```bash
brew services stop postgresql@17           # or: docker compose ... stop
# run a collection or hit /api/execute-audit -> rows land in SQLite, db_target = sqlite_fallback
brew services start postgresql@17
# next write -> back to Postgres, db_target = postgres
```

## The wake schedule (so the laptop collector doesn't miss days)

The `launchd` collector runs at 06:00, or the next wake if the Mac was asleep.
To make it fire at 06:00 even when the lid is closed:

```bash
cd backend && bash scripts/setup_wake.sh    # asks for your password
```

This runs `sudo pmset repeat wakeorpoweron MTWRFSU 05:55:00` — a daily 05:55
wake, 5 minutes before the job. Undo with `sudo pmset repeat cancel`.

Once the project is deployed to an always-on box, neither the wake schedule nor
a local Postgres is needed — the box runs both.
