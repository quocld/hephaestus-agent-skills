---
name: knowledge-placement
description: >
  Use before editing AGENTS.md or CLAUDE.md, before creating or editing a skill, or when asked to "remember this for the project", "add a rule", "thêm rule", "viết skill".
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

## Writing or editing a skill

- A skill nothing loads is dead weight; keep one workflow per skill.
- The description says only when to load the skill, never what it does or how: start with "Use when" or "Use before", list the situations, symptoms, and phrases the user types (in every language they use), in the third person, under about 500 characters.
  A description that summarizes the workflow gets followed instead of the body.
- The body opens with one or two lines on why the skill exists, then the steps.
  Refer to other skills by name (`root-cause`), never by `@` path, which force-loads the file.
- Pick the form from the failure you observed:
  - A rule skipped under pressure: a plain prohibition plus the excuses it closes.
  - Output in the wrong shape: a recipe saying what the output is, part by part, in order.
  - A required part left out: a required slot in the template the agent fills in.
  - Behavior that depends on a condition: a conditional on something observable.
  Never add "unless it matters" clauses; state a real exception as its own conditional.
- What a script or schema can check gets the script or schema, not prose.
- Exact flags and long references go in a `references/` file or a script's `--help`; call bundled scripts through their interpreter (`bash scripts/x.sh`), since packagers can drop executable bits.
- Test before shipping, red then green:
  1. Red: give a fresh subagent realistic scenarios that tempt the failure, without the skill, and record what it does.
     If it already behaves, there is nothing to write.
  2. Green: run the same scenarios with the skill, plus a fresh reviewer hunting contradictions, unfollowable steps, and gaps; fix and rerun until clean.
  Every edit to an existing skill gets at least the green run.

## Style for tracked Markdown

- One full sentence per line.
- Plain dash "-", never an em dash.
- Prefer rewriting or pruning existing lines over appending new ones.
