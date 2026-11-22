#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/replit/runtime-paths.sh
if [[ ! -x "$MCOD_PYTHON" || ! -d "$MCOD_PACKAGES_ROOT/django" ]]; then
  echo "MCOD Python runtime is missing. Run the configured build command before starting production." >&2
  exit 1
fi
export PYTHONPATH="$MCOD_PACKAGES_ROOT:$PWD"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-mcod.settings.replit}"
if [[ "$DJANGO_SETTINGS_MODULE" == "mcod.settings.replit" && -n "${REPLIT_DEV_DOMAIN:-}" ]]; then
  # Port 5000 is now mapped to standard HTTPS externally, in development too.
  export API_URL="${API_URL:-https://${REPLIT_DEV_DOMAIN}/api}"
fi
export JUPYTER_PATH="$MCOD_PACKAGES_ROOT/share/jupyter${JUPYTER_PATH:+:$JUPYTER_PATH}"
export LIBARCHIVE
LIBARCHIVE="$(ldd "$(command -v bsdtar)" | awk '/libarchive\.so/ {print $3; exit}')"
magic_library="$(ldd "$(command -v file)" | awk '/libmagic\.so/ {print $3; exit}')"
export LD_LIBRARY_PATH="$(dirname "$LIBARCHIVE"):$(dirname "$magic_library")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$MCOD_PYTHON" "$@"
