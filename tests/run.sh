#!/usr/bin/env bash
# Runs the API tests (and the phone-size UI walkthrough if Playwright is
# installed) against a throwaway server with an empty temporary database.
#   tests/run.sh [path-to-python-with-fastapi]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-python3}"
PORT=8799
DATA=$(mktemp -d)
trap 'kill $SERVER 2>/dev/null; rm -rf "$DATA"' EXIT
(cd app && CLUSTERLOG_DATA="$DATA" exec "$PY" -m uvicorn main:app --host 127.0.0.1 --port $PORT) >"$DATA/server.log" 2>&1 &
SERVER=$!
curl -s --retry 20 --retry-connrefused --retry-delay 1 -o /dev/null "http://127.0.0.1:$PORT/api/health"
"$PY" tests/test_api.py "http://127.0.0.1:$PORT"
if "$PY" -c "import playwright" 2>/dev/null; then
  "$PY" tests/ui_walkthrough.py "http://127.0.0.1:$PORT" "${SHOTS:-$DATA/shots}"
else
  echo "(Playwright not installed — skipping UI walkthrough)"
fi
