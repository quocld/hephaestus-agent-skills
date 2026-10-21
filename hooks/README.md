# hooks

Claude Code hooks that turn always-on rules from `AGENTS.md` into gates.
The plugin registers them through `hooks.json`, with `${CLAUDE_PLUGIN_ROOT}` pointing at this folder; nothing goes into `~/.claude/settings.json`.

| Script | Event and matcher | Does |
| --- | --- | --- |
| `session-start.py` | `SessionStart`, `startup\|clear\|compact` | Prints `AGENTS.md` as session context (a plugin cannot write `~/.claude/CLAUDE.md`), unless the same text is already loaded through a legacy `~/.claude/CLAUDE.md` link or the session runs inside this repo, and always names the plugin's `OPINIONS.md` path. Never blocks the start. |
| `no-em-dash.py` | `PreToolUse`, `Write\|Edit\|MultiEdit\|NotebookEdit` | Denies a write that puts an em dash (U+2014) on a line it changes, with a reason telling the agent to replace it on those lines. |
| `feature-status-guard.py` | `PreToolUse`, `Write\|Edit\|MultiEdit\|NotebookEdit` and `Bash` | In repos that use the `feature-status` skill, denies hand edits of `docs/status/*.md` (except `README.md`, the folder names compared without case) through the edit tools and, best effort, through shell writes (`>` also glued to a word, `sed -i`, `awk -i inplace`, `tee`, `cp`, `mv`, `ln`, `git checkout <ref> -- <file>`, `git restore --source`, `python -c` code with a write signal), a `git worktree add`, `git switch -c` or `git checkout -b` of a `<type>/<ID>-<slug>` branch for a ticket ID (`WEST-12`) that has no `claim/<ID>` in the last fetch and no active status file naming it, or that creates a branch for an ID whose claim names a different branch, and a `gh pr create` or `new` / `glab mr create` or `new` from a ticket-ID or claimed branch that lacks a committed status file or, unless `--draft`, is not `in-review` (or `merged`), fails `status.py check`, or has commits its upstream does not. |
| `guard-protected-branches.py` | `PreToolUse`, `Bash` | Returns `ask` (a permission prompt) for `git push` to main, master, staging, stage, prod, or production, `--all`/`--mirror`, `git merge` while on one of those (except `--ff-only` onto its own remote counterpart, `origin/<branch>` or `@{u}`), `git pull` on one of those that names another branch (a bare `git pull` or one naming the current branch passes), every `gh pr merge` or `glab mr merge`, and a push, merge or branch-naming pull whose repo directory it cannot resolve; `deny` instead in `bypassPermissions` and `dontAsk` modes, where no prompt would appear. A repo opts a branch out with `git config agentguard.allow <branch>`, set by the user only. |

All read the hook JSON on stdin, print nothing when the call is fine, and fail open on bad input.
The em dash check judges only changed lines: a line of the new text counts as unchanged when the same exact line is in `old_string` (Edit, and each MultiEdit edit), in the existing file (Write), or in an existing cell of the notebook (NotebookEdit).
So a file that already has em dashes can be edited freely, while a line you touch must lose its em dash; a new file, or one the hook cannot read, is checked in full.
Known gap: edits made through Bash (`sed`, heredocs) are not checked; the `AGENTS.md` rule still applies to them.

Legacy installs registered the gates by hand in `~/.claude/settings.json` (commands under `$HOME/.claude/agent-skills-hooks/`).
With the plugin installed those entries run every gate twice: delete them, then run `migrate-to-plugin.py` to drop the link.

The guard reads the current branch from the repo the command acts on: payload `cwd`, then an earlier `cd <dir>` in the command, then `git -C <dir>`.
It returns `ask` when that directory cannot be resolved, skips `gh`/`glab` `-R`/`--repo` values, and rescans the strings run by `bash -c`, `sh -c`, `zsh -c` and `eval`.
It matches `git`, `gh` and `glab` by basename anywhere in a simple command, so `/usr/bin/git push origin main` asks and `echo git push origin main` unquoted also asks, which errs on the safe side.
A `cd` or `-C` target of `$PWD`, `${PWD}`, `$(pwd)` or `$(git rev-parse --show-toplevel)` (quoted, or in backticks, optionally followed by `/<path>`) resolves to the directory it names; any other variable leaves it unresolved.

