---
name: business-context-explainer
description: >
  Use when a BA or QC wants to understand a ticket, feature, or business rule in plain language, without reading code: "giải thích nghiệp vụ ticket này", "BA cần hiểu gì", "QC cần verify gì", "business rule của chức năng này", "explain this ticket for QA", "what should QC check and why". Also when a QC asks for test cases before the business is understood. Not for a workflow step that writes a spec or test-plan file, and not for a developer (`developer-context-explainer`).
user-invocable: true
---

# business-context-explainer

A BA who only rereads the ticket misses the gaps, and a QC who jumps from the ticket to test cases tests the wording instead of the business.
This skill builds the business picture first (product, terms, journey, rules, history), then says what the BA should clarify and what the QC should verify, and why.

## 1. Set up the run

- Identify the ticket (id, URL, or pasted text) or the feature; nothing at all: ask for it, it is the only thing worth asking before investigating.
- Identify the role from the user's words: BA (requirements, rules, questions for the client), QC (what to verify), or both.
  Not stated and not clear: write both role blocks, short; do not ask.
- The reader says they are a developer, or asks how to implement it: use `developer-context-explainer` instead.
  This is about the reader's role, not the product's users: a BA on a developer tool still gets this skill.
- Load and follow `developer-context-explainer` `references/investigation.md` for the whole run: read-only, the source inventory, evidence labels, asking, and writing rules.
  That file is shared by both skills; the depth below is this skill's.

## 2. Business-specific investigation

After the shared investigation order, build these, in this order, before any recommendation:

1. **Actors and entities**: who acts (roles, client staff, end customers, other systems), on which business objects, and how those objects relate (an order has many lines, an invoice belongs to one contract).
2. **User journey**: the steps the actor takes today, what they see, and what the outcome is; then what the ticket changes in that journey.
3. **Business rules**: each rule as one plain sentence with an id (`BR1`), its source, and its label; include limits, permissions, and the states an entity moves through and who or what moves it.
4. **Code, only to confirm behavior**: read code when no doc says what the product does today, and translate the answer into product behavior ("an invoice can no longer be edited once it is paid", not a function name).
   Name an API, a database field, an event, a scheduled job, or an integration only when it changes what the BA must ask or what the QC must test (a status set by a nightly job, data synced from another system, an email sent by a third party).

## 3. Output

Fill this recipe in order, in the user's language.
Drop a section that has nothing verified or inferred to say; keep 03, 04, 05, and 07 always.
Rules are plain sentences; a code path appears only in the Source column, never in the rule text.

```markdown
**TL;DR**: <what the feature is for, in one line> - <why this ticket exists, in one line> - <the one thing the reader must know>.

## 01. Product context
<the product, its domain, and what this feature does for whom; 2-4 lines>

## 02. Business concepts
<each term at first use with a project example; then how the entities and actors relate, as one short list or table>

## 03. User journey
<numbered steps the actor takes and what each shows or produces; then what changes with this ticket>

## 04. Why this ticket exists
<the business problem, the trigger, expected vs. actual behavior, who is affected and how>

## 05. Business rules and requirements
<BR1..BRn: rule | source | label; then the acceptance criteria as written, or "no AC list" as Unknown; then the states and their allowed moves when an entity has states, stated here once>

## 06. Historical context
<earlier changes, decisions, and related tickets, and whether this ticket keeps or contradicts them>

## 07. Clarifications and recommendations
<the role blocks below>

Deeper on request: <topics>
Sources: <inventory row: result, for each row>
```

Labels, length, and the order of the closing lines follow `developer-context-explainer` `references/investigation.md` sections 4 and 6; with both role blocks, each block item is one line and the length budget stays the same.

### BA block (in 07)

- **Missing requirements**: what a developer or QC would have to guess (an error case, a limit, a permission, an empty state, what happens to existing data).
- **Conflicting rules**: the two sources and what each says.
- **Questions for the PO or client**: each with why it matters (what it changes) and the options you see; ordered by impact on scope.
- **Acceptance criteria**: a proposed Given/When/Then rewording only where an AC is vague or untestable, marked as a proposal.

The BA and PO decide; never present a proposed rule, answer, or AC as decided.

### QC block (in 07)

Write it only after 03-05 exist; every item points to the rule (`BR2`), journey step, or AC it verifies.

- **Expected behavior**: what the user should see at each changed journey step.
- **Rules to verify**: one line per rule, and why it matters to the business.
- **Scenarios**: positive and negative, as one line each (actor, situation, expected outcome), not full test cases; a scenario an existing test already covers says so, with the test's name.
- **Boundaries and edge cases**: limits, empty and maximum values, permissions, concurrent or repeated actions.
- **Status transitions and data consistency**: the forbidden moves to try and what other records must agree afterwards, pointing back to the states in 05 instead of repeating them.
- **Integrations**: other systems, jobs, or emails the result depends on, and how to observe them.
- **Regression scope**: features that share the changed rule, screen, or data, and earlier bugs in this area from 06.
- **Confirm with BA/PO before testing**: expected results no source states.
