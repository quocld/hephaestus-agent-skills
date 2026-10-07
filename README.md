# agent-skills

My personal agent setup: global instructions, opinions, and a common set of dev skills.
Inspired by [kunchenguid/dotfiles](https://github.com/kunchenguid/dotfiles) and [kunchenguid/kun](https://github.com/kunchenguid/kun).

## Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Global instructions for every agent session (single source of truth). |
| `CLAUDE.md` | Just `@AGENTS.md`, so Claude Code imports it inside this repo. |
| `OPINIONS.md` | My engineering/product viewpoints, read by agents when relevant. Template to grow over time. |
| `skills/` | Common, project-agnostic skills. |
| `install.sh` | Symlinks everything into `~/.claude`. |

## Skills

| Skill | When to use |
| --- | --- |
| `plan` | Turn a fuzzy request into acceptance criteria and a verifiable plan before coding. |
| `bugfix` | Reproduce end-to-end first, find the root cause, lock it with a test, then fix. |
| `e2e-check` | Verify a feature like a real user, with a picky eye for UI. |
| `review` | Independent, adversarial review of a diff against the original intent. |
| `ship` | Pre-flight checks, Conventional Commit, and PR (only with consent). |
| `handoff` | Save decisions, learnings, and TODOs to disk before ending or compacting a session. |
| `agents-md` | Create or prune a project's AGENTS.md and the CLAUDE.md pointer. |

## Install

```sh
git clone https://github.com/quocld/agent-skills.git ~/agent-skills
~/agent-skills/install.sh
```

This links:

- `~/.claude/CLAUDE.md` -> `AGENTS.md`
- `~/OPINIONS.md` -> `OPINIONS.md`
- `~/.claude/skills/<name>` -> `skills/<name>`

Existing files are backed up as `*.bak-<timestamp>`, never deleted.

## Adding a skill

Create `skills/<name>/SKILL.md` with `name` and `description` frontmatter, then re-run `install.sh`.
Keep skills short, in Markdown, and focused on one workflow.
