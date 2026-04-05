# Create branch

You are helping with **git branching** in the MedBuddy monorepo (`apps/backend`, `apps/frontend`).

## Goals

1. Choose a **short, kebab-case** branch name that reflects the work (not generic names like `fix` or `update`).
2. Use a **prefix** when it fits: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`, or `ci/`.
3. If the user gave an issue number, include it (e.g. `feat/42-medication-reminders`).

## What to do

1. Confirm current branch and working tree status (`git status -sb`). If there are uncommitted changes, say so and ask whether to stash, commit first, or proceed anyway.
2. **Base branch**: default to `main` unless the user specifies another branch. If `main` does not exist locally, infer the default remote branch or ask once.
3. Propose **one** branch name in the form `prefix/summary` (lowercase, hyphens, no spaces).
4. When the user approves (or if the name is obvious from context), run:

   ```bash
   git fetch origin 2>/dev/null || true
   git checkout <base-branch>
   git pull --ff-only  # if tracking remote exists; otherwise skip with a note
   git checkout -b <new-branch-name>
   ```

5. Print the final branch name and remind them to open a PR against `<base-branch>` when ready.

## Constraints

- Do not force-push or rewrite published history unless the user explicitly asks.
- Do not delete branches.
