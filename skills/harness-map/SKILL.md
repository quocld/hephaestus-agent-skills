---
name: harness-map
description: >
  Use when asked to see, visualize, or audit the whole agent harness setup at once: "harness đang thiếu gì", "setup harness tới đâu rồi", "xem tổng quan setup", "visualize setup", "báo cáo setup ra HTML", "check bộ skill đã cài chưa", "harness map", "what is missing in my setup". Not for fixing one project's AGENTS.md block (project-init doctor) or a single environment (environments).
user-invocable: true
---

# harness-map

Setup gaps hide in many places at once: links install.sh never made, hooks not registered, CLIs a skill needs, plugins, secrets in settings, a project without its agent block.
This skill renders all of them into one HTML page so the user sees what is set up, what is missing, and what to run next.

## 1. Generate

```bash
python3 ~/.claude/skills/harness-map/scripts/harness_map.py --open
```

- It checks the git repo of the current directory as the project; pass `--project <dir>` for another one. Outside a git repo the Project section is skipped.
- The page lands at `~/.claude/harness-map.html` unless `--out <file>` is given.
- `--no-probe` skips `hooks/test.sh` and `gh auth status` when the user wants it instant or offline.
- The skill list comes from the checkout the script runs from, and fix commands point at the main checkout's `install.sh`.

The script is read-only, never prints a secret value (only the key name), and runs nothing that builds, installs or deploys.

## 2. Report

Print the path of the HTML file, the readiness score, and the numbered "Fix first" list from the script's stdout, in that order.
Do not retype the whole report; the page holds the detail.

## 3. Fixing

Fixing is a separate step the user asks for; this skill only maps.
When asked, take the list from the top and route each item to its owner:

| Item | Owner |
| --- | --- |
| Links, skills not installed | `install.sh` in the agent-skills main checkout; confirm first, since it moves existing real files to `~/.claude/backups/` |
| Hook not registered | `hooks/README.md` entries, merged into `hooks.PreToolUse`, never replacing the array |
| Project block, registry, integration branch, `TODO(owner)`, CLAUDE.md import, `secrets.env` not gitignored | `project-init`, then `environments` |
| Plaintext secret in settings | Tell the user: move it out, rotate it, delete the backup copies the row names; never echo the value or edit the file yourself |
| settings.json backups | The user decides which to delete; never delete them yourself |
| CLI missing, no browser tool for `e2e-verify` | The install command in the row; logins as `! <command>` for the user to run |
| Plugin install path missing | `claude plugin install <id>` from the row |

Re-run the script (with `--open` only if the user wants the page again) and show the new score.

## 4. Changing the checks

Every check lives in one collector function in `scripts/harness_map.py`, one per section.
A new skill dependency on a CLI goes into the `TOOLS` table; a new section needs a collector, an entry in `DESCS` and `ICONS`, and a call in `main`.
Keep the page self-contained (inline CSS and JS, fonts from Google Fonts with system fallbacks) and its colors on the tokens in `:root`, which follow the SpecsGraph design system v2.
