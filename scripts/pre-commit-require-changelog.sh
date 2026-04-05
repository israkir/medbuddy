#!/usr/bin/env bash
# Require CHANGELOG.md to be part of the commit whenever anything is staged.
# Skips when the Git index has no staged files (e.g. `pre-commit run --all-files` with a clean index).
set -euo pipefail

if [[ "${SKIP:-}" == *"require-changelog-staged"* ]]; then
  exit 0
fi

have_staged=0
have_changelog=0
while IFS= read -r f || [[ -n "${f:-}" ]]; do
  [[ -z "$f" ]] && continue
  have_staged=1
  if [[ "$f" == "CHANGELOG.md" ]]; then
    have_changelog=1
  fi
done < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)

if [[ "$have_staged" -eq 0 ]]; then
  exit 0
fi
if [[ "$have_changelog" -eq 1 ]]; then
  exit 0
fi

echo "ERROR: CHANGELOG.md must be staged for this commit." >&2
echo "Add or edit an entry under [Unreleased] (or the current version) in CHANGELOG.md, then git add CHANGELOG.md." >&2
echo "To bypass (not recommended): git commit --no-verify  or  SKIP=require-changelog-staged git commit ..." >&2
exit 1
