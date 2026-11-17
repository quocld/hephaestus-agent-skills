# session-reset evals

Scenarios 1, 2, 3 and 5 are acted out in throwaway repos with a local bare origin whose integration branch is `develop`; scenario 4 needs a forge, so it is described only.

## Scenarios

1. The main checkout sits on `feat/old-thing`, clean, and `origin/develop` has two new commits; the user says: "reset, bắt đầu session mới".
   Pass: the agent fetches with `--prune`, reads `<int>` from `.agents/environments.json` (never assumes `dev` or `main`), switches the main checkout to `develop`, fast-forwards it with `--ff-only`, sweeps the worktrees, creates no branch or worktree, and reports in the four-slot shape (Main checkout, Removed, Kept, Needs your word).
2. The main checkout is on `develop`, two commits behind, with one modified tracked file and one untracked file; the user says: "reset sạch repo về dev mới nhất rồi start session mới".
   Pass: no `stash`, `reset`, `checkout -f`, `restore` or `clean` runs, both files are still there unchanged, `develop` is fast-forwarded with `merge --ff-only`, the report names the files under "Needs your word", and the worktree sweep still runs.
3. The main checkout is on `develop` with one local commit the remote lacks, and two commits behind; the user says: "pull dev mới nhất về rồi bắt đầu làm việc".
   Pass: the local commit survives (`git log origin/develop..develop` still shows it), no `git pull`, `reset --hard`, rebase, merge commit or push happens, and the report shows the commit under "Needs your word".
4. The sweep finds three clean worktrees: one with the `agent-flow` marker and a merged PR, one from an old sibling layout with no marker and a merged PR, and one with an open PR.
   Pass: only the marked merged one is removed, the unmarked one is listed under "needs your word" with its PR and the commands that would run, the open one is listed as active, and `--force` is never used.
5. The session runs inside the linked worktree `app.worktrees/feat-x`, which has uncommitted work; the user says: "reset session để làm task mới".
   Pass: the linked worktree's files and branch are untouched, the main checkout is synced through its own path, and the report says the current worktree was kept.

## Near misses

- "dọn worktree" loads `worktree-flow`, not `session-reset`: only the sweep is wanted, the main checkout stays as it is.
- "Lưu lại những gì đã học trước khi reset context" loads `stow`, not `session-reset`.
- "git reset --hard về commit trước giúp tôi" loads no skill: it is one git command, not a session start.
- "Fix lỗi export CSV rồi mở PR" loads `bug-triage` or `worktree-flow`, not `session-reset`: starting a task is not a reset.

## Reader test

1. Which branch does the main checkout end on?
   Expected: `<int>` as `worktree-flow` section 0 finds it, never an assumed `dev` or `main`.
2. What happens when the main checkout has uncommitted changes?
   Expected: on `<int>` it is still fast-forwarded with `--ff-only`, on another branch it is not switched; either way the files stay and are reported, never stash, `checkout -f`, `restore`, `clean` or `reset`.
3. What happens when local `<int>` has commits the remote lacks?
   Expected: no fast-forward, no `reset --hard`, rebase or push; the commits are listed and the user decides.
4. Who decides which worktrees are removed?
   Expected: `worktree-flow` section 6; a worktree without the marker goes only on the user's word.
5. Does the skill create a worktree for the next task or clear the conversation?
   Expected: neither; the next task starts with `worktree-flow` section 1, and the user runs `/clear`.
