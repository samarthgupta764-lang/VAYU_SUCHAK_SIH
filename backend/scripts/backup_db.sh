#!/usr/bin/env bash
#
# Snapshot the fare-quote database. Once daily collection starts, this file is
# the one irreplaceable asset — a lost DB means starting the 30-day back-test
# window over. Run this now and then (or add it to the launchd job later).
#
#     bash scripts/backup_db.sh
#
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="$BACKEND_DIR/db/fallback.sqlite"
DEST_DIR="$BACKEND_DIR/data/backups"

[ -f "$DB" ] || { echo "no database at $DB yet — nothing to back up"; exit 0; }
mkdir -p "$DEST_DIR"

STAMP="$(date +%Y%m%dT%H%M%S)"
OUT="$DEST_DIR/fare_quotes_$STAMP.sqlite"

# .backup is safe to run while the collector may be writing (WAL-aware)
sqlite3 "$DB" ".backup '$OUT'"
gzip -f "$OUT"
echo "backed up -> $OUT.gz"

# keep the 14 most recent, drop older
ls -1t "$DEST_DIR"/fare_quotes_*.sqlite.gz 2>/dev/null | tail -n +15 | xargs -r rm --
