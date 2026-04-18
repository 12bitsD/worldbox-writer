#!/bin/sh

set -eu

MODE="${1:-all}"
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
FRONTEND_DIR="$ROOT_DIR/frontend"
REPORTS_DIR="${REPORTS_DIR:-$ROOT_DIR/artifacts/reports/frontend}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
PNPM_VERSION="${PNPM_VERSION:-9.15.9}"

mkdir -p "$REPORTS_DIR"

if command -v corepack >/dev/null 2>&1; then
  corepack enable
  corepack prepare "pnpm@${PNPM_VERSION}" --activate
elif ! command -v pnpm >/dev/null 2>&1; then
  npm install -g "pnpm@${PNPM_VERSION}"
fi

cd "$FRONTEND_DIR"

if [ "$INSTALL_DEPS" = "1" ]; then
  CI="${CI:-true}" pnpm install --frozen-lockfile
fi

run_lint() {
  pnpm run lint
}

run_tests() {
  pnpm exec vitest run --reporter=default --reporter=junit --outputFile="$REPORTS_DIR/vitest.xml"
  pnpm run build
}

case "$MODE" in
  --lint-only)
    run_lint
    ;;
  --test-only)
    run_tests
    ;;
  all)
    run_lint
    run_tests
    ;;
  *)
    echo "Unsupported mode: $MODE" >&2
    exit 1
    ;;
esac
