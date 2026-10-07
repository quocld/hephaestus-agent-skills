---
name: ship
description: >
  Get a change from working tree to a clean commit/PR. Use when asked to "commit", "ship",
  "tạo PR", "push", or "open a pull request".
---

# Ship: clean commit and PR

## 1. Pre-flight

- Check `git status` and `git diff`. Make sure only intended changes are included; never commit secrets, `.env`, or large generated files.
- If on the default branch, create a branch first: `<type>/<short-kebab-description>`.
- Run lint, typecheck, and tests that cover the change. Fix failures, including ones you did not cause, or report them clearly.
- Do not hand-edit CHANGELOG.md or auto-generated files.

## 2. Commit

- Use Conventional Commits: `type(scope): summary` where type is one of feat, fix, refactor, perf, test, docs, chore, ci, build.
- Summary in imperative mood, under ~72 characters, no trailing period.
- Body explains *why*, not what the diff already shows. Reference the ticket if there is one.
- Split unrelated changes into separate commits.

## 3. Push and PR (only with explicit consent)

- Push only when the user asked to push or open a PR.
- Open the PR with `gh pr create`. Follow the repo's PR template if it has one.
- PR body: what and why, how it was verified (commands, screenshots for UI), risks and follow-ups.
- Report the PR URL.
