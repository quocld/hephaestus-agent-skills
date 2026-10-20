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
- An earlier Hephaestus install: old `install.sh` links, or the plugin under its old id `agent-skills@quocld`

Show the user the list.

## 3. Never overwrite: fork what clashes

Compare that list with Hephaestus. For each overlap, draft the answer you will propose in step 5:

- **Identical to ours:** skip it.
- **Same name or same job but different** (a skill, a hook, a rule file): keep the existing one active and fork ours next to it as `hx-<name>` (for a project skill, `.claude/skills/hx-worktree-flow/` in the project's setup PR/MR), then tell the user what differs.
- **A rule that contradicts ours** (which branch PRs target, commit attribution, push or deploy rules): the project's rule wins inside this project; note the contradiction.
- **An earlier Hephaestus install:** upgrade it in place instead of adding a second copy; the old plugin id `agent-skills@quocld` is replaced by `hephaestus@quocld` (uninstall the old one, and rename a project's `enabledPlugins` key in the setup PR/MR).

Do not ask yet: every question goes in the one batch of step 5.

## 4. Run the check

Clone the repo to `~/.hephaestus-skills` (or `git pull` it if it is already there), then run its harness check from the directory the user started you in:

```text
python3 ~/.hephaestus-skills/skills/harness-map/scripts/harness_map.py --open
```

It only reads; it shows what is set up, missing or clashing on this machine and in the current project.
If the current directory is not a git repo, say so: the project steps (`project-init`, `environments`) are skipped, by name, and everything else still runs.

## 5. Ask once, then do everything

This is a setup request: never stop after the check.
Draft every decision the whole setup needs, as the harness-map skill's setup flow lists them (`skills/harness-map/SKILL.md` in the clone, section 3, steps 2 and 3), and ask them all in one message with your drafted answers shown:

- The install: every file you will create or change outside the clone, and the commands of step 6 or 7.
- Each clash from step 3: keep theirs and fork ours as `hx-<name>`, switch to ours, or merge.
- A legacy hook entry that would run a gate twice: delete it, yes or no.
- The plugin under its old id `agent-skills@quocld`: replace it with `hephaestus@quocld`, yes or no.
- Which branch PRs go into (your guess shown; `dev` or `main` only when the user chooses it).
- Which environments exist (local or dev, staging, prod, any other), each with its URL, drafted from the repo: environment docs such as `.claude/environments.local.md`, `.env*.example`, `.vercel/`, `supabase/`, CI and deploy scripts.
- Whether to run the `version` and `verify` probe on prod once (default no).
- The tracker, test account roles and logins (never passwords), and which optional items the user wants.
- What will be waiting on the user: secrets to move and rotate (one in the global settings is a machine item every project sees, never this project's need), logins, the `.agents/secrets.env` names to fill in the file, never in chat.

After the answer, do everything below in this same run without asking again.

## 6. Install in Claude Code

Run:

```text
claude plugin marketplace add quocld/hephaestus-agent-skills
claude plugin install hephaestus@quocld
```

Or ask the user to run `/plugin marketplace add quocld/hephaestus-agent-skills` and `/plugin install hephaestus@quocld`.
The plugin brings the skills, the safety hooks and the global rules; a forked project skill goes in the project's `.claude/skills/hx-<name>/` through the setup PR/MR of step 8, never straight into the main checkout.
A new session picks the plugin up; until then, read each skill from the clone (`~/.hephaestus-skills/skills/<name>/SKILL.md`) and go straight on with step 8 in this session.

## 7. Install in any other harness

Wire the clone the way your harness loads instructions and skills:

- **Global rules:** load the clone's `AGENTS.md` as your global instructions. Add a reference to it in your global instructions file or setting; never overwrite a file that already has content.
- **Skills:** make every `skills/<name>/SKILL.md` available the way your harness loads skills, using the `hx-` forks from step 3 where names clash. If your harness has no skills feature, add one line per skill (name, description, path) to your instructions and read a skill's `SKILL.md` before any task its description matches.
- **Hooks:** `hooks/` holds Claude Code hooks (no em dash on changed lines, ask before pushing or merging to protected branches). Wire them only if your harness has an equivalent pre-tool hook; otherwise tell the user those rules stay advisory.

## 8. Finish the setup in the same run

Carry on with the harness-map skill's setup flow from its section 3 step 4, with the answers from step 5: hooks, tools, then `project-init` and `environments` for the current git repo in one worktree, ending as one PR/MR into the branch the user chose (with the project's `hx-` forks), then the optional items they picked.
`project-init` and `environments` take the batch's answers as given and do not ask them again; `environments` imports an existing environment doc into `.agents/environments.json` and says what it took from where.
It then creates `.agents/secrets.env` with empty values; the user fills it in the file, never in chat, and the Dashboard's environment cards show each name still missing.

The setup is done only when a final check shows core 100%, except what only the user can do (moving or rotating a secret, a login, filling `.agents/secrets.env`, merging the setup PR/MR) and changes the user declined in step 5.
End with those as "Waiting on you" and "Declined", each with its exact command, and show that every core gap left on the page is in one of them.
