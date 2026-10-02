#!/usr/bin/env bash
#
# Schedule the Mac to wake at 05:55 every day so the 06:00 collector job runs
# even if the laptop is closed / asleep. Needs your password (sudo) — it changes
# a system power setting, nothing else.
#
#     bash scripts/setup_wake.sh
#
# Undo later with:   sudo pmset repeat cancel
#
set -euo pipefail

echo "Scheduling a daily 05:55 wake (5 min before the 06:00 collector)."
echo "You'll be asked for your password."
sudo pmset repeat wakeorpoweron MTWRFSU 05:55:00

echo
echo "Done. Current schedule:"
pmset -g sched
