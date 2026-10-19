#!/usr/bin/env bash
# Pipe allow, ask and deny payloads through every hook, then check that settings.json registers them.
# Exits non-zero on any mismatch. Builds its own throwaway repos and never touches a remote.
set -euo pipefail
# An inherited GIT_DIR or GIT_WORK_TREE would point the throwaway git commands below at a real repo.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR

HOOKS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
TMP="$(mktemp -d "${TMPDIR%/}/hooks-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
FAIL=0
EM="$(python3 -c 'print(chr(8212))')"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# A main checkout and a worktree on a feature branch.
MAIN="$TMP/repo"
FEAT="$TMP/feature-wt"
git init -q -b main "$MAIN"
git -C "$MAIN" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$MAIN" worktree add -q -b feature "$FEAT"

# decision <hook> <payload json> prints allow, ask or deny, or error when the hook exits non-zero or writes stderr.
decision() {
  local out rc
  set +e
  out="$(printf '%s' "$2" | python3 "$HOOKS/$1" 2>"$TMP/hook-stderr")"
  rc=$?
  set -e
  if [ "$rc" != 0 ] || [ -s "$TMP/hook-stderr" ]; then echo error; return; fi
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

# mode_case <expected> <cwd> <permission_mode> <command>
mode_case() {
  local payload got
  payload="$(python3 -c 'import json,sys; print(json.dumps({"cwd": sys.argv[1], "permission_mode": sys.argv[2], "tool_input": {"command": sys.argv[3]}}))' "$2" "$3" "$4")"
  got="$(decision guard-protected-branches.py "$payload")"
  if [ "$got" = "$1" ]; then echo "ok   $got  [${2##*/} $3] $4"; else echo "FAIL want $1 got $got  [${2##*/} $3] $4"; FAIL=1; fi
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
# git, gh and glab by path count, matched by basename
bash_case ask   "$FEAT" '/usr/bin/git push origin main'
bash_case ask   "$MAIN" '/opt/homebrew/bin/git push'
bash_case ask   "$FEAT" '/usr/local/bin/gh pr merge 1'
bash_case allow "$FEAT" '/usr/bin/git push origin feature'
# $PWD and $(git rev-parse --show-toplevel) resolve to the directory they name; other variables still ask
bash_case allow "$FEAT" 'cd "$(git rev-parse --show-toplevel)" && git push'
bash_case ask   "$MAIN" 'cd "$(git rev-parse --show-toplevel)" && git push'
bash_case allow "$FEAT" 'git -C "$PWD" push'
bash_case ask   "$MAIN" 'git -C "${PWD}" push'
bash_case ask   "$MAIN" 'cd `pwd` && git push'
bash_case ask   "$FEAT" 'cd "$(git rev-parse --show-toplevel)/../repo" && git push'
raw_case guard-protected-branches.py allow 'bad JSON fails open' 'not json'
raw_case guard-protected-branches.py allow 'non-object JSON fails open' '[1]'
raw_case guard-protected-branches.py allow 'non-string cwd fails open' '{"cwd":123,"tool_input":{"command":"git push"}}'
raw_case guard-protected-branches.py allow 'non-object tool_input fails open' '{"tool_input":"git push origin main"}'

echo "== no-em-dash.py"
raw_case no-em-dash.py deny  'Write with em dash' '{"tool_name":"Write","tool_input":{"file_path":"a.md","content":"a EMDASH b"}}'
raw_case no-em-dash.py deny  'Edit with em dash' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"x","new_string":"aEMDASHb"}}'
raw_case no-em-dash.py deny  'MultiEdit with em dash' '{"tool_name":"MultiEdit","tool_input":{"file_path":"a.md","edits":[{"old_string":"x","new_string":"ok"},{"old_string":"y","new_string":"EMDASH"}]}}'
raw_case no-em-dash.py deny  'NotebookEdit with em dash' '{"tool_name":"NotebookEdit","tool_input":{"notebook_path":"a.ipynb","new_source":"# a EMDASH b"}}'
raw_case no-em-dash.py allow 'Write with plain dash' '{"tool_name":"Write","tool_input":{"file_path":"a.md","content":"a - b"}}'
raw_case no-em-dash.py allow 'Edit removing an em dash' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"aEMDASHb","new_string":"a - b"}}'
# only changed lines count: an exact line already in old_string, the existing file or notebook passes
python3 - "$TMP/em.md" "$TMP/em.ipynb" <<'PY'
import json, sys
em = chr(8212)
open(sys.argv[1], "w").write(f"keep a {em} b\nplain\n")
json.dump({"cells": [{"cell_type": "markdown", "source": [f"# a {em} b\n", "x"]}]}, open(sys.argv[2], "w"))
PY
raw_case no-em-dash.py allow 'Write keeps unchanged em-dash lines of an existing file' "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TMP/em.md\",\"content\":\"keep a EMDASH b\\nplain edited\\n\"}}"
raw_case no-em-dash.py allow 'Write, relative path resolved from cwd' "{\"tool_name\":\"Write\",\"cwd\":\"$TMP\",\"tool_input\":{\"file_path\":\"em.md\",\"content\":\"new\\nkeep a EMDASH b\\n\"}}"
raw_case no-em-dash.py deny  'Write adds a new em-dash line to an existing file' "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TMP/em.md\",\"content\":\"keep a EMDASH b\\nnew EMDASH line\\n\"}}"
raw_case no-em-dash.py deny  'Write changes an em-dash line and keeps the dash' "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TMP/em.md\",\"content\":\"keep a EMDASH c\\nplain\\n\"}}"
raw_case no-em-dash.py deny  'Write of a new file with an em dash' "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TMP/new-em.md\",\"content\":\"keep a EMDASH b\"}}"
raw_case no-em-dash.py allow 'Edit repeats an unchanged em-dash line of old_string' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"keep a EMDASH b\nplain","new_string":"keep a EMDASH b\nplain edited"}}'
raw_case no-em-dash.py deny  'Edit changes an em-dash line and keeps the dash' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"keep a EMDASH b","new_string":"kept a EMDASH b"}}'
raw_case no-em-dash.py deny  'Edit adds an em-dash line next to an unchanged one' '{"tool_name":"Edit","tool_input":{"file_path":"a.md","old_string":"keep a EMDASH b","new_string":"keep a EMDASH b\nnew EMDASH"}}'
raw_case no-em-dash.py allow 'MultiEdit whose edits keep unchanged em-dash lines' '{"tool_name":"MultiEdit","tool_input":{"file_path":"a.md","edits":[{"old_string":"a EMDASH b\nx","new_string":"a EMDASH b\ny"},{"old_string":"p","new_string":"q"}]}}'
raw_case no-em-dash.py deny  'MultiEdit judges each edit against its own old_string' '{"tool_name":"MultiEdit","tool_input":{"file_path":"a.md","edits":[{"old_string":"a EMDASH b","new_string":"a EMDASH b"},{"old_string":"y","new_string":"a EMDASH b"}]}}'
raw_case no-em-dash.py allow 'NotebookEdit keeps an em-dash line of an existing cell' "{\"tool_name\":\"NotebookEdit\",\"tool_input\":{\"notebook_path\":\"$TMP/em.ipynb\",\"new_source\":\"# a EMDASH b\\ny\"}}"
raw_case no-em-dash.py deny  'NotebookEdit adds an em-dash line' "{\"tool_name\":\"NotebookEdit\",\"tool_input\":{\"notebook_path\":\"$TMP/em.ipynb\",\"new_source\":\"# c EMDASH d\"}}"
raw_case no-em-dash.py deny  'Write over an unreadable path checks the new text in full' "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$TMP\",\"content\":\"keep a EMDASH b\"}}"
raw_case no-em-dash.py allow 'bad JSON fails open' 'not json'
raw_case no-em-dash.py allow 'non-object JSON fails open' '[1]'
# When the changed-line check itself raises, the fallback checks every new text line by line, MultiEdit edits included.
if python3 -I - "$HOOKS/no-em-dash.py" <<'PY'
import importlib.util, io, json, sys, contextlib
spec = importlib.util.spec_from_file_location("hook", sys.argv[1]); hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(hook)
def boom(*a): raise RuntimeError("boom")
bad = "bad " + chr(8212) + " line"
hook.changed_em_dash_lines = boom
sys.stdin = io.StringIO(json.dumps({"tool_input": {"edits": [{"old_string": "x", "new_string": "ok\n" + bad}]}}))
out = io.StringIO()
with contextlib.redirect_stdout(out): hook.main()
reason = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
sys.exit(0 if reason.startswith("1 line(s)") and repr(bad) in reason else 1)
PY
then echo "ok   deny  fallback checks MultiEdit edits line by line"; else echo "FAIL fallback checks MultiEdit edits line by line"; FAIL=1; fi

