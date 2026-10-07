---
name: spec-driven-workflow-init
description: Use when bootstrapping (or retrofitting) a project to use the OpenSpec → BE → FE → verify → archive workflow with strict defer-discipline, honest tick legend, and capability-slice changes. Triggers when asked to "init workflow", "set up spec-driven flow", "add OpenSpec to this project", "make this repo follow VOCO's workflow", or similar. Works for greenfield repos AND existing codebases.
---

# Spec-driven workflow init

## Overview

Installs the workflow methodology proven on VOCO (1 capability slice = 1 OpenSpec change; Phase A decisions FIRST; defer needs owner; archive lifecycle real; build-plan derived). Produces a minimal, opinionated scaffold the team can build on. Skill is **idempotent** — safe to re-run; never overwrites without explicit confirm.

## When to use

- Greenfield repo, you want spec-driven from day 1.
- Existing repo where decisions get lost, PRs land without specs, "done" is ambiguous, defers sit untracked.
- Migrating from ad-hoc Notion/Linear plans into in-repo, version-controlled, agent-readable specs.

## When NOT to use

- Project is single-file scripts / one-off prototype.
- Team already has its own spec process they're happy with — skill is opinionated, will fight other conventions.
- Repo is in active emergency hotfix mode — finish the fire first.

## What you produce

```
<repo>/
├── CLAUDE.md                              # appended (never overwritten)
├── docs/
│   └── build-plan.md                      # derived dashboard
├── openspec/
│   ├── config.yaml                        # rules + module catalogue
│   ├── specs/                             # baseline of shipped capabilities
│   └── changes/
│       └── archive/                       # YYYY-MM-<id>/ folders
├── scripts/
│   ├── check-defer-owner.mjs              # pre-commit enforcement
│   └── check-buildplan-honest.mjs         # tick-vs-defer consistency
├── .githooks/pre-commit                   # wires the scripts
└── .claude/skills/implement-module/
    └── SKILL.md                           # project-specific loop (parameterized)
```

## The init flow

Follow exactly. Each step asks a question before writing; never assume.

### Step 1 — Detect repo state

```bash
ls openspec/ 2>/dev/null      # already initialized?
ls docs/ 2>/dev/null
cat package.json 2>/dev/null | head -20
git log --oneline -5 2>/dev/null
```

Classify: **greenfield** (no openspec, no specs anywhere) vs **brownfield** (existing code, possibly other spec system). Greenfield → proceed full scaffold. Brownfield → ask before touching CLAUDE.md / existing docs/.

### Step 2 — Gather customization inputs (AskUserQuestion)

Ask 3-4 questions in one batch:

1. **Project module/phase taxonomy** — how should slices be grouped?
   - `M1..M12` (VOCO style — explicit modules)
   - `<area>-<slice>` (e.g. `auth-signup`, `billing-invoice`)
   - `feature/<name>` (lighter, flat)
2. **Language for product docs** — English / Vietnamese / French / mix? Affects template strings only.
3. **Backend stack** — Supabase / Prisma / Drizzle / raw SQL / none. Determines whether to add the "BE via Supabase MCP" section or generalise.
4. **Defer enforcement strictness** — `block-commit` (pre-commit fails) / `warn-only` / `manual-review`.

### Step 3 — Install OpenSpec CLI

```bash
ls openspec/config.yaml || pnpm add -D @fission-ai/openspec
# OR npx @fission-ai/openspec@latest init
```

Verify with `pnpm exec openspec --version`. If repo uses npm/yarn/bun, substitute accordingly.

### Step 4 — Write `openspec/config.yaml`

Template lives at `templates/openspec-config.yaml` in this skill. Fill in:
- `context`: 2–4 lines about the project (stack, source-of-truth docs, conflict resolution).
- `rules.proposal/specs/tasks`: keep verbatim (proven).
- `modules`: derived from Step 2 Q1.

### Step 5 — Scaffold `docs/build-plan.md`

Template `templates/build-plan.md`. Includes:
- Legend (`[x]` = zero defer shipped; `[~]` = defer with owner; `[ ]` = not started).
- One row per module/area with `| id | sprint | change-id | Specs | BE | FE | Done | Notes |`.
- A footer block "Defer registry" — every defer item gets a `[ ]` line here OR a follow-up change id.

### Step 6 — Append to `CLAUDE.md`

**Brownfield: always append, never overwrite.** Insert a `## Spec-driven workflow` section pointing to `openspec/`, `docs/build-plan.md`, and the implement-module skill. Reference template `templates/claude-md-section.md`.

If `CLAUDE.md` doesn't exist, create it from `templates/claude-md.md`.

### Step 7 — Install enforcement scripts

