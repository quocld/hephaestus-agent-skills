---
name: verify-loop
description: >
  Use before calling a code change done, before the last commit or opening a PR/MR, after a subagent reports success, and when asked "verify loop", "verify before PR", "check before PR", "verify trước khi mở PR", "code xong chưa", "đã chắc chưa". Also when adding a project check: "thêm check", "lần sau nhớ kiểm tra", "lỗi này lặp lại hoài". Not for checking a deployed environment or one screen in a browser (`e2e-verify`).
user-invocable: true
---

# verify-loop

Every gate already has an owner skill; changes still ship broken because a gate ran on an older head, was skipped without a reason, or never existed for the one rule this project keeps breaking.
This skill owns the order of the gates, the loop back after a red one, and the one table that proves the final head passed; each gate's method stays with its owner.

## 0. A claim needs fresh evidence

Before writing "passes", "fixed", "done", or any word that implies it, run the command that proves it in this turn and read its exit code and output.

| Claim | Evidence | Not evidence |
| --- | --- | --- |
| Tests pass | The test command's output with 0 failures, on this head | An earlier run, "should pass" |
| Build or typecheck passes | That command exits 0 | Lint passing, an editor with no red |
| Bug fixed | The reporter's sequence passes, and the test fails with the fix reverted | Code changed |
| Requirement met | Section 2 gate 7, every row with evidence | Tests passing |
| A subagent finished | Its diff read and its checks rerun by you | Its report |

## 1. Scope the run

- `<int>` per `worktree-flow` section 0; the range is `origin/<int>...HEAD` plus uncommitted files.
- Classify the change from `git diff --name-only origin/<int>...HEAD`: docs or config only, code, user-facing (routes, components, copy), and whether it hits the `security-pass` triggers (its section 0) or the `flow-trace` triggers (`AGENTS.md`).
- A caller skill can hand a gate to someone else (`jira-bug-hunter` defers gate 6 until its PR is merged and deployed to dev): mark it DEFER with who runs it, and that runner runs the whole gate, `security-pass` and `flow-trace` included.
  No caller can rule a gate out; a user-facing change gets gate 6 whatever the bug's tier.
- A repo that uses the `no-mistakes` gate: run every gate here first, then hand over to its pipeline for the push, the PR/MR, and CI; its own review is a second opinion.
  When the pipeline adds commits, sync the branch the way `no-mistakes` says first, treat them as a fix commit (section 2), and update the table in the PR/MR body afterwards (`gh pr edit <n> --body-file <file>`, `glab mr update <n> --description "$(cat <file>)"`, or without `glab` the user pastes it, per `worktree-flow` section 4); its head is the pipeline's final head.
- Project checks: `python3 <this skill>/scripts/checks.py match origin/<int>` lists the checks in `.agents/checks/` whose paths the change touches.

## 2. Gates, in order

Run them top to bottom on one head.
A red gate stops the run: fix the cause (`root-cause` when it is not obvious), commit, and restart at gate 2, never at the gate that failed.

1. **Base**: rebased on the latest `origin/<int>` (`worktree-flow` section 4 step 1), so nothing after this changes the head except fixes.
2. **Toolchain**: build when the project-init block of `AGENTS.md` lists one, typecheck, lint, and tests of the touched packages, with that block's commands, plus the Verify section of each `feature-build` tech file the work loaded.
   The block's E2E suite belongs to gate 6, not here.
   Read the exit code and the failure count, not the tail of the log.
3. **Project script checks**: `python3 <this skill>/scripts/checks.py run origin/<int>` exits 0; keep its "Project checks for the reviewer" lines for gate 5.
4. **Proof**: every behavior the change adds or fixes has a test that fails without it, proven with the revert-only-the-change commands of `root-cause` section 5.
   The failure must be the assertion: when the revert leaves only import or compile errors (new code), break the new code in one small way instead, per that section's mutation list.
   A migration's proof runs on your own database (`worktree-flow` section 2), never on a shared one.
   A copy-only change has no unit proof (`root-cause` section 5 bans asserting on copy): its proof is the gate 6 step that shows the new text, so mark gate 4 `SKIP copy-only, proven in behavior`.
   Docs or config only: skip with that reason.
