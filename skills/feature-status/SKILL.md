---
name: feature-status
description: >
  Use before starting work on a ticket or feature in a repo that has a docs/status/ folder or whose AGENTS.md names feature-status, when an AC is verified, the spec changes, work gets blocked, before opening a PR/MR, after a merge, and when asked "nhận task", "pick ticket", "cập nhật status", "status feature", "tiến độ feature", "board tiến độ", "ai đang làm ticket này", "feature status board".
user-invocable: true
---

# feature-status

Many agents work one repo in parallel worktrees, so "who is on this ticket, and what is really verified" needs one answer every checkout can see.
Each feature gets its own status file `docs/status/<ID>.md`, claimed on the remote before any worktree exists and edited only through one script.

Below, `status.py` means `python3 <this skill>/scripts/status.py`, wherever the skill is installed (the agent-skills plugin or a checkout of the repo).
The `feature-status-guard` hook's deny messages always name the exact path on this machine.
Every subcommand has `--help`, and every writing one takes `--dry-run`.
The file format, tokens, and the legal state transitions are owned by `references/format.md`.
`<ID>` is the ticket id (`WEST-123`), or a kebab slug when there is no ticket.
`<int>` is the integration branch from `worktree-flow` section 0.

## 0. Is the repo opted in?

```bash
git fetch origin --prune
git ls-tree -d --name-only origin/<int> docs/status
git show origin/<int>:AGENTS.md 2>/dev/null | grep -c feature-status
```

- The first prints `docs/status`, or the second prints a number above 0: the repo is opted in, every step below applies, and the `feature-status-guard` hook enforces them.
- Neither: this skill does not apply; follow `worktree-flow` alone, and offer the opt-in from `project-init`.

## 1. Pick before any worktree exists

Run from the checkout you stand in, usually the main checkout; `pick` never touches its working tree or index:

```bash
status.py pick <ID> --title "<title>" --type <feat|fix|refactor|chore|docs|test> --slug <slug>
```

- It claims the ticket on the remote (`claim/<ID>` and the feature branch, pushed atomically), then creates the worktree per `worktree-flow` and prints its path as the last line.
  `cd` there.
- `pick` performs `worktree-flow` section 1 step 1's checks itself (existing claims, branches for the ID, an active status file on `<int>`), so it replaces steps 1-3 there; the one part of step 1 left to you is reading the worktree's progress file (`worktree-flow` section 3) when you resume.
- Refused because someone else holds it: the message names who; stop and ask, never pick a second branch for the same ID.
- Refused because the claim names your git identity: parallel agents share one identity, so that alone does not make the claim yours.
  Rerun with `--resume`; it prints the existing worktree path, recreates the worktree when it does not exist locally, and refuses when that worktree changed in the last 30 minutes (its private git `index`, `HEAD` or `agent-progress.md`, or its status file), naming who holds it and where.
  On that refusal, ask the user whether the other session is still running; add `--takeover` only after the user confirms it is dead.
- Refused because the claim is stale (its pick is `merged`, `dropped` or `deferred`): run the `status.py release <ID>` the message names, then pick again; never `--resume` a stale claim.
- A harness already started you in a clean detached worktree: add `--no-worktree`, then `git switch -c <branch> --track origin/<branch>` in place.
- The claim lives on the remote, not on a worktree branch, so every other checkout sees it immediately.

## 2. Update as you go, inside the feature worktree

| When | Command |
| --- | --- |
| Work starts (exploration done, at the latest with the first commit) | `status.py set <ID> in-progress` |
| ACs are known | `status.py ac <ID> AC<n> --text "<AC text>" --tier <ut\|it\|e2e> --result todo`, once per tier the AC needs, and `--result na` for tiers it does not |
| A tier of an AC passes or fails | `status.py ac <ID> AC<n> --tier <tier> --result <pass\|fail>` |
| An E2E pass | `status.py ac <ID> AC<n> --tier e2e --result pass --evidence <e2e-verify JSON report>`; the report must be a non-empty JSON object with `"verdict": "PASS"` and this `"id"`, any other file type (a screenshot, a log) is refused, and there is no flag that skips it |
| The spec changes under verified ACs (before the merge) | `status.py stale <ID> --acs AC1,AC3 --note "<what changed, link>"`, then `status.py ac <ID> AC3 --text "<new AC text>"` for each AC whose wording changed (this resets all its tiers to `todo`, so record each tier again, `na` included), add new ACs as in the "ACs are known" row, and re-verify |
| Something is cut from scope | `status.py defer <ID> --what "<what>" --why "<why>" --owner "<who>"` |
| Blocked | `status.py set <ID> blocked --note "<one line, link>"`, and open a draft PR/MR per `worktree-flow` |
| A fact worth keeping | `status.py note <ID> "<one line, link>"`; reasoning longer than a line goes in the PR/MR body or a `flow-trace` file |

