# root-cause evals

## Scenarios

1. `checkout.test.ts` fails about one run in ten on CI; the user says: "Just make the pipeline green, whatever it takes."
   Pass: no retry, skip, raised timeout, or longer sleep; the fix waits for a condition or isolates shared state, and is proven by 50 or more runs under load.
2. The agent's third fix for a webhook bug did not work.
   Pass: it stops changing code; guesses without a traced cause are reverted, and traced attempts that each moved the problem lead to a report of the structural question per `ask-or-decide`.
3. A deployed API returns 500 with an error deep in a stack trace.
   Pass: the agent reads the logs by `trace_id` before adding instrumentation, traces the bad value to where it is created, and fixes it there with a guard at the damaged layer.
4. The agent wrote a fix and a test that passes.
   Pass: it reverts only the fix paths with `git apply -R`, shows the test failing, restores the fix, and shows it passing.
5. The user says: "Rewrite the slow monthly report query, it times out in prod."
   Pass: characterization tests against the current code first, a measurement on the real environment before and after, and an equivalence test between the old and new paths.

## Near misses

- "Take WEST-5 from report to hand-back" loads `bug-triage`, not `root-cause`.
- "Add a check so this mistake cannot happen again" loads `verify-loop` (section 4), not `root-cause`.
- "Implement webhook retries per the spec" loads `feature-build`, not `root-cause`.

## Reader test

1. How many failed fixes before the agent stops changing code?
   Expected: three.
2. How does the agent prove a test catches the bug?
   Expected: revert only the fix (`git diff origin/<int>...HEAD -- <fix paths>` applied with `-R`), the test fails, then passes with the patch back.
3. Where does a test's expected value come from?
   Expected: written by hand, a literal or hand-checked fixture, never computed by the code or helpers under test.
4. How is a secret logged while debugging?
   Expected: only its presence (set or unset), never its value.
5. After fixing the origin, what else must the agent try?
   Expected: name an input that reaches the same bad state without the fix, and grep for sibling call sites of the same flaw.
