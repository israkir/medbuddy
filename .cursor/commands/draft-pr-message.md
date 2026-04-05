# Draft PR message

You are drafting a **pull request title and body** for MedBuddy, **separate from** creating the branch or committing. Produce text the user can paste into GitHub.

## Inputs

1. Prefer **git context**: `git log main..HEAD --oneline` (or `origin/main..HEAD` if `main` is not local) and `git diff main...HEAD --stat`. If the base branch is not `main`, use the branch the user names.
2. Read **`.github/pull_request_template.md`** and mirror its sections (Description, Type of Change, Related Issues, Changes Made, Testing, Code Quality, Documentation, etc.).
3. If **`CHANGELOG.md`** `[Unreleased]` bullets exist for this branch, align the PR description with them.

## Output format

Return **two fenced blocks** in this order:

1. **Title** — one line, imperative mood (e.g. `Add medication reminder API`), ≤ ~72 characters, no trailing period.

2. **Body** — full Markdown for the PR, including:

   - Clear **Description** (what / why).
   - **Type of Change**: mark the relevant checkbox with `[x]` and leave others `[ ]`.
   - **Related Issues**: `Fixes #…` / `Closes #…` only if the user or branch mentions an issue; otherwise `N/A` or leave placeholders clearly marked.
   - **Changes Made**: bullet list tied to real commits/files.
   - **Testing**: state `make be-check` / `make fe-check` or equivalent commands actually applicable to this repo (`apps/backend`, `apps/frontend`). Do not invent tools (e.g. do not require `mypy` unless the project uses it).
   - Short **checklist** reflecting what was done; note that **`CHANGELOG.md` is required** for commits in this repo.

Do **not** create the PR on GitHub unless the user asks. Do **not** run destructive git commands. End with a one-line reminder to run **`/create-branch`** or **`/commit`** if they still need those steps.
