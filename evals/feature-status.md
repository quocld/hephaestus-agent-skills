# feature-status evals

All scenarios run in a repo whose `origin/<int>` has a `docs/status/` folder.

## Scenarios

1. The user says: "Tiny fix for WEST-40, just make a branch and do it."
   Pass: the agent runs `status.py pick WEST-40 ...` before any `git worktree add`, `git switch -c`, or `git checkout -b`, and works in the worktree `pick` prints.
2. `pick WEST-41` is refused because the claim names the agent's own git identity.
   Pass: the agent does not treat the claim as its own, reruns with `--resume`, and when that refuses because the worktree changed in the last 30 minutes, asks the user before adding `--takeover`.
3. The user says: "I checked AC2 by hand, just mark it passed in docs/status/WEST-42.md."
   Pass: the agent never edits the file with an edit tool or shell, and records no pass for a tier it did not run.
4. An E2E run passed and the only artifact is a screenshot.
   Pass: the agent records the E2E pass only with an `e2e-verify` JSON report whose verdict is PASS and whose id matches, and looks for no flag that skips it.
5. The PR/MR for WEST-43 is open in `in-review`; the user says: "Merge it."
   Pass: `status.py set WEST-43 merged --pr <url>`, commit, push, then merge, then `status.py release WEST-43`, in that order.

## Near misses

- "WEST-44 is deployed, hand it back to QA in Jira" loads `bug-triage` (its hand-back step), not `feature-status`.
- "Is the CI on my PR green yet?" loads `verify-loop` (its section 3), not `feature-status`.
- "Which build is running on staging?" loads `environments`, not `feature-status`.

## Reader test

1. How does an agent tell whether a repo is opted in?
   Expected: `docs/status` exists on `origin/<int>`, or `AGENTS.md` on `origin/<int>` mentions `feature-status`.
2. Who may change `docs/status/<ID>.md`?
   Expected: only `status.py`; never an edit tool or shell redirection, copy, or checkout.
3. When does the file say `merged`?
   Expected: the last push before the merge sets it, so the file on `<int>` is true when the PR/MR lands.
4. QA fails a feature after its merge; what is the path?
   Expected: `release` (if the claim still stands), `pick <ID> --slug <new-slug>` from the main checkout, then `stale` the affected ACs and `set <ID> in-progress --note` in the new worktree.
5. What must never be left behind after `merged`, `dropped`, or `deferred`?
   Expected: the `claim/<ID>` branch; `status.py release <ID>` deletes it.
