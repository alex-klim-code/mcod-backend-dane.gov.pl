#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
for attempt in $(seq 1 60); do
  if redis-cli ping >/dev/null 2>&1 && curl --silent --fail http://127.0.0.1:9200 >/dev/null; then
    exec bash scripts/replit/python.sh manage.py runserver 0.0.0.0:5000 --noreload
  fi
  sleep 1
done
echo "Supporting services are not ready. Start the Supporting services workflow." >&2
exit 1