echo "== permission modes and per-repo opt-out"
mode_case deny  "$FEAT" bypassPermissions 'git push origin main'
mode_case deny  "$FEAT" dontAsk 'gh pr merge 3'
mode_case ask   "$FEAT" default 'git push origin main'
mode_case allow "$FEAT" bypassPermissions 'git push origin feature'
git -C "$MAIN" config agentguard.allow main
mode_case allow "$MAIN" bypassPermissions 'git push'
mode_case deny  "$MAIN" bypassPermissions 'git push origin staging'
mode_case deny  "$MAIN" bypassPermissions 'gh pr merge 3'
git -C "$MAIN" config --unset agentguard.allow

# hint_case <expected: yes|no> <cwd> <command>: does the deny reason suggest agentguard.allow?
hint_case() {
  local payload got
  payload="$(python3 -c 'import json,sys; print(json.dumps({"cwd": sys.argv[1], "permission_mode": "bypassPermissions", "tool_input": {"command": sys.argv[2]}}))' "$2" "$3")"
  got="$(printf '%s' "$payload" | python3 "$HOOKS/guard-protected-branches.py" | python3 -c 'import json,sys; r=json.load(sys.stdin)["hookSpecificOutput"]["permissionDecisionReason"]; print("yes" if "opt this repo out" in r else "no")')"
  if [ "$got" = "$1" ]; then echo "ok   hint=$got  $3"; else echo "FAIL want hint=$1 got $got  $3"; FAIL=1; fi
}
hint_case yes "$FEAT" 'git push origin main'
hint_case no  "$FEAT" 'gh pr merge 3'
hint_case no  "$FEAT" 'glab mr merge 3'

