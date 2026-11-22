#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

export DJANGO_SETTINGS_MODULE=mcod.settings.production_replit
export MCOD_APP_STORAGE_ENABLED=true
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
export RABBITMQ_HOST="${RABBITMQ_HOST:-127.0.0.1:5672}"
export ELASTICSEARCH_HOSTS="${ELASTICSEARCH_HOSTS:-127.0.0.1:9200}"

if [[ -z "${AED_INTEGRATION_SECRET:-}" ]]; then
  echo "Set AED_INTEGRATION_SECRET in Replit Secrets before starting the production service." >&2
  exit 1
fi

cleanup() {
  kill "${nginx_pid:-}" "${api_pid:-}" "${admin_pid:-}" "${worker_pid:-}" "${services_pid:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

bash scripts/replit/services.sh &
services_pid=$!
for attempt in $(seq 1 120); do
  if redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 \
    && curl --silent --fail http://127.0.0.1:9200 >/dev/null \
    && (echo >/dev/tcp/127.0.0.1/5672) >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 120 ]]; then
    echo "Redis, RabbitMQ, or Elasticsearch did not become ready." >&2
    exit 1
  fi
  sleep 1
done

COMPONENT=admin bash scripts/replit/python.sh manage.py aed_storage_check
COMPONENT=api bash scripts/replit/python.sh manage.py aed_prepare_search
# Replit applies managed PostgreSQL schema changes through the Publish flow.
# Do not run Django migrations from this deployment process.

COMPONENT=admin bash scripts/replit/python.sh -m gunicorn --workers 1 --timeout 120 \
  --bind 127.0.0.1:8001 mcod.wsgi:application &
admin_pid=$!
COMPONENT=api bash scripts/replit/python.sh -m gunicorn --workers 1 --timeout 120 \
  --bind 127.0.0.1:8000 mcod.api:app &
api_pid=$!
COMPONENT=celery bash scripts/replit/python.sh -m celery --app=mcod.celeryapp:app worker \
  --pool=solo --concurrency=1 --loglevel=INFO &
worker_pid=$!

sed "s|@STATIC_ROOT@|$PWD/statics|" scripts/replit/nginx.conf > /tmp/mcod-nginx-production.conf
nginx -e stderr -p "$PWD" -c /tmp/mcod-nginx-production.conf -g "daemon off;" &
nginx_pid=$!

wait -n "$admin_pid" "$api_pid" "$worker_pid" "$nginx_pid" "$services_pid"
