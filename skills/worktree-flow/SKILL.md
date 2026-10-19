---
name: worktree-flow
description: >
  Use at the start of any task that will change files in a git repo, when answering questions about the code, before committing or opening a PR/MR, when resuming, finishing, or abandoning a task, and when asked "tạo worktree", "mở PR", "mở MR", "xong thì commit", "dọn worktree", "lên staging".
user-invocable: true
---

# worktree-flow

Several agents work on the same repo at the same time, so the main checkout belongs to nobody.
Every task gets its own worktree and branch, work is pushed as it goes, and finished work always ends as a PR/MR.

## 0. Before anything: fetch and find the integration branch

```bash
git fetch origin --prune
```

- The integration branch is the `branch` of the `dev` environment in `.agents/environments.json`, otherwise `dev` if `git ls-remote --exit-code --heads origin refs/heads/dev` succeeds.
- Neither exists: stop and ask which branch PRs/MRs go into.
  Never fall back to `main`, `master`, or any branch the registry lists for staging or prod.
- Below, `<int>` means that branch.

Read-only questions ("explain this function") need no worktree, but answer from `origin/<int>` (`git show origin/<int>:<path>`), not from the main checkout, which may be on another branch or hold someone's edits.
Say which ref you read.

## 1. Start or resume: one task = one worktree = one branch

0. Check whether you already stand in a linked worktree (a harness may have started you in one):
   ```bash
   git rev-parse --path-format=absolute --git-dir --git-common-dir   # two different paths = linked worktree
   git rev-parse --show-superproject-working-tree                    # prints a path = submodule, not a worktree
   ```
   - Linked worktree on this task's branch: use it and go to section 2.
   - Linked worktree on a detached HEAD with a clean tree (made for you by the harness): continue with steps 1 and 2, then in step 3 create the branch in place with `git switch --no-track -c <branch> origin/<int>` instead of adding a worktree.
   - Linked worktree on another task's branch: do not work there; continue with step 1 to create your own.
1. Look for existing work on the ticket:
   ```bash
   git worktree list
   git branch -a --list '*/<ticket>-*' '<ticket>-*'
   gh pr list --state open --search '<ticket>'      # GitLab: glab mr list --search '<ticket>'
   ```
   - Nothing found: create it (step 2).
   - Found, and the user asked to continue or resume that work: reuse that worktree or branch; do not create a second one.
   - Found otherwise: another agent may be on it; stop and ask.
2. Name the branch `<type>/<ticket>-<slug>` (`fix/WEST-12-paid-invoice-lock`); with no ticket, `<type>/<slug>`.
   Types follow Conventional Commits: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`.
3. Create it as a sibling of the main checkout, so watchers, linters, and test runners there never scan it, and without tracking `<int>`:
   ```bash
   MAIN="$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)"
   WT="$(dirname "$MAIN")/$(basename "$MAIN").worktrees/<branch-with-slashes-as-dashes>"
   git worktree add --no-track -b <branch> "$WT" origin/<int>
   ```
   Use these commands rather than a harness's built-in worktree feature, which may put the worktree inside the repo or base it on a stale local HEAD.
4. Work only inside `$WT` from now on; every command runs there.

## 2. Make the worktree runnable without touching other agents

- Install dependencies (`pnpm install --frozen-lockfile` or the repo's equivalent).
  Docs-only or config-only changes may skip install, baseline, and E2E; still run the linters that cover those files.
- Gitignored local config: symlink files that only hold secrets (`.agents/secrets.env`) from the main checkout; copy and edit files whose values must differ per worktree (`.env.local` with its port, database name, callback URLs).
  Never commit either.
- Processes you did not start (dev servers, watchers, containers) belong to someone else; never kill them.
  Run yours on a free port and update the URLs that depend on it.
- Docker Compose: your own project name (`-p <repo>-<slug>`).
  Fixed `ports:` or `container_name:` in the compose file cannot run twice; say so and use the already running stack read-only, or ask.
- Databases: never reset or migrate a database another worktree uses.
  When the task changes the schema or runs destructive tests, use your own database or schema.
  If the app cannot run isolated, say so instead of fighting over shared resources.
- Record the baseline of already-failing tests before changing anything.
  A test that fails only while other agents share the test database is a shared-state flake: confirm it in isolation, then fix the isolation in its own branch per `root-cause`, not inside this task.

## 3. Commit and push as you go

- Small commits at each working step; check `git status` first and stage only files you meant to change.
  Never commit secrets, build output, or local config.
- Conventional Commit with the ticket id: `fix(billing): [WEST-12] keep paid invoices unlocked`.
- Push after the first commit and keep pushing, so nothing lives only on this machine:
  ```bash
  git push -u origin HEAD
  ```
- Rewriting history only on your own branch, then `git push --force-with-lease`.
  Never force-push a branch you do not own.
- Something unrelated found along the way: fix a trivial one in this PR and mention it in the body; anything bigger gets its own branch and PR/MR, after checking an open PR/MR does not already fix it.

## 4. Done means a PR/MR into `<int>`

A task is finished only when all of these hold:

1. Rebased on the latest base: `git fetch origin && git rebase origin/<int>`, conflicts resolved keeping other people's work, then `git push --force-with-lease`.
2. Checks pass: typecheck, lint, tests of the touched packages, and the project's own gates; E2E evidence (`e2e-verify`) when the change is user-facing.
3. A change that matters has passed `fresh-review`, with `origin/<int>` as the base.
4. A PR/MR is open into `<int>` (detect GitHub or GitLab from `git remote get-url origin`):
   ```bash
   gh pr create --base <int> --head <branch> --title "<conventional title>" --body-file <file>
   glab mr create --source-branch <branch> --target-branch <int> --title "<conventional title>" --description "$(cat <file>)" --yes
   ```
   A missing or unauthenticated CLI is a blocker to report, not a reason to skip the PR/MR.
5. The body says: the ticket or request, what changed and why, how it was verified (commands, evidence files), risks, and what is deliberately left out.

- Do not merge your own PR/MR unless the user asks.
- Blocked or partly done work becomes a draft (`gh pr create --draft`, `glab mr create --draft`) whose body lists what remains.
  Do this as soon as you know you will stop, not at the very end.

## 5. Staging and prod only on the user's explicit word

- Never open a PR/MR into, merge into, push to, or deploy the staging or production branches unless the user says so explicitly in this conversation.
  The approval covers exactly what was named, this time only.
- "Lên staging" by default means promoting `<int>` as a whole: open a PR/MR from `<int>` into the staging branch, and list in its body every commit it carries, since that includes other people's merged work.
  Merge a single feature branch directly into staging only when the user asks for exactly that.
- Merge the promotion PR/MR only if the user asked to merge.
  If CI deploys on merge, merging is a deploy and follows the `environments` skill.
- Prod works the same way, from staging into the production branch, under that environment's `confirm-each-step` policy.

## 6. Clean up

- At the start of a session, sweep the worktrees under `<repo>.worktrees/`: when its PR/MR is merged or closed (check `gh pr view <branch>` or `glab mr view <branch>`), the tree is clean, and the branch head equals the PR/MR's head commit (`gh pr view <branch> --json headRefOid -q .headRefOid`, or `glab mr view <branch>`), remove it with `git worktree remove "$WT"` and `git branch -D <branch>`.
  `-D` is needed after squash merges; only use it once the PR/MR state confirms the merge.
- Never remove a worktree with uncommitted or unpushed work, or one whose PR/MR is still open.
- Stop the dev servers and containers you started.

## Report

Branch, worktree path, PR/MR URL, verification results, and anything the user must decide.