echo "== feature-status-guard.py"
# A bare origin whose dev branch is opted in (docs/status/), plus clones acting as main checkouts.
FS_ORIGIN="$TMP/fs-origin.git"
FS_SEED="$TMP/fs-seed"
git init -q --bare -b dev "$FS_ORIGIN"
git init -q -b old "$FS_SEED"
git -C "$FS_SEED" remote add origin "$FS_ORIGIN"
git -C "$FS_SEED" commit -q --allow-empty -m init
git -C "$FS_SEED" push -q origin old
git -C "$FS_SEED" switch -q -c dev
mkdir -p "$FS_SEED/docs/status"
status_md() { printf -- '---\nid: %s\ntitle: t\nstate: %s\nbranch: %s\npicked_by: t@t\npicked_at: 2026-01-01T00:00:00Z\nupdated_at: 2026-01-01T00:00:00Z\npr:\nspec:\n---\n\n## Acceptance criteria\n\n## Deferred\n\n## Notes\n' "$1" "$2" "$3"; }
touch "$FS_SEED/docs/status/.gitkeep"
status_md WEST-1 merged feat/WEST-1-done > "$FS_SEED/docs/status/WEST-1.md"
# WEST-12: merged on GitHub while its file still said in-review (the documented recovery case)
status_md WEST-12 in-review feat/WEST-12-landed > "$FS_SEED/docs/status/WEST-12.md"
git -C "$FS_SEED" add -A && git -C "$FS_SEED" commit -q -m status && git -C "$FS_SEED" push -q origin dev
# feature branches on origin: WEST-5 in-progress, WEST-6 in-review, WEST-3 merged, WEST-7 without a status file
# and WEST-4 in-review whose branch field does not name the ID, which status.py check rejects
for spec in "WEST-5 in-progress feat/WEST-5-pr" "WEST-6 in-review feat/WEST-6-ready" "WEST-3 merged feat/WEST-3-merged" "- - fix/WEST-7-nofile" "WEST-4 in-review feat/WEST-4-bad feat/other" "WEST-11 picked feat/WEST-11-picked"; do
  set -- $spec
  git -C "$FS_SEED" switch -q -c "$3" dev
  if [ "$1" != - ]; then status_md "$1" "$2" "${4:-$3}" > "$FS_SEED/docs/status/$1.md"; git -C "$FS_SEED" add -A; fi
  git -C "$FS_SEED" commit -q --allow-empty -m "$3" && git -C "$FS_SEED" push -q origin "$3"
done
git -C "$FS_ORIGIN" symbolic-ref HEAD refs/heads/dev
FS_A="$TMP/fs-a"
git clone -q "$FS_ORIGIN" "$FS_A"
for b in feat/WEST-5-pr feat/WEST-6-ready feat/WEST-3-merged fix/WEST-7-nofile feat/WEST-4-bad; do
  git -C "$FS_A" worktree add -q "$TMP/fs-wt-${b//\//-}" -b "$b" "origin/$b"
done
git -C "$FS_A" worktree add -q --detach "$TMP/fs-detached" origin/dev
git -C "$FS_A" branch -q --no-track feat/WEST-13-handmade origin/dev
DET="$TMP/fs-detached"
WT5="$TMP/fs-wt-feat-WEST-5-pr"; WT6="$TMP/fs-wt-feat-WEST-6-ready"; WT7="$TMP/fs-wt-fix-WEST-7-nofile"; WT4="$TMP/fs-wt-feat-WEST-4-bad"; WT3="$TMP/fs-wt-feat-WEST-3-merged"
# claims pushed from another clone after A was cloned, so A sees them only on origin
git -C "$FS_SEED" push -q origin dev:refs/heads/claim/WEST-2 dev:refs/heads/claim/dark-mode
# claim/WEST-20 whose status file names feat/WEST-20-real: any other new branch for WEST-20 is a second branch
git -C "$FS_SEED" switch -q -c claim-20 dev
status_md WEST-20 picked feat/WEST-20-real > "$FS_SEED/docs/status/WEST-20.md"
git -C "$FS_SEED" add -A && git -C "$FS_SEED" commit -q -m pick20 && git -C "$FS_SEED" push -q origin claim-20:refs/heads/claim/WEST-20
# a slug ID picked without a ticket: claim/csv-export and its branch fix/csv-export, state picked
git -C "$FS_SEED" switch -q -c fix/csv-export dev
status_md csv-export picked fix/csv-export > "$FS_SEED/docs/status/csv-export.md"
git -C "$FS_SEED" add -A && git -C "$FS_SEED" commit -q -m pick-csv
git -C "$FS_SEED" push -q origin fix/csv-export fix/csv-export:refs/heads/claim/csv-export
# clone E whose origin is unreachable: the hook must decide from local refs without touching the network
FS_E="$TMP/fs-e"
git clone -q "$FS_ORIGIN" "$FS_E"
git -C "$FS_E" remote set-url origin "file://$TMP/does-not-exist.git"
# clone C checked out on a branch without docs/status: opted in only through origin/dev
FS_C="$TMP/fs-c"
git clone -q -b old "$FS_ORIGIN" "$FS_C"
# repo D: no docs/status, opted in through AGENTS.md
FS_D="$TMP/fs-d"
git init -q -b main "$FS_D"
echo 'Track features with the feature-status skill.' > "$FS_D/AGENTS.md"
git -C "$FS_D" add -A && git -C "$FS_D" commit -q -m init
# not opted in: $MAIN, with a ticket-shaped branch for the PR rule
git -C "$MAIN" worktree add -q -b feat/WEST-8-x "$TMP/plain-wt"
STUB_OK="$TMP/status-ok.py"; STUB_BAD="$TMP/status-bad.py"
printf 'import sys\nsys.exit(0)\n' > "$STUB_OK"
printf 'import sys\nprint("WEST-6: AC1 E2E pass has no evidence file")\nsys.exit(1)\n' > "$STUB_BAD"
export FEATURE_STATUS_SCRIPT="$STUB_OK"

