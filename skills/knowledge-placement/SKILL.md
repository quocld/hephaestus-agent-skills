---
name: knowledge-placement
description: >
  Decide where a new fact, rule, or lesson belongs (AGENTS.md, a skill, docs, a script's --help, or task notes) and keep AGENTS.md lean.
  Use before editing AGENTS.md or CLAUDE.md, before creating a new skill, or when asked to "remember this for the project" or "add a rule".
user-invocable: false
---

# knowledge-placement

AGENTS.md is paid for by every session, every time.
A skill is paid for only by sessions that load it.
Put each fact at the first tier that fits, not the most convenient one.

## Decision tree (stop at the first yes)

1. Does an agent need it on almost every session to operate?
   -> `AGENTS.md`, inline, a line or two.
2. Is it needed only in a nameable situation (a deploy, a migration, a release, a specific workflow)?
   -> A skill whose description states that trigger.
   Add a one-line pointer to AGENTS.md only if an always-loaded rule must name the skill.
3. Is it product, setup, or user reference?
   -> README or user-facing docs.
4. Is it architecture a maintainer needs (ownership, boundaries, extension points, rationale)?
   -> Architecture docs.
5. Is it exact mechanics (flags, commands, paths)?
   -> The script's header comment and its `--help`, not prose elsewhere.
6. Is it task evidence (chronology, failed hypotheses, temp paths, delivery proof)?
   -> The PR description, Jira ticket, or a handoff note; distill any durable fact into its real owner first.

## One-owner rule

- State every contract (format, state machine, procedure) in full exactly once.
- Everywhere else, use a one-line cross-reference, never a restatement; copies drift.
- When changing a contract, edit the owner's existing wording, then grep for references and fix them.

## Moving content out of AGENTS.md

- Keep behind only what must survive with no skill loaded: the trigger to load the skill and any safety-critical fact.
- Move everything else out completely; no partial "just in case" copies.

## New skills

- A skill nothing loads is dead weight.
- Write the description as a load condition ("Use before X", "Use when the user says Y"), including the phrases the user actually types.
- Keep one workflow per skill.

## Style for tracked Markdown

- One full sentence per line.
- Plain dash "-", never an em dash.
- Prefer rewriting or pruning existing lines over appending new ones.
