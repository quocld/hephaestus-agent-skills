---
name: developer-context-explainer
description: >
  Use when a developer wants to understand a ticket before or while working on it, without changing anything yet: "explain ticket ABC-123", "giải thích ticket này", "context của ticket", "ticket này để làm gì", "tại sao cần làm cái này", "hiểu ticket trước khi code", "onboard me on this ticket", "tôi làm tới đâu rồi". Not for implementing it (`feature-build`), fixing a bug (`bug-triage`), or a BA or QC reader (`business-context-explainer`).
user-invocable: true
---

# developer-context-explainer

A new developer who codes a ticket without knowing why it exists builds the wrong thing correctly.
This skill makes them understand the business first, then the system, then their own progress, from evidence, before they write code.

## 1. Set up the run

- Identify the ticket (id, URL, or pasted text) and the developer's repo; no ticket at all: ask for one, it is the only thing worth asking before investigating.
- The reader says they are a BA or QC, or asks what to test or clarify: use `business-context-explainer` instead.
- Load and follow `references/investigation.md` for the whole run: read-only, the source inventory, evidence labels, asking, and writing rules.

## 2. Developer-specific investigation

After the shared order in `references/investigation.md` section 3, add these, in this order:

1. **Current behavior**: trace the path the ticket touches, from entry point (route, screen, job, event) through the modules to the data and any external integration, on `origin/<int>`.
   Name each file by what it does in that path ("`billing/invoice.service.ts:88` decides whether a paid invoice can be edited"), never as a bare list.
2. **Classify what the ticket asks**: each item is a business requirement (what the user or business needs), a technical implementation (how the code will do it), or a technical constraint (what limits the how: a contract, a schema, a third-party API, performance).
   A ticket that prescribes an implementation without the requirement behind it is a question for the BA or PO.
3. **Risks**: callers of the code you would change (`git grep` the symbol), shared components, data already stored in the old shape, the `flow-trace` triggers in `AGENTS.md`, and earlier bugs in the same area from the history step.
4. **Progress, from Git only**:
   ```bash
   git worktree list; git branch -a --list '*<ticket>*'
   gh pr list --state all --search '<ticket>'
   git -C <their worktree> status --short
   git -C <their worktree> log --oneline origin/<int>..HEAD
   git -C <their worktree> diff --stat origin/<int>...HEAD
   ```
   Map each acceptance criterion to `done`, `partial`, or `not started`, each with the commit, file, or PR check that shows it.
   No branch, commit, or PR found: progress is "not started (no Git evidence)", never estimated from what the developer said or the branch name.
   Uncommitted changes count as `partial` and are named as uncommitted.

## 3. Output

Fill this recipe in order, in the user's language.
Drop a section that has nothing verified or inferred to say; keep 03 and 07 always.

```markdown
**TL;DR**: <ticket in one line> - <why it exists in one line> - <the one thing to know before coding>.

## 01. Ticket overview
<goal, type, status, assignee, links; 2-4 lines>

## 02. Business context
<domain, the terms the ticket uses, each explained at first use with a project example, how they relate, who the users are and what they do in this workflow>

## 03. Why this ticket exists
<trigger (incident, client request, decision), the problem, expected vs. actual behavior, business impact if left undone>

## 04. Historical context
<related tickets, earlier implementations and why they chose what they did, decisions, whether this ticket changes or contradicts an earlier decision; timeline only per references/investigation.md section 6>

## 05. Technical impact
<the path from section 2 step 1, affected modules, APIs, data, integrations, dependencies; requirement vs. implementation vs. constraint>

## 06. Development progress
<branch, commits, PR and its checks, uncommitted changes; the AC table: AC | done/partial/not started | evidence>

## 07. Recommendations
- First: <the next concrete step>
- Investigate further: <what is still Unknown and where to look>
- Confirm with BA/PO: <each question, addressed to who can answer, or "nothing to confirm">
- Risks: <regression and edge cases to keep in mind>
- Ready to implement: <yes / yes after X / no, because Y>; when yes, the work goes through `feature-build` or `bug-triage`.

Sources: <inventory row: result, for each row>
```

- Business sections (02, 03) come before technical ones (05), even when the reader asked a technical question; answer that question in the TL;DR and keep the order.
- Every claim in 03-07 carries its label from `references/investigation.md` section 4.
