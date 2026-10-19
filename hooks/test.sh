#!/usr/bin/env bash
# Pipe allow, ask and deny payloads through both hooks, then check that settings.json registers them.
# Exits non-zero on any mismatch. Builds its own throwaway repos and never touches a remote.
set -euo pipefail

HOOKS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
TMP="$(mktemp -d "${TMPDIR%/}/hooks-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
FAIL=0
EM="$(python3 -c 'print(chr(8212))')"

# A main checkout and a worktree on a feature branch.
MAIN="$TMP/repo"
FEAT="$TMP/feature-wt"
git init -q -b main "$MAIN"
git -C "$MAIN" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$MAIN" worktree add -q -b feature "$FEAT"

# decision <hook> <payload json> prints allow, ask or deny.
decision() {
  local out
  out="$(printf '%s' "$2" | python3 "$HOOKS/$1")"
  if [ -z "$out" ]; then echo allow; else
    printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["hookSpecificOutput"]["permissionDecision"])'
  fi
}

# bash_case <expected> <cwd> <command>
bash_case() {
  local payload got
  payload="$(python3 -c 'import json,sys; print(json.dumps({"cwd": sys.argv[1], "tool_input": {"command": sys.argv[2]}}))' "$2" "$3")"
  got="$(decision guard-protected-branches.py "$payload")"
  if [ "$got" = "$1" ]; then echo "ok   $got  [${2##*/}] $3"; else echo "FAIL want $1 got $got  [${2##*/}] $3"; FAIL=1; fi
}

# raw_case <hook> <expected> <label> <payload json, EMDASH replaced by U+2014>
raw_case() {
  local got
  got="$(decision "$1" "${4//EMDASH/$EM}")"
  if [ "$got" = "$2" ]; then echo "ok   $got  $3"; else echo "FAIL want $2 got $got  $3"; FAIL=1; fi
}

echo "== guard-protected-branches.py"
bash_case allow "$FEAT" 'git push'
bash_case ask   "$MAIN" 'git push'
bash_case allow "$FEAT" 'git push origin HEAD'
bash_case ask   "$MAIN" 'git push origin HEAD'
bash_case allow "$FEAT" 'git push -u origin feature'
bash_case ask   "$FEAT" 'git push origin feature:main'
bash_case ask   "$FEAT" 'git push origin +main'
bash_case ask   "$FEAT" 'git push origin refs/heads/staging'
bash_case ask   "$FEAT" 'git push --all origin'
bash_case allow "$FEAT" 'git push --force-with-lease origin dev'
bash_case ask   "$FEAT" "git -C $MAIN push"
bash_case allow "$MAIN" "git -C $FEAT push"
bash_case ask   "$FEAT" 'git -C ../does-not-exist push'
bash_case ask   "$FEAT" 'git status && git push origin main'
bash_case ask   "$FEAT" "cd $MAIN && git push"
bash_case ask   "$FEAT" 'cd ../repo && git push'
bash_case allow "$MAIN" "cd $FEAT && git push"
bash_case ask   "$FEAT" 'cd "$SOMEWHERE" && git push'
bash_case ask   "$MAIN" 'git merge feature'
bash_case allow "$FEAT" 'git merge main'
bash_case ask   "$FEAT" "cd $MAIN; git merge feature"
bash_case ask   "$FEAT" 'gh pr merge 12 --squash'
bash_case ask   "$FEAT" 'gh -R owner/repo pr merge 12'
bash_case ask   "$FEAT" 'gh pr --repo owner/repo merge 12'
bash_case ask   "$FEAT" 'glab mr merge 3'
bash_case ask   "$FEAT" 'glab -R group/repo mr merge 3'
bash_case allow "$FEAT" 'gh pr create --base dev --fill'
bash_case allow "$FEAT" 'echo "git push origin main && gh pr merge 1"'
bash_case ask   "$FEAT" "bash -c 'git status && git push origin main'"
bash_case ask   "$FEAT" "sh -lc \"cd $MAIN && git push\""
bash_case ask   "$FEAT" "eval 'gh pr merge 1'"
raw_case guard-protected-branches.py allow 'bad JSON fails open' 'not json'
raw_case guard-protected-branches.py allow 'non-object JSON fails open' '[1]'

echo "== no-em-dash.py"
raw_case no-em-dash.py deny  'Write with em dash' '{"tool_name":"Write","tool_input":{"file_path":"a.md","content":"a EMDASH b"}}'
raw_case no-em-dash.py deny  'Edit with em dash' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"x","new_string":"aEMDASHb"}}'
raw_case no-em-dash.py deny  'MultiEdit with em dash' '{"tool_name":"MultiEdit","tool_input":{"file_path":"a.md","edits":[{"old_string":"x","new_string":"ok"},{"old_string":"y","new_string":"EMDASH"}]}}'
raw_case no-em-dash.py deny  'NotebookEdit with em dash' '{"tool_name":"NotebookEdit","tool_input":{"notebook_path":"a.ipynb","new_source":"# a EMDASH b"}}'
raw_case no-em-dash.py allow 'Write with plain dash' '{"tool_name":"Write","tool_input":{"file_path":"a.md","content":"a - b"}}'
raw_case no-em-dash.py allow 'Edit removing an em dash' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"aEMDASHb","new_string":"a - b"}}'
raw_case no-em-dash.py allow 'bad JSON fails open' 'not json'
raw_case no-em-dash.py allow 'non-object JSON fails open' '[1]'

echo "== settings registration ($SETTINGS)"
if [ ! -f "$SETTINGS" ]; then
  echo "WARN $SETTINGS not found, skipping the registration check (expected in CI)"
else
  python3 - "$SETTINGS" <<'PY' || FAIL=1
import json, sys
entries = (json.load(open(sys.argv[1])).get("hooks") or {}).get("PreToolUse") or []
want = {"no-em-dash.py": "Write", "guard-protected-branches.py": "Bash"}
bad = 0
for script, tool in want.items():
    hit = any(tool in (e.get("matcher") or "").split("|") and
              any("agent-skills-hooks/" + script in (h.get("command") or "") for h in e.get("hooks") or [])
              for e in entries)
    print(("ok   " if hit else "FAIL ") + f"PreToolUse matcher with {tool} runs agent-skills-hooks/{script}")
    bad |= not hit
sys.exit(bad)
PY
fi

if [ "$FAIL" = 0 ]; then echo "all hook checks passed"; else echo "hook checks FAILED"; exit 1; fi
