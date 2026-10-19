---
name: harness-map
description: >
  Use when asked to see or audit the whole agent harness, or to finish setting it up step by step: "harness đang thiếu gì", "setup harness", "hoàn thành setup harness", "kiểm tra còn thiếu và hỏi tôi", "check bộ skill đã cài chưa", "harness map", "docs harness", "skill nào chạy ở đâu", "finish my harness setup". Not for one project's AGENTS.md block alone (project-init) or one environment (environments).
user-invocable: true
---

# harness-map

Setup gaps hide in many places at once: links install.sh never made, hooks not registered, CLIs a skill needs, plugins, secrets in settings, a project without its agent block.
This skill renders one HTML page with two tabs: Dashboard (what is set up, what is missing, core versus optional, the eight-component harness wheel, the project facts and every environment from `.agents/environments.json`) and Docs (the Claude Code lifecycle with every skill and hook placed on it, the task path, the verification loop, the skill reference, and every wired hook with what it does).

## 1. Generate

```bash
python3 <this skill>/scripts/harness_map.py --open    # -> ~/.claude/harness-map.html; --help lists the flags
```

`<this skill>` is this skill's base directory, wherever it is installed; never write a machine-specific path into anything the user copies or commits.
It checks the git repo of the current directory (`--project <dir>` for another); `#docs` opens the Docs tab.
`--no-probe` skips the hooks test and the login checks when the user wants it instant or offline.
The script is read-only, never prints a secret value (only key names, and for registry secrets only whether they resolve), and runs nothing that builds, installs, deploys or reaches a remote environment.
It owns the machine checks; `project-init` section 4 (the doctor) reuses them, adds the network probes, and owns the project-block and registry probes.

## 2. Report

Print the path of the HTML file, the core and optional readiness, and the numbered "Fix first" list from the script's stdout, in that order; core items first.
Also print any skill the script says is not placed in `assets/lifecycle.json`; the Skills section flags it too.
Do not retype the whole report; the page holds the detail.
When the user only asked to see the harness, stop here; finishing it is section 3 and needs the user's word.

## 3. Setup flow

The Dashboard's setup prompt (`--prompt` prints it) starts this flow; the user may also ask for it in their own words.
Run it from the project the user wants set up, one step at a time, never as one batch of changes.
Never use `--no-probe` here: the hooks test is how step 2 knows it is done.
When this skill runs from a checkout before step 1, read any skill this flow names next to it (`<this skill>/../<name>/SKILL.md`); if the user declines the install, keep reading them there.

1. **Check**: run the script with `--open` and read its fix list; the order below decides what comes first, not the list's order.
2. **Take the steps in this order**, skipping a step with no gap:

   | Step | Gaps it closes | How |
   | --- | --- | --- |
   | 1. Install | agent-skills plugin missing, skills not installed, legacy links | Ask first, then the fix command the script prints; a legacy install also runs `migrate-to-plugin.py` after its settings entries are gone; a new session picks the plugin up; a `name clash` row means the user already has a different skill with that name: keep theirs active, fork ours as `hx-<name>` next to it, say what differs, and ask whether to keep, switch or merge; a `duplicate copy` row only needs the extra copy removed, with the user's yes |
   | 2. Hooks | Hook not registered, or registered twice | The plugin registers the gates; a gate that runs twice has a legacy `agent-skills-hooks` entry in `~/.claude/settings.json`: ask, delete only that entry, then run the plugin's `hooks/test.sh` |
   | 3. Secrets | Plaintext secret in settings, backups that hold it | Tell the user where it is, to move it out and rotate it, and which backups hold it; never read, echo, move or delete it yourself |
   | 4. Tools and logins | CLI missing, `gh` not logged in, Jira access, browser tool, Better Stack MCP | The install command from the row; logins and MCP sign-ins as `! <command>` or `/mcp` for the user, marked waiting on you |
   | 5. Project | No AGENTS.md or project-init block, CLAUDE.md import, integration branch, `TODO(owner)` | `project-init`, which asks the gaps in one batch, including which branch PRs go into (this step's own PR targets it) |
   | 6. Environments | No registry, prod policy, version command, unresolved secrets, `logs` rename, `secrets.env` not gitignored | `environments` (its create section), which asks for URLs, SSH aliases and test accounts |
   | 7. Optional | Everything in the optional list | Show the list and ask which ones the user wants; do only those |

3. **Ask before you change**: in steps 1 to 4 and 7, when a step needs a fact or a decision only the user has, ask once per step with your drafted answer shown (`ask-or-decide`); never invent one, and write `TODO(<owner>)` for what the user does not know yet.
   In steps 5 and 6 the owner skill asks; do not ask the same things again.
   A step only the user can finish (a login, moving a secret) is marked "waiting on you" and the flow goes on to the next step; check it again in the final run.
   Steps 5 and 6 run in a worktree and end as a PR/MR into the integration branch (`worktree-flow`); steps 1 to 4 change only the user's machine.
4. **Show progress**: after each step, rerun the script with `--open` so the user sees the page change, and say in one line what moved.
5. **Repeat** until no core gap is left, then run step 7.
   A gap that stays after its step was done is a finding: say why (`root-cause`), do not loop on it.
6. **Finish**: rerun the script with `--open` one last time and report the core and optional readiness, what changed, the PR/MR links, and every item still waiting on the user; then stop.

## 4. Changing the page

| Change | Where |
| --- | --- |
| A new skill in the repo | `assets/lifecycle.json`: its `tier` (core or optional), lifecycle `events`, task-path steps in `path` (setup, prompt, gather, act, verify, retry, response, remember), `when`; and the pillar(s) it serves in `assets/pillars.json` |
| A skill that runs a whole workflow end to end and orchestrates other skills | `"ultimate": true` on it in `assets/lifecycle.json`; every page then draws its name in the animated gradient |
| A new or changed hook | Registered in `hooks/hooks.json`; its one-line "Does" in the README hooks table, which the Hooks wired table reads; and the hooks line of the Quality Gates pillar in `assets/pillars.json` |
| A new eval, CI check, or verify-loop rule | Evals and CI: `covered_by` of the Evaluation or Quality Gates pillar in `assets/pillars.json`; gates, rules, and the retry label: `verify_loop` in `assets/lifecycle.json` |
| A gap closed or found in one of the eight components | `gaps` of that pillar in `assets/pillars.json` |
| A new check | One collector per section in `scripts/harness_map.py`; a CLI goes in `TOOLS`; a new section also needs `DESCS` and an icon in `scripts/page.py`; a check of the project-init block or a registry probe goes in `project-init`'s `scripts/doctor.py` instead |
| Look and feel | `assets/template.html` only; the page renders through `render_page` in `scripts/page.py`; the Docs tab body comes from `scripts/harness_docs.py` |

A core item is one every session depends on; optional only matters for some skills, stacks or habits (`tier_of` in `harness_map.py`).
Keep pages self-contained (inline CSS and JS, Google Fonts with system fallbacks) and every color on the `:root` tokens, which follow the SpecsGraph design system v2.
