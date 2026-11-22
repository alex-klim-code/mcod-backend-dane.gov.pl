#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

export MCOD_RUNTIME_ROOT="$PWD/runtime"
bash scripts/replit/setup.sh
DJANGO_SETTINGS_MODULE=mcod.settings.production_replit \
  COMPONENT=admin \
  bash scripts/replit/python.sh manage.py collectstatic --noinput
test -x "$MCOD_RUNTIME_ROOT/python/cpython-3.8.20-linux-x86_64-gnu/bin/python3.8"
test -f "$MCOD_RUNTIME_ROOT/site-packages/django/__init__.py"
test -x "$MCOD_RUNTIME_ROOT/elasticsearch-6.8.23/bin/elasticsearch"
for plugin in analysis-stempel analysis-icu; do
  test -f "$MCOD_RUNTIME_ROOT/elasticsearch-6.8.23/plugins/$plugin/plugin-descriptor.properties"
done
printf 'python=3.8.20\nelasticsearch=6.8.23\n' > "$MCOD_RUNTIME_ROOT/build-ready"
echo "Production dependencies and static assets are packaged for publishing."