# fs_bash <expected> <cwd> <command>
fs_bash() {
  local payload got
  payload="$(python3 -c 'import json,sys; print(json.dumps({"tool_name": "Bash", "cwd": sys.argv[1], "tool_input": {"command": sys.argv[2]}}))' "$2" "$3")"
  got="$(decision feature-status-guard.py "$payload")"
  if [ "$got" = "$1" ]; then echo "ok   $got  [${2##*/}] $3"; else echo "FAIL want $1 got $got  [${2##*/}] $3"; FAIL=1; fi
}

# fs_write <expected> <tool> <cwd> <file_path>
fs_write() {
  local payload got
  payload="$(python3 -c 'import json,sys; print(json.dumps({"tool_name": sys.argv[1], "cwd": sys.argv[2], "tool_input": {"file_path": sys.argv[3], "content": "x", "old_string": "a", "new_string": "b"}}))' "$2" "$3" "$4")"
  got="$(decision feature-status-guard.py "$payload")"
  if [ "$got" = "$1" ]; then echo "ok   $got  $2 [${3##*/}] ${4#"$TMP"/}"; else echo "FAIL want $1 got $got  $2 [${3##*/}] ${4#"$TMP"/}"; FAIL=1; fi
}

echo "-- rule 1: status files are written only by status.py"
fs_write deny  Write     "$FS_A" "$FS_A/docs/status/WEST-1.md"
fs_write deny  Edit      "$FS_A" "$FS_A/docs/status/WEST-1.md"
fs_write deny  MultiEdit "$FS_A" "$FS_A/docs/status/WEST-1.md"
fs_write deny  Write     "$FS_A" 'docs/status/WEST-9.md'
fs_write deny  Write     "$WT5"  "$WT5/docs/status/WEST-5.md"
fs_write deny  Write     "$FS_D" "$FS_D/docs/status/NEW-1.md"
fs_write allow Write     "$FS_A" "$FS_A/docs/status/README.md"
fs_write allow Write     "$FS_A" "$FS_A/docs/status/.gitkeep"
fs_write allow Write     "$FS_A" "$FS_A/docs/other.md"
fs_write allow Write     "$FS_A" "$FS_A/app/docs/status/page.md"
fs_write allow Write     "$MAIN" "$MAIN/docs/status/X-1.md"
fs_write allow Write     "$TMP"  "$TMP/no-repo/docs/status/X-1.md"
ln -s "$FS_A/docs/status/WEST-1.md" "$TMP/link-out.md"
ln -s docs/status/WEST-1.md "$FS_A/link-in.md"
fs_write deny  Write     "$TMP"  "$TMP/link-out.md"
fs_write deny  Edit      "$FS_A" "$FS_A/link-in.md"
rm "$FS_A/link-in.md"
fs_bash deny  "$FS_A" "echo x > docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "echo x >docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "printf x >> $FS_A/docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "sed -i '' s/merged/in-review/ docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "perl -pi -e s/merged/in-review/ docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "tee docs/status/WEST-1.md </dev/null"
fs_bash deny  "$FS_A" "cp /tmp/x.md docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "mv docs/status/WEST-1.md /tmp/x.md"
fs_bash deny  "$FS_A" "python3 -c \"open('docs/status/WEST-1.md','w').write('x')\""
fs_bash deny  "$MAIN" "cd $FS_A && echo x > docs/status/WEST-1.md"
fs_bash deny  "$MAIN" "bash -c 'cd $FS_A && echo x > docs/status/WEST-1.md'"
# a redirect glued to the word before it, and other writers
fs_bash deny  "$FS_A" "echo x>docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "echo x>>docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "echo x 2>docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "ln -sf /tmp/x docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "awk -i inplace 1 docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "gawk -iinplace 1 docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "git checkout origin/dev -- docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "git checkout HEAD~1 docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "git restore --source origin/dev docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "git restore -s origin/dev -- docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "git restore --source=HEAD~1 docs/status/WEST-1.md"
fs_bash deny  "$FS_A" "node -e \"require('fs').writeFileSync('docs/status/WEST-1.md','x')\""
# the docs/status part is compared without case (macOS resolves Docs/Status to docs/status)
fs_write deny  Write     "$FS_A" "$FS_A/Docs/Status/WEST-1.md"
fs_write deny  Edit      "$FS_A" 'docs/STATUS/WEST-1.md'
fs_bash deny  "$FS_A" "echo y > Docs/Status/WEST-1.md"
fs_bash deny  "$FS_A" "python3 -c \"open('Docs/Status/WEST-1.md','w').write('x')\""
# git by path, and cd/-C targets given as $PWD or $(git rev-parse --show-toplevel)
fs_bash deny  "$FS_A" "/usr/bin/git checkout origin/dev -- docs/status/WEST-1.md"
fs_bash deny  "$FS_A" 'cd "$(git rev-parse --show-toplevel)" && echo x > docs/status/WEST-1.md'
fs_bash allow "$FS_A" "git checkout -- docs/status/WEST-1.md"
fs_bash allow "$FS_A" "git restore docs/status/WEST-1.md"
fs_bash allow "$FS_A" "git restore --staged docs/status/WEST-1.md"
fs_bash allow "$FS_A" "ln -s docs/status/WEST-1.md /tmp/link.md"
fs_bash allow "$FS_A" "awk 1 docs/status/WEST-1.md"
fs_bash allow "$FS_A" "echo x 2>&1"
fs_bash allow "$FS_A" "git commit -m 'picked->in-progress'"
fs_bash allow "$FS_A" "python3 -c \"print(open('docs/status/WEST-1.md').read())\""
fs_bash allow "$FS_A" "node -e \"console.log(require('fs').readFileSync('docs/status/WEST-1.md','utf8'))\""
fs_bash allow "$FS_A" "cat docs/status/WEST-1.md"
fs_bash allow "$FS_A" "grep state docs/status/WEST-1.md > /tmp/state.txt 2>/dev/null"
fs_bash allow "$FS_A" "sed -n p docs/status/WEST-1.md"
fs_bash allow "$FS_A" "cp docs/status/WEST-1.md /tmp/copy.md"
fs_bash allow "$FS_A" "git add docs/status/WEST-1.md && git commit -m status"
fs_bash allow "$FS_A" "python3 ~/.claude/skills/feature-status/scripts/status.py note WEST-1 x"
fs_bash allow "$FS_A" "echo x > docs/status/README.md"
fs_bash allow "$MAIN" "echo x > docs/status/X-1.md"

