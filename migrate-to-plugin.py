#!/usr/bin/env python3
"""Move a machine from the old install.sh links to the hephaestus plugin.

The plugin now delivers the skills and the global rules, so the links install.sh made would load them twice.
This removes only symlinks whose target is a file of a checkout of this repo (any clone or worktree, found by
what the target folder holds, never by where this script runs); real files are never touched.
~/.claude/agent-skills-hooks is never removed here: any user or project settings file may still call it, and a
hook command whose script is gone exits 2, which Claude Code treats as "block this tool call".

Usage: python3 migrate-to-plugin.py [--dry-run]
"""
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE = Path(os.environ.get("CLAUDE_DIR", HOME / ".claude"))
DRY = "--dry-run" in sys.argv


def is_agent_skills_dir(d):
    """A checkout or plugin folder of this repo: its manifest names the plugin (hephaestus, or agent-skills before the
    rename), or it has the repo's shape."""
    try:
        if json.loads((d / ".claude-plugin" / "plugin.json").read_text()).get("name") in ("hephaestus", "agent-skills"):
            return True
    except (OSError, ValueError, AttributeError):
        pass
    return (d / "AGENTS.md").is_file() and (d / "skills" / "worktree-flow" / "SKILL.md").is_file()


def ours(link, rel):
    """True when link is a symlink to <a checkout of this repo>/<rel>, comparing path parts, not text."""
    if not link.is_symlink():
        return False
    target = Path(os.path.realpath(link))
    parts = Path(rel).parts
    if not target.exists() or target.parts[-len(parts):] != parts:
        return False
    return is_agent_skills_dir(target.parents[len(parts) - 1])


def remove(link, why):
    print(f"{'would remove' if DRY else 'removed'} {link} ({why})")
    if not DRY:
        link.unlink()


def main():
    skills = CLAUDE / "skills"
    if skills.is_dir():
        for link in sorted(skills.iterdir()):
            if ours(link, f"skills/{link.name}"):
                remove(link, "the plugin ships this skill")
    if ours(CLAUDE / "CLAUDE.md", "AGENTS.md"):
        remove(CLAUDE / "CLAUDE.md", "the plugin loads AGENTS.md at session start")
    if ours(HOME / "OPINIONS.md", "OPINIONS.md"):
        remove(HOME / "OPINIONS.md", "the session start note names the plugin's OPINIONS.md")
    if ours(CLAUDE / "agent-skills-hooks", "hooks"):
        print(f"kept {CLAUDE / 'agent-skills-hooks'}: the plugin registers the same hooks, so delete every "
              "agent-skills-hooks entry from ~/.claude/settings*.json and from each project's .claude/settings*.json "
              "(grep -rl agent-skills-hooks), then remove this link by hand.")
    print()
    print("Install the plugin in Claude Code, if you have not yet:")
    print("  /plugin marketplace add quocld/hephaestus-agent-skills")
    print("  /plugin install hephaestus@quocld")
    print("Installed under its old name agent-skills@quocld? Replace it (a project that enables it in .claude/settings.json")
    print("renames that enabledPlugins key to hephaestus@quocld):")
    print("  /plugin uninstall agent-skills@quocld")


if __name__ == "__main__":
    main()
