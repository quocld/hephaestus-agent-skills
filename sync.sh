#!/usr/bin/env bash
# Pull Kun's skills (skills.manifest) and global docs from GitHub.
#  - MIT skills are vendored into skills/ and committed, with licenses in LICENSES/.
#  - kunchenguid/kun (no upstream license) docs and skill go to vendor/kun/. Keep this repo private.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OWNER="kunchenguid"
RAW="https://raw.githubusercontent.com/$OWNER"
cd "$REPO"

api() {
  if command -v gh >/dev/null 2>&1; then gh api "$1"; else curl -fsSL "https://api.github.com/$1"; fi
}

fetch() { # <repo> <path> <dest>
  mkdir -p "$(dirname "$3")"
  curl -fsSL "$RAW/$1/HEAD/$2" -o "$3"
}

rm -rf skills LICENSES vendor
mkdir -p skills LICENSES vendor/kun

CACHE="$(mktemp -d)"; trap 'rm -rf "$CACHE"' EXIT
while read -r repo path name; do
  [[ -z "$repo" || "$repo" == \#* ]] && continue
  name="${name:-$(basename "$path")}"
  if [[ ! -f "$CACHE/$repo" ]]; then
    api "repos/$OWNER/$repo/git/trees/HEAD?recursive=1" | jq -r '.tree[] | select(.type=="blob") | .path' > "$CACHE/$repo"
    lic="$(api "repos/$OWNER/$repo/license" 2>/dev/null | jq -r '.download_url // empty' || true)"
    [[ -n "$lic" ]] && curl -fsSL "$lic" -o "LICENSES/$repo.txt"
  fi
  count=0
  while IFS= read -r file; do
    [[ "$file" == "$path/"* ]] || continue
    fetch "$repo" "$file" "skills/$name/${file#"$path/"}"
    count=$((count + 1))
  done < "$CACHE/$repo"
  # Claude Code expects name: to match the folder; some upstream skills use display names.
  N="$name" perl -pi -e 'if (!$done && /^name:/) { $_ = "name: $ENV{N}\n"; $done = 1 }' "skills/$name/SKILL.md"
  echo "skills/$name <- $repo/$path ($count files)"
done < skills.manifest

# Global agent instructions (MIT-0)
fetch dotfiles home/AGENTS.md AGENTS.md
fetch dotfiles LICENSE LICENSES/dotfiles.txt
echo "AGENTS.md <- dotfiles/home/AGENTS.md"

# kunchenguid/kun: no license -> local only
for f in ENTRY.md TOOLS.md OPINIONS.md VOICE.md skills/kun/SKILL.md scripts/pull-kun.mjs; do
  fetch kun "$f" "vendor/kun/$f"
done
echo "vendor/kun <- kun"
