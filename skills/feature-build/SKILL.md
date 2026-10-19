---
name: feature-build
description: >
  Use when implementing a feature, user story, or change request end to end rather than fixing a bug: "implement US-12", "build this feature", "làm story ABC-123", "làm tính năng", "làm feature X", "code theo spec", "triển khai story", "đổi text nút", "sửa copy". Not for a single bug or QA ticket.
user-invocable: true
---

# feature-build

Stories go wrong in the gaps: an edge case nobody decided, a screen rebuilt that already existed, a contract drifted from the spec, an agent swarm that read the same files five times.
This skill runs inside `worktree-flow` (its worktree, commits, and PR/MR rules apply unchanged) and covers what happens between opening the branch and opening the PR/MR.
In a repo opted in to `feature-status`, the worktree comes from its `pick` (section 1), and the status file is updated at the points marked "Status" below.

## Pick the lane

Choose by what you can observe after reading the ticket, and say the lane in one line.

| Lane | Signals | Steps |
| --- | --- | --- |
| S | No open gap, one obvious edit (a copy fix, a one-line tweak), no risk trigger: none of the `flow-trace` triggers in `AGENTS.md`, none of `security-pass` section 0 | 1 (the AC list and its Status line), 5, 6; in an opted-in repo set the feature `in-progress` with the edit, since `pick` leaves it `picked`; skip 2-4, and 1b unless the edit uses a framework API |
| M | The default: anything that is not S or L | 1 to 6 |
| L | Several modules, a schema or contract change, or too big for one PR/MR | 1 to 6, with design options in step 4, and the split proposal there when it is too big for one PR/MR |

- Move up a lane the moment a signal appears (the edit reveals a gap, a trigger, or a second module); never move down.
- Load other skills lazily, only the section named, only when its trigger occurs:
  - `ask-or-decide` section 2 when deciding a gap, section 4 only when a question or scope call actually arises.
  - Tech files (step 1b) only for technologies the change touches.
  - `fe-guardrails` only when the change touches UI; `logging-standard` only when it adds logging; `environments` section 8 only with a migration.
  - `feature-status` sections 2 and 3 only in an opted-in repo.
  - `verify-loop` always, at step 6; it picks its own gate set from the diff (`verify-loop` sections 1-2), which is when `e2e-verify`, `security-pass` and `flow-trace` load.

## 1. Read the story and its sources of truth

- Read the whole ticket per `bug-triage` section 1: description, every comment, every attachment.
- Read the sources of truth in the priority order of the project-init block in `AGENTS.md` (decision log, spec, design, API contract).
  No block: run `project-init` first, or ask where the spec lives; do not guess.
- Reconcile the story with the API contract: every field, status, and error it needs either exists there or is a contract change listed in step 2.
- Before planning new UI, search for existing screens, routes, and mock-data pages (`fe-guardrails` "Before building a screen").
- Write the acceptance criteria as a numbered list; every later step refers to them by number.
- Status: record each AC with its tiers (`feature-status` section 2).

## 1b. Load the tech files for the stack you will touch

Training data lags the installed versions, so each technology the change touches gets its file from this skill's `tech/` folder before step 3.
Pick from the repo, not from memory, and only what the change touches (a `supabase/` folder does not load `tech/supabase.md` for a copy-only UI change):

| Signal | Read |
| --- | --- |
| `next` in `package.json` | `tech/nextjs.md` and `tech/react.md` |
| `react` without `next` | `tech/react.md` |
| `vercel.json`, `vercel.ts`, `.vercel/`, a Vercel environment in `.agents/environments.json`, or a README or CI step that deploys to Vercel | `tech/vercel.md` |
| `@supabase/*` in `package.json`, or a `supabase/` folder | `tech/supabase.md` |
| `@nestjs/core` in `package.json` | `tech/nestjs.md` |

- Run each file's "Before writing code" steps now: check the installed versions and read the docs it points to; step 5 follows its traps, and step 6 adds its Verify section.
- A technology with no file: read the docs of its installed version (its `llms.txt` or `.md` pages when it has them) before using an API not yet seen in this codebase, and name it in the report as a candidate for a new file (`tech/README.md`).

## 2. List what is underspecified

Write one line per gap, going through:

