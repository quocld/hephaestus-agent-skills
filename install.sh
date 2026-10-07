#!/usr/bin/env bash
# Symlink this repo into ~/.claude so edits here apply everywhere.
# Existing files that are not our symlinks are backed up to <file>.bak-<timestamp>.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
TS="$(date +%Y%m%d%H%M%S)"

link() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ]; then
    rm "$dst"
  elif [ -e "$dst" ]; then
    mv "$dst" "$dst.bak-$TS"
    echo "backed up $dst -> $dst.bak-$TS"
  fi
  ln -s "$src" "$dst"
  echo "linked $dst -> $src"
}

# Global instructions: Claude Code reads ~/.claude/CLAUDE.md
link "$REPO/AGENTS.md" "$CLAUDE_DIR/CLAUDE.md"

link "$REPO/OPINIONS.md" "$HOME/OPINIONS.md"

# Skills
for dir in "$REPO"/skills/*/; do
  name="$(basename "$dir")"
  link "${dir%/}" "$CLAUDE_DIR/skills/$name"
done
