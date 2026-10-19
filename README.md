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
| `install.sh` | Symlinks everything into `~/.claude` and `~`. |

## Skills

| Skill | Use it for | Needs |
| --- | --- | --- |
| `fresh-review` | Independent review by a fresh subagent before a PR, looped until clean. | - |
| `ask-or-decide` | When to decide autonomously vs. ask, and how to ask. | - |
| `knowledge-placement` | Where a new rule or fact belongs; keeps AGENTS.md lean. | - |
| `flow-trace` | Trace one business lifecycle end-to-end to find one-way-door states, unhandled events, broken idempotency. | - |
| `e2e-verify` | Strict "verified" definition for ACs in a real browser, with PASS/FAIL evidence files. | Playwright MCP or chrome-devtools-axi |
| `bug-triage` | Bug/QA ticket loop: read all, classify, depth by risk triggers, prove the test, verify deploy, hand back. | Jira access (MCP or API) |
| `fe-guardrails` | React/Next rules for loading, empty, error states, form errors, and copy. | - |
| `environments` | Per-project registry of dev/staging/prod: servers, deploy commands (VPS, Vercel, Supabase), test accounts, rules; prod confirmed step by step. | `.agents/environments.json` in the project |
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

Links `~/.claude/CLAUDE.md` -> `AGENTS.md`, `~/OPINIONS.md` -> `OPINIONS.md`, and every skill into `~/.claude/skills/`.
Existing files are backed up as `*.bak-<timestamp>`, never deleted.

## Adding a skill

Follow `skills/knowledge-placement` first, then create `skills/<name>/SKILL.md` with `name` and `description` frontmatter and re-run `install.sh`.
