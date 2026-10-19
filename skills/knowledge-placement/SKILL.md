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

1. Is it mechanically checkable on every tool call (a banned character, a banned command, a protected branch)?
   -> A Claude Code hook registered in `~/.claude/settings.json`, its script kept in this repo's `hooks/` folder.
   The prose keeps one line naming the hook, so an agent knows why a call was blocked; prose alone gets skipped under pressure.
   A hook is a guard, so it needs the mounted-and-fails test from AGENTS.md.
2. Is it a rule about code in one project that a diff can be checked against (a migration needs a backfill, no raw SQL in handlers)?
   -> A project check in that project's `.agents/checks/`, per `verify-loop` section 4, which runs it before every PR/MR.
3. Does an agent need it on almost every session to operate?
   -> `AGENTS.md`, inline, a line or two.
4. Is it needed only in a nameable situation (a deploy, a migration, a release, a specific workflow)?
   -> A skill whose description states that trigger.
   Add a one-line pointer to AGENTS.md only if an always-loaded rule must name the skill.
5. Is it product, setup, or user reference?
   -> README or user-facing docs.
6. Is it architecture a maintainer needs (ownership, boundaries, extension points, rationale)?
   -> Architecture docs.
7. Is it exact mechanics (flags, commands, paths)?
   -> The script's header comment and its `--help`, not prose elsewhere.
8. Is it task evidence (chronology, failed hypotheses, temp paths, delivery proof)?
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
- Test before shipping, red then green, with the same 3-5 scenarios on both sides and one fresh subagent per side; never a swarm for a skill test.
  1. Red: give a fresh subagent realistic scenarios that tempt the failure, without the skill, and record what it does.
     When editing an existing skill, first snapshot it (`cp -r skills/<name> <scratchpad>/<name>-old`) and run red against the snapshot, so red compares old against new.
     If it already behaves, there is nothing to write.
  2. Green: run the same scenarios with the skill in one fresh subagent whose prompt also asks it to hunt contradictions, unfollowable steps, and gaps, and to answer the reader-test questions below when they apply.
     Fix and rerun at most 3 green iterations, then report the remaining gaps instead of looping.
  Every edit that changes an instruction gets at least the green run.
  An edit that changes no instruction (a typo, a link fix, a trim whose diff shows no rule changed) needs no run.
- Add 2-3 near-miss phrases to the scenarios: requests that share keywords with the description but need something else; the skill must not load for them.
- Judge from the subagent's transcript or reasoning, not only its final answer; a right answer reached by skipping a step is a failure.
- If the runs keep writing the same helper script, bundle it in the skill's `scripts/` and point the steps at it.
- A green on a weak check is worse than none: when a scenario was trivially satisfied, or the old version passes it too, say so and replace it.
- For a document agents read (AGENTS.md, a `project-init` block, a skill body), add a reader test: 3-5 questions a future agent would need answered from the document alone, folded into the green subagent's prompt, or given to one fresh subagent when there is no green run; fix the document until every answer is correct, within the same 3-iteration cap.

## Style for tracked Markdown

- One full sentence per line.
- Plain dash "-", never an em dash.
- Prefer rewriting or pruning existing lines over appending new ones.
