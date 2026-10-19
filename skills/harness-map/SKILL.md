---
name: harness-map
description: >
  Use when asked to see, visualize, document, or audit the whole agent harness at once: "harness đang thiếu gì", "setup harness tới đâu rồi", "xem tổng quan setup", "visualize setup", "báo cáo setup ra HTML", "check bộ skill đã cài chưa", "harness map", "vòng tròn harness", "docs harness", "skill nào chạy ở đâu", "what is missing in my setup". Not for fixing one project's AGENTS.md block (project-init doctor) or a single environment (environments).
user-invocable: true
---

# harness-map

Setup gaps hide in many places at once: links install.sh never made, hooks not registered, CLIs a skill needs, plugins, secrets in settings, a project without its agent block.
This skill renders two HTML pages from one template: a live dashboard (what is set up, what is missing, core versus optional, the eight-component harness wheel) and the harness docs (the wheel's definitions, the Claude Code lifecycle with every skill and hook placed on it, the task path, ultracode).

## 1. Generate

```bash
python3 ~/.claude/skills/harness-map/scripts/harness_map.py --open    # dashboard -> ~/.claude/harness-map.html
python3 ~/.claude/skills/harness-map/scripts/harness_docs.py --open   # docs -> ~/.claude/harness-docs.html
```

Run the dashboard for "what is missing" questions and the docs for "how does it fit together" questions; run both when unsure.

- It checks the git repo of the current directory as the project; pass `--project <dir>` for another one. Outside a git repo the Project section is skipped.
- Either page goes elsewhere with `--out <file>`.
- `--no-probe` skips `hooks/test.sh` and `gh auth status` when the user wants it instant or offline.
- The skill list comes from the checkout the script runs from, and fix commands point at the main checkout's `install.sh`.

The script is read-only, never prints a secret value (only the key name), and runs nothing that builds, installs or deploys.

## 2. Report

Print the path of the HTML file, the core and optional readiness, and the numbered "Fix first" list from the script's stdout, in that order; core items first.
For the docs, print the path and any skill the script says is not placed in `assets/lifecycle.json` (it exits 1 then).
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

## 4. Changing the pages

| Change | Where |
| --- | --- |
| A new skill in the repo | `assets/lifecycle.json`: its `tier` (core or optional), lifecycle `events`, task-path `stage`, `when`; and the pillar(s) it serves in `assets/pillars.json` |
| A gap closed or found in one of the eight components | `gaps` of that pillar in `assets/pillars.json` |
| A new check | One collector per section in `scripts/harness_map.py`; a CLI goes in `TOOLS`; a new section also needs `DESCS` and an icon in `scripts/page.py` |
| Look and feel | `assets/template.html` only; both pages render through `render_page` in `scripts/page.py` |

A core item is one every session depends on; optional only matters for some skills, stacks or habits (`tier_of` in `harness_map.py`).
Keep pages self-contained (inline CSS and JS, Google Fonts with system fallbacks) and every color on the `:root` tokens, which follow the SpecsGraph design system v2.
