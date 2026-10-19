# hooks

Claude Code hooks that turn always-on rules from `AGENTS.md` into gates.
`install.sh` links this folder to `~/.claude/agent-skills-hooks`, and `~/.claude/settings.json` calls the scripts from there.

| Script | Event and matcher | Does |
| --- | --- | --- |
| `no-em-dash.py` | `PreToolUse`, `Write\|Edit\|MultiEdit\|NotebookEdit` | Denies a write whose new text contains an em dash (U+2014), with a reason telling the agent to rewrite it. |
| `guard-protected-branches.py` | `PreToolUse`, `Bash` | Returns `ask` (a permission prompt) for `git push` to main, master, staging, stage, prod, or production, `--all`/`--mirror`, `git merge` while on one of those, every `gh pr merge` or `glab mr merge`, and a push or merge whose repo directory it cannot resolve. |

Both read the hook JSON on stdin, print nothing when the call is fine, and fail open on bad input.

Settings entries (merge into `hooks.PreToolUse`, never replace the array):

```json
{"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [{"type": "command", "command": "python3 \"$HOME/.claude/agent-skills-hooks/no-em-dash.py\"", "timeout": 10}]},
{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 \"$HOME/.claude/agent-skills-hooks/guard-protected-branches.py\"", "timeout": 10}]}
```

The guard reads the current branch from the repo the command acts on: payload `cwd`, then an earlier `cd <dir>` in the command, then `git -C <dir>`.
It returns `ask` when that directory cannot be resolved, skips `gh`/`glab` `-R`/`--repo` values, and rescans the strings run by `bash -c`, `sh -c`, `zsh -c` and `eval`.
It matches `git`, `gh` and `glab` anywhere in a simple command, so `echo git push origin main` unquoted also asks, which errs on the safe side.

Run `hooks/test.sh` after any change: it pipes allow, ask and deny payloads through both hooks in throwaway repos and checks that `~/.claude/settings.json` registers both scripts (a warning only when that file is absent, as in CI).
Add a case there for every new rule and confirm it fails with the rule removed.
