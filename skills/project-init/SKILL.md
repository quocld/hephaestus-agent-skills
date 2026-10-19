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

### 3d. Test personas

For each persona the E2E skills need: an account per environment in the registry (secret references only), a seed script or documented way to create it on dev, and a saved-session setup so tests do not log in through the UI every run.

## 4. Doctor: check every tool the skills call and the block's drift

Run every check yourself in one pass, batching the commands into as few shell calls as you can, then print one table: check, status (`OK` / `MISSING` / `FAILING` / `DRIFT` / `SKIP`), and the fix.
Never spawn subagents for it, and never re-run a check that already passed in this session.
A row whose precondition is absent (no registry, no `op://` reference, no GitLab remote) is `SKIP`, not run.

| Check | Command |
| --- | --- |
| agent-skills plugin installed | `claude plugin list` shows `agent-skills@agent-skills` enabled; the skills, hooks and global rules all come with it |
| Hooks registered and working | `bash <agent-skills plugin or checkout>/hooks/test.sh` passes: it checks the plugin's `hooks.json` mounts every gate and runs the deny and allow probes |
| Git platform CLI logged in | `gh auth status` or `glab auth status` |
| Integration branch exists | `git ls-remote --exit-code --heads origin refs/heads/<int>`, with `<int>` from `worktree-flow` section 0 |
| Node and package manager | `node --version`, `pnpm --version` (or the repo's manager) |
| `jq` (version commands) | `jq --version` |
| Registry valid | The `environments` skill's validation command |
| Secrets resolve | Every `env:` name has a value in the shell or `.agents/secrets.env` (check presence, never print); `op whoami` when `op://` references exist |
| SSH aliases | For every `access.ssh`, `ssh -G <alias> 2>/dev/null \| awk '$1=="hostname"{print $2}'` prints a host other than the lowercased alias (`ssh -G` exits 0 and echoes the name back when no `Host` entry matches) |
| Platform CLIs used by the registry | `vercel whoami`, `supabase --version`, `docker compose version` |
| Version endpoints | Each environment's `version` prints a 40-character SHA (asks first on `confirm-each-step` environments) |
| Browser tool for E2E | The first tool in the `e2e-verify` order is available: Playwright MCP, otherwise `npx -y --prefer-offline chrome-devtools-axi --help` runs |
| Better Stack MCP connected | `claude mcp list 2>/dev/null \| grep -E '^(plugin:betterstack:)?betterstack(-ro)?: .*Connected'` prints a line; a `Needs authentication` line means run `/mcp` and sign in (`betterstack-logs` section 1) |
| Log sources registered | `jq -r '.environments \| to_entries[] \| select(.value.url // "" \| test("//localhost") \| not) \| .key as $e \| .value.services[]? \| select(.type != "local") \| if (.logs \| type) == "string" then "\($e)/\(.name): old string logs, rename to logsCommand" elif (.logs.source // "") == "" then "\($e)/\(.name)" else empty end' .agents/environments.json` prints nothing; each printed service lacks `logs.source` or needs the `environments` section 1 rename |
| Logger contract | The project's logger test passes; no such test: log one line with the project's logger, Better Stack env unset so nothing ships, and check the keys, e.g. `out=$(env -u BETTER_STACK_SOURCE_TOKEN -u BETTER_STACK_INGESTING_HOST NODE_ENV=production node -e "import('<built logger entry>').then((m) => m.createLogger({ service: 'doctor' }).info('probe'))" \| head -1); [ -n "$out" ] && printf '%s\n' "$out" \| jq -r 'keys as $k \| $ARGS.positional - $k \| if . == [] then "OK" else "MISSING \(join(" "))" end' --args <every key logging-standard section 1 requires on every line> \|\| echo FAILING` prints `OK`; a crash, no output, or a non-JSON line prints `FAILING` |
| Markers intact | `AGENTS.md` has exactly one `project-init:start` and one `project-init:end` |
| Block paths exist | Every repo path the block names exists (`test -e <path>`); a gitignored path such as a storage state folder counts as `OK` when `git check-ignore -q <path>` succeeds, with a trailing slash on folders (`e2e/.auth/`) so dir-only patterns match |
| Block commands resolve | Each listed command, checked with the cheap probe below, never by running it |
| Project checks valid | `python3 <verify-loop skill>/scripts/checks.py list` exits 0; `SKIP` when `.agents/checks/` does not exist |
| Open `TODO(<owner>)` | `grep -n 'TODO(' AGENTS.md .agents/environments.json`, one row per hit |

Print the block once with `sed -n '/project-init:start/,/project-init:end/p' AGENTS.md` and take its paths and commands from that output.
Cheap probes for block commands:

- Package script (`pnpm lint`, `npm run e2e`, `pnpm --filter web test`): `jq -e --arg s <script> '.scripts[$s]' <package dir>/package.json` plus `command -v <manager>`.
- Package manager built-in (`pnpm install --frozen-lockfile`): `command -v <manager>` and the lockfile exists.
- Make target: `make -n <target>`.
- Any other binary: `command -v <bin>`, then `<bin> --version` or `<bin> --help`.
- Never run a command that builds, tests, installs, migrates, starts a server, or writes, unless the user asks for that run; the logger contract row is the one exception, and runs only the logger's own test file or its one-line probe with the Better Stack variables unset.

The doctor itself never writes.
Fix cheap drift in this skill's own block and files through the normal flow of section 0 (worktree, PR/MR into `<int>`):

- A path that was renamed (`git log -1 --format= --name-status -M --full-diff -- <old path>` shows an `R` line naming the new one): update the block.
- A script that now exists under another name or package with the same body in `package.json`: update the block.
- A fact the user just answered in place of a `TODO(<owner>)`: replace the TODO.
- Missing gitignore lines or example files from the `environments` skill's create section: add them.

Report everything else with the exact command the user should run, using `! <command>` for logins.

## 5. Report

What was found and where, what was written, the doctor table (it already lists every open `TODO(<owner>)`), and the PR/MR URL when one was opened.
