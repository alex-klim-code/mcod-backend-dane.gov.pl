#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
export RABBITMQ_HOST="${RABBITMQ_HOST:-127.0.0.1:5672}"
export ELASTICSEARCH_HOSTS="${ELASTICSEARCH_HOSTS:-127.0.0.1:9200}"

cleanup() {
  kill "${nginx_pid:-}" "${api_pid:-}" "${admin_pid:-}" "${worker_pid:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for attempt in $(seq 1 90); do
  if redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 \
    && curl --silent --fail http://127.0.0.1:9200 >/dev/null \
    && (echo >/dev/tcp/127.0.0.1/5672) >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 90 ]]; then
    echo "Supporting services are not ready. Start the Supporting services workflow." >&2
    exit 1
  fi
  sleep 1
done

COMPONENT=admin bash scripts/replit/python.sh manage.py collectstatic --noinput
COMPONENT=admin bash scripts/replit/python.sh manage.py runserver 127.0.0.1:8001 --noreload &
admin_pid=$!
COMPONENT=api bash scripts/replit/python.sh -m gunicorn --workers 1 --bind 127.0.0.1:8000 mcod.api:app &
api_pid=$!
COMPONENT=celery bash scripts/replit/python.sh -m celery --app=mcod.celeryapp:app worker \
  --pool=solo --concurrency=1 --loglevel=INFO &
worker_pid=$!
sed "s|@STATIC_ROOT@|$PWD/statics|" scripts/replit/nginx.conf > /tmp/mcod-nginx.conf
nginx -p "$PWD" -c /tmp/mcod-nginx.conf -g "daemon off;" &
nginx_pid=$!

wait -n "$admin_pid" "$api_pid" "$worker_pid" "$nginx_pid"
