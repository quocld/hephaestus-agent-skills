---
name: session-reset
description: >
  Use when the user starts a new work session or asks to put the repo back to a clean start: "reset", "reset session", "start session mới", "bắt đầu session mới", "bắt đầu làm việc", "về dev pull mới nhất", "sync lại repo", "fresh start", "start of day".
  Not for a plain `git reset` of commits or files, only removing worktrees ("dọn worktree": `worktree-flow`), or saving what was learned (`stow`).
user-invocable: true
---

# session-reset

Between sessions the main checkout drifts (left on a task branch, behind the remote) and finished worktrees pile up, so the next task starts from a stale base.
This puts the main checkout back on the latest integration branch and sweeps the worktrees, without ever discarding work: "reset" here never means `git reset`.

Every step acts on the main checkout through its path, so it runs the same from inside a linked worktree, which stays untouched.
Once `<int>` is known, a step that stops does not stop the sweep: section 4 still runs, and so does the report.

## 1. Read the state

`<int>` and the fetch per `worktree-flow` section 0; an unrecorded `<int>` is asked there, never assumed to be `dev` or `main`, also when the user says "dev".
Without `<int>` (no answer yet, or the fetch failed) report that and stop: nothing below runs on a guess.

```bash
git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1    # <main>, the main checkout
git -C <main> status --porcelain --branch                               # branch, uncommitted and untracked files
git -C <main> rev-parse --short HEAD                                    # the "was" sha for the report
```

Write `<main>` as the literal path in every command below: the `guard-protected-branches` hook asks on, or denies, a merge whose directory it cannot resolve.

## 2. Put the main checkout on `<int>`

First match wins:

- An operation in progress (a `rebase-merge`, `rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD` or `BISECT_LOG` under `git -C <main> rev-parse --path-format=absolute --git-path <name>`): leave the main checkout exactly as it is, skip section 3, and go to section 4.
- Already on `<int>`: nothing to do here, uncommitted files or not.
- Uncommitted or untracked files (`status --porcelain` prints more than its `##` line) on any other branch or a detached HEAD: leave the main checkout where it is, list the files, skip section 3, and go to section 4; a switch would carry them onto `<int>`.
- Detached HEAD, clean: when `git -C <main> rev-list --count HEAD --not --branches --remotes --tags` is not 0, those commits are on no ref, so leave it and report the sha; when 0, switch as below.
- On another branch: `git -C <main> switch <int>`.
  The branch keeps its commits; report it with `git -C <main> rev-list --count <branch> --not --remotes` (commits on no remote).
  A refused switch (for example `<int>` is checked out in another worktree) is reported, never forced.

Never `stash`, `checkout -f`, `switch --discard-changes`, `restore`, `clean` or `reset` to get past uncommitted files, here or in section 3: nobody is meant to work in the main checkout, so whatever is there is someone's stray work, and the user decides after seeing the files.
A request worded "reset sạch" or "clean everything" is not that decision.

## 3. Fast-forward `<int>`

Only when the main checkout is on `<int>` with no operation in progress; otherwise the report says why it was not moved.
Count after section 2, since a switch may have just created local `<int>`: `git -C <main> rev-list --left-right --count <int>...origin/<int>` prints ahead, then behind.

- ahead 0: `git -C <main> merge --ff-only origin/<int>`, never `git pull`.
  Uncommitted files stay as they are; git refuses by itself when a pulled commit touches one of them, and that refusal is reported, not worked around.
- ahead above 0: local `<int>` has commits the remote lacks, so do not merge; report `git -C <main> log --oneline origin/<int>..<int>`.
  Never `reset --hard origin/<int>`, rebase, merge without `--ff-only`, or push them: they may be someone's only copy, and the user decides.

Do not install dependencies or run anything else there; the main checkout is for reading.

## 4. Sweep the worktrees

Run `worktree-flow` section 6 at its "dọn worktree" scope: every worktree of this repo, old sibling layouts included.
It owns the classes, the merge detection, the removal gates and the commands; nothing here loosens them.
A worktree without the marker that passes every other gate goes under "Needs your word" below, with the commands that would run.
When the user's answer comes, check its gates again before removing it; it may have changed since the list.

## 5. Report, then stop

Fill every slot, one line per worktree or item, and write "none" in an empty one:

```text
Main checkout: <main> on <branch> @ <sha> (was <branch> @ <sha>; <n> commits pulled | not switched: <reason> | not fast-forwarded: <reason>)
Removed: <branch> - <PR/MR> - <worktree path>
Kept: <branch> - <class> - <worktree path>
Needs your word: <what> - <evidence> - <the command that would run, or the options>
```

- `<n>` is the behind count of section 3.
- "Needs your word" holds the uncommitted files found in the main checkout (on `<int>` or not), the local commits of section 3, a branch the main checkout left that has commits on no remote, and the "needs decision" and unmarked worktrees of section 4.
  An unmarked worktree gets its removal commands; the rest get options, since no single command is right for someone's files or commits.
  Ask about them once, together, per `ask-or-decide`, and act only on what the user names.
- Below the slots, add the branch the main checkout left (section 2) and the uncommitted files of the current worktree, which its "current" class hides.
- Create no branch and no worktree for the next task here: it starts with `worktree-flow` section 1 when the user gives it.
- This does not clear the conversation; the user runs `/clear` for that, after `stow` when the session learned something worth keeping.
