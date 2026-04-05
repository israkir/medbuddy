## Summary

<!-- What this PR does and why (1–3 sentences). -->

## Scope

<!-- Mark what this PR touches -->

- [ ] Backend (`apps/backend`)
- [ ] Frontend (`apps/frontend`)
- [ ] Repo / tooling (root `Makefile`, `.github`, pre-commit, etc.)

## Type of change

<!-- Mark the relevant option with an `x` -->

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation only
- [ ] Refactor / internal cleanup
- [ ] Build / CI / config

## Related issues

<!-- e.g. Fixes #123 — remove lines you don’t use -->

Fixes #
Closes #
Related to #

## Changes

<!-- Bullet list: behavior, APIs, UX, env vars, migrations — be specific -->

-
-

## How to test

<!-- Commands you ran (adjust if your change is docs-only). -->

- [ ] `make be-check` (backend tests + ruff + black) — **N/A** if no backend changes
- [ ] `make fe-check` (ESLint + TypeScript) — **N/A** if no frontend changes; requires `make fe-install` first
- [ ] `make pre-commit-run` — optional full-repo hook dry-run (skips changelog rule; uses `SKIP=require-changelog-staged`)

```bash
# From repo root, after: make be-install  and  make fe-install  (when needed)
make be-check
make fe-check
```

- [ ] **Frontend UI:** exercised in Expo (e.g. `make fe-dev` or `make fe-dev-api`) — **N/A** if no UI change

## Screenshots (optional)

<!-- For visible UI changes in the app, add before/after or simulator captures. Delete if N/A. -->

## Commits & changelog

<!-- Aligns with pre-commit and Cursor `/commit` -->

- [ ] Commits use **Conventional Commits** subjects (`feat`, `fix`, `chore`, …) with a **detailed body** when the change is non-trivial
- [ ] **`CHANGELOG.md`** updated under `## [Unreleased]` (required for commits that stage other files; pre-commit enforces staging `CHANGELOG.md`)

## Reviewer notes

<!-- Risks, follow-ups, areas you want feedback on — or delete this section -->

---

## Checklist

<!-- Complete all relevant items -->

- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published

## Additional Notes

<!-- Add any additional context, notes, or considerations for reviewers -->

## Reviewer Notes

<!-- Any specific areas you'd like reviewers to focus on -->
