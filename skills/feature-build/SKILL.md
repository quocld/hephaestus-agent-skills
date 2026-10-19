---
name: feature-build
description: >
  Use when implementing a feature, user story, or change request end to end rather than fixing a bug: "implement US-12", "build this feature", "làm story ABC-123", "làm tính năng", "làm feature X", "code theo spec", "triển khai story", "đổi text nút", "sửa copy". Not for a single bug or QA ticket.
user-invocable: true
---

# feature-build

Stories go wrong in the gaps: an edge case nobody decided, a screen rebuilt that already existed, a contract drifted from the spec, an agent swarm that read the same files five times.
This skill runs inside `worktree-flow` (its worktree, commits, and PR/MR rules apply unchanged) and covers what happens between opening the branch and opening the PR/MR.
A change with no open gap and one obvious edit (a copy fix, a one-line tweak) skips steps 1b-4: list its AC, make the edit, and run step 6.

## 1. Read the story and its sources of truth

- Read the whole ticket the way `bug-triage` step 1 describes: description, every comment, every attachment.
- Read the sources of truth in the priority order listed in the project-init block of the project's `AGENTS.md` (decision log, spec, design, API contract).
  No block: run `project-init` first, or ask where the spec lives; do not guess.
- Reconcile the story with the API contract: every field, status, and error the story needs either exists in the contract or is a contract change you list in step 2.
- Search for existing screens, routes, and mock-data pages before planning new UI (`fe-guardrails`, "Before building a screen").
- Write down the acceptance criteria as a numbered list; every later step refers to them by number.

## 1b. Load the tech files for the stack you will touch

Training data lags the installed framework versions, so every technology the change touches gets its file from this skill's `tech/` folder before step 3.
Pick them from the repo, not from memory, and only for technologies the change itself touches (a `supabase/` folder does not load `tech/supabase.md` for a copy-only UI change):

| Signal | Read |
| --- | --- |
| `next` in `package.json` | `tech/nextjs.md` and `tech/react.md` |
| `react` without `next` | `tech/react.md` |
| `vercel.json`, `vercel.ts`, `.vercel/`, a Vercel environment in `.agents/environments.json`, or a README or CI step that deploys to Vercel | `tech/vercel.md` |
| `@supabase/*` in `package.json`, or a `supabase/` folder | `tech/supabase.md` |
| `@nestjs/core` in `package.json` | `tech/nestjs.md` |

- Run each file's "Before writing code" steps now: check the installed versions it names and read the docs for those versions that it points to.
- Step 5 follows each file's traps, and step 6 adds each file's Verify section.
- A technology with no file here: read the docs of its installed version (its `llms.txt` or `.md` pages when it has them) before using an API you have not seen in this codebase, and name it in the report as a candidate for a new file (`tech/README.md`).

## 2. List what is underspecified

Go through each item and write one line per gap:

- Edge cases: empty, zero, duplicate, very large, concurrent edits.
- Error handling: which failures the user sees and how (`fe-guardrails` owns the display rules).
- Integration points: other modules, webhooks, jobs, emails, third-party APIs the change touches.
- Tenant and role scope: which tenants and roles can see and do each action.
- Scope boundaries: what the story does not include.
- Design preferences: anything the design source does not show (states, responsive, copy).
- Backward compatibility: existing data, running clients, API consumers, migrations.
- Performance: expected data volume per tenant and any list or query that grows with it.

For each gap, decide it yourself when `ask-or-decide` section 2 covers it, and record the decision with its reason.
Keep the rest for one batched question in step 4; do not ask gap by gap.

## 3. Explore the code: read directly, or at most 3 explorers

- The area is small or already known (one module, files you can name): read it directly, no subagents.
- The area is unfamiliar or spans several modules: spawn at most 3 read-only explorer subagents, each on a different aspect (a similar existing feature, the data and permission path, the UI and test patterns).
  Never spawn more than 3, and never a second wave.
- Explorer prompt, part by part:
  1. The story in two sentences and the aspect this explorer owns.
  2. Read-only: no edits, no installs, no tests, no dev servers.
  3. Return at most 300 words: the 5-10 key files, each with `path:line` and one line on why it matters; the pattern a new change should copy; anything surprising (a guard, an existing half-built version, a TODO).
