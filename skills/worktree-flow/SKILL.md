---
name: worktree-flow
description: >
  Use at the start of any task that will change files in a git repo, before committing or opening a PR/MR, when resuming, finishing, or abandoning a task, and when asked "tạo worktree", "mở PR", "mở MR", "xong thì commit", "dọn worktree", "lên staging".
user-invocable: true
---

# worktree-flow

Many agents share the repo, so the main checkout belongs to nobody: each task gets its own worktree and branch, pushes as it goes, and ends as a PR/MR.

## 0. Fetch and find the integration branch

Run `git fetch origin --prune`.
`<int>` is `integrationBranch` in `.agents/environments.json`, the branch the user chose for PRs/MRs.
Not there but the `dev` environment has a `branch`: use that (legacy) and say once that `integrationBranch` should be recorded.
Neither: stop and ask which branch PRs/MRs go into, showing your guess (`dev` when `git ls-remote --exit-code --heads origin refs/heads/dev` succeeds, else the remote default branch); never assume it, not `dev`, `main`, `master`, or a staging or prod branch.
Record the answer as `integrationBranch` (a registry may hold only `project`, `integrationBranch` and an empty `environments`) in its own PR/MR into that branch, with the user's yes per `environments` section 1.
When the `harness-map` setup batch (its section 3), `project-init` section 2 or `environments` section 10 already got that answer in this run, use it as `<int>` without asking again, and record `integrationBranch` in that skill's own PR/MR, not a separate one.
`main` is fine as `<int>` only when the user chose it.

## 1. Start or resume: one task = one worktree = one branch

