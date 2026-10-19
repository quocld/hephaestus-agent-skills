---
name: project-init
description: >
  Use when starting work in a repo whose AGENTS.md has no project-init block, when skills keep asking for the same project facts, or when asked "init dự án", "setup agent cho repo", "khởi tạo config cho skills", "kiểm tra setup", "doctor", or when a path or command in that block looks stale ("AGENTS.md lỗi thời", "lệnh trong AGENTS.md không chạy").
user-invocable: true
---

# project-init

The other skills assume facts about the project: which branch PRs go into, how to run the tests, where the spec lives, which environments exist.
This skill writes those facts down once, in the places every agent already reads, so no session has to rediscover or guess them.
It is safe to re-run: it updates its own blocks, fills gaps, and reports drift.
On a re-run or when asked for "doctor", start with section 4 and rediscover only what it flags.

## 0. Work like any other task

Run this in its own worktree and finish with a PR/MR into the integration branch (`worktree-flow`).
Read-only re-checks ("doctor") need no worktree.

## 1. Discover before asking

Read the places in this table, not the whole tree, and draft every answer from evidence; record where each one came from.

| Fact | Where to look |
| --- | --- |
| Integration branch (recorded as the `branch` of the registry's `dev` environment, which `worktree-flow` reads) | `git ls-remote --heads origin`, CI triggers, branch names in `git log --merges` |
| Ticket prefix and tracker | Branch names and commit subjects (`WEST-123`), PR templates, links in README |
| PR/MR platform | `git remote get-url origin` (GitHub or GitLab) |
| Package manager and monorepo | Lockfile, `pnpm-workspace.yaml`, `turbo.json`, `nx.json` |
| Stack per app or package | `package.json` dependencies (`next`, `react`, `@nestjs/core`, `@supabase/*`), `vercel.json`/`vercel.ts`, `supabase/`; the signals table in `feature-build` step 1b |
| Commands: install, dev, build, typecheck, lint, test, E2E | `package.json` scripts per package, `Makefile`, CI workflow steps |
| Sources of truth | `openspec/`, `docs/`, spec or PRD files, decision log, API contracts (OpenAPI, shared schema packages), design links (Figma) |
| E2E setup | `playwright.config.*`, existing personas, storage state files, seed scripts, report folders |
| Frontend conventions | Shared UI folder, error-parsing helper, form library |
| Deploy targets | Facts listed in the `environments` skill's create section |
| Logger and log shipping (`logging-standard`, `betterstack-logs` section 2) | Logger package and its tenant field (`pino`, `@logtail/*` in `package.json`, a shared `logger` package), Vector or collector configs, Vercel or Supabase log drains |
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

- Branches: PRs/MRs go into the integration branch from `worktree-flow` section 0; staging and prod branches only on explicit request.
- Tracker: Jira project `WEST`; branch and commit ids look like `WEST-123`. PR/MR platform: GitLab (`glab`).
- Stack: Next.js App Router in `apps/web` (docs for the installed version in `apps/web/node_modules/next/dist/docs/`), NestJS in `apps/api`, Supabase; before using a framework API, read the docs of the installed version (`feature-build` tech files).
- Commands (repo root): install `pnpm install --frozen-lockfile`; dev `pnpm dev`; typecheck `pnpm typecheck`; lint `pnpm lint`; test `pnpm test`; E2E `pnpm e2e`.
- Sources of truth, in priority order: decision log `docs/decisions.md` > OpenSpec `openspec/specs/` > Figma (link) > existing code.
- API contract: `packages/contracts/`.
- E2E: personas `admin`, `member` with storage states in `e2e/.auth/` (gitignored); evidence in `e2e/reports/`.
- Flow traces: `docs/flow-traces/`.
- Project checks: `.agents/checks/` (`verify-loop` section 4).
- Frontend: shared UI in `packages/ui/`; errors parsed only by `lib/api-error.ts`.
- Environments: `.agents/environments.json` (see the `environments` skill).
- Logging: logger `packages/logger/` (`logging-standard`); tenant field is organization_id (logging-standard alias); log sources in the registry (`betterstack-logs`).
<!-- project-init:end -->
```

Keep it under 20 lines: facts only, each pointing at the file that owns the detail.
The Stack line names no version numbers, which go stale; when `next dev` already wrote its own `nextjs-agent-rules` block, leave that block alone and drop the Next.js docs path from the Stack line.
Leave out what the code shows on its own; if a fact is only needed in one rare situation, it belongs in a project skill instead (`knowledge-placement`).

### 3b. Environment registry

Create or update `.agents/environments.json` by following the `environments` skill's create section (gitignore entries, secrets example file, validation).

### 3c. Version endpoint

Every deployed HTTP service needs the version endpoint from the `environments` skill's `references/version-endpoint.md`.
Implement it in the project's own stack, prove it locally (build with a known SHA, the endpoint returns it, it works logged out), and point each environment's `version` command at it.

### 3d. Feature status

Offer to opt the repo in to `feature-status` when several agents or people work it in parallel.
On yes: commit an empty `docs/status/.gitkeep` and add `- Feature status: one file per feature in docs/status/, edited only through the feature-status skill.` to the block.

### 3e. Test personas

For each persona the E2E skills need: an account per environment in the registry (secret references only), a seed script or documented way to create it on dev, and a saved-session setup so tests do not log in through the UI every run.

## 4. Doctor: check every tool the skills call and the block's drift

```bash
python3 <this skill>/scripts/doctor.py    # from the project root; --help lists every probe and flag
```

The script runs every doctor check and prints one table: check, status (`OK` / `MISSING` / `FAILING` / `DRIFT` / `SKIP`), detail, and fix.
Its machine rows (plugin, hooks, CLIs, logins, MCP) come from the `harness-map` collectors, so each check has one owner.
Run it yourself, never through a subagent, and rerun it only to confirm a fix.

- It never writes a project file, never prints a secret value, and never runs one of the project's own build, test, install, migrate, or server commands; the tool probes it runs are listed in `--help`.
- A row whose precondition is absent is `SKIP`; so is a `version` on a `confirm-each-step` environment, with the command to run once the user says yes.
- When the block has a Logging line, run it in the same pass with `--logger-test '<the logger's own test command>'`, or `--logger-entry <built logger entry>` when there is no test; that is the one exception to the rule above, runs with the Better Stack variables unset, and without either flag the row is `DRIFT`, not a finished doctor.
- `--no-probe` skips the tool probes and the `version` commands when the user wants it offline; their rows become `SKIP`.

Fix cheap drift in this skill's own block and files through the normal flow of section 0 (worktree, PR/MR into `<int>`):

- A block path the table shows as renamed, or a script that now has another name with the same body in `package.json`: update the block.
- A fact the user just answered in place of a `TODO(<owner>)`: replace the TODO.
- Missing gitignore lines or example files from the `environments` skill's create section: add them.

Report every other row with its fix command, using `! <command>` for logins.

## 5. Report

What was found and where, what was written, the doctor table (it already lists every open `TODO(<owner>)`), and the PR/MR URL when one was opened.
