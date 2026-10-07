---
name: adversarial-review
description: Use after a ship cloud agent pushes a branch, before any pull request.
---

# Adversarial review

Review draft ship work on a pushed branch. Do not open a pull request until this pass is clean.

## Who runs it

A project crewmate starts a **fresh** subagent. Do not resume an old review subagent. The parent model is whatever the crewmate is running unless the captain asked for a specific one.

The subagent starts blank. The dispatch must include the repo, source control CLI, branch, base, and this entire prompt.

The subagent cannot see a cloud agent VM. It reads the branch through the source control CLI recorded for the project (`gh`, `glab`, or the recorded forge) or git, on the shared Grok Bot computer.

## Prompt

<Use this as the subagent task. Fill the context fields.>

Review the code changes and return structured findings with a risk assessment.

Context:

- branch: <branch>
- base: <default branch or merge base>
- review scope: branch changes between base and the pushed tip
- ignore patterns: none, unless the project listed some

Task:

- Read the relevant history and diff yourself.
- Focus findings on risks introduced by changed code, but inspect surrounding code, call sites, shared helpers, tests, and invariants when needed to understand root cause.
- Do NOT run tests during review.
- Analyze for bugs, risks, and code simplification opportunities.
- Simplification means reducing code complexity through non-functional refactoring. It does NOT mean removing features or changing product behavior.
- Treat security issues, performance regressions, breaking changes, and insufficient error handling as risks.
- Do a full review pass before returning. Do not stop after the first valid finding.

Rules:

- Anchor every finding to a specific file and one-indexed line number in the changed code when possible.
- Severity `error` must not merge. `warning` can be a follow-up. `info` is nice to have.
- Be concise and actionable. No generic advice like "add more tests".
- Only comment on things that genuinely matter.
- Do NOT report styling, formatting, linting, compilation, or type-checking issues.
- If the change is clean, return an empty findings array.
- For each finding, set action to one of:
  - `ask-user`: functional requirements, product behavior, or the author's deliberate intent. When in doubt, ask-user.
  - `auto-fix`: non-functional, not user-visible (correctness, error handling, security, performance, mechanical quality) that can be fixed without discussing intent.
  - `no-op`: informational.

Risk assessment after all findings:

- `low` if well-bounded and straightforward
- `medium` if room to improve but safe to raise first
- `high` if it should not raise without explicit human approval

Return JSON:

```json
{
  "findings": [
    {
      "severity": "error|warning|info",
      "action": "ask-user|auto-fix|no-op",
      "file": "path",
      "line": 1,
      "description": "..."
    }
  ],
  "risk_level": "low|medium|high",
  "risk_rationale": "one sentence"
}
```

## Loop

- `auto-fix`: reply to the same cloud agent. Then a new fresh review subagent.
- `ask-user`: Firstmate takes one decision card to the captain. Do not raise.
- `error`: do not raise.
- Empty findings, or only `info` / already-answered `ask-user`: the crewmate may open the pull request.

Fix-forward. Do not revert the author's intentional first commit to silence a finding.

## Do not

- Do not open a pull request to make the branch visible for review
- Do not run this on scout tasks
