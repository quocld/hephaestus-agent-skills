---
name: plan
description: >
  Turn a fuzzy request into a clear, verifiable plan before coding. Use for new features,
  non-trivial changes, "lên plan", "plan this", or when requirements are unclear.
---

# Plan: intent first, then a verifiable plan

## 1. Understand the intent

- Restate the goal in one or two sentences: who it is for and what changes for them.
- Read the relevant code, docs, and specs before proposing anything. Ground the plan in what exists.
- Ask a few anchoring questions only where the answer would change the design. For everything else, make a reasonable call and list it as an assumption.

## 2. Define done

- Write acceptance criteria as observable behavior ("user can X and sees Y"), not implementation steps.
- Decide how each criterion will be verified, preferably end-to-end.

## 3. Design

- Pick the simplest design that meets the criteria and stays maintainable. Do not weigh development cost heavily; weigh quality and long-term cost.
- Note alternatives you rejected in one line each, with the reason.
- List affected files/modules, data/schema changes, and migration or rollout concerns.

## 4. Break it down

- Ordered steps, each small enough to verify on its own.
- Mark risky steps and what could go wrong.

## Output

A short plan: Goal, Assumptions, Acceptance criteria, Design, Steps, Risks, Open questions.
Wait for approval before implementing if the user asked for a plan only.
