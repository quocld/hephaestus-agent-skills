---
name: implement-module
description: Use when implementing or continuing a {{PROJECT_NAME}} capability slice end-to-end — turning an OpenSpec change into applied schema, wired FE, and an archived, honestly-ticked build-plan row. Triggers when asked to "build/implement <change-id>", "continue <slice>", "apply migration", or wire a prototype page.
---

# Implementing a {{PROJECT_NAME}} slice (OpenSpec → BE → FE → verify → archive)

## Overview
{{PROJECT_NAME}} ships one **capability slice** per OpenSpec change. A module can host N changes; never cram unrelated slices into one. The loop: **write OpenSpec → implement BE → implement FE → test+review → tick honest → archive → commit**. Decisions BEFORE code. Provisional data never reaches production.

**Single direction of truth.** `openspec/changes/<id>/` is the live plan. `openspec/specs/` is the production baseline (updated on archive). `docs/build-plan.md` is a derived dashboard — never tick green from intent; tick from `tasks.md` reality.

## The loop (per slice)

1. **OpenSpec** — `pnpm exec openspec new change <id>`; write `proposal.md` (Why/What/Capabilities/Impact/Defer), `design.md` (decisions + conventions), `tasks.md` (Phase A → B → C), one `specs/<cap>/spec.md` per capability (`## ADDED Requirements` → `### Requirement` → `#### Scenario` WHEN/THEN). `openspec validate <id> --strict`.

2. **Phase A — decisions FIRST.** Resolve every open choice. A decision MUST NOT be `[x]` decided AND in `## Defer` simultaneously. Pick one: ship it or defer it (then the decision row stays PENDING).

3. **BE on {{BE_STACK}}** — write migration file FIRST, then apply (whichever order this stack uses, do file→apply, not apply→file; prevents schema parity drift). Edge fns / services: write code, deploy via CLI (most platforms' MCPs do not deploy). Verify on the cloud: tables, RLS, cron, secrets.

4. **FE** — wire prototype pages to real backend via typed clients + server actions. Replace fake forms, not the markup.

5. **Test + review** — `pnpm typecheck && pnpm lint && pnpm build`; runtime smoke via `pnpm dev`; dispatch a subagent code-review on the diff before declaring done; apply findings.

6. **Status + tick** — update `tasks.md`, then build-plan row. Legend:
   - `[x]` = every proposal item shipped; zero Defer.
   - `[~]` = defer remains, owner named.
   - `[ ]` = not started.
   "Defer:" notes do NOT upgrade tick.

7. **Archive** — apply each `## ADDED Requirements` block into `openspec/specs/<cap>/spec.md`; move change folder to `openspec/changes/archive/<YYYY-MM>-<id>/`. Active vs archived must be distinguishable from `ls openspec/changes/`.

8. **Commit** — split: `feat(<id>): BE` · `feat(<id>): FE` · `docs(<id>): openspec + build-plan` · `chore(<id>): archive`.

## Defer discipline

Every Defer line MUST end with an inline owner:
- `→ <change-id>` (folder exists in `openspec/changes/`)
- `→ build-plan §X [ ]` (real `[ ]` row, not note column)
- `→ TICKET-123` (external tracker)

No owner = unfinished scope. Pre-commit hook `check-defer-owner.mjs` enforces.

## Verify gate (before declaring "done")

1. `openspec validate <id> --strict` pass
2. `pnpm typecheck && lint && build` clean
3. BE parity verified (migrations applied = files; cron/secrets/RLS green)
4. Edge fns / services deployed; secrets set
5. Runtime check on `pnpm dev`
6. Subagent code-review findings applied
7. Defer audit — every line has owner
8. Phase A vs Defer consistency — no item in both
9. Tick honesty — `[~]` if anything deferred, `[x]` only when scope fully shipped
10. Archive done — folder under `archive/`, specs baseline updated

Only after all 10 → declare done.

## Common mistakes (do not repeat)

- Tick `[x]` build-plan with "Defer: …" in notes column → green lie. Use `[~]`.
- Decision `[x]` in Phase A while subject sits in Defer → contradiction; pick one.
- Migration applied to cloud but file not written → parity drift; do file→apply.
- Edge fn deployed but secrets / vault not set → silent runtime fail.
- Change folder still in `openspec/changes/<id>/` (not archive/) is in-flight, regardless of how green tasks.md looks.
- {{BE_STACK_SPECIFIC_GOTCHAS}}
