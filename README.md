# agent-skills

My agent setup: global instructions, opinions, and dev skills for Claude Code (and any harness that reads AGENTS.md).

## Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Global instructions for every agent session (single source of truth). |
| `CLAUDE.md` | Just `@AGENTS.md`. |
| `OPINIONS.md` | My engineering and product viewpoints, read by agents when relevant. |
| `skills/` | Skills, one folder each. |
| `reference/` | Example material for writing my own files. |
| `SOURCES.md`, `LICENSES/` | Upstream sources and their licenses. |
| `hooks/` | Claude Code hooks that enforce `AGENTS.md` rules (see `hooks/README.md`). |
| `install.sh` | Symlinks everything into `~/.claude` and `~`. |

## Skills

| Skill | Use it for | Needs |
| --- | --- | --- |
| `verify-loop` | One ordered chain of gates before any PR (toolchain, project checks, proof tests, requirements, review, E2E) with a PASS/FAIL table; per-project checks in `.agents/checks/`; optional CI jobs. | - |
| `fresh-review` | Independent review by a fresh subagent before a PR, looped until clean. | - |
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
| `jira-bug-hunter` | Work through my assigned Jira bugs one by one (up to 3 workers): fix, review, merge into `dev`, verify on dev with video, and add each result to one shared HTML demo report grouped by day. | Jira access, Playwright MCP, `environments` registry |
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

```sh
git clone https://github.com/quocld/agent-skills.git ~/agent-skills
~/agent-skills/install.sh
```

Links `~/.claude/CLAUDE.md` -> `AGENTS.md`, `~/OPINIONS.md` -> `OPINIONS.md`, `~/.claude/agent-skills-hooks` -> `hooks/`, and every skill into `~/.claude/skills/`.
Existing files that are not symlinks move to `~/.claude/backups/agent-skills-<timestamp>/`, never deleted.
The hooks take effect only after you merge their entries from `hooks/README.md` into `hooks.PreToolUse` in `~/.claude/settings.json`.
Then run `hooks/test.sh`, which exercises both hooks and checks that the settings register them.

## Adding a skill

Follow `skills/knowledge-placement` first, then create `skills/<name>/SKILL.md` with `name` and `description` frontmatter and re-run `install.sh`.
