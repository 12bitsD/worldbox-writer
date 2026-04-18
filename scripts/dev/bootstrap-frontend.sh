#!/bin/sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
FRONTEND_DIR="$ROOT_DIR/frontend"
PNPM_VERSION="${PNPM_VERSION:-9.15.9}"

if command -v corepack >/dev/null 2>&1; then
  corepack enable
  corepack prepare "pnpm@${PNPM_VERSION}" --activate
elif ! command -v pnpm >/dev/null 2>&1; then
  npm install -g "pnpm@${PNPM_VERSION}"
fi

cd "$FRONTEND_DIR"
pnpm install --frozen-lockfile
