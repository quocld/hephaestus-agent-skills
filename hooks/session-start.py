#!/usr/bin/env python3
"""SessionStart hook: give every session the global rules from this plugin's AGENTS.md.

A plugin cannot write ~/.claude/CLAUDE.md, so the rules arrive as session context instead: whatever this prints,
Claude Code adds to the session. It stays quiet about the rules when they are already loaded (a legacy
~/.claude/CLAUDE.md link to the same text, or a session inside this repo, whose CLAUDE.md imports AGENTS.md),
and always names the OPINIONS.md path, which AGENTS.md points to. Never fails the session start.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def same_text(path, text):
    try:
        return path.exists() and path.read_text().strip() == text.strip()
    except OSError:
        return False


def main():
    try:
        rules = (ROOT / "AGENTS.md").read_text()
    except OSError:
        return
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    loaded = same_text(Path.home() / ".claude" / "CLAUDE.md", rules) or same_text(project / "AGENTS.md", rules)
    if not loaded:
        print("Global rules from the agent-skills plugin (its AGENTS.md). They apply to every session, like ~/.claude/CLAUDE.md:")
        print()
        print(rules.strip())
        print()
    print(f"agent-skills OPINIONS.md (the viewpoints AGENTS.md refers to): {ROOT / 'OPINIONS.md'}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - a broken hook must never block a session from starting
        pass
    sys.exit(0)
