---
name: harness-map
description: >
  Use when asked to see or audit the whole agent harness, or to set it up or finish setting it up: "harness đang thiếu gì", "setup harness", "hoàn thành setup harness", "kiểm tra còn thiếu và hỏi tôi", "check bộ skill đã cài chưa", "harness map", "docs harness", "skill nào chạy ở đâu", "finish my harness setup", "check what is missing and ask me", and after installing Hephaestus Skills (the onboard prompt, the install guide). Not for one project's AGENTS.md block alone (project-init) or one environment (environments).
user-invocable: true
---

# harness-map

Setup gaps hide in many places at once: links install.sh never made, hooks not registered, CLIs a skill needs, plugins, secrets in the global settings, a project without its agent block.
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
Stop here only when the user asked only to see the harness ("harness map", "what is missing", "docs harness") and nothing about setting it up.
Any setup intent goes straight on to section 3 in the same run, with no stop at the report: the Dashboard's setup prompt, the onboard prompt or install guide, "setup harness", "finish setup", "check what is missing and ask me", or any request to install, fix or finish.

## 3. Setup flow

Run it from the project the user wants set up: one check, one question batch, then every step to the end, without asking again.
Never use `--no-probe` here: the hooks test is how step 2 knows it is done.
When this skill runs from a checkout before the plugin is installed, read any skill this flow names next to it (`<this skill>/../<name>/SKILL.md`); if the user declines the install, keep reading them there.

1. **Check**: run the script with `--open` and read its fix list.
   Not in a git repo: say so in the batch, and skip only steps 5 and 6 of the table, by name.
