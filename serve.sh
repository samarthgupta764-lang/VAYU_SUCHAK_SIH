#!/usr/bin/env bash
#
# VAYU-SUCHAK dev server launcher.
#
#   ./serve.sh            start in the foreground (Ctrl-C to stop)
#   ./serve.sh --bg       start in the background, log to backend/data/server.log
#   ./serve.sh --stop     stop whatever is listening on the port
#   ./serve.sh --restart  stop then start (foreground)
#
# PORT / HOST env vars override the defaults, e.g.  PORT=9000 ./serve.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$REPO_ROOT/backend"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
PY="$BACKEND/.venv/bin/python"
LOG="$BACKEND/data/server.log"

port_pids() { lsof -ti "tcp:$PORT" 2>/dev/null || true; }

stop_server() {
  local pids; pids="$(port_pids)"
  if [ -n "$pids" ]; then
    echo "stopping server on :$PORT (pid $pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(port_pids)"
    # shellcheck disable=SC2086
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  else
    echo "nothing listening on :$PORT"
  fi
}

preflight() {
  if [ ! -x "$PY" ]; then
    echo "error: venv not found at $PY" >&2
    echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    echo "  .venv/bin/playwright install chromium" >&2
    exit 1
  fi
}

start_server() {
  preflight
  stop_server
  cd "$BACKEND"
  echo "VAYU-SUCHAK  ·  http://$HOST:$PORT"
  if [ "${1:-}" = "--bg" ]; then
    mkdir -p "$(dirname "$LOG")"
    HOST="$HOST" PORT="$PORT" nohup "$PY" run.py > "$LOG" 2>&1 &
    sleep 3
    if [ -n "$(port_pids)" ]; then
      echo "running in background (pid $(port_pids)) · logs: $LOG"
    else
      echo "failed to start — check $LOG" >&2
      tail -n 20 "$LOG" >&2 || true
      exit 1
    fi
  else
    exec env HOST="$HOST" PORT="$PORT" "$PY" run.py
  fi
}

case "${1:-}" in
  --stop)               stop_server ;;
  --restart)            start_server ;;
  --bg)                 start_server --bg ;;
  "" | --fg | --start)  start_server ;;
  -h | --help)          sed -n '3,11p' "${BASH_SOURCE[0]}" | sed 's/^#\s\{0,1\}//' ;;
  *) echo "unknown option: $1 (try --help)" >&2; exit 1 ;;
esac
