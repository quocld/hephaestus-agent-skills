# agent-skills

Kun Chen's ([@kunchenguid](https://github.com/kunchenguid)) full public agent setup, collected in one place so I can install it and improve on it.

## Layout

| Path | Source | Purpose |
| --- | --- | --- |
| `AGENTS.md` | [dotfiles/home/AGENTS.md](https://github.com/kunchenguid/dotfiles/blob/main/home/AGENTS.md) | Global agent instructions. |
| `CLAUDE.md` | dotfiles | Just `@AGENTS.md`. |
| `skills/` | see `skills.manifest` | Kun's skills, vendored (MIT). |
| `LICENSES/` | each source repo | License of every vendored repo. |
| `vendor/kun/` | [kunchenguid/kun](https://github.com/kunchenguid/kun) | `OPINIONS.md`, `VOICE.md`, `TOOLS.md`, `ENTRY.md`, `/kun` skill. Upstream has no license, so keep this repo private. |

## Skills

| Skill | From | What it does | Needs |
| --- | --- | --- | --- |
| `no-mistakes` | no-mistakes | Push through an AI review/test/lint gate before opening a clean PR. | `no-mistakes` CLI |
| `gnhf` | gnhf | Overnight autonomous loop: one small committed change per iteration. | `gnhf` CLI |
| `vision` | vision | Mine repo history into a VISION.md, stress-test it, review on an HTML board. | - |
| `stow` | firstmate | Save session state durably so a restart is a non-event. | - |
| `firstmate-coding-guidelines` | firstmate | Kun's coding guidelines for crewmate agents. | - |
| `compact-adviser` | compact-adviser | Advise when it is safe to compact context. | `compact-adviser` |
| `axi` | axi | Design principles for agent-ergonomic CLIs/tools. | - |
| `gh-axi` | gh-axi | GitHub via the agent-friendly `gh-axi` CLI. | `gh-axi` |
| `chrome-devtools-axi` | chrome-devtools-axi | Browser automation for agents. | `chrome-devtools-axi` |
| `tasks-axi` | tasks-axi | Task/backlog management for agents. | `tasks-axi` |
| `quota-axi`, `quota-interpretation` | quota-axi | Read LLM subscription quota windows and reason about them. | `quota-axi` |
| `lavish` | lavish-axi | Turn plans/diagrams/reports into reviewable HTML artifacts. | `lavish-axi` (npx) |
| `lavish-session` | grok-ship | Lavish review session variant used by the grok-ship factory. | `lavish-axi` |
| `adversarial-review` | grok-ship | Fresh-subagent adversarial review before any PR. | - |
| `ahoy`, `project-management` | grok-ship | Firstmate-style session kickoff and project tracking. | - |
| `vision-md-triage-verdict`, `triage-eligible-fetch`, `14-day-stale-pr-close` | grok-ship | Triage incoming issues/PRs against VISION.md, close stale PRs. | `gh`, python3 |
| `whathappened` | whathappened | Adaptive X briefing: what happened, opinions, debates. | X access |
| `shorts-from-longform` | short-pipe | Cut shorts from long-form video. | short-pipe |
| `use-kunchenguid-design-system` | kunchenguid-design-system | Kun's personal design system. | - |
| `kun` | kun (vendor) | `/kun` - answer the way Kun thinks, from his OPINIONS/TOOLS/VOICE. | node |

Repo-internal skills under each project's `.agents/skills/` (e.g. no-mistakes daemon internals, firstmate crew ops) are left out because they only make sense inside those repos.

## Install

```sh
git clone https://github.com/quocld/agent-skills.git ~/agent-skills
cd ~/agent-skills
./sync.sh      # refresh skills from upstream + fetch vendor/kun
./install.sh   # symlink into ~/.claude and ~
```

`install.sh` links `~/.claude/CLAUDE.md` -> `AGENTS.md`, `~/OPINIONS.md`, `~/VOICE.md`, and every skill into `~/.claude/skills/`.
Existing files are backed up as `*.bak-<timestamp>`, never deleted.

## Updating from upstream

Edit `skills.manifest` to add or drop skills, then run `./sync.sh` and commit.
`sync.sh` overwrites `skills/`, `LICENSES/`, and `AGENTS.md` with upstream, so put my own changes in separate files (or a fork section) rather than editing vendored skills in place.
