#!/usr/bin/env bash
# Source after changing to the project root. Production dependencies are release
# files, not disposable development caches.
if [[ -n "${MCOD_RUNTIME_ROOT:-}" ]]; then
  MCOD_PYTHON_INSTALL_ROOT="$MCOD_RUNTIME_ROOT/python"
  MCOD_PACKAGES_ROOT="$MCOD_RUNTIME_ROOT/site-packages"
  MCOD_ELASTICSEARCH_HOME="$MCOD_RUNTIME_ROOT/elasticsearch-6.8.23"
else
  MCOD_PYTHON_INSTALL_ROOT="$PWD/.cache/python"
  MCOD_PACKAGES_ROOT="$PWD/.pythonlibs/lib/python3.8/site-packages"
  MCOD_ELASTICSEARCH_HOME="$PWD/.cache/services/elasticsearch-6.8.23"
fi
MCOD_PYTHON="$MCOD_PYTHON_INSTALL_ROOT/cpython-3.8.20-linux-x86_64-gnu/bin/python3.8"
export MCOD_PYTHON_INSTALL_ROOT MCOD_PACKAGES_ROOT MCOD_ELASTICSEARCH_HOME MCOD_PYTHON
