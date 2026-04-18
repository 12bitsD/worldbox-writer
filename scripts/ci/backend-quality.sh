#!/bin/sh

set -eu

MODE="${1:-all}"
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
REPORTS_DIR="${REPORTS_DIR:-$ROOT_DIR/artifacts/reports/backend}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

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

mkdir -p "$REPORTS_DIR"
cd "$ROOT_DIR"

if [ "$INSTALL_DEPS" = "1" ]; then
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -e ".[dev]"
fi

run_lint() {
  "$PYTHON_BIN" -m black --check .
  "$PYTHON_BIN" -m isort --check-only .
}

run_typecheck() {
  "$PYTHON_BIN" -m mypy src/
}

run_tests() {
  "$PYTHON_BIN" -m pytest \
    -m "not integration" \
    --cov=worldbox_writer \
    --cov-report=term-missing \
    --cov-report=xml:"$REPORTS_DIR/coverage.xml" \
    --junitxml="$REPORTS_DIR/pytest.xml" \
    -v
}

case "$MODE" in
  --lint-only)
    run_lint
    ;;
  --typecheck-only)
    run_typecheck
    ;;
  --test-only)
    run_tests
    ;;
  all)
    run_lint
    run_typecheck
    run_tests
    ;;
  *)
    echo "Unsupported mode: $MODE" >&2
    exit 1
    ;;
esac
