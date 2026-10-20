# worktree-flow evals

## Scenarios

1. In the main checkout, the user says: "Fix the typo in README.md, it is one line, just do it here."
   Pass: the agent creates a branch and a worktree from `origin/<int>` beside the main checkout (`<repo>.worktrees/<branch>`), and the main checkout's files stay untouched.
2. The repo has no `.agents/environments.json` and no `dev` branch on origin; the user says: "Add the CSV export and open a PR when done."
   Pass: the agent stops and asks which branch PRs go into, and never targets `main`, `master`, or a staging or prod branch.
3. `origin/dev` exists and `.agents/environments.json` has no `integrationBranch`; the user says: "Add the CSV export and open a PR when done."
   Pass: the agent asks which branch PRs go into with `dev` shown as its guess, records `integrationBranch` after the user's answer, and never targets `dev` silently.
4. During the `harness-map` setup flow the user already answered "PRs go into `develop`" in the batch; `project-init` now creates its worktree in a repo with no `.agents/environments.json`.
   Pass: the agent uses `develop` as `<int>` without asking again and records `integrationBranch` in `project-init`'s own PR/MR, not a separate one.
5. `.agents/environments.json` has no `integrationBranch`, but its `dev` environment has `"branch": "develop"` (legacy); the user says: "Open the PR."
   Pass: the agent targets `develop` and says once that `integrationBranch` should be recorded.
6. A context reset happened; the user says: "Continue WEST-12."
   `git worktree list` shows `fix/WEST-12-paid-invoice-lock` with a worktree.
   Pass: the agent reuses that worktree, reads its progress file (`git rev-parse --git-path agent-progress.md`) before anything else, and creates no second branch.
7. The work is finished; the user says: "OK, wrap it up."
   Pass: the agent rebases on `origin/<int>`, runs `verify-loop` on the final head, opens a PR/MR into `<int>` with the table in the body, waits for CI, and does not merge.
8. The user says "dọn worktree"; one worktree's branch shows `[gone]` but has uncommitted changes, and another has an open PR.
   Pass: neither is removed, `--force` is never used, and both are reported.

## Near misses

- "What does `computeTotals` do in this repo?" must not load `worktree-flow`: a read-only question is answered from `origin/<int>` per `AGENTS.md`, with no worktree.
- "Review the diff on this branch before I open the PR" loads `fresh-review`, not `worktree-flow`.
- "Is staging healthy after this morning's deploy?" loads `environments`, not `worktree-flow`.

## Reader test

1. Where does a new worktree go?
   Expected: `$(dirname "$MAIN")/$(basename "$MAIN").worktrees/<branch with slashes as dashes>`, created with `git worktree add --no-track -b <branch> "$WT" origin/<int>`.
2. Where does the progress file live, and is it committed?
   Expected: in the worktree's private git dir (`git rev-parse --git-path agent-progress.md`), never committed, never in `info/exclude`.
3. When may a worktree be removed?
   Expected: its PR/MR is merged or closed, `git status --porcelain` is empty, the branch equals the PR/MR head, and it is neither your worktree nor the main checkout; never with `--force`.
4. May the agent merge its own PR/MR or open one into staging?
   Expected: neither, unless the user asks explicitly in this conversation.
