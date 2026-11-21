#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="$PWD/.pythonlibs/lib/python3.8/site-packages:$PWD"
export DJANGO_SETTINGS_MODULE=mcod.settings.replit
export JUPYTER_PATH="$PWD/.pythonlibs/lib/python3.8/site-packages/share/jupyter${JUPYTER_PATH:+:$JUPYTER_PATH}"
export LIBARCHIVE
LIBARCHIVE="$(ldd "$(command -v bsdtar)" | awk '/libarchive\.so/ {print $3; exit}')"
magic_library="$(ldd "$(command -v file)" | awk '/libmagic\.so/ {print $3; exit}')"
export LD_LIBRARY_PATH="$(dirname "$LIBARCHIVE"):$(dirname "$magic_library")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PWD/.cache/python/cpython-3.8.20-linux-x86_64-gnu/bin/python3.8" "$@"
