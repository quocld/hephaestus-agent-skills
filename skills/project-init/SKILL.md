---
name: project-init
description: >
  Set up or re-check a project so the whole skill set works in it: fill the project's agent setup block in AGENTS.md (integration branch, tracker, commands, sources of truth, E2E personas), create the environment registry, add a version endpoint to every deployed service, and check that every tool the skills call is installed and logged in.
  Use when starting work in a new repo, when skills keep asking for the same project facts, or when asked "init dự án", "setup agent cho repo", "khởi tạo config cho skills", "kiểm tra setup", "doctor".
user-invocable: true
---

# project-init

The other skills assume facts about the project: which branch PRs go into, how to run the tests, where the spec lives, which environments exist.
This skill writes those facts down once, in the places every agent already reads, so no session has to rediscover or guess them.
It is safe to re-run: it updates its own blocks, fills gaps, and reports drift.

## 0. Work like any other task

Run this in its own worktree and finish with a PR/MR into the integration branch (`worktree-flow`).
Read-only re-checks ("doctor") need no worktree.

## 1. Discover before asking

Read the repo and draft every answer from evidence; record where each one came from.

| Fact | Where to look |
| --- | --- |
| Integration branch | `git ls-remote --heads origin`, CI triggers, branch names in `git log --merges` |
| Ticket prefix and tracker | Branch names and commit subjects (`WEST-123`), PR templates, links in README |
| PR/MR platform | `git remote get-url origin` (GitHub or GitLab) |
| Package manager and monorepo | Lockfile, `pnpm-workspace.yaml`, `turbo.json`, `nx.json` |
| Commands: install, dev, build, typecheck, lint, test, E2E | `package.json` scripts per package, `Makefile`, CI workflow steps |
| Sources of truth | `openspec/`, `docs/`, spec or PRD files, decision log, API contracts (OpenAPI, shared schema packages), design links (Figma) |
| E2E setup | `playwright.config.*`, existing personas, storage state files, seed scripts, report folders |
| Frontend conventions | Shared UI folder, error-parsing helper, form library |
| Deploy targets | Facts listed in the `environments` skill's create section |
| Existing agent files | `AGENTS.md`, `CLAUDE.md`, `.claude/skills/`, `.agents/` |

## 2. Ask only the gaps, in one batch

Ask once, with your drafted answers shown so the user only corrects them.
Typical gaps: the environment list and URLs, SSH aliases, test personas and their logins, the decision log location, rules such as deploy windows.
Anything the user does not know yet is written as `TODO(<owner>)` and reported, never invented.

## 3. Write the project's agent setup

### 3a. AGENTS.md block

Add or update one block in the project's `AGENTS.md`, between markers so re-runs replace only their own text.
Create `AGENTS.md` if missing, and a `CLAUDE.md` containing `@AGENTS.md` if Claude Code is used and that file is missing.
Never rewrite text outside the markers.

```markdown
<!-- project-init:start -->
## Agent setup

- Integration branch: `dev` (PRs/MRs go here; staging `staging`, prod `main` only on explicit request).
- Tracker: Jira project `WEST`; branch and commit ids look like `WEST-123`. PR/MR platform: GitLab (`glab`).
- Commands (repo root): install `pnpm install --frozen-lockfile`; dev `pnpm dev`; typecheck `pnpm typecheck`; lint `pnpm lint`; test `pnpm test`; E2E `pnpm e2e`.
- Sources of truth, in priority order: decision log `docs/decisions.md` > OpenSpec `openspec/specs/` > Figma (link) > existing code.
- API contract: `packages/contracts/`.
- E2E: personas `admin`, `member` with storage states in `e2e/.auth/` (gitignored); evidence in `e2e/reports/`.
- Flow traces: `docs/flow-traces/`.
- Frontend: shared UI in `packages/ui/`; errors parsed only by `lib/api-error.ts`.
- Environments: `.agents/environments.json` (see the `environments` skill).
<!-- project-init:end -->
```

Keep it under 20 lines: facts only, each pointing at the file that owns the detail.
Leave out what the code shows on its own; if a fact is only needed in one rare situation, it belongs in a project skill instead (`knowledge-placement`).

### 3b. Environment registry

Create or update `.agents/environments.json` by following the `environments` skill's create section (gitignore entries, secrets example file, validation).

### 3c. Version endpoint

Every deployed HTTP service needs the version endpoint from the `environments` skill's `references/version-endpoint.md`.
Implement it in the project's own stack, prove it locally (build with a known SHA, the endpoint returns it, it works logged out), and point each environment's `version` command at it.

### 3d. Test personas

For each persona the E2E skills need: an account per environment in the registry (secret references only), a seed script or documented way to create it on dev, and a saved-session setup so tests do not log in through the UI every run.

## 4. Doctor: check every tool the skills call

Run read-only checks and print one table: check, status (`OK` / `MISSING` / `FAILING`), and the fix.

| Check | Command |
| --- | --- |
| Global skills installed | Each skill folder of the agent-skills repo exists in `~/.claude/skills/` |
| Git platform CLI logged in | `gh auth status` or `glab auth status` |
| Integration branch exists | `git ls-remote --exit-code --heads origin refs/heads/<int>` |
| Node and package manager | `node --version`, `pnpm --version` (or the repo's manager) |
| `jq` (version commands) | `jq --version` |
| Registry valid | The `environments` skill's validation command |
| Secrets resolve | Every `env:` name has a value in the shell or `.agents/secrets.env` (check presence, never print); `op whoami` when `op://` references exist |
| SSH aliases | `ssh -G <alias>` resolves for every `access.ssh` |
| Platform CLIs used by the registry | `vercel whoami`, `supabase --version`, `docker compose version` |
| Version endpoints | Each environment's `version` prints a 40-character SHA (asks first on `confirm-each-step` environments) |
| Browser tool for E2E | Playwright MCP available, or `npx -y chrome-devtools-axi --help` runs |
| Markers intact | `AGENTS.md` has exactly one `project-init:start` and one `project-init:end` |

Fix what is safe and local (gitignore lines, missing example files); report the rest with the exact command the user should run, using `! <command>` for logins.

## 5. Report

What was found and where, what was written, the doctor table, every `TODO(<owner>)`, and the PR/MR URL.
