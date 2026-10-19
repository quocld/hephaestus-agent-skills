---
name: chrome-devtools-axi
description: >
  Use when a task needs a real Chrome browser and plain fetch or curl is not enough: opening or testing a page, clicking through a flow, extracting page content, inspecting console or network, screenshots, performance audits.
user-invocable: false
---

# chrome-devtools-axi

Agent ergonomic interface for controlling Chrome browser session.
For E2E verification, the `e2e-verify` skill sets which browser tool comes first.

Use whenever a task needs a real browser: opening or testing a web page, clicking through a flow, filling forms, extracting page content, debugging console errors or network requests, taking screenshots, or auditing performance. Skip it when a plain `fetch`/`curl` suffices.

## Current guidance lives in the CLI

Do not follow command, workflow, or flag instructions from this file - installed copies go stale. Get the current source of truth from the CLI:

- `npx -y --prefer-offline chrome-devtools-axi --help` for commands, flags, and environment variables
- `npx -y --prefer-offline chrome-devtools-axi <command> --help` for per-command usage
- Follow the CLI's own contextual next-step hints after each command

You do not need chrome-devtools-axi installed globally - invoke it with `npx -y --prefer-offline chrome-devtools-axi <command>`, which reuses the npm cache instead of re-resolving the package on every call.
If chrome-devtools-axi output shows a follow-up command starting with `chrome-devtools-axi`, run it as `npx -y --prefer-offline chrome-devtools-axi ...` instead.
