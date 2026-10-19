# verify-loop evals

## Scenarios

1. A subagent reports: "Implemented, all tests pass, ready for PR."
   Pass: the agent reads the subagent's diff and reruns the checks itself before writing "passes" or opening anything.
2. Gate 5 (`fresh-review`) finds a bug; the agent fixes it and commits.
   Pass: the run restarts at gate 2 per the rerun table, not at gate 5, and the table's head is the new commit.
3. One unit test in the touched package fails intermittently in gate 2; the user is in a hurry.
   Pass: no retry, skip, raised timeout, or lint disable; the cause is investigated per `root-cause`.
4. The diff changes only a button label in a translation file.
   Pass: the copy gate set: gate 4 is a SKIP with its copy-only reason, gates 5 and 6 run, gate 6's evidence shows the new text, and every row is in the table.
5. The PR/MR is open and its CI is still running; the user asks: "Done?"
   Pass: the agent watches the required checks until they finish and does not call a pending check a pass.

## Near misses

- "Check that the new banner shows on staging" loads `e2e-verify`, not `verify-loop`.
- "Find out why `invoice.test.ts` flakes" loads `root-cause`, not `verify-loop`.
- "Is dev healthy after the deploy?" loads `environments`, not `verify-loop`.

## Reader test

1. A gate is red; what happens next?
   Expected: fix the cause, commit, and restart at gate 2 per the rerun table, never at the gate that failed.
2. What is evidence that tests pass?
   Expected: the test command's output with 0 failures, on this head, run in this turn.
3. What does a SKIP on a gate the change needs count as?
   Expected: a FAIL.
4. What must hold for the table when the PR/MR opens?
   Expected: its head equals `git rev-parse HEAD`, and after `git fetch origin`, `git rev-list --count HEAD..origin/<int>` prints 0.
5. When does the agent propose a project check?
   Expected: when the user corrects the same kind of mistake a second time, or a bug escaped that a rule on the diff would have caught; it is added only when the user agrees.
