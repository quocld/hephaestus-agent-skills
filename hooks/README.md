# hooks

Claude Code hooks that turn always-on rules from `AGENTS.md` into gates.
The plugin registers them through `hooks.json`, with `${CLAUDE_PLUGIN_ROOT}` pointing at this folder; nothing goes into `~/.claude/settings.json`.

| Script | Event and matcher | Does |
| --- | --- | --- |
| `session-start.py` | `SessionStart`, `startup\|clear\|compact` | Prints `AGENTS.md` as session context (a plugin cannot write `~/.claude/CLAUDE.md`), unless the same text is already loaded through a legacy `~/.claude/CLAUDE.md` link or the session runs inside this repo, and always names the plugin's `OPINIONS.md` path. Never blocks the start. |
| `no-em-dash.py` | `PreToolUse`, `Write\|Edit\|MultiEdit\|NotebookEdit` | Denies a write whose new text contains an em dash (U+2014), with a reason telling the agent to rewrite it. |
| `guard-protected-branches.py` | `PreToolUse`, `Bash` | For `git push` to main, master, staging, stage, prod, or production, `--all`/`--mirror`, `git merge` while on one of those, and every `gh pr merge` or `glab mr merge`: returns `ask` (a permission prompt), or `deny` in `bypassPermissions` and `dontAsk` modes, where no prompt would appear. A repo opts a branch out with `git config agentguard.allow <branch>`, set by the user only. |

Both read the hook JSON on stdin, print nothing when the call is fine, and fail open on bad input.
The em dash check reads only the new text, so editing a file that already has em dashes works as long as the replacement text does not carry them; rewrite those lines with a plain dash when you touch them, and keep `old_string` small enough not to copy unchanged em-dash lines into the new text.
Known gap: edits made through Bash (`sed`, heredocs) are not checked; the `AGENTS.md` rule still applies to them.

Legacy installs registered the gates by hand in `~/.claude/settings.json` (commands under `$HOME/.claude/agent-skills-hooks/`).
With the plugin installed those entries run every gate twice: delete them, then run `migrate-to-plugin.py` to drop the link.

The guard reads the current branch from the repo the command acts on: payload `cwd`, then an earlier `cd <dir>` in the command, then `git -C <dir>`.
It returns `ask` when that directory cannot be resolved, skips `gh`/`glab` `-R`/`--repo` values, and rescans the strings run by `bash -c`, `sh -c`, `zsh -c` and `eval`.
It matches `git`, `gh` and `glab` anywhere in a simple command, so `echo git push origin main` unquoted also asks, which errs on the safe side.

Run `hooks/test.sh` after any change: it pipes allow, ask and deny payloads through both hooks in throwaway repos and checks that `~/.claude/settings.json` registers both scripts (a warning only when that file is absent, as in CI).
Add a case there for every new rule and confirm it fails with the rule removed.
