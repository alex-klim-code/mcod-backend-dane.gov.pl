#!/usr/bin/env bash
# Restore the imported lock and legacy runtime without creating a virtualenv.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p generated-artifacts .cache/services
uv python install 3.8.20 --install-dir .cache/python
python scripts/replit/locked_requirements.py > generated-artifacts/locked-requirements.txt
uv pip install \
  --python .cache/python/cpython-3.8.20-linux-x86_64-gnu/bin/python3.8 \
  --target .pythonlibs/lib/python3.8/site-packages \
  --no-deps -r generated-artifacts/locked-requirements.txt

elastic=.cache/services/elasticsearch-6.8.23
if [[ ! -x "$elastic/bin/elasticsearch" ]]; then
  (
    cd .cache/services
    base=https://artifacts.elastic.co/downloads/elasticsearch
    curl --fail --location --retry 2 -O "$base/elasticsearch-6.8.23.tar.gz"
    curl --fail --location --retry 2 -O "$base/elasticsearch-6.8.23.tar.gz.sha512"
    sha512sum --check elasticsearch-6.8.23.tar.gz.sha512
    tar -xzf elasticsearch-6.8.23.tar.gz
  )
fi
for plugin in analysis-stempel analysis-icu; do
  if [[ ! -d "$elastic/plugins/$plugin" ]]; then
    "$elastic/bin/elasticsearch-plugin" install --batch "$plugin"
  fi
done
echo "Dependencies are ready. Start Project, then run database migrations if this is a new database."