2. **Draft every decision** the whole flow needs, from the fix list and the evidence, before asking anything; the table says what each step closes and how:

   | Step | Gaps it closes | Decisions to draft for the batch | How |
   | --- | --- | --- | --- |
   | 1. Install | Hephaestus plugin missing, the legacy plugin id `agent-skills@quocld` (alone, or next to `hephaestus@quocld`: installed twice, or only a stale `enabledPlugins` key left), skills not installed, legacy links, name clashes | Install yes or no; replace `agent-skills@quocld` with `hephaestus@quocld`, yes or no (default yes); per `name clash` row: keep theirs and fork ours as `hx-<name>` (the default), switch to ours, or merge; per `duplicate copy` row: remove the extra copy | The fix command the script prints: for the legacy id `/plugin uninstall agent-skills@quocld`, then `/plugin install hephaestus@quocld` if it is not there yet (`/plugin enable hephaestus@quocld` first when it is only disabled), and the project's `.claude/settings.json` `enabledPlugins` key renamed in step 5's PR/MR (the stale key row, pending once that PR/MR holds it); a legacy install also runs `migrate-to-plugin.py` after its settings entries are gone; a clash in the project is settled in step 5's PR/MR (a fork in `.claude/skills/hx-<name>/`, or theirs deleted for a switch), one in `~/.claude/skills` here, and the report says what differs |
   | 2. Hooks | Hook not registered, or registered twice | Per gate that runs twice: delete its legacy `agent-skills-hooks` entry from `~/.claude/settings.json`, yes or no | Delete only that entry, then run the plugin's `hooks/test.sh` |
   | 3. Secrets | `This machine (every project)` rows: a plaintext secret in the global settings or a user MCP server, backups that hold it | Nothing to ask: always waiting on you | Name the file and the key, say that global env reaches every session of every project, so it is this machine's risk and not a need of this project, say whether this project references the key, and give the row's fix (not referenced: remove from the global settings and rotate; referenced: move to this project's `.agents/secrets.env` or `op://` and rotate); never read, echo, move or delete it or its backups yourself |
   | 4. Tools and logins | CLI missing, `gh` not logged in, Jira access, browser tool, Better Stack MCP | Which CLIs to install | The install command from the row; logins and MCP sign-ins are waiting on you, as `! <command>` or `/mcp` |
   | 5. Project | No project AGENTS.md or project-init block, CLAUDE.md import, integration branch not recorded (or only legacy), `TODO(owner)` | Every `project-init` section 2 question, starting with which branch PRs go into (your guess shown, even when `origin/dev` exists), then the tracker, test personas, feature-status opt-in | `project-init` with the batch's answers, plus step 1's project-side clash changes; the branch becomes `integrationBranch` and this step's own PR targets it |
   | 6. Environments | No registry or no environment in it, prod policy, version command, unresolved secrets, `logs` rename, `secrets.env` not gitignored | Which environments exist (local or dev, staging, prod, any other), each with its URL and branch, drafted per `environments` section 10 step 1, an existing env doc such as `.claude/environments.local.md` included; SSH aliases; test account roles and logins; run the `version` and `verify` probe on prod once, yes or no (default no) | `environments` section 10 with the batch's answers; a standard environment the project does not have goes in `absentEnvironments`; it creates the gitignored `.agents/secrets.env` with empty values, which the user fills (waiting on you) |
   | 7. Optional | Everything in the optional list | Which ones the user wants | Only those |

   An integration branch or environment list not recorded in `.agents/environments.json` is always in the batch, whatever else the page shows.
3. **Ask once**: one message, every decision numbered with your drafted answer, so the user only corrects what is wrong (`ask-or-decide`); a short "ok" takes every draft.
   The same message lists what will be waiting on the user (secrets to move and rotate, logins, `secrets.env` names to fill), so they can start while you work.
   A secret in the global settings is listed as a machine item that every project sees, never as something this project needs.
   Never ask for a secret value; drafts keep prod at its defaults, and a looser prod setting needs the user's explicit words.
   A fact the user does not know yet is written as `TODO(<owner>)`; a change the user declined or did not answer is not made, and is listed at the end as declined.
4. **Do every step in the table's order without asking again**, skipping a step with no gap.
   Steps 5 and 6 hand the batch's answers to `project-init`, `environments` and `worktree-flow` section 0, which take them as already asked; they run in one worktree and end as one PR/MR into the integration branch, which also carries step 1's project-side clash changes; steps 1 to 4 change only the user's machine.
   Ask again only when a step turns up a decision the batch could not foresee and only the user can make, all such decisions in one message.
   A clash the user kept (ours forked as `hx-<name>`) is their recorded choice, not a gap: the script shows it as settled once the fork exists, `pending` while it is in the setup PR/MR.
   A step only the user can finish is marked waiting on you, and the flow goes on.
5. **Show progress**: after each step, rerun the script with `--open` and say in one line what moved.
   A gap that stays after its step was done is a finding: say why (`root-cause`), do not loop on it.
6. **Finish**: rerun the script with `--open` one last time.
   The flow is done only when core readiness is 100% except items only the user can do (moving or rotating a secret, a login or MCP sign-in, filling `.agents/secrets.env`, merging the setup PR/MR, which shows as `pending` rows) and changes the user declined in the batch.
   Any other core gap left is either a step not done (do it, once) or a finding per step 5; name it as such, never loop.
   Report the core and optional readiness, what changed, the PR/MR links, a "Waiting on you" list and a "Declined" list, each item with the exact command that does it later.
   Then name every core gap still in the final fix list next to its line in one of those lists, so the user sees nothing else is left.

## 4. Changing the page

| Change | Where |
| --- | --- |
| A new skill in the repo | `assets/lifecycle.json`: its `tier` (core or optional), lifecycle `events`, task-path steps in `path` (setup, prompt, gather, act, verify, retry, response, remember), `when`; and the pillar(s) it serves in `assets/pillars.json` |
| A skill that runs a whole workflow end to end and orchestrates other skills | `"ultimate": true` on it in `assets/lifecycle.json`; every page then draws its name in the animated gradient |
| A new or changed hook | Registered in `hooks/hooks.json`; its one-line "Does" in the README hooks table, which the Hooks wired table reads; and the hooks line of the Quality Gates pillar in `assets/pillars.json` |
| A new eval, CI check, or verify-loop rule | Evals and CI: `covered_by` of the Evaluation or Quality Gates pillar in `assets/pillars.json`; gates, rules, and the retry label: `verify_loop` in `assets/lifecycle.json` |
| A gap closed or found in one of the eight components | `gaps` of that pillar in `assets/pillars.json` |
| A new check | One collector per section in `scripts/harness_map.py`; a CLI goes in `TOOLS`; a new section also needs `DESCS` and an icon in `scripts/page.py`; a check of the project-init block or a registry probe goes in `project-init`'s `scripts/doctor.py` instead |
| A new page on the public docs site | A repo file (license, policy, guide) goes in `REPO_PAGES` in `scripts/harness_map.py`, which renders it, adds it to the footer and the sitemap; any other page goes through `emit` or `doc_page` in `write_docs_site`, so it gets the SEO head, breadcrumbs and footer |
| Look and feel | `assets/template.html` only; the page renders through `render_page` in `scripts/page.py`; the Docs tab body comes from `scripts/harness_docs.py` |

A core item is one every session depends on; optional only matters for some skills, stacks or habits (`tier_of` in `harness_map.py`).
Keep pages self-contained (inline CSS and JS, Google Fonts with system fallbacks) and every color on the `:root` tokens, which follow the SpecsGraph design system v2.
