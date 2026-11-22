#!/usr/bin/env bash
# Initialize catalog indexes without blocking web startup or probing services.
set -euo pipefail
cd "$(dirname "$0")/../.."
child_pid=""
cleanup() {
  kill "${child_pid:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

while true; do
  COMPONENT=api bash scripts/replit/python.sh manage.py aed_prepare_search --skip-checks &
  child_pid=$!
  if wait "$child_pid"; then
    exit 0
  fi
  echo "Catalog initialization failed; retrying the operation in 5 seconds." >&2
  sleep 5 &
  child_pid=$!
  wait "$child_pid"
done
