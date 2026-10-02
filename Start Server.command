#!/usr/bin/env bash
#
# Double-click this file in Finder to start the VAYU-SUCHAK server.
# It opens a Terminal window, starts the backend (via serve.sh), and opens
# the dashboard in your browser once it's up. Close the Terminal window
# (or press Ctrl-C in it) to stop the server.
#
cd "$(dirname "${BASH_SOURCE[0]}")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

# open the dashboard once the server responds (don't block server startup on it)
(
  for _ in $(seq 1 30); do
    sleep 1
    curl -s -o /dev/null "http://$HOST:$PORT/" && { open "http://$HOST:$PORT/"; break; }
  done
) &

./serve.sh
