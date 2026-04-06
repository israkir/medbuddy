# Draft PR message

You are drafting a **pull request title and body** for MedBuddy, **separate from** creating the branch or committing. The primary deliverable is a **new Markdown file** in the repo root; the user can open it and paste into GitHub.

## Inputs

1. Prefer **git context**: `git log main..HEAD --oneline` (or `origin/main..HEAD` if `main` is not local) and `git diff main...HEAD --stat`. If the base branch is not `main`, use the branch the user names.
2. Read **`.github/pull_request_template.md`** and mirror its sections (Summary, Scope, Type of change, Related issues, Changes, How to test, etc.).
3. If **`CHANGELOG.md`** `[Unreleased]` bullets exist for this branch, align the PR description with them.

## Output file (required)

1. **Create or overwrite** **`PULL_REQUEST.md`** at the **repository root** (`medbuddy/PULL_REQUEST.md`, sibling of `README.md`).
2. **Structure**:
   - **First line**: `# <Title>` — one line after `# `, imperative mood (e.g. `Add medication reminder API`), ≤ ~72 characters of title text, no trailing period.
   - **Blank line**, then the **full PR body** as Markdown (everything that belongs in the GitHub description): mirror the template sections, checkboxes as `[x]` / `[ ]`, accurate **Testing** commands (`make be-check`, `make fe-check`, `make pre-commit-run` only as applicable—do not invent tools like `mypy` unless the project uses it).
3. Do **not** wrap the file in an outer fenced code block. The file must be normal Markdown GitHub can read when copied.

## Chat reply (brief)

After writing the file, reply in one short paragraph: confirm the path **`PULL_REQUEST.md`**, repeat the **title** (plain text, no `#`), and note that the **body** is in the file below the title heading. Optionally mention adding **`PULL_REQUEST.md`** to **`.gitignore`** if they want to keep drafts local-only.

## Constraints

- Do **not** create the PR on GitHub unless the user asks.
- Do **not** run destructive git commands.
- End with a one-line reminder to run **`/create-branch`** or **`/commit`** if they still need those steps.
