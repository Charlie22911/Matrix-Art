#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${MATRIX_ART_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PYTHON="$(pwd)/.venv/bin/python"
  else
    PYTHON="$(command -v python3)"
  fi
fi
exec "$PYTHON" -m matrix_art "$@"
