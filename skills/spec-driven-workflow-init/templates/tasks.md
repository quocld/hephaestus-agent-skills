## 1. Phase A — Decisions
- [ ] 1.1 D-<id> <decision title>

> A decision must NOT also appear in `## Deferred`. If X is deferred, this row stays PENDING or is removed.

## 2. Phase B — Deliverables

### BE
- [ ] 2.1 Migration `NNNN_<slug>.sql` — applied + repo file
- [ ] 2.2 Edge fn / service — deployed
- [ ] 2.3 Secrets / vault — set

### FE
- [ ] 2.4 Page / component wiring
- [ ] 2.5 Server actions
- [ ] 2.6 i18n strings (if applicable)

## 3. Phase C — Verify
- [ ] 3.1 `pnpm typecheck && pnpm lint && pnpm build` pass
- [ ] 3.2 Runtime smoke (HTTP render + guard redirects)
- [ ] 3.3 MCP / DB verify (RLS, cron, secrets, table counts)
- [ ] 3.4 Subagent code-review applied
- [ ] 3.5 `pnpm exec openspec validate <id> --strict` pass
- [ ] 3.6 build-plan + tasks.md ticked honestly (no `[x]` if Defer open)
- [ ] 3.7 Archive: move to `openspec/changes/archive/<YYYY-MM>-<id>/` + merge spec deltas into `openspec/specs/`

## 4. Deferred

<!-- Every line below MUST end with an owner arrow. Examples: -->
<!-- - [ ] DOCX parse → m7-ai-cv-extras -->
<!-- - [ ] First-token SLO metrics → build-plan §⑨a [ ] SLO -->
<!-- - [ ] Live Stripe prices → VOCO-123 -->
