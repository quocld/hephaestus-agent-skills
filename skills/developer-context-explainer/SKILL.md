---
name: developer-context-explainer
description: >
  Use when a developer wants to understand a ticket before or while working on it, without changing anything yet: "explain ticket ABC-123", "giải thích ticket này", "context của ticket", "ticket này để làm gì", "tại sao cần làm cái này", "hiểu ticket trước khi code", "onboard me on this ticket", "tôi làm tới đâu rồi". Not for implementing it (`feature-build`), fixing a bug (`bug-triage`), or a BA or QC reader (`business-context-explainer`).
user-invocable: true
---

# developer-context-explainer

A developer who codes a ticket without knowing why it exists builds the wrong thing correctly.
Explain the business first, then the system, then where the developer stands, following `references/rules.md`.

## What the developer needs

- Why the ticket exists: the business problem, expected vs. actual behavior, who is affected.
- How the system behaves today on the path the ticket touches, each file named by its role ("`invoice.service.ts:88` decides whether a paid invoice can be edited"), not as a list.
- What must change, kept apart: the business requirement, the implementation, and the technical constraints.
- Risks: callers and shared code, data already stored, earlier bugs in the same area.
- Progress from Git only: branch, commits, PR, merged or not, per acceptance criterion; no Git evidence means "not started", and the developer's own estimate is answered with the AC count, never confirmed; matching commits to ACs is Inferred unless the PR or commit names the AC.

## Output

A TL;DR line (what, why, the one thing to know), then, dropping any with nothing to say: Ticket overview, Business context, Why this ticket exists, Historical context, Technical impact, Development progress, Next steps.
Next steps says what to do first, what to confirm with the BA or PO, which risks to watch, and whether the developer can start implementing.
