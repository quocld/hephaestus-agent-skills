---
name: bug-triage
description: >
  Take a bug or QA ticket from intake to verified fix and hand-back: read the whole ticket, classify it, pick the fix depth by risk triggers (not diff size), prove the test catches the regression, verify on the deployed environment, and hand it back to the reporter.
  Use for "fix bug X", "fix ticket ABC-123", "loop qua bug Jira", "QA báo lỗi", "màn Y bị lỗi". For implementing a whole user story use the project's story/slice skill instead.
user-invocable: true
---

# bug-triage

## 0. Once per session

- Work in your own worktree per `worktree-flow`, including its baseline of already-failing tests.

## 1. Read the WHOLE ticket

- Description, change history, **every comment**, and every attachment (screenshots, videos, spreadsheets).
  The real scope often lives in the comments, not the description.
- Reopened ticket: read the **newest** attachments; they often show a different bug than last time.
- Videos may show a legacy or reference system rather than the broken screen; check the URL in the frames.
- Open attached files for real (images, xlsx) instead of guessing their structure.
- Fetch tickets, comments, and attachments with whatever Jira access the session has (Atlassian MCP or the REST API).

## 2. Classify before writing any code

| Branch | Signal | Action |
| --- | --- | --- |
| **Fix** | Code is wrong vs. spec, legacy behavior, or the API contract | Continue to step 3 |
| **Correct per a signed decision** | Reporter cites an older spec than a recorded decision | No code change; comment citing the decision and its date |
| **Cannot reproduce** | Code, API, and real browser all behave | Gather evidence (browser run, logs) and ask the reporter to recheck |
| **Needs a business decision** | Spec is silent and every fix is a new rule | Do not decide; escalate per `ask-or-decide`. If one option keeps existing rules intact, take it and say so |

Always search the spec and the project's decision log first; decision logs are often newer than the spec.

## 3. Pick the depth by risk triggers, not by diff size

Five triggers: **status / state machine**, **webhook or external event**, **scheduled job**, **money**, **access gate (guard, permission, paywall)**.

| Tier | Condition | Do |
| --- | --- | --- |
| **ask** | Not reproduced yet, or not traced to any file | Stop and ask. Do not guess. |
| **light** | No trigger touched | Fix -> typecheck, lint -> tests of the touched package |
| **heavy** | At least one trigger touched | `flow-trace` is mandatory + sequence reproduction test + `e2e-verify` evidence |

A one-line change can be the most dangerous bug of the month: if it touches money and status, it is heavy.
Answer these yourself; any "don't know" makes the tier **ask**: reproduced with a real persona? traced to a spec/AC? is it a spec deviation, a design deviation, or code wrong vs. spec?

An "empty screen" bug must be traced to its read endpoint before concluding anything.

## 4. Fix and prove the test works

- The reproduction test runs the reporter's exact sequence **in one test** (save -> enable -> 422 -> verify -> enable OK), never split into separate single-step tests.
- **Break the fix to prove the test catches it**, for every bug:
  ```bash
  cp <file> /tmp/f.bak && git show HEAD:<path> > <file> && <run test>; cp /tmp/f.bak <file>
  ```
  If the test stays green without the fix, it is an empty test; rewrite it.
- If tightening a guard breaks old fixtures, fix the fixtures to match the new precondition; never loosen the guard.
- Performance fixes: measure on the real environment first, and add an equivalence test (new path equals old path) before trusting it.

## 5. Commit and deploy

- Commit and open the PR/MR per `worktree-flow`.
- Batch 2-3 bug fixes into one push when CI deploys per push, so one build carries all of them.

## 6. "Pushed" is not "deployed"

- Confirm the running build contains the fix: grep a marker string from the change inside the running container or the served bundle.
- Then verify on the deployed environment with a real persona (API with a cookie jar, or a browser run).
- Never modify existing records to test.
  Create your own test records and delete them afterwards.
  Treat any integration that writes to a customer's production system as read-only unless explicitly allowed.

## 7. Hand back to the reporter

Comment in English, written for QA:
the cause in plain words, what changed, **how to retest and the expected result**, and what did **not** change (so the ticket is not reopened by mistake).
No em dash, no AI-slop phrasing.
Transition the ticket per the project's workflow and assign it back to the **reporter** (read it from the ticket, do not guess).

Never send the same ticket back to QA a third time without asking the user first.

## 8. Report to the user

A short table: ticket -> result -> new status.
Then the list of decisions the user must make, each with context, options, and a recommendation.
