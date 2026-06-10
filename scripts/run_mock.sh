#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${MATRIX_ART_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PYTHON="$(pwd)/.venv/bin/python"
  else
    PYTHON="$(command -v python3)"
  fi
fi
PORT_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--web-port" || "$arg" == --web-port=* ]]; then
    PORT_ARGS=()
    break
  fi
  PORT_ARGS=(--web-port 8080)
done
if [[ "$#" -eq 0 ]]; then
  PORT_ARGS=(--web-port 8080)
fi
exec "$PYTHON" -m matrix_art --mock-display "${PORT_ARGS[@]}" "$@"