echo "-- rule 2: a feature worktree needs a claim"
fs_bash deny  "$FS_A" "git worktree add -b feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add --no-track -b fix/WEST-9-new \"$TMP/wt9\" origin/dev"
fs_bash deny  "$FS_A" "git worktree add ../wt9 origin/feat/WEST-9-new"
fs_bash deny  "$MAIN" "git -C $FS_A worktree add -b feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$MAIN" "cd $FS_A && git worktree add -b feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$MAIN" "bash -c 'cd $FS_A && git worktree add -b feat/WEST-9-new ../wt9 origin/dev'"
fs_bash deny  "$FS_C" "git worktree add -b feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -B feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -bfeat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -Bfeat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add --orphan=feat/WEST-9-new ../wt9"
fs_bash deny  "$FS_A" "git worktree add --orphan feat/WEST-9-new ../wt9"
fs_bash deny  "$FS_A" "git worktree add --reason x -b feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -b feat/WEST-1-again ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -b feat/WEST-1-done ../wt9 origin/dev"
fs_bash allow "$FS_A" "git worktree add --no-track -b feat/WEST-12-landed ../wt12 origin/dev"
fs_bash deny  "$FS_E" "git worktree add -b feat/WEST-9-new ../wt9 origin/dev"
# a slug-only branch with no claim is a small no-ticket change, out of scope for rules 2 and 3
fs_bash allow "$FS_A" "git worktree add -b feat/dark-modes-toggle ../wt9 origin/dev"
fs_bash allow "$FS_A" "git worktree add -b fix/csv-typo ../wt9 origin/dev"
fs_bash allow "$DET"  "git switch -c docs/readme-typo origin/dev"
fs_bash allow "$DET"  "git checkout -b docs/readme-typo origin/dev"
# a ticket branch with no claim is still denied
fs_bash deny  "$FS_A" "git worktree add -b fix/WEST-30-typo ../wt9 origin/dev"
fs_bash deny  "$DET"  "git switch -c docs/WEST-30-readme origin/dev"
# claims pushed after A was cloned are seen only after a fetch: the hook reads local refs, never the network
fs_bash deny  "$FS_A" "git worktree add -b feat/WEST-2-claimed ../wt2 origin/dev"
git -C "$FS_A" fetch -q origin
fs_bash allow "$FS_A" "git worktree add -b feat/WEST-2-claimed ../wt2 origin/dev"
fs_bash allow "$FS_A" "git worktree add -fb feat/WEST-2-claimed ../wt2 origin/dev"
fs_bash allow "$FS_A" "git worktree add -b feat/dark-mode-toggle ../wt9 origin/dev"
# a slug branch WITH a claim is still judged: one ID, one branch
fs_bash deny  "$FS_A" "git worktree add -b fix/csv-export-v2 ../wtc origin/dev"
fs_bash deny  "$DET"  "git switch -c feat/csv-export origin/dev"
fs_bash allow "$FS_A" "git worktree add -b fix/csv-export ../wtc origin/fix/csv-export"
# a claim that names another branch does not cover a new branch for the same ID (read from the local claim ref)
fs_bash deny  "$FS_A" "git worktree add -b feat/WEST-20-other ../wt20 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -b fix/WEST-20 ../wt20 origin/dev"
fs_bash deny  "$DET"  "git switch -c feat/WEST-20-other origin/dev"
fs_bash deny  "$DET"  "git checkout -b feat/WEST-20-other origin/dev"
fs_bash allow "$FS_A" "git worktree add -b feat/WEST-20-real ../wt20 origin/dev"
fs_bash allow "$DET"  "git switch -c feat/WEST-20-real --track origin/feat/WEST-20-real"
fs_bash deny  "$DET"  "git switch -c feat/WEST-9-new"
fs_bash deny  "$DET"  "git switch --no-track -c feat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git switch -cfeat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git switch --create=feat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git checkout -b feat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git checkout -B feat/WEST-1-again origin/dev"
fs_bash deny  "$FS_A" "git worktree add --detach ../wt9 origin/dev && git -C ../wt9 switch -c feat/WEST-9-new"
fs_bash deny  "$FS_A" "git -C $DET switch -c feat/WEST-9-new"
fs_bash deny  "$DET"  "git switch feat/WEST-13-handmade"
# bundled short flags whose last letter creates the branch, as git reads them
fs_bash deny  "$DET"  "git checkout -qb feat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git checkout -qbfeat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git switch -qc feat/WEST-9-new origin/dev"
fs_bash deny  "$DET"  "git switch -fC feat/WEST-9-new origin/dev"
fs_bash deny  "$FS_A" "git worktree add -fb feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "git worktree add -qB feat/WEST-9-new ../wt9 origin/dev"
fs_bash allow "$DET"  "git checkout -qb spike origin/dev"
fs_bash allow "$DET"  "git switch -qc feat/WEST-2-x origin/dev"
# git by path, and cd/-C targets the hook cannot resolve fall back to the payload cwd's repo
fs_bash deny  "$FS_A" "/usr/bin/git worktree add -b feat/WEST-9-new ../wt9 origin/dev"
fs_bash deny  "$FS_A" "/opt/homebrew/bin/git worktree add ../wt9 origin/feat/WEST-9-new"
fs_bash deny  "$FS_A" 'cd "$(git rev-parse --show-toplevel)" && git worktree add -b feat/WEST-9-new ../wt9 origin/dev'
fs_bash deny  "$FS_A" 'cd $(git rev-parse --show-toplevel) && git worktree add -b feat/WEST-9-new ../wt9 origin/dev'
fs_bash deny  "$FS_A" 'git -C "$PWD" worktree add -b feat/WEST-9-new ../wt9 origin/dev'
fs_bash deny  "$FS_A" 'git -C "$REPO" worktree add -b feat/WEST-9-new ../wt9 origin/dev'
fs_bash deny  "$FS_A" 'cd "$REPO" && git worktree add -b feat/WEST-9-new ../wt9 origin/dev'
fs_bash allow "$FS_A" 'cd "$(git rev-parse --show-toplevel)" && git worktree add -b feat/WEST-2-claimed ../wt2 origin/dev'
fs_bash allow "$MAIN" 'cd "$REPO" && git worktree add -b feat/WEST-9-new ../wt9 origin/dev'
fs_bash allow "$DET"  "git switch -c feat/WEST-11-picked --track origin/feat/WEST-11-picked"
fs_bash allow "$DET"  "git switch -c feat/WEST-2-x origin/dev"
fs_bash allow "$DET"  "git switch -c spike origin/dev"
fs_bash allow "$DET"  "git checkout -- docs/README.md"
fs_bash allow "$DET"  "git checkout docs/README.md"
fs_bash allow "$WT5"  "git switch feat/WEST-5-pr"
fs_bash allow "$FS_A" "git checkout feat/WEST-3-merged"
fs_bash allow "$MAIN" "git switch -c feat/WEST-9-new"
fs_bash allow "$FS_A" "git worktree add ../wt5 origin/feat/WEST-5-pr"
fs_bash allow "$FS_A" "git worktree add -b spike ../wt9 origin/dev"
fs_bash allow "$FS_A" "git worktree list"
fs_bash allow "$MAIN" "git worktree add -b feat/WEST-9-new ../wt9"
fs_bash allow "$FS_A" 'echo "git worktree add -b feat/WEST-9-new ../wt9 origin/dev"'

