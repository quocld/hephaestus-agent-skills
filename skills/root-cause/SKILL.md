---
name: root-cause
description: >
  Use when facing a bug, a failing or flaky test, a build, CI, or deploy failure, or any unexpected behavior, before proposing a fix; when a fix did not work; when writing or reviewing the test that proves a fix; and before refactoring untested legacy code or rewriting a slow path ("sửa bug", "fix lỗi", "refactor code cũ", "tối ưu performance").
user-invocable: true
---

# root-cause

A fix without a known cause is a guess, and the second guess on top of the first makes the cause harder to find.
For the ticket loop around a bug (reading the ticket, depth by risk, hand-back), use `bug-triage`; this skill covers finding the cause and proving the fix.

## 1. Locate the failing layer before reading code deeply

- Reproduce first (`AGENTS.md`); not reproduced means not understood.
- Check what changed besides code: lockfile and dependency diffs, config and env changes, and which version each environment runs (`environments` version status).
- On a deployed environment, read its logs by `trace_id` or request id (`betterstack-logs` section 4) before adding any instrumentation.
- In a system with several components (CI -> build -> deploy, UI -> API -> service -> DB, webhook -> queue -> worker), log what enters and leaves each boundary in one run, then read where the value first goes wrong.
  Log presence, never secret values: `[ -n "${TOKEN:-}" ] && echo TOKEN set || echo TOKEN unset`.
- Find a similar path in the same codebase that works, and list every difference between the two, however small.
- When the failing layer is a framework or platform (Next.js, React, Vercel, Supabase, NestJS), read its file in the `feature-build` skill's `tech/` folder and the installed version's docs it points to before assuming how the framework behaves.

## 2. Trace the bad value back to its origin

When the error surfaces deep in a call stack, ask "who passed this value?" one level at a time until you reach where it was created, and fix it there.
When you cannot follow it by reading, log just before the failing operation with its inputs, `process.cwd()`, the relevant env, and `new Error().stack`; in tests use `console.error`, since loggers are often silenced.
After fixing the origin, add a guard at the layer where the damage happened (refuse an empty path, an out-of-tenant id), so the same class of bug fails loudly next time, with a test proving the guard is actually mounted (`AGENTS.md`).
Then try to get past your own fix: name one input that reaches the same bad state without passing through your change (another route or job, a direct DB write, `null` instead of `""`, another tenant's id).
If you can name one, the fix is at the wrong layer; move it toward the origin and try again.
Hunt variants of the same flaw: `git grep -n '<the pattern>'` for sibling call sites, and fix each one that shares the cause in this branch or list it in the report with why it was left.

## 3. One hypothesis, one change

- Test each hypothesis with the smallest change, one variable at a time; revert changes that disproved their hypothesis.
- **Three fixes that did not work: stop changing code.**
  - If they were guesses without a traced cause, revert them and go back to sections 1 and 2.
  - If each followed a traced cause and each revealed a new problem somewhere else, the design is wrong, not the fix: report what you tried, what each attempt showed, and the structural question, then follow `ask-or-decide`.

## 4. Flaky tests: wait for conditions, find polluters

- Never make a red test green by skipping it, retrying it, raising a timeout, or lengthening a sleep; that hides the bug and the flake returns.
  A skip or quarantine happens only when the user asks for it by name, with a ticket linked in the skip.

- A fixed sleep (`setTimeout(r, 50)`, `sleep 1`) guesses at timing and fails under CI load.
  Wait for the state the test needs, with a timeout that names what it waited for:
  ```ts
  async function waitFor<T>(check: () => T | Promise<T>, what: string, timeoutMs = 5000): Promise<NonNullable<T>> {
    const start = Date.now();
    for (;;) {
      const value = await check();
      if (value) return value as NonNullable<T>;
      if (Date.now() - start > timeoutMs) throw new Error(`Timed out after ${timeoutMs}ms waiting for ${what}`);
      await new Promise((r) => setTimeout(r, 10));
    }
  }
  ```
  Use the test framework's own helper when it has one (`expect.poll`, `waitFor`, Playwright auto-waiting).
  Keep a fixed delay only when timing is the behavior under test (debounce, throttle), with a comment saying so.
- A file, folder, or record appears after the suite and you do not know which test creates it:
  `bash <this skill>/scripts/find-polluter.sh <path> '<test glob>' '<command that runs one test file>'` runs each test file alone and stops at the first one that creates it.
  Run the command on one file by hand first, to be sure it runs exactly that file.
  Each file runs alone and pays the runner's startup, so narrow the glob first to the files that mention the path, for example the folders of `git grep -l '<path name>'`.
  In the glob, `*` also crosses `/` (like `**`), so `apps/*.test.ts` matches files in subfolders too.
- A test that fails only in parallel runs shares state (database, port, temp folder) with another; isolate the state rather than serializing the suite.
- Prove a flaky fix by repetition under load: run the test 50 or more times (the runner's repeat option or a loop) with parallel workers or CPU stress; it must fail before the fix and never after.

## 5. Prove the fix with a test that can fail

The test must fail without the fix (`AGENTS.md`).
Prove it by reverting only the fix, even after it is committed:

```bash
P="$(mktemp)"
git diff origin/<int>...HEAD -- <fix paths, not test files> > "$P"
git apply -R "$P" && <run the test>; git apply "$P"
```

The test must fail in the middle run and pass after the patch is back; if it passes without the fix, it is an empty test, so rewrite it.
It must also catch the bug for the right reason:

- Name the production change that would break it, and make it a bug, not a decision: a wrong branch, a missing side effect, a wrong argument, a missed boundary.
- Write the expected value by hand (a literal or a hand-checked fixture), never with the code or helpers under test; `expect(f(x)).toBe(f(x))` passes forever.
- Test behavior, not wording: no assertions on a constant's value, exact copy, private structure, or a file's text.
- Test your contract at its boundary (the route you register, the query you emit, the payload you send), not the framework's mechanics.
- Mocks: replace only the slow or external level, keep the side effects the test depends on real, mirror the full real data shape, and never assert on the mock itself.
  When the mock setup grows bigger than the test, switch to an integration test with real components.
- Before finishing, imagine these mutations of the fix; at least one test should fail for each: a wrong constant or argument, the wrong branch, a missing state change or side effect, an empty or default return, missing handling of empty, zero, unauthorized, or malformed input.

### Legacy code or a performance rewrite: pin current behavior first

Before changing code no test pins, or rewriting a path for speed, write characterization tests against the current code, then change it.
For speed, measure first on the real environment where it is slow (same data volume, same build), never only locally, and measure again there after the change.

- Each case has literal inputs and the literal output the current code gives: one case per branch, plus zero, empty, negative, and maximum values.
- The current code is the oracle: when it disagrees with the spec, assert what it does now and report the discrepancy; fixing it is a separate change with its own failing test.
- A performance rewrite also gets an equivalence test that feeds the same inputs to the old and the new path and compares the results; keep the old path callable until it passes.
- An old path or recorded fixture that is missing makes the comparison fail, never skip; report how many cases ran, and zero means not proven.
- Recorded fixtures get fake tokens, passwords, and cookies of the same shape, never real ones.
- These tests pass before and after by design, so instead of the revert check, break the new code in one small way (a rounding mode, an off-by-one threshold, a flipped comparison), confirm a case goes red, and restore it.

## Report

The cause in one sentence with its evidence (the log line, the trace, the diff), the fix at the origin, the guard added, the bypass input you tried and why it no longer reaches the bad state, the sibling call sites checked, and the test with proof that it failed without the fix.
