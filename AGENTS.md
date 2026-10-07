# Global agent instructions

Common instructions for my agents across all projects and harnesses.

## General guidelines

- Never use the em dash "—". Use a plain dash "-" instead.
- Never manually modify CHANGELOG.md or any file marked as auto-generated. Regenerate it with its tool instead.
- When writing or substantially editing long Markdown files, put each full sentence on its own line.
  Keep normal Markdown structure, but do not wrap multiple sentences onto one physical line.
- When making technical decisions, do not give much weight to development cost.
  Prefer quality, simplicity, robustness, scalability, and long-term maintainability.
- For one-off or infrequent operational work, take the simplest direct end-to-end path.
  Do not build wrappers, control planes, or automation until a concrete blocker or repeated need justifies it.
- Gather evidence (search, grep, run tests, run the app) before claiming something is true. If you are not sure, say so.
- Make reasonable calls on obvious or reversible decisions instead of asking. Ask only when the tradeoff is subjective, risky, or hard to undo.
- Never publish, push, open PRs, or cause other external side effects without explicit consent for that action.

## Bugs, testing, and quality

- When fixing a bug, first reproduce it end-to-end, as close to how a real user hits it as possible. See the `bugfix` skill.
- Prefer end-to-end tests that mirror real user behavior over unit tests as proof that a feature works.
  Self-written unit tests are not proof of done.
- When end-to-end testing a product, be picky about the UI and obsessed with pixel perfection.
  If something clearly looks off, fix it along the way, even if it is unrelated to the current task.
- Apply the same standard to lint errors, failing tests, and flaky tests: if you see one, get it fixed, even if you did not cause it.
- Match validation rigor to stakes, not to task size. Changes that could go badly wrong get an independent review (see the `review` skill).

## Context and multi-agent work

- Before using any feature that spawns a large swarm of subagents ("workflows", "ultra" modes), explain the tradeoffs and ask for explicit approval.
- Before a long session ends or gets compacted, save decisions, learnings, and open TODOs to disk (see the `handoff` skill).

## Opinions

When the work would benefit from my viewpoints on engineering and product, read `~/OPINIONS.md` (template in this repo).

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
Keep entries concise.
