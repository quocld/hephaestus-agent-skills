---
name: fresh-review
description: >
  Use before opening a PR/MR for a change that matters, after an agent finishes an implementation, or when asked to "review", "check before PR", "review lại branch".
user-invocable: true
---

# fresh-review

The implementer's context biases it toward missing edge cases, ripple effects, and over-engineering.
A review only helps when the reviewer starts blank.

## Setup

1. Collect the intent: the Jira ticket, OpenSpec change, or the user's request.
   If none exists, write your best one-paragraph reading of the intent and flag it as an assumption.
2. Identify the branch, the base (the integration branch from `worktree-flow`, e.g. `origin/dev`), and any ignore patterns (generated files, lockfiles).
3. Spawn a **new** subagent for every review round.
   Never resume an old reviewer, and never review in the implementer's own context.
   Pass it the intent, branch, base, and the prompt below.

## Reviewer prompt

```text
Review the code changes on <branch> against <base> and return structured findings with a risk assessment.

Intent: <ticket / spec / request summary>
Ignore: <patterns or "none">

Task:
- Read the relevant history and diff yourself.
- Focus on risks introduced by the changed code, but inspect call sites, shared helpers, tests, and invariants when needed to understand root cause.
- Check the change against the intent: missing pieces, and scope creep beyond it.
- Analyze for bugs, risks, and simplification opportunities.
  Simplification means reducing complexity without changing product behavior.
- Treat security issues, performance regressions, breaking changes, and weak error handling as risks.
- Do not run tests during review.
- Do a full pass before returning; do not stop at the first finding.

Rules:
- Anchor every finding to a file and 1-indexed line in the changed code when possible.
- Severity: error = must not merge; warning = can be a follow-up; info = nice to have.
- Be concise and actionable; no generic advice like "add more tests".
- Do not report formatting, lint, compile, or type-check issues; tooling owns those.
- If the change is clean, return an empty findings array.
- action for each finding:
  - ask-user: product behavior, functional requirements, or the author's deliberate intent. When in doubt, ask-user.
  - auto-fix: non-functional and not user-visible (correctness, error handling, security, performance, mechanical quality), fixable without discussing intent.
  - no-op: informational.

Return JSON:
{
  "findings": [{"severity": "error|warning|info", "action": "ask-user|auto-fix|no-op", "file": "path", "line": 1, "description": "..."}],
  "risk_level": "low|medium|high",
  "risk_rationale": "one sentence"
}
risk_level: low = well-bounded; medium = room to improve but safe to raise; high = needs explicit human approval before raising.
```

## Loop

- `auto-fix` findings: fix them, commit, then run a **new** fresh reviewer on the updated branch.
- `ask-user` findings: decide or escalate per the `ask-or-decide` skill; do not open the PR while one is unanswered.
- Any `error`: do not open the PR.
- Clean (empty, or only `info` and already-answered `ask-user`): the PR may be opened.
- Fix forward; never revert the author's intentional work just to silence a finding.
- If the same theme keeps coming back after two rounds, stop and escalate: the abstraction itself is probably wrong.

## Report to the user

Risk level with rationale, findings fixed per round, open decisions, and the PR URL if one was opened.
