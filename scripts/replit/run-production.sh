#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

# Use the same application launcher as development. Only the packaged runtime,
# secure environment profile and ownership of supporting services differ.
export MCOD_RUNTIME_ROOT="$PWD/runtime"
export DJANGO_SETTINGS_MODULE=mcod.settings.production_replit
export MCOD_APP_STORAGE_ENABLED=true
export MCOD_START_SERVICES=true
exec bash scripts/replit/start.sh
