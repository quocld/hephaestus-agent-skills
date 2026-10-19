#!/usr/bin/env python3
"""Move a machine from the old install.sh links to the agent-skills plugin.

The plugin now delivers the skills, the hooks and the global rules, so the links install.sh made would load
everything twice. This removes only symlinks that point into a checkout of this repo; real files are never
touched. ~/.claude/agent-skills-hooks stays while a settings file still calls it, because a hook command whose
script is gone exits 2, which Claude Code treats as "block this tool call".

Usage: python3 migrate-to-plugin.py [--dry-run]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
HOME = Path.home()
CLAUDE = Path(os.environ.get("CLAUDE_DIR", HOME / ".claude"))
DRY = "--dry-run" in sys.argv


def common_dir(path):
    """The git common dir of the checkout holding path, so any worktree of this repo counts as this repo."""
    p = subprocess.run(["git", "-C", str(path if path.is_dir() else path.parent), "rev-parse",
                        "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


OURS = common_dir(REPO)


def ours(link, rel):
    """True when link is a symlink to <a checkout of this repo>/<rel>."""
    if not link.is_symlink():
        return False
    target = Path(os.path.realpath(link))
    root = target.parents[len(Path(rel).parts) - 1] if len(Path(rel).parts) > 1 else target.parent
    return target.as_posix().endswith(rel) and (root == REPO or common_dir(root) == OURS)


def remove(link, why):
    print(f"{'would remove' if DRY else 'removed'} {link} ({why})")
    if not DRY:
        link.unlink()


def settings_call_legacy_hooks():
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((CLAUDE / name).read_text())
        except (OSError, ValueError):
            continue
        for entries in (data.get("hooks") or {}).values():
            for e in entries or []:
                if any("agent-skills-hooks/" in (h.get("command") or "") for h in e.get("hooks") or []):
                    return CLAUDE / name
    return None


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
    hooks = CLAUDE / "agent-skills-hooks"
    caller = settings_call_legacy_hooks()
    if caller:
        print(f"kept {hooks}: {caller} still calls agent-skills-hooks. Remove those PreToolUse entries "
              "(the plugin registers the same hooks), then run this again.")
    elif ours(hooks, "hooks"):
        remove(hooks, "the plugin registers the hooks")
    print()
    print("Install the plugin in Claude Code, if you have not yet:")
    print("  /plugin marketplace add quocld/agent-skills")
    print("  /plugin install agent-skills@quocld")


if __name__ == "__main__":
    main()