The feature-status guard treats a repo as opted in when `docs/status/` exists at its top level or its `AGENTS.md` mentions `feature-status`; the Bash rules also check `origin/<int>` with `git ls-tree` and `git show`, where `<int>` is `integrationBranch` in `.agents/environments.json`, else the legacy `dev` environment's branch; for this opt-in check only, `origin/dev` and `origin/HEAD` are read too.
It finds commands the same way as the protected-branch guard (payload `cwd`, `cd`, `git -C`, `bash -c`, `eval`) and reuses that script's parser.
Where that guard asks on an unresolvable `cd` or `-C` target, this one falls back to the payload `cwd`, whose repo shares its refs with every worktree, so `cd $(git rev-parse --show-toplevel)` unquoted is still checked.
Short flags bundled as git reads them (`-qb <branch>`, `-fb`, `-qc`) count as the branch-creating flag.
It reads the status file from the committed branch, not the working tree, so a PR/MR never ships an uncommitted state change.
It runs `status.py check <ID> --ref <branch>`, which validates the committed file and requires its E2E evidence to be committed too, from `$FEATURE_STATUS_SCRIPT` when set, otherwise `~/.claude/skills/feature-status/scripts/status.py`, otherwise `../skills/feature-status/scripts/status.py` next to this folder, and only checks the state when none is usable.
A claim is looked up among the local `refs/remotes/origin/claim/*` refs, as of the last `git fetch` (which `pick` and `worktree-flow` run); the hook never calls the network, so it neither stalls nor fails open offline, and its deny reason says to fetch and retry.
A status file inherited from `<int>` (a merged `WEST-1`) does not count as a claim for a new branch of the same ID; it counts only when its `branch` names the branch and its state is active, or it sits on that branch's own ref.
Creating a branch (`-b`, `-c`, not checking out an existing one) for an ID whose `claim/<ID>` exists is denied when the claim's status file, read from the local ref `refs/remotes/origin/claim/<ID>`, names a different branch, since parallel agents share one git identity and one ID gets one branch; an unreadable claim file fails open.
Known limit: the branch rules only see branch names with a recognizable `<type>/<ID>` (`feat/WEST-12-x`, `fix/csv-export`), so a branch named `wip-12` or `west12` is out of scope and is never denied.
The branch and PR/MR rules judge a branch only when its ID is ticket-shaped (`WEST-12`: uppercase letters, a dash, digits) or a `claim/<ID>` exists for it among the local refs, so a small no-ticket change on `fix/csv-export` or `docs/readme-typo` passes without `pick`; a lowercase `west-12` counts as a slug.
A non-draft PR/MR is also denied while the local branch is ahead of its local upstream tracking ref (unpushed commits), judged from local refs only, with the fix `git push`; a branch without an upstream is not judged.
The shell-write rule is best effort, since arbitrary shell cannot be parsed completely; `status.py check` in the PR rule is the backstop for malformed files.
Interpreter `-c`/`-e` code that names a status file is denied only with a write signal (a `w`/`a`/`x` open mode, `write`, `append`, `rename`, `unlink`, `remove`, `copy`, `move`, `>`), so reading one stays allowed; a quoted string that merely contains `x>docs/status/<ID>.md` is denied too.
`git checkout -- <file>` and `git restore <file>` without a ref stay allowed, since they only drop uncommitted edits.

Run `hooks/test.sh` after any change: it pipes allow, ask and deny payloads through every hook in throwaway repos (with a local bare origin for the feature-status guard) checks that `hooks.json` mounts every script on its event and matcher, and checks that `~/.claude/settings.json` enables the plugin or, on a legacy install, registers every script on each tool of its matchers (a warning only when that file is absent, as in CI).
Add a case there for every new rule and confirm it fails with the rule removed.
