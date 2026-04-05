#!/usr/bin/env bash
# Full backend lint + tests (matches make be-lint + make be-test paths).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/apps/backend"
VENV_BIN="${ROOT}/.venv/bin"
RUFF="${VENV_BIN}/ruff"
BLACK="${VENV_BIN}/black"
PYTEST="${VENV_BIN}/pytest"

if [[ ! -x "$RUFF" ]]; then
  echo "ERROR: ${RUFF} missing. Run: make be-install" >&2
  exit 1
fi

cd "$BACKEND"
"$RUFF" check src tests
"$BLACK" --check src tests
"$PYTEST" -q