echo "-- rule 3: a PR/MR needs a status file in-review that passes check"
fs_bash deny  "$WT5"  "gh pr create --base dev --fill"
fs_bash allow "$WT5"  "gh pr create --base dev --fill --draft"
fs_bash deny  "$FS_A" "gh pr create --base dev --head feat/WEST-5-pr --fill"
fs_bash deny  "$FS_A" "gh pr create --base dev --head owner:feat/WEST-5-pr --fill"
fs_bash deny  "$FS_A" "gh pr create --base dev -Hfeat/WEST-5-pr --fill"
fs_bash deny  "$WT5"  "gh pr new --base dev --fill"
fs_bash deny  "$WT5"  "glab mr new --target-branch dev"
fs_bash deny  "$FS_A" "glab mr create -sfeat/WEST-5-pr --target-branch dev"
fs_bash allow "$WT6"  "gh pr new --base dev --fill"
fs_bash allow "$WT6"  "gh pr create --base dev --fill"
fs_bash allow "$WT6"  "glab mr create --target-branch dev --fill"
fs_bash allow "$WT3"  "gh pr create --base dev --fill"
fs_bash deny  "$WT7"  "gh pr create --base dev --fill"
fs_bash deny  "$WT7"  "gh pr create --base dev --fill --draft"
fs_bash deny  "$WT7"  "glab mr create --draft --target-branch dev"
fs_bash deny  "$MAIN" "cd $WT5 && gh pr create --fill"
fs_bash allow "$TMP/plain-wt" "gh pr create --base main --fill"
fs_bash deny  "$WT5"  "/opt/homebrew/bin/gh pr create --base dev --fill"
fs_bash deny  "$WT5"  "/usr/local/bin/glab mr create --target-branch dev"
fs_bash deny  "$WT5"  'cd "$(git rev-parse --show-toplevel)" && gh pr create --fill'
fs_bash deny  "$WT5"  'cd $(git rev-parse --show-toplevel) && gh pr create --fill'
fs_bash allow "$WT6"  'cd "$(git rev-parse --show-toplevel)" && gh pr create --fill'
fs_bash allow "$TMP/plain-wt" 'cd "$SOMEWHERE" && gh pr create --base main --fill'
fs_bash allow "$FS_A" "gh pr list --search WEST-5"
# rule 3 judges a slug branch only when it has a claim
git -C "$FS_A" worktree add -q -b docs/readme-typo "$TMP/fs-wt-typo" origin/dev
git -C "$FS_A" worktree add -q -b fix/csv-export "$TMP/fs-wt-csv" origin/fix/csv-export
fs_bash allow "$TMP/fs-wt-typo" "gh pr create --base dev --fill"
fs_bash allow "$TMP/fs-wt-typo" "glab mr create --target-branch dev --fill"
fs_bash allow "$FS_A" "gh pr create --base dev --head docs/readme-typo --fill"
fs_bash deny  "$TMP/fs-wt-csv" "gh pr create --base dev --fill"
fs_bash allow "$TMP/fs-wt-csv" "gh pr create --base dev --fill --draft"
FEATURE_STATUS_SCRIPT="$STUB_BAD" fs_bash deny  "$WT6" "gh pr create --base dev --fill"
FEATURE_STATUS_SCRIPT="$STUB_BAD" fs_bash allow "$WT6" "gh pr create --base dev --fill --draft"
FEATURE_STATUS_SCRIPT="$TMP/absent.py" fs_bash allow "$WT6" "gh pr create --base dev --fill"
FEATURE_STATUS_SCRIPT="$TMP/absent.py" fs_bash deny  "$WT5" "gh pr create --base dev --fill"
REAL_STATUS="$HOOKS/../skills/feature-status/scripts/status.py"
if [ -f "$REAL_STATUS" ]; then
  FEATURE_STATUS_SCRIPT="$REAL_STATUS" fs_bash allow "$WT6" "gh pr create --base dev --fill"
  FEATURE_STATUS_SCRIPT="$REAL_STATUS" fs_bash deny  "$WT4" "gh pr create --base dev --fill"
  # E2E evidence present in the working tree but not committed: the PR would ship without it
  mkdir -p "$WT6/e2e"
  echo '{"id":"WEST-6","verdict":"PASS"}' > "$WT6/e2e/ev.json"
  python3 - "$WT6/docs/status/WEST-6.md" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read().replace("## Acceptance criteria\n\n## Deferred", "## Acceptance criteria\n\n- AC1: works | UT pass | IT na | E2E pass | evidence: e2e/ev.json\n\n## Deferred")