Repo opted in to `feature-status` (its section 0): for ticket work and for no-ticket features other agents could collide on, its `pick`, run before any worktree exists, replaces steps 1-3 (in a harness's detached worktree: `pick --no-worktree`, then `git switch -c <branch> --track origin/<branch>`); on `pick --resume` still read the progress file (section 3).
A small no-ticket change follows the steps below alone; `feature-status` section 1 owns who picks.

0. `git rev-parse --path-format=absolute --git-dir --git-common-dir` prints two different paths in a linked worktree.
   - Linked, on this task's branch: use it, read its progress file, go to section 2.
   - Linked, detached HEAD, clean tree (the harness's): steps 1-2, then in step 3 `git switch --no-track -c <branch> origin/<int>` in place.
   - Another task's branch, or the main checkout: never work there; step 1.
1. Look for existing work:
   ```bash
   git worktree list
   git branch -a --list '*/<ticket>-*' '<ticket>-*'
   gh pr list --state open --search '<ticket>'      # GitLab: glab mr list --search '<ticket>' (no glab: references/gitlab.md)
   ```
   Nothing: step 2.
   Found and the user asked to resume it: reuse it, read its progress file first, never create a second.
   Found otherwise: another agent may be on it; stop and ask.
2. Branch `<type>/<ticket>-<slug>` (`fix/WEST-12-paid-invoice-lock`), or `<type>/<slug>` without a ticket; type is `feat`, `fix`, `refactor`, `chore`, `docs`, or `test`.
3. Create it beside the main checkout, so the watchers, linters, and test runners there never scan it, without tracking `<int>`, using these commands rather than a harness feature (which may nest it in the repo or use a stale local HEAD):
   ```bash
   MAIN="$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)"
   WT="$(dirname "$MAIN")/$(basename "$MAIN").worktrees/<branch-with-slashes-as-dashes>"
   git worktree add --no-track -b <branch> "$WT" origin/<int>
   ```
4. Every command from now on runs in `$WT`.

## 2. Run without touching other agents

- Install dependencies (`pnpm install --frozen-lockfile` or equivalent); docs- or config-only changes may skip install and E2E, not the linters for those files.
- Symlink secrets-only gitignored files (`.agents/secrets.env`) from the main checkout; copy and edit per-worktree ones (`.env.local`: port, database, callback URLs); never commit either.
- Never kill processes you did not start; run yours on a free port and fix the URLs that depend on it.
- Docker Compose: `-p <repo>-<slug>`; with fixed `ports:` or `container_name:`, say so and use the running stack read-only, or ask.
- Never reset or migrate another worktree's database; schema changes and destructive tests get your own database or schema; if the app cannot run isolated, say so instead of running them on the shared one.
- Run the touched packages' tests once after your change; only a failing test is rerun on `origin/<int>` (`git worktree add --detach "$WT.base" origin/<int>`, removed after) and the result goes in Decisions.
- A test failing only on a shared test database is a flake: confirm in isolation, fix the isolation in its own branch per `root-cause`.

## 3. Commit, push, and keep the progress file as you go

Context resets lose chat, so each worktree keeps a resume file in its private git dir (never committed, no `.gitignore`, removed with the worktree; never `info/exclude`, which all worktrees share):

```bash
P="$(git rev-parse --path-format=absolute --git-path agent-progress.md)"   # inside $WT
```

- Under 30 lines, rewritten not appended, stale lines dropped: `# <branch>` and the ticket, `## Done` (steps, short hashes), `## In progress` (one step, its state), `## Next`, `## Decisions` (`<what> - <why> - <cost if wrong>`, pre-existing test failures).
- Read it first on resume and after a context summary; trust it and `git log origin/<int>..HEAD` over memory; update it with every commit.
- Small commits; check `git status` and stage only what you meant; never secrets, build output, or local config.
- Conventional Commit with the ticket id: `fix(billing): [WEST-12] keep paid invoices unlocked`, body wrapped at 72 (commitlint rejects body lines over 100).
- Helper files a tool needs in the repo are named in your notes and deleted before committing; the rest goes in the scratchpad.
- `git push -u origin HEAD` after the first commit, then keep pushing.
- Rewrite history only on your own branch, then `git push --force-with-lease`; never force-push a branch you do not own.
- Unrelated findings: per `AGENTS.md`.

## 4. Done means a PR/MR into `<int>`

All of these hold:

1. `git fetch origin && git rebase origin/<int>`, conflicts resolved keeping others' work, `git push --force-with-lease`.
2. `verify-loop` passed all its gates on the final head (including `fresh-review` beyond docs or config, `e2e-verify` when user-facing).
3. Its table is in the body, with head equal to `git rev-parse HEAD`.
4. A PR/MR is open into `<int>` (forge per `git remote get-url origin`):
   ```bash
   gh pr create --base <int> --head <branch> --title "<conventional title>" --body-file <file>
   glab mr create --source-branch <branch> --target-branch <int> --title "<conventional title>" --description "$(cat <file>)" --yes
   ```
   Missing or unauthenticated `gh` is a blocker to report, never a reason to skip; GitLab without `glab` follows `references/gitlab.md`.
   Never read a stored git credential to call a forge API.
5. The body: ticket or request, what changed and why, verification (table, evidence), risks, what is left out.
6. CI on the head is green (`verify-loop` section 3).
7. The PR/MR merges cleanly into `<int>`, checked after CI and again whenever you resume or report it:
   ```bash
   gh pr view <n> --json mergeable,mergeStateStatus -q '.mergeable + " " + .mergeStateStatus'   # UNKNOWN: still computing, retry
   glab mr view <n> --output json | jq -r '.has_conflicts, .detailed_merge_status'
   ```
   `CONFLICTING` / `DIRTY` or `has_conflicts: true`: resolve it now, without asking:
   `git fetch origin && git rebase origin/<int>`, and for each conflicted hunk read what the other side meant (`git log -p origin/<int> -- <file>`) and keep both intents; never take one side wholesale (`-X ours`, `--theirs`).
   No conflict markers left (`git diff --check`), then rerun `verify-loop` per its rerun table, `git push --force-with-lease`, update the table in the body, and check again until clean and CI is green.
   A conflict where keeping both intents is impossible (two changes to the same behavior) goes through `ask-or-decide` with both versions shown.
   GitLab without `glab`: `git merge-tree --write-tree origin/<int> HEAD` exits 1 on a conflict.

- Never merge your own PR/MR unless asked.
- `feature-status` repos: states, merge, release, and recovery per its section 3.
- Blocked or partial work: a draft (`--draft`) listing what remains, as soon as you know you will stop.
- Copy the progress file's Decisions and Next into the body; it dies with the worktree.

## 5. Promote to staging and prod

Only on the user's explicit word, per `AGENTS.md`.

- "Lên staging" means a PR/MR from `<int>` into staging, listing every commit it carries (others' work too); a single feature branch only when asked for exactly that.
- Merge it only if asked; if CI deploys on merge, that is a deploy under `environments`.
- Prod: the same from staging, under its `confirm-each-step` policy.

## 6. Clean up

Session start: `[gone]` branches only; "dọn worktree": also every worktree under `<repo>.worktrees/` (repos keeping merged branches never show `[gone]`).

```bash
git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads | awk '$2 == "[gone]" {print $1}'
git worktree list --porcelain | awk -v b="refs/heads/<branch>" '/^worktree /{p=substr($0,10)} $0=="branch "b{print p}'   # its $WT
gh pr view <branch> --json state,headRefOid -q '.state + " " + .headRefOid'   # GitLab: glab mr view <branch> --output json | jq -r '.state + " " + .sha' (no glab: references/gitlab.md)
```

Remove only when its PR/MR is merged or closed (`[gone]` proves nothing), `git -C "$WT" status --porcelain` is empty, `git rev-parse <branch>` equals the PR/MR head, and it is neither your worktree nor the main checkout.
`feature-status` repos, merged feature: `status.py release <ID>` first; when it names the recovery, do it in this worktree before removing anything.
Then `git worktree remove "$WT"` (if any) and `git branch -D <branch>` (needed after squash merges, safe only after these checks).

- Never `git worktree remove --force`; on refusal, keep it and report.
- Open PR/MR or no PR/MR: never remove, report.
- Stop the servers and containers you started.

## Report

Branch, worktree path, PR/MR URL, verification results, and anything the user must decide.
