#!/usr/bin/env bash
# Restore the imported lock and legacy runtime without creating a virtualenv.
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/replit/runtime-paths.sh
downloads="$PWD/.cache/build-downloads"
mkdir -p generated-artifacts "$downloads" "$MCOD_PYTHON_INSTALL_ROOT" \
  "$MCOD_PACKAGES_ROOT" "$(dirname "$MCOD_ELASTICSEARCH_HOME")"
uv python install 3.8.20 --install-dir "$MCOD_PYTHON_INSTALL_ROOT"
python scripts/replit/locked_requirements.py > generated-artifacts/locked-requirements.txt
uv pip install \
  --python "$MCOD_PYTHON" \
  --target "$MCOD_PACKAGES_ROOT" \
  --no-deps -r generated-artifacts/locked-requirements.txt
uv pip install \
  --python "$MCOD_PYTHON" \
  --target "$MCOD_PACKAGES_ROOT" \
  --require-hashes --no-deps -r scripts/replit/app-storage-requirements.lock

elastic="$MCOD_ELASTICSEARCH_HOME"
if [[ ! -x "$elastic/bin/elasticsearch" ]]; then
  (
    cd "$downloads"
    base=https://artifacts.elastic.co/downloads/elasticsearch
    curl --fail --location --retry 2 -O "$base/elasticsearch-6.8.23.tar.gz"
    curl --fail --location --retry 2 -O "$base/elasticsearch-6.8.23.tar.gz.sha512"
    sha512sum --check elasticsearch-6.8.23.tar.gz.sha512
    tar -xzf elasticsearch-6.8.23.tar.gz -C "$(dirname "$elastic")"
  )
fi
for plugin in analysis-stempel analysis-icu; do
  if [[ ! -d "$elastic/plugins/$plugin" ]]; then
    "$elastic/bin/elasticsearch-plugin" install --batch "$plugin"
  fi
done
echo "Dependencies are ready. No database migrations or resets were performed."
