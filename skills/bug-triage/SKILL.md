---
name: bug-triage
description: >
  Use when taking a bug or QA ticket from report to fix and hand-back: "fix bug X", "fix ticket ABC-123", "QA báo lỗi", "màn Y bị lỗi". Not for implementing a whole user story, and not for working through all my assigned bugs (`jira-bug-hunter`).
user-invocable: true
---

# bug-triage

Most bug tickets come back because the fix answered the description instead of the whole ticket, or was never checked where the reporter saw it.

## 0. One bug, one branch

- Each bug gets its own worktree, branch, and PR/MR per `worktree-flow`, including its baseline of already-failing tests.

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

The triggers are the risk triggers named in `AGENTS.md`; an access gate includes guards, permissions, and paywalls.

| Tier | Condition | Do |
| --- | --- | --- |
| **ask** | Not reproduced yet, or not traced to any file | Stop and ask. Do not guess. |
| **light** | No trigger touched | Fix -> `verify-loop` (its E2E gate only when the change is user-facing) |
| **heavy** | At least one trigger touched | `flow-trace` is mandatory + sequence reproduction test + `e2e-verify` evidence |

A one-line change can be the most dangerous bug of the month: if it touches money and status, it is heavy.
Answer these yourself; any "don't know" makes the tier **ask**: reproduced with a real persona? traced to a spec, an AC, or the reporter's stated expected behavior? is it a spec deviation, a design deviation, or code wrong vs. spec?

An "empty screen" bug must be traced to its read endpoint before concluding anything.

## 4. Fix and prove the test works

- Find the cause and write the proving test per `root-cause`.
- The reproduction test runs the reporter's exact sequence **in one test** (save -> enable -> 422 -> verify -> enable OK), never split into separate single-step tests.
- **Break the fix to prove the test catches it**, for every bug, with the revert-only-the-fix commands in `root-cause`.
- If tightening a guard breaks old fixtures, fix the fixtures to match the new precondition; never loosen the guard.
- Performance fixes: follow the legacy and performance subsection of `root-cause`.

## 5. Verify, commit, and open the PR/MR

- Run `verify-loop`; its requirements gate is the reporter's expected result and every scope item the comments added (step 1).
- Commit and open the PR/MR per `worktree-flow`.
- Merging and deploying to dev is the user's step (or CI after a merge the user asked for), per `worktree-flow` section 4.

## 6. "Pushed" is not "deployed"

- While the PR/MR is open or the merge is not deployed yet, the bug is **pending deploy**, never "fixed": do not transition or reassign the ticket, report it to the user as pending deploy with the PR/MR link, and come back to this step once it is deployed.
- Confirm the running build contains the fix: grep a marker string from the change inside the running container or the served bundle.
- Then verify on the deployed environment with a real persona (API with a cookie jar, or a browser run), following that environment's policy and testing scope in `environments`.

## 7. Hand back to the reporter

Hand back only after step 6 passed on the deployed environment.
Comment in English, written for QA:
the cause in plain words, what changed, **how to retest and the expected result**, and what did **not** change (so the ticket is not reopened by mistake).
No AI-slop phrasing.
Transition the ticket per the project's workflow and assign it back to the **reporter** (read it from the ticket, do not guess).

Never send the same ticket back to QA a third time without asking the user first.

## 8. Report to the user

A short table: ticket -> result (fixed, pending deploy, or another step 2 branch) -> new status.
Then the list of decisions the user must make, each with context, options, and a recommendation.