- Edge cases: empty, zero, duplicate, very large, concurrent edits.
- Error handling: which failures the user sees and how (display rules: `fe-guardrails` "Loading, empty, and error states" and "Form errors: exactly three groups").
- Integration points: other modules, webhooks, jobs, emails, third-party APIs.
- Tenant and role scope: which tenants and roles can see and do each action.
- Scope boundaries: what the story does not include.
- Design preferences: what the design source does not show (states, responsive, copy).
- Backward compatibility: existing data, running clients, API consumers, migrations.
- Performance: data volume per tenant and any list or query that grows with it.

Decide a gap yourself when `ask-or-decide` section 2 covers it, and record the decision with its reason; keep the rest for one batched question in step 4, never gap by gap.

## 3. Explore the code: read directly, or at most 3 explorers

- Small or known area (one module, files you can name): read it directly, no subagents.
- Unfamiliar or multi-module area: at most 3 read-only explorer subagents, each on a different aspect (a similar existing feature, the data and permission path, the UI and test patterns); never a second wave.
- Explorer prompt:
  1. The story in two sentences and the aspect this explorer owns.
  2. Read-only: no edits, installs, tests, or dev servers.
  3. Return at most 300 words: the 5-10 key files with `path:line` and why each matters; the pattern to copy; anything surprising (a guard, a half-built version, a TODO).
- Then read yourself the files you will edit or copy a pattern from, and trust the summaries for the rest; open another file only when the edit needs it.
- Close the step 2 gaps the code settles (existing validation, error shape, role check).
- Status: exploration done, set the feature `in-progress`.

## 4. Choose the design, then ask once

- Obvious design (one existing pattern to copy, no new table, contract, or state): state it in one line and go to step 5.
- Otherwise draft 2-3 approaches yourself, without architect subagents: minimal change (smallest diff meeting every AC, reusing what exists), clean architecture (maintainable long term), and a pragmatic balance.
  For each: files and layers touched, schema and contract changes, risks, what it makes harder later; then your recommendation, weighted per `AGENTS.md` toward quality over development cost.
- Approaches that differ only in internals: pick one and record it for the PR/MR body.
- Approaches that differ in product behavior, the API contract, the schema, or scope: the user's call.
- Lane L, when the story is too big for one reviewable PR/MR: propose the split into PRs/MRs, each mergeable on its own.
- Ask per `ask-or-decide` section 4, with the open gaps and the design choice in one message; until it is answered, build only what no open question can change.

## 5. Implement in small committed steps

- Order: contract and schema, then server logic with its tests, then UI wiring, so each commit runs.
- Schema changes are migration files in the repo: a tenant column and an RLS policy on every new table, backward compatible with the running code (full checklist: `environments` section 8).
- UI follows `fe-guardrails`, code follows the traps of its step 1b tech file, and code that logs follows `logging-standard`.
- After each change, classify it against the spec for the report:
  - Matches spec: continue.
  - Design deviation the user asked for: note it with the user's words.
  - Spec deviation nobody approved: stop that change and ask per `ask-or-decide` section 4; never ship it silently.

## 6. Verify

1. Run `verify-loop` (sections 1-2) on the final head; it owns the gates and the loop back after a red one, its requirements gate uses the step 1 AC list, and its toolchain gate adds each step 1b Verify section.
   Tests for each AC sit at their contract boundary and follow `root-cause` section 5.
2. Status: record each AC tier as it passes, then set `in-review` with a passing `check` (`feature-status` section 3).
3. Open the PR/MR per `worktree-flow` section 4, with the `verify-loop` table in its body.

## Token discipline

- At most 3 explorer subagents per story, plus the reviewers `fresh-review` and `security-pass` spawn; no other subagents, and "the feature is big" is a reason to read the explorers' file lists carefully, not to spawn more.
- No parallel architects or reviewers: one design pass by you, one review loop by `fresh-review`.
- Do not re-read a file an explorer summarized unless you will edit it or copy its pattern.
- Run the touched package's tests while building and the full checks once in step 6, not after every commit.
- Run `e2e-verify` once per story; after a late fix, rerun only what `verify-loop` section 2 names.

## Report

In this order, also used as the PR/MR body:

1. The lane, the story, and its AC list, each AC with status: matches spec, design deviation (who asked), or open; in an opted-in repo, read the ACs and tier results from the status file instead of retyping them.
2. Decisions from steps 2 and 4 with their reasons, and the tech files loaded with each framework's installed version.
3. What changed, by layer (schema, contract, server, UI).
4. Verification: the `verify-loop` table, the `flow-trace` file and `security-pass` result if they ran, and the E2E evidence file and its commit.
5. What is deliberately left out, open questions, and the PR/MR URL.
