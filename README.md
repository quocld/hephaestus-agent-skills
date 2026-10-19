<p align="center">
  <img src="assets/icon.png" alt="Hephaestus Skills logo: a hammer striking hot metal on an anvil" width="160" height="160">
</p>

<h1 align="center">Hephaestus Skills</h1>

<p align="center">
  <strong>A Claude Code plugin that forges a disciplined AI coding agent:</strong><br>
  global AGENTS.md rules, 25 agent skills for the whole dev loop, and safety hooks.
</p>

<p align="center">
  <a href="https://hephaestus-skills-docs.vercel.app"><strong>Docs</strong></a> ·
  <a href="#install">Install</a> ·
  <a href="#skills">Skills</a> ·
  <a href="#hooks">Hooks</a> ·
  <a href="#references">References</a>
</p>

---

**Hephaestus Skills** is a [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) plugin and [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) collection for teams that run several AI coding agents in parallel on the same repo.
It gives every session the same rules (`AGENTS.md`), one git worktree per task, root-cause debugging, verification gates, E2E evidence, security and code review, environment and log access, and hooks that stop risky actions before they happen.
The `AGENTS.md` and skills also work in any harness that reads them (Codex, Cursor, OpenCode).

**Documentation:** [hephaestus-skills-docs.vercel.app](https://hephaestus-skills-docs.vercel.app) shows the eight components of an agent harness, where every skill and hook acts in the Claude Code lifecycle, the task path, the verification loop, and each skill in full.
It is built from this repo with `python3 skills/harness-map/scripts/harness_map.py --docs-only <dir> --site-url <url>` and deployed per `.agents/environments.json` (environment `docs`).

## Install

In Claude Code:

```text
/plugin marketplace add quocld/agent-skills
/plugin install agent-skills@quocld
```

Restart the session, then ask Claude to **"finish my harness setup"**: the `harness-map` skill checks tools, logins and project setup and asks for what is missing.

Update:

```sh
claude plugin marketplace update quocld && claude plugin update agent-skills@quocld
```

Try a local checkout for one session: `claude --plugin-dir <path-to-checkout>`.
Coming from the old `install.sh` symlinks: run `python3 migrate-to-plugin.py` (`--dry-run` to preview), then `hooks/test.sh`.

## Skills

Skills are namespaced, for example `/agent-skills:worktree-flow`; Claude also picks them up on its own from their descriptions.

| Skill | Use it for | Needs |
| --- | --- | --- |
| `worktree-flow` | One worktree + branch per task for parallel agents; done = PR/MR into `dev`; staging/prod only on explicit word. | `gh` or `glab` |
| `feature-build` | Implement a feature or user story end to end: gaps, exploration, design options, verify, PR. Lean per-technology notes for Next.js, React, Vercel, Supabase, NestJS. | - |
| `root-cause` | Find the cause before fixing: failing layer, backward trace, 3-failed-fixes stop, flaky tests, polluter bisection. | - |
| `verify-loop` | One ordered chain of gates before any PR (toolchain, project checks, proof tests, requirements, review, E2E) with a PASS/FAIL table. | - |
| `fresh-review` | Independent review by a fresh subagent before a PR, looped until clean. | - |
| `e2e-verify` | Strict "verified" definition for acceptance criteria in a real browser, with evidence files. | Playwright MCP or chrome-devtools-axi |
| `security-pass` | Per-PR security pass for Next.js/Supabase multi-tenant apps: RLS, service role, route auth, tenant isolation. | - |
| `flow-trace` | Trace one business lifecycle end to end: one-way-door states, unhandled events, broken idempotency. | - |
| `bug-triage` | Bug/QA ticket loop: classify, depth by risk, prove the test, verify the deploy, hand back. | Jira access |
| `jira-bug-hunter` | Work assigned Jira bugs one at a time: fix, review, merge into `dev`, verify with video, daily HTML demo report. | Jira, Playwright MCP, `environments` |
| `fe-guardrails` | React/Next rules for loading, empty and error states, form errors, and copy. | - |
| `environments` | Per-project registry of dev/staging/prod: servers, deploy commands, test accounts; prod confirmed step by step. | `.agents/environments.json` |
| `server-touch` | Docker Compose ops over SSH on a shared host: scoped commands, deploy, logs, `.env`, psql, rollback. | `environments` |
| `logging-standard` | Structured log contract: fields, levels, correlation, errors, redaction, volume, tests. | - |
| `betterstack-logs` | Better Stack log setup per project and reading an environment's logs while debugging. | Better Stack MCP |
| `harness-map` | One HTML page: setup dashboard, ranked fix list, and a lifecycle map of every skill and hook. | python3 |
| `project-init` | Set up a repo for this plugin: AGENTS.md block, environment registry, version endpoint, tool doctor. | - |
| `ask-or-decide` | When to decide autonomously vs. ask, and how to ask. | - |
| `knowledge-placement` | Where a new rule or fact belongs; keeps AGENTS.md lean; how to write a skill. | - |
| `stow` | Save durable knowledge from a session before a reset or break. | - |
| `vision` | Draft and stress-test a project VISION.md. | node |
| `no-mistakes` | Push through an AI review/test/lint gate before a clean PR. | `no-mistakes` CLI |
| `gnhf` | Overnight autonomous loop of small committed changes. | `gnhf` CLI |
| `chrome-devtools-axi` | Token-efficient browser automation for E2E checks. | node |
| `axi` | Design standards for CLIs meant for agents. | - |

## Hooks

| Hook | Does |
| --- | --- |
| `session-start.py` | Loads `AGENTS.md` into every session and points to `OPINIONS.md`. |
| `no-em-dash.py` | Blocks writes that contain an em dash. |
| `guard-protected-branches.py` | Asks before (or denies, in no-prompt modes) pushes and merges to `main`, `staging`, `prod` and PR/MR merges. |

Details and tests: [`hooks/README.md`](hooks/README.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Global instructions for every agent session (single source of truth); `CLAUDE.md` just imports it. |
| `OPINIONS.md` | Engineering and product viewpoints, read by agents when relevant. |
| `skills/` | One folder per skill (`SKILL.md` plus scripts and references). |
| `hooks/` | Gate hooks, registered by `hooks/hooks.json`. |
| `.claude-plugin/` | Plugin manifest and the marketplace that serves it from this repo. |
| `assets/` | Logo (`icon.svg`, `icon.png`). |
| `SOURCES.md`, `LICENSES/` | Upstream sources and their licenses. |

## Adding a skill

Follow `skills/knowledge-placement` first, create `skills/<name>/SKILL.md` with `name` and `description` frontmatter, and place it in `skills/harness-map/assets/lifecycle.json`.
`.claude-plugin/plugin.json` has no `version` on purpose: the commit SHA is the version, so every pushed commit reaches users through `claude plugin update`.

## References

- [Claude Code plugins](https://docs.claude.com/en/docs/claude-code/plugins) and [plugin marketplaces](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces)
- [Agent Skills overview](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) and [Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks)
- [AGENTS.md](https://agents.md), the open format for agent instructions
- Upstream work this builds on: [kunchenguid/dotfiles](https://github.com/kunchenguid/dotfiles), [obra/superpowers](https://github.com/obra/superpowers), [anthropics/skills](https://github.com/anthropics/skills), [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official); full list with licenses in [`SOURCES.md`](SOURCES.md)

## Author

**Ryan Le** ([@quocld](https://github.com/quocld))
