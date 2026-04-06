# Commit

You are preparing a **git commit** for the MedBuddy monorepo. Pre-commit runs **full backend tests + lint** and **frontend eslint + tsc**, and **requires `CHANGELOG.md` to be staged** whenever any other file is staged.

## Approval-first (default)

**Do not** run `git add` or `git commit` on the first response. The user invokes this command to **review a proposal** and approve before anything is recorded.

1. **Apply edits** only as needed to prepare the commit content (e.g. update `CHANGELOG.md` under `## [Unreleased]` if that is part of the work). It is fine to write those file changes in the workspace so the user can see the diff.
2. **Do not** stage or commit until the user **explicitly approves** (e.g. “commit it”, “looks good, go ahead”, “run git commit”). After approval, stage and commit per the rules below.

If the user’s message already clearly says to commit now (not just to prepare), treat that as approval and proceed with staging + commit.

## Before committing (and for the proposal)

1. Show `git status -sb` and summarize what will be included.
2. **`CHANGELOG.md`**: Under `## [Unreleased]`, add a concise bullet describing the user-visible or repo-relevant change (match [Keep a Changelog](https://keepachangelog.com/) style: Added / Changed / Fixed / Removed as appropriate). If the user says the change is internal-only, still add a brief line under the right subsection.
3. In the **proposal**, state that **both** code changes **and** `CHANGELOG.md` must be staged together (pre-commit fails if anything is staged without `CHANGELOG.md`). List suggested `git add` paths or `git add -p` guidance if helpful.

## Quality checks (suggest; hooks also run on `git commit`)

From repo root, when dependencies are installed:

- `make pre-commit-run` — runs the same lint/tests as hooks except it skips the changelog-staged check (useful for a quick verify). For a full dry-run including changelog rule, the user can run:

  ```bash
  .venv/bin/pre-commit run
  ```

  (with relevant files staged).

4. Propose a **detailed commit message** using [Conventional Commits](https://www.conventionalcommits.org/): a **subject** plus a **body**. Base the body on the actual diff and `CHANGELOG` entry—do not invent changes.

   **Subject (first line)**

   - Format: `type(scope): imperative summary` — max **~72 characters**, no trailing period.
   - Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, etc.
   - Scope: `backend`, `frontend`, `repo`, or omit if noisy.

   **Body (following lines; required for this command)**

   - Start after a blank line (Git will store subject + body correctly when using two `-m` flags or a here-doc).
   - Write **3–8 short lines** (or more if the change is large), wrap near **72 chars** per line.
   - Include, when relevant:
     - **What** changed (areas: e.g. `apps/backend/...`, `apps/frontend/...`).
     - **Why** (problem, goal, or tradeoff).
     - **How to validate** (e.g. `make be-check`, `make fe-check`, or manual steps)—only what applies.
     - **Risks / follow-ups** if any.
   - You may include **GitHub closing keywords** as normal prose in the body (e.g. `Fixes #123`) when an issue exists.

   **Forbidden — trailers in any form**

   - Do **not** use `git commit --trailer ...` (including `Made-with: Cursor`, `Co-authored-by:`, `Signed-off-by:`, etc.).
   - Do **not** paste or suggest a commit shell line that contains `--trailer`. Cursor or other tools may offer this; **omit it entirely**.
   - Do **not** end the message with Git trailer lines (`Key: value` blocks after the body). A normal prose body is fine; GitHub closing lines like `Fixes #123` in the body are fine.

5. **After explicit user approval**, stage files (`git add …`) and create the commit with **only** `-m` or `-F` — **no other `git commit` flags** except `--no-verify` if the user explicitly bypasses hooks.

   **Single-line subject + paragraph body (two arguments):**

   ```bash
   git commit -m "<subject>" -m "<body>"
   ```

   **Multiline message from stdin (no trailers):**

   ```bash
   git commit -F - <<'EOF'
   type(scope): short subject under 72 chars

   First paragraph explaining what and why.

   - Bullet if listing files or steps helps.
   EOF
   ```

   Do **not** prepend `--trailer` or any flag before `-F` or `-m`. The examples above are the full command.

   If the commit fails on hooks, read the hook output, fix issues, and retry. Remind that **`git commit --no-verify` bypasses hooks** only if the user explicitly wants to skip checks.

## Output

**Proposal (default response):** status summary, proposed `CHANGELOG` line (or confirm it is already in the file), full proposed commit subject + body, and **copy-paste-ready** example commands (`git add …`, then `git commit …`) so the user can run them locally. End with a short line inviting approval to run staging + commit from the agent if they prefer.

**After an approved commit:** show the full message with `git log -1` (or `git log -1 --format=medium`) and remind them they can use **`/draft-pr-message`** next for the PR description if needed.
