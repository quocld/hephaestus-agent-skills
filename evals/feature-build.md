# feature-build evals

## Scenarios

1. The user says: "Implement US-12, the invoice export page," in a repo the agent has not seen, touching billing, permissions, and UI.
   Pass: at most 3 read-only explorer subagents in one wave, no architect or reviewer subagents of its own, and the agent reads itself only the files it will edit or copy from.
2. US-13 is silent on an empty invoice list and on which roles may export.
   Pass: one line per gap, gaps covered by `ask-or-decide` section 2 decided with a reason, and the rest asked in one batched message, never one question per gap.
3. The user says: "Đổi text nút Save thành Lưu."
   Pass: the agent names lane S in one line, writes the AC list, edits, and runs `verify-loop`, with no explorers and no design options.
4. A lane S label change turns out to need an edit to a helper that also formats the payment amount, in a second module.
   Pass: the agent moves up a lane as soon as it sees it, citing the lane rule "a trigger, or a second module", and never moves back down.
5. While building, the agent finds the spec's sort order (by due date) awkward and sorting by name easier.
   Pass: the agent stops that change and asks per `ask-or-decide` section 4; it does not ship the deviation silently.

## Near misses

- "Fix bug WEST-88: the invoice total is wrong" loads `bug-triage`, not `feature-build`.
- "Review my changes before I open the PR" loads `fresh-review`, not `feature-build`.
- "Why does the export test fail only in CI?" loads `root-cause`, not `feature-build`.

## Reader test

1. How many explorer subagents may a story use?
   Expected: at most 3, each on a different aspect, in one wave, read-only, each returning at most 300 words.
2. Which steps does lane S run?
   Expected: step 1 (the AC list), 5, and 6; step 1b only when the edit uses a framework API.
3. Two designs differ in the API contract; who chooses?
   Expected: the user; designs that differ only in internals are the agent's call, recorded for the PR/MR body.
4. In what order is the code built?
   Expected: contract and schema, then server logic with its tests, then UI wiring, so each commit runs.
5. When is a `tech/` file read, and which one for a Next.js app?
   Expected: before step 3, only for technologies the change touches; `tech/nextjs.md` and `tech/react.md`.
