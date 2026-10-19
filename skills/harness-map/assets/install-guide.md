# Install Hephaestus Skills

This guide is for the coding agent (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot, or another) that the user asked to install [Hephaestus Skills](https://github.com/quocld/hephaestus-agent-skills) for itself.
Follow it step by step, in order. Talk to the user in their language.

## 1. Name your harness

Tell the user which harness you run in.

## 2. Take stock of what already exists

Before installing anything, list the harness this machine and this project already have:

- Global and project rules: `AGENTS.md`, `CLAUDE.md` and the like
- Skills: user, project and plugin skills
- Hooks and permission settings
- Installed plugins and MCP servers
- An earlier Hephaestus install: old `install.sh` links or an earlier plugin

Show the user the list.

## 3. Never overwrite: fork what clashes

Compare that list with Hephaestus. For each overlap:

- **Identical to ours:** skip it.
- **Same name or same job but different** (a skill, a hook, a rule file): keep the existing one active and fork ours next to it as `hx-<name>` (for example `skills/hx-worktree-flow/`), then tell the user what differs.
- **A rule that contradicts ours** (which branch PRs target, commit attribution, push or deploy rules): the project's rule wins inside this project; note the contradiction.
- **An earlier Hephaestus install:** upgrade it in place instead of adding a second copy.

Then ask the user, item by item, whether to keep the existing one, switch to ours, or merge the two.

## 4. Install in Claude Code

Run:

```text
claude plugin marketplace add quocld/hephaestus-agent-skills
claude plugin install agent-skills@quocld
```

Or ask the user to run `/plugin marketplace add quocld/hephaestus-agent-skills` and `/plugin install agent-skills@quocld`.
Then tell them to start a new session.
The plugin brings the skills, the safety hooks and the global rules; a forked skill goes in the project's `.claude/skills/hx-<name>/`.

## 5. Install in any other harness

Clone the repo to `~/.hephaestus-skills` (or `git pull` it if it is already there), then wire it the way your harness loads instructions and skills:

- **Global rules:** load the clone's `AGENTS.md` as your global instructions. Add a reference to it in your global instructions file or setting; never overwrite a file that already has content.
- **Skills:** make every `skills/<name>/SKILL.md` available the way your harness loads skills, using the `hx-` forks from step 3 where names clash. If your harness has no skills feature, add one line per skill (name, description, path) to your instructions and read a skill's `SKILL.md` before any task its description matches.
- **Hooks:** `hooks/` holds Claude Code hooks (no em dash on changed lines, ask before pushing or merging to protected branches). Wire them only if your harness has an equivalent pre-tool hook; otherwise tell the user those rules stay advisory.

## 6. Ask before you change

Show the user every file you will create or change outside the clone before you change it, and wait for their yes.

## 7. Finish the setup

When it is installed, run the harness-map skill:

```text
python3 <the clone or plugin>/skills/harness-map/scripts/harness_map.py --open
```

Show the user what is still missing or clashing, and walk them through it one step at a time.
