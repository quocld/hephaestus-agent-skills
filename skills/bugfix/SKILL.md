---
name: bugfix
description: >
  Reproduce-first bug fixing. Use when asked to fix a bug, investigate a broken behavior,
  "sửa bug", "fix lỗi", or when a test/user report shows something not working.
---

# Bugfix: reproduce first, then fix

The goal is to fix the real problem, not the symptom you guessed at.

## 1. Reproduce end-to-end

- Reproduce the bug the way a real user hits it: run the app, hit the API, click the UI, run the CLI.
  Use a browser tool or Playwright for UI bugs, curl/httpie for APIs.
- Write down the exact steps, inputs, and the observed vs. expected result.
- If you cannot reproduce it, stop and report what you tried. Do not fix a bug you have not seen.

## 2. Find the root cause

- Trace from the symptom to the cause with evidence: logs, stack traces, git blame/log, bisecting when needed.
- State the root cause in one or two sentences before editing code.
- Check whether the same cause breaks other paths.

## 3. Lock it with a test

- Add a failing test at the highest level that is practical (E2E or integration over unit) that captures the user-visible bug.
- Confirm it fails for the right reason before the fix.

## 4. Fix

- Make the smallest change that fixes the root cause. Do not paper over it with retries, sleeps, or try/catch.
- Fix nearby lint errors, flaky tests, or obviously broken UI you notice along the way, and mention them separately.

## 5. Verify

- Re-run the original reproduction steps and confirm the result is now correct.
- Run the relevant test suites.

## Report

- Repro steps, root cause, the fix, how you verified it, and anything else you fixed or noticed.
