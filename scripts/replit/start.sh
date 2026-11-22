#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
printf '%s [mcod-launcher] event=start pid=%s\n' "$(date -u +%FT%TZ)" "$$" >&2
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
  echo "[mcod-launcher] event=collectstatic_begin" >&2
  if COMPONENT=admin bash scripts/replit/python.sh manage.py collectstatic --noinput --verbosity 0; then
    echo "[mcod-launcher] event=collectstatic_complete" >&2
  else
    exit_code=$?
    echo "[mcod-launcher] event=collectstatic_failed exit_code=$exit_code" >&2
    exit "$exit_code"
  fi
fi
echo "[mcod-launcher] event=admin_supervisor_spawn" >&2
bash scripts/replit/run-admin.sh &
admin_pid=$!
echo "[mcod-launcher] event=admin_supervisor_spawned pid=$admin_pid" >&2
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
if wait -n "${processes[@]}"; then exit_code=0; else exit_code=$?; fi
echo "[mcod-launcher] event=monitored_process_exit exit_code=$exit_code" >&2
exit "$exit_code"
