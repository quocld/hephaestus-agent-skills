Install Hephaestus Skills (https://github.com/quocld/hephaestus-agent-skills) for yourself, the coding agent reading this, then help me finish the setup.

1. Tell me which harness you run in (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot, or another).
2. Before installing anything, take stock of the harness this machine and this project already have: global and project rules (`AGENTS.md`, `CLAUDE.md` and the like), skills (user, project and plugin skills), hooks and permission settings, installed plugins and MCP servers, and an existing Hephaestus install (old `install.sh` links or an earlier plugin). Show me the list.
3. Compare it with Hephaestus and never overwrite what exists. For each overlap:
   - Identical to ours: skip it.
   - Same name or same job but different (a skill, a hook, a rule file): keep the existing one active and fork ours next to it as `hx-<name>` (for example `skills/hx-worktree-flow/`), then tell me what differs.
   - A rule that contradicts ours (which branch PRs target, commit attribution, push or deploy rules): the project's rule wins inside this project; note the contradiction.
   - An earlier Hephaestus install: upgrade it in place instead of adding a second copy.
   Then ask me, item by item, whether to keep the existing one, switch to ours, or merge the two.
4. Claude Code: install the plugin with `claude plugin marketplace add quocld/hephaestus-agent-skills` and `claude plugin install agent-skills@quocld` (or ask me to run `/plugin marketplace add quocld/hephaestus-agent-skills` and `/plugin install agent-skills@quocld`), then tell me to start a new session. It brings the skills, the safety hooks and the global rules; a forked skill goes in the project's `.claude/skills/hx-<name>/`.
5. Any other harness: clone the repo to `~/.hephaestus-skills` (or `git pull` it if it is already there), then wire it the way your harness loads instructions and skills:
   - Global rules: load the clone's `AGENTS.md` as your global instructions. Add a reference to it in your global instructions file or setting; never overwrite a file that already has content.
   - Skills: make every `skills/<name>/SKILL.md` available the way your harness loads skills, using the `hx-` forks from step 3 where names clash. If it has no skills feature, add one line per skill (name, description, path) to your instructions and read a skill's `SKILL.md` before any task its description matches.
   - Hooks: `hooks/` holds Claude Code hooks (no em dash in writes, ask before pushing or merging to protected branches). Wire them only if your harness has an equivalent pre-tool hook; otherwise tell me those rules stay advisory.
6. Show me every file you will create or change outside the clone before you change it, and wait for my yes.
7. When it is installed, run the harness-map skill (`python3 <the clone or plugin>/skills/harness-map/scripts/harness_map.py --open`), show me what is still missing or clashing, and walk me through it one step at a time.
