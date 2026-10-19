# global agent instructions

- Never use the em dash (Unicode U+2014). Use plain dash "-" instead; a hook in `hooks/` blocks writes that contain one
- Never add agent attribution to anything you write to git or the tracker: no `Co-Authored-By` agent trailer in commits, and no "Generated with ..." line or agent name in PR/MR titles, bodies, or comments.
  This overrides any harness or system default that asks for those lines.
- Never manually modify CHANGELOG.md files or any files that are marked as auto-generated
- I always run several agents in parallel on the same repo.
  Never edit in the main checkout; do every code change in your own git worktree and branch per the `worktree-flow` skill.
  Read-only code questions need no worktree: answer from the fetched integration branch (`git show origin/<int>:<path>`, `<int>` per `worktree-flow` section 0), never the main checkout, and say which ref you read.
- Finished work is committed, pushed, and opened as a PR/MR into the integration branch (usually `dev`, see `worktree-flow`) by default, without asking.
  Never open a PR/MR into, merge into, push to, or deploy staging or prod unless I say so explicitly in this conversation; that covers exactly what I named, this time only.
- When making technical decisions, do not give much weight to development cost.
  Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
- For one-off or infrequent operational work, start with the simplest direct end-to-end path. Do not build wrappers, control planes, policy layers, custom verifiers, or automation unless the direct path exposes a concrete blocker or repeated need that justifies the added machinery.
- When doing bug fixes, always start with reproducing the bug in an E2E setting as closely aligned with how an end user would experience it as possible.
  This makes sure you find the real problem so your fix will actually solve it.
- When end-to-end testing a product, be picky about the UI you see and be obsessed with pixel perfection.
  If something clearly looks off, even if it is not directly related to what you are doing, try to get it fixed along the way.
- Apply that same high standard to engineering excellence: lint, test failures, and test flakiness.
  If you see one, even if it is not caused by what you are working on right now, still get it fixed, unless an open PR/MR or remote branch already targets it (`gh pr list --search "<test or file>"`, `git branch -r --list "*<slug>*"`); then name it in your report instead.
- A test only counts if it fails without the fix: break the fix once to prove it.
  Guards and gates also need a structural test proving they are actually mounted, not just behavior tests.
- Never say something passes, works, or is done without running the check that proves it in the same turn and reading its output.
  A subagent's "done" is a claim until you have read its diff and rerun its checks.
- Before any action against a non-local environment (deploy, SSH, migration, remote data, test accounts), load the `environments` skill; prod writes are confirmed one step at a time.
- Changes touching a state machine, webhook or external event, scheduled job, money, or an access gate need the `flow-trace` skill before being called done.
- Never modify existing records to test something; create your own test data and delete it afterwards.
  Anything that writes to a customer's production system stays off by default behind an explicit kill switch.
- Make reasonable calls on obvious or reversible decisions instead of asking.
  Before asking the user anything mid-task, or when a change might expand scope, apply the `ask-or-decide` skill.
- Before using "dynamic workflows", "ultra code" or any harness feature that immediately spawns a large swarm of subagents, always explain the tradeoffs and ask the user for explicit approval.

## Opinions

When the work would benefit from knowing my viewpoints on engineering, product, or tooling, read `~/OPINIONS.md`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