open(p, "w").write(s)
PY
  git -C "$WT6" commit -q -m ac docs/status/WEST-6.md && git -C "$WT6" push -q
  FEATURE_STATUS_SCRIPT="$REAL_STATUS" fs_bash deny  "$WT6" "gh pr create --base dev --fill"
  git -C "$WT6" add e2e/ev.json && git -C "$WT6" commit -q -m evidence && git -C "$WT6" push -q
  FEATURE_STATUS_SCRIPT="$REAL_STATUS" fs_bash allow "$WT6" "gh pr create --base dev --fill"
  git -C "$WT6" push -q -f origin HEAD~2:feat/WEST-6-ready && git -C "$WT6" reset -q --hard HEAD~2
else
  echo "WARN $REAL_STATUS not found, skipping the cases against the real status.py check"
fi
# unpushed commits (local branch ahead of its local upstream ref): a ready PR/MR would not ship what was checked
git -C "$WT6" commit -q --allow-empty -m unpushed
fs_bash deny  "$WT6"  "gh pr create --base dev --fill"
fs_bash deny  "$FS_A" "gh pr create --base dev --head feat/WEST-6-ready --fill"
fs_bash deny  "$WT6"  "glab mr create --target-branch dev --fill"
fs_bash allow "$WT6"  "gh pr create --base dev --fill --draft"
git -C "$WT6" push -q
fs_bash allow "$WT6"  "gh pr create --base dev --fill"
git -C "$WT6" push -q -f origin HEAD~1:feat/WEST-6-ready && git -C "$WT6" reset -q --hard HEAD~1
fs_bash allow "$WT6"  "gh pr create --base dev --fill"
echo 'state: in-review' >> "$WT5/docs/status/WEST-5.md"
fs_bash deny  "$WT5"  "gh pr create --base dev --fill"
git -C "$WT5" checkout -q -- docs/status/WEST-5.md

