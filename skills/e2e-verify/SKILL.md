---
name: e2e-verify
description: >
  Use after implementing a user-facing feature or fix and before calling it done, when asked to "verify", "test E2E", "kiểm tra lại trên browser", or when closing a ticket or story that needs E2E evidence.
user-invocable: true
---

# e2e-verify

Typecheck, build, and unit tests prove the code compiles, not that the screen works.
"Wired to the API" is not the same as "a user can complete the flow".

## 0. Prerequisites (missing = blocked, not a reason to skip)

- Seed data and test personas exist for every role the AC involves (e.g. admin vs. regular user; they often hit different code paths and FKs).
- Login is bypassed with a saved session state per persona (Playwright storage state, injected cookies/localStorage), so no tokens are spent on the login flow every run.
- If any prerequisite is missing, build it first; do not record PASS without it.

## 1. Drive the UI like a user

- Use a real browser, in this order: Playwright MCP; when it is not available, `chrome-devtools-axi`, invoked on every call as `npx -y --prefer-offline chrome-devtools-axi <command>`; the project's own tool only when the project's `AGENTS.md` names one.
  This skill owns that order; other skills point here.
- Interact through the accessibility tree (role + label: `button "Save"`, `textbox "Email"`), never hard-coded CSS selectors.
- One AC = one action sequence that follows its Given/When/Then.
- Prioritize ACs marked stale or changed since last verification.

## 2. An AC counts as verified only when ALL hold

- **(a) Submitted, not just loaded.** Any form, dialog, or drawer is submitted and the result read: success plus data visible, or the backend error shown on the right field.
  Opening a screen and taking a screenshot does not count.
- **(b) Every select/combobox the AC touches has at least one ENABLED option with a non-empty value.**
  Placeholders ("Select...", "No items found", disabled options) do not count.
- **(c) Network and console scanned even on PASS.** No responses with status >= 400, no console errors.
  Scanning only on FAIL never sees a 403 silently swallowed into an empty list.
- **(d) Data created through the UI in this session**, not hand-seeded into the one convenient shape and read back.
- **(e) At least one failure branch exercised** when the AC has a known failure state (payment failed, expired, rejected, no permission): the system enters that state AND the user still has a way out.
  If the failure branch cannot be driven from the browser (needs an external webhook or time travel), the AC is NOT verified: record the gap and cover it with a sequence test at the integration level.

Real example: an API returned 200 with every row, but the account picker in a "create bill" dialog was completely empty because the FE filtered out rows that only seeded data could make valid.
Checks (b) and (d) catch this; typecheck, lint, and tests do not.

- Side effects outside the browser (email, SMS, webhooks to third parties) are verified where they land: the local test inbox (Mailpit or the Supabase local Inbucket) or the provider's sandbox log named in the project's agent setup block.
  No such place: record the side effect as unverified in the evidence file instead of claiming it.

## 3. Multi-tenant leak scan (multi-tenant apps only)

Once at the end of each flow, check that no API response body from the session contains an ID or marker string belonging to another tenant.
Never read the bodies into context; save them to files and count hits with `grep`:

1. Save the bodies under one dump folder: Playwright MCP `browser_network_requests` (`filter: "/api/"`, `filename`) for the index list, then `browser_network_request` with `part: "response-body"` and a `filename` per request; or a HAR from the project's tool.
2. Write the other tenant's IDs and markers one per line to a file.
3. Run `grep -r -o -n -F -f <ids file> <dump folder> > <hits file>; wc -l < <hits file>; head -5 <hits file>` and read only that output.

Any hit is an immediate FAIL, whether or not the AC mentions isolation.

## 4. On FAIL, trace the backend

Get the `trace_id`/request id from the failing response (or the timestamp) and look up the structured backend logs (log platform, `docker compose logs`, dev server stdout).
Report the UI symptom together with the backend error and stack.

## Output: PASS and FAIL both leave evidence

An asymmetric report is the root problem: FAIL leaves a file, PASS leaves only the agent's word, yet PASS is what people need to trust.

Write `e2e/reports/<id>-<ISO>.json` (or the project's equivalent), tracked in git:

```json
{"id": "US-xx or TICKET-123", "verdict": "PASS|FAIL", "startedAt": "", "finishedAt": "", "commit": "<full SHA of the head that was tested>", "personas": [], "routes": [], "failures": []}
```

- PASS: the evidence file is what allows closing the story/ticket. No file, no close.
- FAIL: add a screenshot and failure details, go back to fixing; do not close.
- After a fix, re-run only the failed ACs plus the ACs whose route or component files the fix touched (`git diff --name-only <evidence commit>..HEAD`), not the whole suite.
- After 3 FAIL cycles on the same AC, stop patching and switch to the `root-cause` skill.
- Never report "works" for a flow that was not actually exercised; say exactly what was skipped and why.
