#!/usr/bin/env bash
# Convenience wrapper for the Phase 2 web app.
#
#   scripts/run_web.sh              # runs on 127.0.0.1:5000
#   scripts/run_web.sh --host 0.0.0.0 --port 8080
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
python3 -m events_tool.cli web run "$@"