raw_case feature-status-guard.py allow 'bad JSON fails open' 'not json'
raw_case feature-status-guard.py allow 'non-object JSON fails open' '[1]'
raw_case feature-status-guard.py allow 'non-object tool_input fails open' '{"tool_name":"Bash","tool_input":"git worktree add"}'
raw_case feature-status-guard.py allow 'non-string cwd fails open (Bash)' '{"tool_name":"Bash","cwd":123,"tool_input":{"command":"ls"}}'
raw_case feature-status-guard.py allow 'non-string cwd fails open (Write)' '{"tool_name":"Write","cwd":["a"],"tool_input":{"file_path":"/x/docs/status/A.md"}}'

echo "== settings registration ($SETTINGS)"
# Structural: the plugin manifest mounts every gate with the right event and matcher.
python3 - "$HOOKS/hooks.json" <<'PY' || FAIL=1
import json, sys
hooks = json.load(open(sys.argv[1]))["hooks"]
want = [("PreToolUse", "Write", "no-em-dash.py"), ("PreToolUse", "Bash", "guard-protected-branches.py"),
        ("PreToolUse", "Write", "feature-status-guard.py"), ("PreToolUse", "Edit", "feature-status-guard.py"),
        ("PreToolUse", "Bash", "feature-status-guard.py"), ("SessionStart", "startup", "session-start.py")]
bad = 0
for event, match, script in want:
    hit = any(match in (e.get("matcher") or "").split("|") and
              any("${CLAUDE_PLUGIN_ROOT}/hooks/" + script in (h.get("command") or "") for h in e.get("hooks") or [])
              for e in hooks.get(event) or [])
    print(("ok   " if hit else "FAIL ") + f"hooks.json {event} matcher with {match} runs {script}")
    bad |= not hit
sys.exit(bad)
PY

# This machine: the gates run through the enabled plugin, or through legacy settings entries.
if [ ! -f "$SETTINGS" ]; then
  echo "WARN $SETTINGS not found, skipping the registration check (expected in CI)"
else
  python3 - "$SETTINGS" <<'PY' || FAIL=1
import json, sys
settings = json.load(open(sys.argv[1]))
if any(k.startswith("agent-skills@") and v for k, v in (settings.get("enabledPlugins") or {}).items()):
    print("ok   agent-skills plugin enabled, its hooks.json registers the gates")
    sys.exit(0)
entries = (settings.get("hooks") or {}).get("PreToolUse") or []
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
want = [("no-em-dash.py", t) for t in WRITE_TOOLS] + [("guard-protected-branches.py", "Bash")]
want += [("feature-status-guard.py", t) for t in WRITE_TOOLS + ("Bash",)]
bad = 0
for script, tool in want:
    hit = any(tool in (e.get("matcher") or "").split("|") and
              any("agent-skills-hooks/" + script in (h.get("command") or "") for h in e.get("hooks") or [])
              for e in entries)
    print(("ok   " if hit else "FAIL ") + f"legacy settings: PreToolUse matcher with {tool} runs agent-skills-hooks/{script}")
    bad |= not hit
if bad:
    print("     install the agent-skills plugin (README) instead of registering the hooks by hand")
sys.exit(bad)
PY
fi

if [ "$FAIL" = 0 ]; then echo "all hook checks passed"; else echo "hook checks FAILED"; exit 1; fi
