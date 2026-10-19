# knowledge-placement evals

## Scenarios

1. In a project repo, the user says: "Add a rule: never use raw SQL in handlers."
   Pass: the rule becomes a project check in that project's `.agents/checks/` per `verify-loop` section 4, not a line in `AGENTS.md`.
2. The user says: "Remember that deploys to staging need the VPN."
   Pass: the agent walks the decision tree, stops at the first yes (a nameable situation, so the deploy skill, with an `AGENTS.md` pointer only if an always-loaded rule must name it), and says which tier it chose and why.
3. The user says: "Make sure nobody ever pushes to main again."
   Pass: a hook script in `hooks/`, registered in `hooks/hooks.json`, with cases in `hooks/test.sh` and the mounted-and-fails test; one prose line names the hook.
4. The agent edits the steps of an existing skill to fix a gap a user hit.
   Pass: it snapshots the skill first, runs red against the snapshot and green against the edit with one fresh subagent each, uses or creates that skill's evals file, and puts the results in the PR/MR body, not the repo.
5. While editing `AGENTS.md`, the agent wants to restate the worktree naming format already owned by `worktree-flow`.
   Pass: it writes a one-line cross-reference to `worktree-flow` instead of a copy.

## Near misses

- "Remember my preferred editor theme" is a Claude Code setting, handled by `update-config`, not `knowledge-placement`.
- "Write the PR description for this branch" is task evidence, owned by `worktree-flow` section 4, not `knowledge-placement`.
- "Review this skill change for bugs" loads `fresh-review`, not `knowledge-placement`.

## Reader test

1. Where does a rule that a script can check on every tool call go?
   Expected: a hook in `hooks/`, registered in `hooks/hooks.json`, with cases in `hooks/test.sh`.
2. What may a skill's description say?
   Expected: only when to load it, starting with "Use when" or "Use before", never what it does or how.
3. How many subagents does a skill test use?
   Expected: one fresh subagent per side, red and green, never a swarm.
4. Which edits need no red/green run?
   Expected: an edit that changes no instruction, such as a typo, a link fix, or a trim whose diff shows no rule changed.
5. How many green iterations before reporting the remaining gaps?
   Expected: at most 3.
