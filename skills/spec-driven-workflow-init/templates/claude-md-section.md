<!-- spec-driven-workflow-init: START -->
## Spec-driven workflow

This project follows an OpenSpec → BE → FE → verify → archive loop. Every shipped capability is a *change* under `openspec/changes/<id>/` (then archived to `openspec/changes/archive/<YYYY-MM>-<id>/`). The live dashboard is `docs/build-plan.md`.

**Core rules (enforced by pre-commit hooks):**
1. **Decisions before code.** Phase A in `tasks.md` is closed before any migration or implementation begins.
2. **Defer needs an owner.** Every line in `## Defer` or `## Deferred` ends with `→ <change-id>` / `→ build-plan §X` / `→ TICKET-id`. No owner = unfinished scope.
3. **Honest tick.** Build-plan row is `[x]` only when proposal scope is fully shipped; `[~]` while any defer is open with an owner; `[ ]` if not started.
4. **Archive is real.** Folder moves to `archive/`; capability spec deltas merge into `openspec/specs/` baseline.

**Per-slice loop** — see `.claude/skills/implement-module/SKILL.md`. Invoke when implementing or continuing a slice.

**Commands:**
- `pnpm exec openspec new change <id>` — scaffold a new slice
- `pnpm exec openspec validate <id> --strict` — verify proposal/specs
- `node scripts/check-defer-owner.mjs` — pre-commit: every defer has owner
- `node scripts/check-buildplan-honest.mjs` — pre-commit: no dishonest `[x]`

When briefs or legacy docs conflict with the OpenSpec-recorded decision, **OpenSpec wins**.
<!-- spec-driven-workflow-init: END -->
