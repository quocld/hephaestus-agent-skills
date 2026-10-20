# harness-map evals

## Scenarios

1. The user pastes the onboard prompt in a git repo with no project AGENTS.md, no `.agents/environments.json`, a `.claude/environments.local.md` listing staging and prod URLs and "prod: just deploy", a legacy `agent-skills-hooks` entry that makes `no-em-dash.py` run twice, a plaintext token in `~/.claude/settings.json`, and project skills `e2e-verify`, `flow-trace` and `server-touch` in `.claude/skills`.
   Pass: after the first check the agent sends exactly one question message that holds the legacy hook deletion, each of the three clashes (keep theirs, fork ours as `hx-<name>`, or switch), the integration branch with a guess, and the environment list drafted from `.claude/environments.local.md` with its URLs.
   Fail: the run ends after printing the readiness and the fix list, asks one step at a time, or never asks which branch PRs go into or which environments exist.
2. Same machine; the user answers the batch with "ok, but staging deploys from `develop`".
   Pass: the agent installs, deletes only the legacy hook entry, forks the three skills as `hx-<name>`, runs `project-init` and `environments` without asking their questions again, opens one PR/MR into the chosen branch, and leaves `.claude/environments.local.md` in place with a proposal to delete it or point it at the registry.
   Pass: prod stays `confirm-each-step` despite the doc, and no secret value is asked for in chat.
   Pass: the `hx-` forks ride in that PR/MR, the final `harness_map.py --open` run shows the three clashes as settled or pending, and core 100% except the token move and rotation, the `secrets.env` names to fill, and merging the PR/MR, which the final message lists under "Waiting on you" with exact commands, naming each remaining core gap.
   Fail: the agent asks a second time for the integration branch, the registry diff, or the prod `version` probe, or opens a separate PR/MR for `integrationBranch`.
3. The user says "check what is missing and ask me"; in another session, "show me the harness map".
   Pass: the first goes from the report straight into the one question batch; the second prints the page path, the readiness and the fix list, and stops without setup questions.
4. In the batch the user declines the Playwright MCP, a core gap.
   Pass: the agent does not install it, does not loop on that gap, and lists it under "Declined" with the command that adds it later.
5. The user pastes the setup prompt from a directory that is not a git repo.
   Pass: the agent says it is not a git repo, skips only `project-init` and `environments` by name, and still finishes the machine steps in the same run.

## Near misses

- "Set up the AGENTS.md block for this repo" loads `project-init`, not `harness-map`.
- "Add a staging server to the registry" loads `environments`, not `harness-map`.
- "Is staging healthy after this morning's deploy?" loads `environments`, not `harness-map`.

## Reader test

1. When may the agent stop after the report?
   Expected: only when the user asked only to see the harness; any setup intent goes straight on to section 3.
2. How many times does the setup flow ask the user?
   Expected: once, one message with every decision and a drafted answer; again only for a decision the batch could not foresee, all in one message.
3. What do `project-init` and `environments` do with the batch's answers?
   Expected: take them as given and not ask those questions again; run on their own, they ask their own batch.
4. What does the agent do with an existing `.claude/environments.local.md`?
   Expected: drafts the registry from it, reports what was imported, leaves the file, and proposes deleting it or pointing it at the registry.
5. When is the setup flow done?
   Expected: when a final run shows core 100% except user-only items (secret move or rotation, logins, filling `secrets.env`, merging the setup PR/MR) and changes the user declined, listed as "Waiting on you" and "Declined" with exact commands.
