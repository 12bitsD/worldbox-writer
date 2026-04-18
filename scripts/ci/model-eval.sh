#!/bin/sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
PROVIDERS="${MODEL_EVAL_PROVIDERS:-all}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found. Set PYTHON_BIN to a Python 3.11+ executable." >&2
  exit 1
fi

cd "$ROOT_DIR"

if [ "$INSTALL_DEPS" = "1" ]; then
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -e ".[dev]"
fi

echo "Model eval placeholder"
echo "Requested providers: $PROVIDERS"
echo "Expected env: LLM_PROVIDER / LLM_API_KEY / LLM_BASE_URL / LLM_MODEL"
echo "Next step: replace this script with a real Sprint 9 evaluation matrix."
