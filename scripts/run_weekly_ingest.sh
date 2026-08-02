#!/usr/bin/env bash
# Weekly ingestion + roundup, for a plain OS cron/Task Scheduler entry when
# this tool is self-hosted (i.e. not relying on a Claude Code Routine).
#
# Example crontab entry (Monday 8am local time):
#   0 8 * * 1 /path/to/Events-Calendar-Tool/scripts/run_weekly_ingest.sh >> /path/to/Events-Calendar-Tool/data/ingest.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src

echo "=== $(date -u +%FT%TZ) weekly ingest ==="
python3 -m events_tool.cli ingest
python3 -m events_tool.cli roundup --days 7 --export md --out "data/roundup_$(date +%F).md"
echo "=== done ==="
