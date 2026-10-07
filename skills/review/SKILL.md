---
name: review
description: >
  Independent, adversarial review of a change against the original intent. Use when asked to
  "review", "check my changes", before shipping a risky change, or after an agent finished an
  implementation that matters.
---

# Review: check the change against intent, with fresh eyes

The implementer's context biases it toward missing edge cases, ripple effects, and over-engineering.
A review is only useful if it is independent.

## Setup

- Prefer running the review in a fresh context: a new session or a subagent that did NOT write the code.
- Gather the intent first: the task, ticket, spec, or user request. If there is none, ask for it or write down your best reading and flag it.
- Get the diff: `git diff main...HEAD` (or the staged/working diff, or the PR via `gh pr diff`).

## What to check, in order

1. **Intent** - Does the change do what was asked? Anything missing? Anything done that was not asked (scope creep)?
2. **Correctness** - Bugs, edge cases, error handling, concurrency, data migrations, security (input validation, authz, secrets).
3. **Ripple effects** - Callers, other features, configs, docs, and tests that depend on what changed.
4. **Simplicity** - Could it be smaller or simpler? Prefer removing machinery over adding it.
5. **Verification** - Is there evidence it works end-to-end? Do tests encode real requirements, or just restate the implementation?
6. **Hygiene** - Lint, types, dead code, docs drift, naming that does not match the surrounding code.

## Rules

- Every finding needs a concrete failure scenario (input/state -> wrong result), not a vague worry.
- Verify findings before reporting them: read the code path, run it, or write a quick test.
- Rank findings by severity. Separate "must fix" from "nice to have".
- Escalate scope creep and subjective tradeoffs to the human instead of deciding alone.
- Do not apply fixes unless asked; report first.
