---
name: business-context-explainer
description: >
  Use when a BA or QC wants to understand a ticket, feature, or business rule in plain language, without reading code: "giải thích nghiệp vụ ticket này", "BA cần hiểu gì", "QC cần verify gì", "business rule của chức năng này", "explain this ticket for QA", "what should QC check and why". Also when a QC asks for test cases before the business is understood. Not for a workflow step that writes a spec or test-plan file, and not for a developer (`developer-context-explainer`).
user-invocable: true
---

# business-context-explainer

A BA who only rereads the ticket misses the gaps, and a QC who jumps from the ticket to test cases tests the wording instead of the business.
Build the business picture first, then say what the BA should clarify or what the QC should verify, following `developer-context-explainer` `references/rules.md` (`../developer-context-explainer/references/rules.md` from this skill's folder).

## What the reader needs

- The product and the terms the ticket uses, and how the actors and business objects relate.
- The user journey today, and what this ticket changes in it.
- Why the ticket exists: the business problem, expected vs. actual behavior, who is affected.
- The business rules (`BR1`, `BR2`, ...) and acceptance criteria, with their states and transitions when there are any.
- History, when found: earlier changes and decisions this ticket keeps or contradicts.
- Code only to confirm what the product does, told as product behavior; an API, job, or integration is named only when it changes what to ask or test.

## Role

Take the role from the user's words; when it is unclear, give both blocks, briefly.

- **BA**: missing requirements, conflicting rules, questions for the PO or client with what each changes and the options, and AC rewordings marked as proposals.
- **QC**, only after the rules are clear: what to verify and why, the key positive, negative, and edge scenarios in one line each tied to a rule, the regression scope, and what to confirm with the BA or PO before testing.

## Output

A TL;DR line (what, why, the one thing to know), then, dropping any with nothing to say: Product context, Business concepts, User journey, Why this ticket exists, Business rules and requirements, Historical context, Clarifications and recommendations (the role blocks).