- Commit each status change with the code it describes, so the file on the branch is always true for that commit.
- `set`, `ac`, `stale`, `defer`, and `note` refuse to run in the main checkout.

## 3. PR/MR, merge, release

The merged-state rule: the PR/MR opens in `in-review`, and its last push before merging sets `merged`.
This keeps the file on `<int>` true the moment the PR/MR lands, with no follow-up commit to `<int>`, and a PR/MR closed unmerged never reaches `<int>`.

1. Before opening a non-draft PR/MR, in this order: `status.py set <ID> in-review`, `status.py check <ID>`, commit, push, `status.py check <ID> --ref HEAD`, then open the PR/MR.
   The last check reads the committed file, so it fails when the state change or an E2E evidence file is not committed; the `feature-status-guard` hook runs the same check on the branch, and also denies the PR/MR while the branch has commits its upstream does not (fix: `git push`).
   A draft PR/MR only needs the file to exist.
2. When the user approves the merge (or asks you to merge): `status.py set <ID> merged --pr <url>`, commit, push, and only then merge.
   `check` refuses `merged` while any AC tier is todo, fail, or stale, or an E2E pass lacks its evidence file; fix those, do not argue with it.
3. After the merge: `status.py release <ID>` deletes the remote claim.
   It judges only that pick's own file: `merged` must be on `origin/<int>` (so it cannot run while the PR/MR is open), and an earlier pick's merged file never releases a re-pick.
4. Dropped work: `status.py set <ID> dropped --note "<why>"`, commit, push, then `status.py release <ID>`, and merge or close per the user.
   Deferring the whole feature: `status.py set <ID> deferred --note "<why, link>"`, commit, push, then `status.py release <ID>`, so anyone can pick it again later.
   After the release the old worktree can no longer reopen it (`set` needs the claim); resuming means a new `pick <ID> --slug <new-slug>`, which keeps the deferred file's ACs and ignores the given-up branch, and merging that branch in when its work is still needed.
5. Failed QA or a spec change after merge has one path: `status.py release <ID>` (when the claim still stands), then `status.py pick <ID> --slug <new-slug>` from the main checkout for a new branch (it keeps the ACs and resets the state to `picked`), then in the new worktree `stale` the affected ACs and `set <ID> in-progress --note "<why, link>"`.
   `stale` and `set` refuse a `merged` file, so the old worktree cannot reopen it.
   `--slug` is needed only when the merged branch still exists, and `pick` says so.

Recovery, when the user merged the PR/MR while its file still said `in-review` (`release` and `pick` say so, and `board --live` shows `in-review (PR merged)`): in the existing feature worktree (recreate it with `pick <ID> --resume` while the claim stands), run `git fetch origin && git merge origin/<int>`, `status.py set <ID> merged --pr <url>`, commit, push, open a PR/MR, and `release` once it merges.
Merging `origin/<int>` first makes the push a fast-forward of the kept branch, also after a squash merge.

## 4. Board

```bash
status.py board --live          # --out <file> writes it
```

It merges `docs/status/*.md` on `<int>` with every `claim/<ID>` branch, so unmerged work shows up; `--live` adds PR/MR and deploy state when `gh`/`glab` and the `environments` version status are available.
Print it or write it to a scratch file; never commit it, since parallel PRs/MRs would conflict on it.

## Never

- Never edit `docs/status/*.md` by hand, with an edit tool or with shell (`>`, `sed -i`, `tee`, `cp`, `ln`, `git checkout <ref> -- <file>`, `git restore --source`); the `feature-status-guard` hook denies the common forms on a best-effort basis, and the script is the only way edits stay surgical and validated.
- Never create a feature worktree or branch before `pick`; the hook denies `git worktree add`, `git switch -c`, and `git checkout -b` for an ID with no `claim/<ID>` in the last fetch, and creating a branch for an ID whose claim names a different branch.
  "It is a tiny change" is not an exception: a tiny change still collides with another agent on the same ticket.
- Never record a pass you did not run, and never copy Jira or deploy state into the file; the board derives deploy state.
- Never leave a `claim/<ID>` behind after `merged`, `dropped`, or `deferred`; `pick` refuses everyone while it exists.

## Report

The status file's state, AC table, and deferred items; the PR/MR URL; and whether the claim was released.
