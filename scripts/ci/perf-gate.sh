#!/bin/sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
PERF_GATE_OUTPUT="${PERF_GATE_OUTPUT:-$ROOT_DIR/artifacts/perf/report.json}"

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

PERF_GATE_OUTPUT="$PERF_GATE_OUTPUT" "$PYTHON_BIN" -m worldbox_writer.perf.load_gate
