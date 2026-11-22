#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
export RABBITMQ_HOST="${RABBITMQ_HOST:-127.0.0.1:5672}"
export ELASTICSEARCH_HOSTS="${ELASTICSEARCH_HOSTS:-127.0.0.1:9200}"

cleanup() {
  kill "${search_pid:-}" "${nginx_pid:-}" "${api_pid:-}" "${admin_pid:-}" \
    "${worker_pid:-}" "${services_pid:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

processes=()
if [[ "${MCOD_START_SERVICES:-false}" == "true" ]]; then
  bash scripts/replit/services.sh &
  services_pid=$!
  processes+=("$services_pid")
fi

# Publishing already packages static assets. Avoid a redundant full Django
# initialization before starting the real servers in either environment.
# A fresh development checkout still gets the required assets automatically.
if [[ ! -f "$PWD/statics/admin/css/base.css" ]]; then
  COMPONENT=admin bash scripts/replit/python.sh manage.py collectstatic --noinput --verbosity 0
fi
COMPONENT=admin bash scripts/replit/python.sh scripts/replit/admin_server.py \
  --bind 127.0.0.1 --port 8001 mcod.asgi:application &
admin_pid=$!
COMPONENT=api bash scripts/replit/python.sh -m gunicorn --workers 1 --timeout 120 \
  --bind 127.0.0.1:8000 mcod.api:app &
api_pid=$!
COMPONENT=celery bash scripts/replit/python.sh -m celery --app=mcod.celeryapp:app worker \
  --pool=solo --concurrency=1 --loglevel=INFO &
worker_pid=$!

# Perform actual catalog initialization asynchronously, not readiness probes.
bash scripts/replit/prepare-search.sh &
search_pid=$!

sed "s|@STATIC_ROOT@|$PWD/statics|" scripts/replit/nginx.conf > /tmp/mcod-nginx.conf
nginx -e stderr -p "$PWD" -c /tmp/mcod-nginx.conf -g "daemon off;" &
nginx_pid=$!

processes+=("$admin_pid" "$api_pid" "$worker_pid" "$nginx_pid")
wait -n "${processes[@]}"
