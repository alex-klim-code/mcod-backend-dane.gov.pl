#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

export MCOD_RUNTIME_ROOT="$PWD/runtime"
bash scripts/replit/setup.sh
DJANGO_SETTINGS_MODULE=mcod.settings.production_replit \
  COMPONENT=admin \
  bash scripts/replit/python.sh manage.py collectstatic --noinput
echo "Production dependencies and static assets are packaged for publishing."