Copy `templates/check-defer-owner.mjs` and `templates/check-buildplan-honest.mjs` into `scripts/`. They are dependency-free Node ESM scripts.

`check-defer-owner.mjs` greps every `openspec/changes/**/{proposal,tasks}.md`, parses `## Defer` / `## Deferred` lines, fails if any line lacks an arrow owner: `→ <change-id>` / `→ build-plan §...` / `→ <ticket-id>`.

`check-buildplan-honest.mjs` parses `docs/build-plan.md` rows; if a row is `[x]` Done but its change folder still has unchecked `[ ]` in Phase B or has Defer without owner, fails.

### Step 8 — Wire pre-commit hook

```bash
mkdir -p .githooks
cat > .githooks/pre-commit <<'EOF'
#!/usr/bin/env bash
set -e
node scripts/check-defer-owner.mjs
node scripts/check-buildplan-honest.mjs
EOF
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
```

For repos using Husky: write into `.husky/pre-commit` instead.

If user picked "warn-only" in Step 2 Q4, replace `set -e` with no-op and emit warnings.

### Step 9 — Install the project-local implement-module skill

Copy the canonical implement-module skill (this skill ships a parameterized template at `templates/implement-module-SKILL.md`) into `<repo>/.claude/skills/implement-module/SKILL.md`. Substitute placeholders:
- `{{PROJECT_NAME}}`
- `{{BE_STACK}}` (Supabase / Prisma / …)
- `{{MODULE_TAXONOMY}}` (from Step 2 Q1)
- `{{DEFER_STRICTNESS}}` (block-commit / warn / manual)

### Step 10 — Smoke test

```bash
pnpm exec openspec validate || true            # should run, may have no changes
node scripts/check-defer-owner.mjs             # should pass on empty repo
git add . && git commit -m "chore: init spec-driven workflow" --dry-run
```

Tell the user: next step is `pnpm exec openspec new change <first-slice-id>` and run the implement-module skill.

## Idempotency rules

- Never overwrite `CLAUDE.md`, `openspec/config.yaml`, or `docs/build-plan.md` if they already exist. Detect, ask, append-with-marker.
- Insert append blocks with a unique marker comment so re-runs can find and update only their section:
  ```
  <!-- spec-driven-workflow-init: START -->
  ...
  <!-- spec-driven-workflow-init: END -->
  ```
- `scripts/check-*.mjs` are overwrite-safe (versioned by header comment).

## Common mistakes when initializing

- **Skipping Step 1 detect.** Running on a brownfield repo with existing `docs/build-plan.md` and overwriting → angry team. Always detect, always ask.
- **Picking module taxonomy wrong.** If the project genuinely has flat features, `M1..M12` adds bureaucracy. Match taxonomy to team mental model.
- **Enabling block-commit on first day.** Pre-commit fail before any change exists confuses devs. Default to `warn-only` for repos with existing history; switch to `block-commit` after 1–2 weeks once the team adopts the format.
- **Forgetting the archive folder.** `openspec/changes/archive/` must exist from day 1; otherwise the first ship has nowhere to land.
- **No template language.** If templates ship in English but team writes specs in Vietnamese, the placeholder text gets copy-pasted forever. Localise templates from Step 2 Q2.

## Templates shipped with this skill

All templates are minimal, opinionated, and reference VOCO's proven patterns:

- `templates/openspec-config.yaml`
- `templates/build-plan.md`
- `templates/claude-md.md` + `claude-md-section.md`
- `templates/implement-module-SKILL.md`
- `templates/check-defer-owner.mjs`
- `templates/check-buildplan-honest.mjs`
- `templates/proposal.md` (example for first change)
- `templates/tasks.md` (Phase A/B/C scaffolding)

If a template is missing on disk, the skill emits an inline minimal version rather than failing — but the on-disk files are richer.

## Verify gate (before declaring init done)

1. `ls openspec/{config.yaml,specs,changes/archive}` — all exist.
2. `ls scripts/check-*.mjs` — both exist + executable.
3. `git config core.hooksPath` returns `.githooks` (or Husky equivalent).
4. `cat CLAUDE.md | grep -c 'spec-driven-workflow-init: START'` returns 1.
5. `ls .claude/skills/implement-module/SKILL.md` — exists.
6. Run `node scripts/check-defer-owner.mjs` and `node scripts/check-buildplan-honest.mjs` on empty state — both pass (no changes to validate).
7. Tell user the 3 next commands: open first change, write proposal, validate strict.

## Closing

This skill installs *methodology*, not features. The team still has to write proposals, make decisions, ship code. What it removes is the drift: every defer has an owner, every tick is honest, every shipped capability lands in the baseline.

Re-run anytime to upgrade templates; idempotent markers protect handcrafted content.
