---
name: handoff
description: >
  Save durable session state to disk so the next session (or another agent) can continue without
  loss. Use before ending a long session, before compacting, when switching tasks, or when asked
  to "handoff", "lưu context", "save progress".
---

# Handoff: make restart a non-event

Compaction is lossy. Disk is durable. Write down what the next agent needs.

## Where

- Default: `HANDOFF.md` at the repo root (or the path the project already uses, e.g. `docs/handoff/`).
- Do not commit it unless the user asks; suggest adding it to `.gitignore` if it is not meant to be shared.

## What to write

```markdown
# Handoff - <task> - <YYYY-MM-DD>

## Goal
<what we are trying to achieve and why>

## Status
<done / in progress / blocked, in one or two lines>

## Decisions
- <decision> - <why>

## Learnings
- <non-obvious facts about the codebase, tools, or environment discovered this session>

## Open TODOs
- [ ] <next concrete step>

## How to resume
<commands to run, files to open first, branch name>
```

## Rules

- Be concrete: file paths, commands, branch names, ticket IDs.
- Keep it short; do not copy code or the whole transcript.
- If a learning is useful for almost every future session, propose adding it to AGENTS.md instead (see the `agents-md` skill).
