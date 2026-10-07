---
name: e2e-check
description: >
  Verify a feature end-to-end the way a user would, with a picky eye for UI. Use after implementing
  a feature, when asked to "test it", "verify", "kiểm tra lại", or before declaring work done.
---

# E2E check: prove it works like a user would

Self-written unit tests are not proof of done. This is.

## 1. Define the user flows

- From the task or spec, list the user-visible flows to verify, including the happy path, one or two edge cases, and an error path.

## 2. Run the real thing

- Start the app (dev server, CLI, API) the way a user or client would use it.
- For web UI, drive a real browser (Playwright / browser tool). Check both light and dark mode and a narrow (mobile) width if the app supports them.
- For APIs, call real endpoints with real-looking payloads and check status codes, bodies, and side effects (DB rows, emails, queues).

## 3. Be picky

- Look for misalignment, overflow, clipped text, inconsistent spacing, wrong colors/contrast, broken loading and empty states, console errors, and failed network requests.
- If something clearly looks off, fix it along the way, even if it is not part of the current task.
- Treat flaky behavior as a bug, not as noise.

## 4. Report

- Each flow: pass/fail, with evidence (screenshot, command output, response).
- Anything fixed along the way, and anything still broken.
- Never say "done" if a flow was not actually exercised; say what was skipped and why.
