#!/usr/bin/env bash
# Full frontend lint + typecheck (npm run check).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/apps/frontend"

if [[ ! -d node_modules ]]; then
  echo "ERROR: apps/frontend/node_modules missing. Run: make fe-install" >&2
  exit 1
fi

npm run check
