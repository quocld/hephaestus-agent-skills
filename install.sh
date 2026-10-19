#!/usr/bin/env bash
# Symlink this repo into ~/.claude so edits here apply everywhere.
# Existing files that are not symlinks move to $CLAUDE_DIR/backups/agent-skills-<timestamp>/, outside the folders Claude Code scans.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
TS="$(date +%Y%m%d%H%M%S)"
BACKUP="$CLAUDE_DIR/backups/agent-skills-$TS"

link() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ -e "$dst" ]; then
    local rel="${dst#"$HOME"/}"
    mkdir -p "$(dirname "$BACKUP/$rel")"
    mv "$dst" "$BACKUP/$rel"
    echo "backed up $dst -> $BACKUP/$rel"
  fi
  ln -s "$src" "$dst"
  echo "linked $dst -> $src"
}

# Global instructions: Claude Code reads ~/.claude/CLAUDE.md
link "$REPO/AGENTS.md" "$CLAUDE_DIR/CLAUDE.md"

link "$REPO/OPINIONS.md" "$HOME/OPINIONS.md"

# Hooks referenced from ~/.claude/settings.json (see hooks/README.md)
link "$REPO/hooks" "$CLAUDE_DIR/agent-skills-hooks"

# Skills
for dir in "$REPO"/skills/*/; do
  name="$(basename "$dir")"
  link "${dir%/}" "$CLAUDE_DIR/skills/$name"
done