5. **Review**: the `fresh-review` loop, with the gate 3 reviewer lines pasted into its prompt.
   Run `security-pass` and `flow-trace` when section 1 found their triggers, even if the reviewer did not flag them, and when the reviewer flags them.
   Docs or config only: skip with that reason.
6. **Behavior**: user-facing change: `e2e-verify`, with its evidence file; otherwise skip with that reason.
7. **Requirements**: one row per acceptance criterion of the ticket, spec, or request (the `feature-build` step 1 list; for a bug, the reporter's expected result and every scope item the comments added), each with its evidence: a test name, an E2E step, or `open`.
   An `open` row is red unless the user already agreed to leave it out; a row whose evidence is a DEFER gate is DEFER too.

- A fix commit after gate 4 restarts at gate 2, with these limits: gate 4 reproves only the behaviors whose files the fix touched, `fresh-review` reviews only its delta and counts the round against its own cap, and `e2e-verify` reruns only what its re-run rule names.
  E2E evidence stays valid for an AC only when the fix touched no file on that AC's path (route, component, handler, service, query, migration); when unsure, rerun the AC.
- The owners keep their caps and what happens at them (3 review rounds, 3 E2E FAIL cycles then `root-cause`, 3 failed fixes then stop).
  Gates 2, 3, and 7 have no owner cap: the same failure after 3 fixes follows `root-cause` section 3.
- Never make a gate green by weakening it: no skipped or retried tests, raised timeouts, lint disables, or deleted checks, unless the user asks for that by name.

## 3. Report

One table for the final head, pasted into the PR/MR body's verification part (`worktree-flow` section 4 step 5):

```text
verify-loop  head <short sha>  base origin/<int> <short sha>
gate          status  evidence
base          PASS    rebased, 0 commits behind
toolchain     PASS    pnpm typecheck (exit 0); pnpm lint (exit 0); pnpm --filter web test (212 passed)
script checks PASS    2 run: no-console, migration-order
proof         PASS    apps/web/billing.test.ts "keeps paid invoice unlocked" fails with the fix reverted
review        PASS    fresh-review 2 rounds, risk low
security      SKIP    no security-pass trigger
flow          PASS    flow-trace docs/flow-traces/invoice.md
behavior      PASS    e2e/reports/WEST-12-2026-10-19T09:12:00Z.json at a1b2c3d, no AC path touched since
requirements  PASS    AC1 test, AC2 test, AC3 e2e step 4
```

Statuses: PASS, FAIL, SKIP, or DEFER, each with its evidence or reason.
A SKIP on a gate the change needs is a FAIL; a DEFER names who runs that gate and where its result will be.
The head in the table must equal `git rev-parse HEAD` when the PR/MR opens, and the base row is rechecked then: after `git fetch origin`, `git rev-list --count HEAD..origin/<int>` prints 0, otherwise rebase and restart at gate 2.

## 4. Add a project check

When the user corrects the same kind of mistake a second time, or a bug escaped that a rule on the diff would have caught, propose a check, and add it in the same branch when the user agrees.

- `python3 <this skill>/scripts/checks.py new <id>` prints the template; its `--help` owns the fields.
- `script` when a command can decide it (a grep, a schema query, a codegen diff); `review` when it needs judgment on the diff.
- `why` names the incident or correction and its date, so the check can be retired when its reason is gone.
- Prove a script check like a test: it fails on the commit that had the mistake and passes on the fix.
- `checks.py list` validates every check; run it after each edit.

## 5. Every PR, in CI

Running the same gates on every PR is the project's choice; `references/ci.md` has the workflow and what it costs.
Propose it once per project when its project checks settle, and add it only when the user agrees.
