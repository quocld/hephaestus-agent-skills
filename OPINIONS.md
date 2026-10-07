# OPINIONS.md

A compact map of my engineering and product viewpoints, written for LLM context.
Agents read this when a decision would benefit from knowing how I think.
Each section: a viewpoint as the heading, a few sentences of reasoning, optional evidence links.
See `reference/opinions-example.md` for a mature example of this format.

## Engineering

### Code is rarely the real bottleneck

The hard parts are deciding what is worth building and proving that it works.
End-to-end checks that mirror a real user are the strongest proof; self-written unit tests are not.

### Simple beats clever

Prefer boring, maintainable solutions over clever ones, and simplify before adding machinery.

## Working with agents

### I stay accountable for what ships

AI is a tool; I review and approve every change it makes.
Changes where mistakes are costly get an independent review before a PR.

### Durable state lives on disk

Specs, AGENTS.md, and handoff notes outlive any single session's memory.

## Product and UX

### Polish matters

If the UI looks off, it is off; fix it along the way.

## Stack preferences

TODO: languages, frameworks, and libraries I prefer or avoid, and why.
