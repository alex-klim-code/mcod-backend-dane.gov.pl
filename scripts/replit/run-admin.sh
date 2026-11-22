#!/usr/bin/env bash
# Keep the real server's output, PID and exit status visible to the supervisor.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."

log() {
  printf '%s [mcod-admin-launcher] %s\n' "$(date -u +%FT%TZ)" "$*" >&2
}

child_pid=""
cleanup() {
  if [[ -n "$child_pid" ]]; then
    kill -TERM "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
}
on_signal() {
  local signal="$1" status="$2" child_status
  log "event=signal_received signal=$signal supervisor_pid=$BASHPID child_pid=${child_pid:-not_started}"
  if [[ -n "$child_pid" ]]; then
    kill "-$signal" "$child_pid" 2>/dev/null || true
    if wait "$child_pid"; then child_status=0; else child_status=$?; fi
    log "event=process_exit pid=$child_pid exit_code=$child_status shutdown_signal=$signal"
    child_pid=""
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'on_signal TERM 143' TERM
trap 'on_signal INT 130' INT
trap 'status=$?; log "event=launcher_error line=$LINENO exit_code=$status"; exit "$status"' ERR

log "event=launcher_enter supervisor_pid=$BASHPID"
source scripts/replit/runtime-paths.sh
for path in "$MCOD_PYTHON" "$MCOD_PACKAGES_ROOT/daphne" \
  "$MCOD_PACKAGES_ROOT/daphne/cli.py" "$PWD/scripts/replit/admin_server.py"; do
  if [[ -e "$path" ]]; then
    log "event=runtime_file path=$path exists=true"
  else
    log "event=runtime_file path=$path exists=false"
  fi
done
log "event=before_spawn bind=127.0.0.1 port=8001 settings=${DJANGO_SETTINGS_MODULE:-mcod.settings.replit}"

# No pipe/tee or log file: both streams go directly to deployment stderr.
# python.sh execs Python, so $! remains the actual Daphne process PID.
COMPONENT=admin MCOD_STARTUP_DIAGNOSTICS=1 PYTHONUNBUFFERED=1 \
  bash scripts/replit/python.sh -u scripts/replit/admin_server.py \
  --bind 127.0.0.1 --port 8001 mcod.asgi:application >&2 &
child_pid=$!
log "event=process_spawned pid=$child_pid supervisor_pid=$BASHPID"
if wait "$child_pid"; then exit_code=0; else exit_code=$?; fi
log "event=process_exit pid=$child_pid exit_code=$exit_code"
if (( exit_code > 128 && exit_code <= 192 )); then
  log "event=process_signal pid=$child_pid signal_number=$((exit_code - 128))"
fi
child_pid=""
exit "$exit_code"
