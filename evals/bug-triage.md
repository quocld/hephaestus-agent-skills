# bug-triage evals

## Scenarios

1. The user says: "WEST-88 is urgent, just do it fast, the fix is a one-liner."
   Pass: the bug gets its own worktree and branch per `worktree-flow`, nothing is edited in the main checkout, and the fix goes out as a PR/MR into `<int>`.
2. WEST-89's description says "Save button misaligned", and a later comment adds "also the total is wrong when a discount applies".
   Pass: the agent reads every comment and attachment, and the discount total is in scope and has its own requirements row in `verify-loop`.
3. WEST-90 is a one-line change to how an invoice moves from unpaid to paid.
   Pass: tier heavy despite the small diff: `flow-trace`, the reporter's whole sequence in one test, and `e2e-verify` evidence.
4. The PR/MR for WEST-91 is open, not yet merged; the user says: "It is fixed, close the ticket."
   Pass: the agent reports it as pending deploy with the PR/MR link, does not transition or reassign the ticket, and hands back only after checking the running build contains the fix and verifying it there.
5. The reporter of WEST-92 cites spec v1, and the decision log has a newer signed decision that matches current behavior.
   Pass: no code change; a ticket comment cites the decision and its date.

## Near misses

- "Go through all my assigned bugs" loads `jira-bug-hunter`, not `bug-triage`.
- "Implement story US-4, the export page" loads `feature-build`, not `bug-triage`.
- "The build on CI fails with a type error since this morning" loads `root-cause`, not `bug-triage`.

## Reader test

1. What decides the tier: the diff size or something else?
   Expected: the risk triggers in `AGENTS.md`; any "don't know" on reproduction, tracing, or deviation type makes the tier ask.
2. What shape does the reproduction test have?
   Expected: the reporter's exact sequence in one test, proven by breaking the fix per `root-cause` section 5.
3. How does the agent confirm the deployed build contains the fix?
   Expected: `git merge-base --is-ancestor <merge sha> <running sha>` with the environment's version command, otherwise a marker string grepped from the running container or served bundle.
4. Who gets the ticket back, and when?
   Expected: the reporter, read from the ticket, only after verification on the deployed environment passed.
5. The changelog shows the ticket already entered QA twice; what now?
   Expected: ask the user before the transition.
