# agent-skills

My agent setup: global instructions, opinions, dev skills and gate hooks, packaged as a Claude Code plugin (and readable by any harness that reads AGENTS.md).

## Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Global instructions for every agent session (single source of truth). |
| `CLAUDE.md` | Just `@AGENTS.md`. |
| `OPINIONS.md` | My engineering and product viewpoints, read by agents when relevant. |
| `skills/` | Skills, one folder each. |
| `reference/` | Example material for writing my own files. |
| `SOURCES.md`, `LICENSES/` | Upstream sources and their licenses. |
| `hooks/` | Claude Code hooks that enforce `AGENTS.md` rules and load it at session start; `hooks/hooks.json` registers them (see `hooks/README.md`). |
| `.claude-plugin/` | Plugin manifest and the marketplace that serves it from this repo. |
| `migrate-to-plugin.py` | Removes the links the old `install.sh` made, so nothing loads twice. |

## Skills

| Skill | Use it for | Needs |
| --- | --- | --- |
| `verify-loop` | One ordered chain of gates before any PR (toolchain, project checks, proof tests, requirements, review, E2E) with a PASS/FAIL table; per-project checks in `.agents/checks/`; optional CI jobs. | - |
| `fresh-review` | Independent review by a fresh subagent before a PR, looped until clean. | - |
| `harness-map` | One HTML page with a Dashboard tab (core vs optional, eight-component wheel, project and environments, ranked fix list) and a Docs tab (lifecycle map of every skill and hook, task path). | python3 |
| `project-init` | Set up a repo for this skill set: AGENTS.md agent setup block, environment registry, version endpoint, tool doctor. | - |
| `worktree-flow` | One worktree + branch per task for parallel agents; done = PR/MR into `dev`; staging/prod only on explicit word. | `gh` or `glab` |
| `ask-or-decide` | When to decide autonomously vs. ask, and how to ask. | - |
| `knowledge-placement` | Where a new rule or fact belongs; keeps AGENTS.md lean. | - |
| `flow-trace` | Trace one business lifecycle end-to-end to find one-way-door states, unhandled events, broken idempotency. | - |
| `e2e-verify` | Strict "verified" definition for ACs in a real browser, with PASS/FAIL evidence files. | Playwright MCP or chrome-devtools-axi |
| `root-cause` | Find the cause before fixing: failing layer, backward trace, 3-failed-fixes stop, flaky tests, polluter bisection, tests that can fail. | - |
| `feature-build` | Implement a feature or user story end to end inside a worktree: gaps, small exploration, design options, verify, PR. Loads lean per-technology files from `tech/` (Next.js, React, Vercel, Supabase, NestJS) that point at the installed version's docs. | - |
| `security-pass` | Per-PR security pass for Next.js/Supabase multi-tenant apps: RLS, service role, auth on routes, tenant-isolation proof. | - |
| `bug-triage` | Bug/QA ticket loop: read all, classify, depth by risk triggers, prove the test, verify deploy, hand back. | Jira access (MCP or API) |
| `jira-bug-hunter` | Work through my assigned Jira bugs one at a time in the main session (pick moves the ticket to in progress, asks me when needed): fix, review, merge into `dev`, verify on dev with video, and add each result to one shared HTML demo report grouped by day. | Jira access, Playwright MCP, `environments` registry |
| `fe-guardrails` | React/Next rules for loading, empty, error states, form errors, and copy. | - |
| `environments` | Per-project registry of dev/staging/prod: servers, deploy commands (VPS, Vercel, Supabase), test accounts, rules, version status; prod confirmed step by step. | `.agents/environments.json` in the project |
| `server-touch` | Docker Compose ops over SSH on a possibly shared host: scoped commands, deploy script, logs, .env, psql, rollback. | `environments` registry |
| `logging-standard` | Structured log contract for code that logs and for loggers: fields, levels, correlation, errors, redaction, volume, tests. | - |
| `betterstack-logs` | Better Stack log setup per project (MCP, shipping path, sources) and reading an environment's logs while debugging. | Better Stack MCP (official plugin or `claude mcp add`), `environments` registry |
| `stow` | Save durable knowledge from a session to disk before a reset or break. | - |
| `vision` | Draft and stress-test a project VISION.md. | node (`npx lavish-axi`) |
| `no-mistakes` | Push through an AI review/test/lint gate before a clean PR. | `no-mistakes` CLI |
| `gnhf` | Overnight autonomous loop of small committed changes. | `gnhf` CLI |
| `chrome-devtools-axi` | Token-efficient browser automation for E2E checks. | node (`npx chrome-devtools-axi`) |
| `axi` | Design standards when building a CLI meant for agents. | - |

## Install

In Claude Code (the repo is private, so your GitHub login needs read access to it):

```text
/plugin marketplace add quocld/agent-skills
/plugin install agent-skills@quocld
```

That brings every skill (namespaced, such as `/agent-skills:harness-map`), the gate hooks, and a `SessionStart` hook that loads `AGENTS.md` into every session and names the path of `OPINIONS.md`; no `~/.claude` file is written.
Update with `claude plugin marketplace update quocld` and `claude plugin update agent-skills@quocld`, then restart the session.
Then ask Claude to "finish my harness setup": `harness-map` checks the rest (tools, logins, project setup) and asks you for what it needs.

Coming from the old `install.sh` links: run `python3 migrate-to-plugin.py` (add `--dry-run` to preview).
It removes only symlinks into this repo, and keeps `~/.claude/agent-skills-hooks` until you delete the two `agent-skills-hooks` entries from `hooks.PreToolUse` in `~/.claude/settings.json`, since the plugin registers the same hooks.
Run `hooks/test.sh` afterwards.

Working on the skills themselves: edits reach your sessions after you commit, push, and update the marketplace; for a quick local try, `claude --plugin-dir <this checkout>` loads the working tree for one session.

## Adding a skill

Follow `skills/knowledge-placement` first, then create `skills/<name>/SKILL.md` with `name` and `description` frontmatter, and place it in `skills/harness-map/assets/lifecycle.json`.
`.claude-plugin/plugin.json` has no `version` on purpose: the commit SHA is the version, so every pushed commit reaches users through `claude plugin update`.
