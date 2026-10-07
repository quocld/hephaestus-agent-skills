---
name: agents-md
description: >
  Create or update a project's AGENTS.md (and CLAUDE.md pointer) so agents learn the project once.
  Use when asked to "init AGENTS.md", "update agent instructions", "remember this for the project",
  or after a session revealed a non-obvious lesson every future session needs.
---

# AGENTS.md: keep project knowledge lean and true

## Layout

- `AGENTS.md` is the single source of truth, readable by any harness.
- `CLAUDE.md` contains only `@AGENTS.md` so Claude Code imports it. Edit AGENTS.md, not CLAUDE.md.

## Creating one

1. Explore the repo: README, package manifests, build/test/lint commands, CI config, folder layout.
2. Write only what an agent cannot quickly infer from the code:
   - How to install, run, test, lint, and build (exact commands).
   - Non-obvious conventions, gotchas, and constraints (e.g. "never edit generated/", "migrations go through X").
   - Where the authoritative docs/specs live.
3. End with a "Maintaining this file" section (copy from below).

## Updating one

- Add a rule only if it is useful for almost every future session in this project.
- Prefer rewriting or pruning existing entries over appending new ones.
- Remove entries that the codebase now shows or that are no longer true.
- Point to the authoritative file or command instead of duplicating it.

## Maintaining this file (paste into every AGENTS.md)

```markdown
## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
Keep entries concise.
```