- Then read yourself the files you will edit or copy a pattern from.
  Trust the explorers' summary for the rest; open another file only when the edit needs it.
- Answer whatever gaps from step 2 the code settles (existing validation, existing error shape, an existing role check).

## 4. Choose the design, then ask once

- The design is obvious (one existing pattern to copy, no new table, contract, or state): state it in one line and go to step 5.
- Otherwise draft 2-3 approaches yourself, without architect subagents:
  - Minimal change: the smallest diff that meets every AC, reusing what exists.
  - Clean architecture: the shape that keeps the module maintainable long term.
  - Pragmatic balance: between the two.
  For each: files and layers touched, schema and contract changes, risks, and what it makes harder later; then your recommendation and why, weighted per `AGENTS.md` toward quality over development cost.
- Approaches that differ only in internals: pick the recommendation and record it for the PR/MR body.
- Approaches that differ in product behavior, the API contract, the schema, or the story's scope: that is the user's call.
- A story too big for one reviewable PR/MR: propose the split into PRs/MRs, each mergeable on its own.
- Ask per `ask-or-decide` section 4; gaps and the design choice that block the same work go in one message, since each would otherwise stall it separately.
  While it is unanswered, build only what no open question can change.

## 5. Implement in small committed steps

- Order: contract and schema first, then server logic with its tests, then UI wiring, so each commit runs.
- Schema changes are migration files in the repo: a tenant column and an RLS policy on every new table, and backward compatible with the code running now (`environments` section 8 owns the full checklist for staging and prod).
- UI follows `fe-guardrails`, and code in each technology follows the traps in its tech file from step 1b.
- After each change, classify it against the spec and record it for the report:
  - Matches spec: continue.
  - Design deviation the user asked for: note it with the user's words.
  - Spec deviation that nobody approved: stop that change and ask per `ask-or-decide`; never ship it silently.

## 6. Verify

In this order, so the evidence names the head that ships:

1. Rebase on `origin/<int>` first (`worktree-flow` section 4 step 1), so nothing after this changes the head except fixes.
2. Run the checks of `worktree-flow` section 4 step 2, plus the Verify section of each tech file loaded in step 1b.
   Tests for each AC sit at its contract boundary and follow `root-cause` section 5; for a change to existing behavior, prove the test with the revert-only-the-change commands there.
3. A change that matters (anything beyond copy, docs, or config): run the `fresh-review` loop.
   It routes to `security-pass` and `flow-trace` itself when their triggers fire, so do not run either separately.
   A copy, docs, or config-only change skips the review and goes to step 4.
4. User-facing change: run `e2e-verify` once on the final head, with its evidence file.
5. A fix commit lands after the evidence (an E2E failure, a late finding): it counts as a `fresh-review` round within that skill's cap, and `e2e-verify` reruns only what its own re-run rule names.
6. Open the PR/MR per `worktree-flow`.

## Token discipline

- Hard cap: at most 3 explorer subagents per story, plus the reviewers `fresh-review` and `security-pass` spawn; no other subagents.
  "The feature is big" is a reason to read the explorers' file lists carefully, not to spawn more.
- No parallel architects and no parallel reviewers; one design pass by you, one review loop by `fresh-review`.
- Do not re-read a file an explorer already summarized unless you are about to edit it or copy its pattern.
- Do not rerun the full suite after every commit; run the touched package's tests while building and the full checks once in step 6.
- Run `e2e-verify` once per story; after a late fix, rerun only what its re-run rule names (step 6.5).

## Report

In this order, also used as the PR/MR body:

1. The story and its AC list, each with status: matches spec, design deviation (who asked), or open.
2. Decisions made in step 2 and step 4, each with its reason, and the tech files loaded with each framework's installed version.
3. What changed, by layer (schema, contract, server, UI).
4. Verification: commands run, tests proven to fail without the change, `flow-trace` file, `security-pass` result if it ran, E2E evidence file and its commit.
5. What is deliberately left out, open questions, and the PR/MR URL.
