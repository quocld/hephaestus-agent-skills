#!/usr/bin/env bash
# End-to-end tests for status.py against a throwaway bare origin and clones under mktemp; never touches a real remote.
# Usage: bash test_status.sh    Exits non-zero on any failed case.
set -euo pipefail

S="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/status.py"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/status-test.XXXXXX")"
TMP="$(cd "$TMP" && pwd -P)"
trap 'rm -rf "$TMP"' EXIT
# Run from outside any repo, so a `git -C "$X"` whose $X a failed case left empty can never touch the caller's checkout.
cd "$TMP"
OUT="$TMP/out"
ERR="$TMP/err"
FAIL=0

# Isolate from the user's git config (hooks paths, signing, identity).
export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1
printf '[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n' >"$GIT_CONFIG_GLOBAL"

ok()  { echo "ok   $1"; }
bad() { echo "FAIL $1"; FAIL=1; }

# rc <want> <label> <dir> <status.py args...>: run status.py in <dir>, compare the exit code.
rc() {
  local want="$1" label="$2" dir="$3" got
  shift 3
  set +e
  (cd "$dir" && python3 "$S" "$@") >"$OUT" 2>"$ERR"
  got=$?
  set -e
  if grep -q '^Traceback' "$ERR"; then bad "$label (crashed: $(tail -n 1 "$ERR"))"; return; fi
  if [ "$got" = "$want" ]; then ok "$label"; else bad "$label (want exit $want, got $got: $(tail -n 3 "$ERR" | tr '\n' ' '))"; fi
}

# expect <label> <shell condition>
expect() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

ORIGIN="$TMP/origin.git"
git init -q --bare "$ORIGIN"

# Seed origin with main and dev, plus an in-progress status file owned by someone else.
SEED="$TMP/seed"
git clone -q "$ORIGIN" "$SEED" 2>/dev/null
git -C "$SEED" config user.email seed@t
git -C "$SEED" config user.name seed
mkdir -p "$SEED/docs/status"
touch "$SEED/docs/status/.gitkeep"
echo "# app" >"$SEED/README.md"
cat >"$SEED/docs/status/WEST-4.md" <<'EOF'
---
id: WEST-4
title: Someone else's feature
state: in-progress
branch: feat/WEST-4-other
picked_by: other@t
picked_at: 2026-01-01T00:00:00Z
updated_at: 2026-01-01T00:00:00Z
pr:
spec:
---

## Acceptance criteria

- AC1: Works | UT pass | IT todo | E2E todo

## Deferred

## Notes

- 2026-01-01 picked by other@t on feat/WEST-4-other
EOF
git -C "$SEED" add -A
git -C "$SEED" commit -q -m init
git -C "$SEED" push -q origin HEAD:main HEAD:dev
git -C "$SEED" push -q origin HEAD:refs/heads/fix/WEST-5-already-there

clone() {
  mkdir -p "$TMP/$1"
  git clone -q "$ORIGIN" "$TMP/$1/repo" 2>/dev/null
  git -C "$TMP/$1/repo" config user.email "$1@t"
  git -C "$TMP/$1/repo" config user.name "$1"
}
clone a
clone b
A="$TMP/a/repo"
B="$TMP/b/repo"

echo "== usage and validation"
rc 2 "no subcommand is a usage error" "$A"
rc 2 "ID with .. is a usage error" "$A" pick 'x..y' --title t
rc 2 "ID with a slash is a usage error" "$A" pick 'a/b' --title t
rc 1 "--int naming a missing branch is refused" "$A" pick WEST-9 --title t --int nope
rc 2 "ID README is a usage error (check and board skip README.md)" "$A" pick README --title t
rc 2 "ID readme is a usage error in any case" "$A" pick readme --title t
rc 2 "an unknown --type is a usage error" "$A" pick WEST-9 --title t --type bogus
rc 2 "a --slug that is not kebab case is a usage error" "$A" pick WEST-9 --title t --slug 'Not_Kebab' --dry-run
rc 2 "check of an invalid ID argument is a usage error" "$A" check 'a/b'
# Line separators that str.splitlines() honours would split the frontmatter; nothing may be pushed.
LS="$(printf '\342\200\250')"   # U+2028
rc 1 "pick refuses a title with U+2028" "$A" pick WEST-11 --title "Cart${LS}total"
rc 1 "pick refuses a title with \\x1c" "$A" pick WEST-11 --title "$(printf 'A\034B')"
rc 1 "pick refuses a --spec that injects a frontmatter line" "$A" pick WEST-11 --title ok --spec "$(printf 'a\nstate: merged')"
expect "no claim was pushed for the refused picks" "! git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-11 >/dev/null"

echo "== pick"
rc 0 "pick --dry-run succeeds" "$A" pick WEST-1 --title "Add login" --dry-run
expect "pick --dry-run prints the new file as a diff" "grep -q '^+state: picked' '$OUT'"
expect "pick --dry-run pushes no claim" "! git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-1 >/dev/null"

STATUS_BEFORE="$(git -C "$A" status --porcelain)"
INDEX_BEFORE="$(shasum "$A/.git/index")"
HEAD_BEFORE="$(git -C "$A" rev-parse HEAD)"
rc 0 "pick WEST-1 from the main checkout" "$A" pick WEST-1 --title "Add login"
WT1="$(tail -n 1 "$OUT")"
expect "pick prints only the worktree path on stdout" "[ \"\$(wc -l <'$OUT' | tr -d ' ')\" = 1 ]"
expect "worktree is a sibling .worktrees folder" "[ '$WT1' = '$TMP/a/repo.worktrees/feat-WEST-1-add-login' ]"
expect "worktree exists on the feature branch" "[ \"\$(git -C '$WT1' branch --show-current)\" = feat/WEST-1-add-login ]"
expect "feature branch tracks origin" "[ \"\$(git -C '$WT1' rev-parse --abbrev-ref '@{u}')\" = origin/feat/WEST-1-add-login ]"
expect "claim/WEST-1 exists on origin" "git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-1 >/dev/null"
expect "feature branch exists on origin at the claim commit" "[ \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/claim/WEST-1)\" = \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/feat/WEST-1-add-login)\" ]"
expect "claim commit sits on top of origin/dev" "[ \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/claim/WEST-1^)\" = \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/dev)\" ]"
expect "status file in the worktree says picked by a@t" "grep -q '^state: picked' '$WT1/docs/status/WEST-1.md' && grep -q '^picked_by: a@t' '$WT1/docs/status/WEST-1.md'"
expect "main checkout status unchanged" "[ \"\$(git -C '$A' status --porcelain)\" = '$STATUS_BEFORE' ]"
expect "main checkout index byte-identical" "[ \"\$(shasum '$A/.git/index')\" = '$INDEX_BEFORE' ]"
expect "main checkout HEAD unchanged" "[ \"\$(git -C '$A' rev-parse HEAD)\" = '$HEAD_BEFORE' ]"
expect "main checkout has no status file" "[ ! -e '$A/docs/status/WEST-1.md' ]"
rc 0 "check accepts the file pick wrote" "$WT1" check WEST-1

rc 1 "second pick of WEST-1 from another clone is refused" "$B" pick WEST-1 --title "Add login"
expect "refusal names the holder" "grep -q 'a@t' '$ERR'"
rc 1 "--resume by someone else is refused" "$B" pick WEST-1 --resume
# Parallel agents share one git identity: a worktree touched in the last 30 minutes may belong to a live session.
rc 1 "--resume by the holder is refused while the worktree changed in the last 30 minutes" "$A" pick WEST-1 --resume
expect "the live refusal names the holder and the worktree and says to ask the user" "grep -q 'a@t' '$ERR' && grep -qF '$WT1' '$ERR' && grep -q 'ask the user' '$ERR' && grep -q -- '--takeover' '$ERR'"
rc 2 "--takeover without --resume is a usage error" "$A" pick WEST-1 --takeover
rc 0 "--resume --takeover resumes a worktree that looks live" "$A" pick WEST-1 --resume --takeover
expect "--resume --takeover prints the existing worktree" "[ \"\$(tail -n 1 '$OUT')\" = '$WT1' ]"
# age_wt <worktree> <ID>: make the worktree look idle for longer than 30 minutes.
age_wt() {
  local gd
  gd="$(git -C "$1" rev-parse --path-format=absolute --git-dir)"
  touch -c -t 202601010000 "$gd/index" "$gd/HEAD" "$gd/agent-progress.md" "$1/docs/status/$2.md"
}
age_wt "$WT1" WEST-1
echo "progress" >"$(git -C "$WT1" rev-parse --path-format=absolute --git-path agent-progress.md)"
rc 1 "--resume is refused when only the progress file changed recently" "$A" pick WEST-1 --resume
age_wt "$WT1" WEST-1
rc 0 "--resume by the holder succeeds once the worktree is idle" "$A" pick WEST-1 --resume
expect "--resume prints the existing worktree" "[ \"\$(tail -n 1 '$OUT')\" = '$WT1' ]"
rc 1 "pick without --resume by the holder is still refused" "$A" pick WEST-1 --title "Add login"

rc 1 "pick refuses when the status on dev is in-progress" "$A" pick WEST-4 --title x
expect "refusal says in-progress" "grep -q 'in-progress' '$ERR'"
rc 1 "pick refuses when a branch for the ID exists" "$A" pick WEST-5 --title x
expect "refusal names the branch" "grep -q 'fix/WEST-5-already-there' '$ERR'"

rc 0 "pick --no-worktree pushes and prints the branch" "$A" pick demo-flow --title "Demo flow" --no-worktree --type chore
expect "slug ID gets branch type/ID" "[ \"\$(tail -n 1 '$OUT')\" = chore/demo-flow ]"
expect "--no-worktree adds no worktree" "[ ! -e '$TMP/a/repo.worktrees/chore-demo-flow' ]"
rc 0 "a slug ID that prefixes another feature's slug ID is not blocked by it" "$B" pick demo --title "Demo" --no-worktree --type chore
expect "the prefix slug ID got its own branch" "[ \"\$(tail -n 1 '$OUT')\" = chore/demo ]"

# The worktree cannot be created after the push: no half-made local branch, and the error says how to resume.
chmod 555 "$TMP/a/repo.worktrees"
rc 1 "pick whose worktree add fails after the push exits 1" "$A" pick WEST-8 --title "Eight"
chmod 755 "$TMP/a/repo.worktrees"
expect "the failure says the claim is held and names --resume" "grep -q 'held by you' '$ERR' && grep -q 'pick WEST-8 --resume' '$ERR'"
expect "the failed pick left no local branch" "[ -z \"\$(git -C '$A' for-each-ref 'refs/heads/feat/WEST-8*')\" ]"
rc 0 "--resume creates the worktree after the failure" "$A" pick WEST-8 --resume
expect "the resumed branch tracks origin" "[ \"\$(git -C \"\$(tail -n 1 '$OUT')\" rev-parse --abbrev-ref '@{u}')\" = origin/feat/WEST-8-eight ]"
# A local branch without upstream (left by an older pick) gets its upstream on --resume.
WT8="$(tail -n 1 "$OUT")"
git -C "$A" worktree remove "$WT8"
git -C "$A" branch -q --unset-upstream feat/WEST-8-eight
rc 0 "--resume reuses an existing local branch" "$A" pick WEST-8 --resume
expect "--resume sets the missing upstream" "[ \"\$(git -C '$WT8' rev-parse --abbrev-ref '@{u}')\" = origin/feat/WEST-8-eight ]"
# --resume --dry-run with neither worktree nor local branch left must create neither.
git -C "$A" worktree remove "$WT8"
git -C "$A" branch -q -D feat/WEST-8-eight
rc 0 "--resume --dry-run succeeds" "$A" pick WEST-8 --resume --dry-run
expect "--resume --dry-run prints the worktree it would add" "[ \"\$(tail -n 1 '$OUT')\" = '$WT8' ]"
expect "--resume --dry-run adds no worktree" "[ ! -e '$WT8' ] && ! git -C '$A' worktree list | grep -q WEST-8"
expect "--resume --dry-run creates no local branch" "[ -z \"\$(git -C '$A' for-each-ref 'refs/heads/feat/WEST-8*')\" ]"

echo "== race"
# A true race: two clones pick the same ID at the same time.
set +e
(cd "$A" && python3 "$S" pick WEST-2 --title "Race" --no-worktree) >"$TMP/race-a" 2>&1 &
PA=$!
(cd "$B" && python3 "$S" pick WEST-2 --title "Race" --no-worktree) >"$TMP/race-b" 2>&1 &
PB=$!
wait $PA; RA=$?
wait $PB; RB=$?
set -e
expect "concurrent picks yield exactly one winner (exits $RA, $RB)" "[ \$(( (RA == 0) + (RB == 0) )) = 1 ]"
expect "origin has exactly one WEST-2 feature branch" "[ \"\$(git --git-dir='$ORIGIN' for-each-ref --format=x 'refs/heads/feat/WEST-2*' | wc -l | tr -d ' ')\" = 1 ]"

# A deterministic lost race: the claim appears on origin after B fetched, right before B pushes.
cat >"$B/.git/hooks/pre-push" <<EOF
#!/bin/sh
git --git-dir="$ORIGIN" update-ref refs/heads/claim/WEST-3 "\$(git --git-dir="$ORIGIN" rev-parse refs/heads/dev)"
EOF
chmod +x "$B/.git/hooks/pre-push"
rc 1 "pick that loses the push race is refused" "$B" pick WEST-3 --title "Lost race"
expect "loser is told it lost the race" "grep -q 'lost the race' '$ERR'"
expect "loser's feature branch was not pushed (atomic)" "[ -z \"\$(git --git-dir='$ORIGIN' for-each-ref 'refs/heads/feat/WEST-3*')\" ]"
expect "loser created no local branch" "[ -z \"\$(git -C '$B' for-each-ref 'refs/heads/feat/WEST-3*')\" ]"
expect "loser created no worktree" "[ ! -e '$TMP/b/repo.worktrees/feat-WEST-3-lost-race' ]"
rm "$B/.git/hooks/pre-push"

# A lost race seen before the push connects: the claim appears on origin between B's fetch and B's push.
# Without the create-only lease this push would fast-forward over the claim, since the claim points at dev.
REALGIT="$(command -v git)"
mkdir -p "$TMP/shim"
cat >"$TMP/shim/git" <<EOF
#!/bin/sh
if [ "\$1" = push ]; then
  "$REALGIT" --git-dir="$ORIGIN" update-ref refs/heads/claim/WEST-6 "\$("$REALGIT" --git-dir="$ORIGIN" rev-parse refs/heads/dev)"
fi
exec "$REALGIT" "\$@"
EOF
chmod +x "$TMP/shim/git"
PATH="$TMP/shim:$PATH" rc 1 "pick whose fetch is stale at push time is refused" "$B" pick WEST-6 --title "Stale fetch"
expect "the existing claim was not overwritten" "[ \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/claim/WEST-6)\" = \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/dev)\" ]"
expect "stale loser's feature branch was not pushed" "[ -z \"\$(git --git-dir='$ORIGIN' for-each-ref 'refs/heads/feat/WEST-6*')\" ]"

# A push the server rejects for its own reasons is not a lost race.
printf '#!/bin/sh\necho "branch names must match policy" >&2\nexit 1\n' >"$ORIGIN/hooks/pre-receive"
chmod +x "$ORIGIN/hooks/pre-receive"
rc 1 "pick whose push the server rejects exits 1" "$A" pick WEST-7 --title "Seven" --no-worktree
expect "a policy rejection is reported as a failed push, not a lost race" "grep -q 'push of claim/WEST-7 and feat/WEST-7-seven failed' '$ERR' && ! grep -q 'lost the race' '$ERR'"
expect "the rejection shows git's reason" "grep -q 'must match policy' '$ERR'"
rm "$ORIGIN/hooks/pre-receive"

echo "== set"
git -C "$A" checkout -q dev
rc 1 "set is refused in the main checkout" "$A" set WEST-4 blocked
expect "refusal says main checkout" "grep -q 'main checkout' '$ERR'"
git -C "$A" checkout -q main
F1="$WT1/docs/status/WEST-1.md"
rc 1 "illegal transition picked -> in-review is refused" "$WT1" set WEST-1 in-review
rc 1 "illegal transition picked -> merged is refused" "$WT1" set WEST-1 merged
SUM="$(shasum "$F1")"
rc 0 "set --dry-run succeeds" "$WT1" set WEST-1 in-progress --dry-run
expect "set --dry-run prints a diff" "grep -q '^+state: in-progress' '$OUT'"
expect "set --dry-run writes nothing" "[ \"\$(shasum '$F1')\" = '$SUM' ]"
rc 0 "legal transition picked -> in-progress" "$WT1" set WEST-1 in-progress --note "first commit"
expect "state is in-progress" "grep -q '^state: in-progress' '$F1'"
expect "transition is noted" "grep -q 'picked -> in-progress: first commit' '$F1'"
rc 2 "set to an unknown state is a usage error" "$WT1" set WEST-1 done
rc 1 "multi-line note is refused" "$WT1" note WEST-1 "$(printf 'a\nb')"
rc 1 "note over 200 characters is refused" "$WT1" note WEST-1 "$(printf 'x%.0s' $(seq 1 201))"
rc 0 "one-line note is accepted" "$WT1" note WEST-1 "see PR for design"
rc 1 "note with U+0085 is refused" "$WT1" note WEST-1 "x$(printf '\302\205')## Deferred"
rc 1 "defer --what with U+2028 is refused" "$WT1" defer WEST-1 --what "a${LS}b" --why w --owner o
rc 1 "ac --text with U+2029 is refused" "$WT1" ac WEST-1 AC9 --text "a$(printf '\342\200\251')b"
rc 1 "set --pr with a line separator is refused" "$WT1" set WEST-1 in-progress --pr "https://x.test/1${LS}state: merged"
rc 0 "check still accepts the file after the refused edits" "$WT1" check WEST-1

echo "== ac"
rc 1 "updating a missing AC without --text is refused" "$WT1" ac WEST-1 AC1 --tier ut --result pass
rc 2 "--tier without --result is a usage error" "$WT1" ac WEST-1 AC1 --tier e2e
rc 2 "--evidence without --tier e2e --result pass is a usage error" "$WT1" ac WEST-1 AC1 --tier ut --result pass --evidence x.json
rc 2 "an AC id that is not AC<number> is a usage error" "$WT1" ac WEST-1 X1 --text t
rc 2 "stale with an empty --acs is a usage error" "$WT1" stale WEST-1 --acs ,
rc 0 "add AC1" "$WT1" ac WEST-1 AC1 --text "User can log in"
expect "AC1 line has all tiers todo" "grep -q '^- AC1: User can log in | UT todo | IT todo | E2E todo$' '$F1'"
rc 0 "AC1 UT pass" "$WT1" ac WEST-1 AC1 --tier ut --result pass
rc 0 "AC1 IT na" "$WT1" ac WEST-1 AC1 --tier it --result na
rc 1 "E2E pass without evidence is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass
expect "refusal asks for an evidence file" "grep -q 'needs an evidence file' '$ERR'"
mkdir -p "$WT1/e2e/reports"
HEADSHA="$(git -C "$WT1" rev-parse HEAD)"
printf '{"id":"WEST-1","verdict":"FAIL","commit":"%s"}\n' "$HEADSHA" >"$WT1/e2e/reports/fail.json"
printf '{"id":"WEST-9","verdict":"PASS","commit":"%s"}\n' "$HEADSHA" >"$WT1/e2e/reports/other.json"
printf '{"id":"west-1","verdict":"PASS","commit":"%s"}\n' "$HEADSHA" >"$WT1/e2e/reports/good.json"
printf 'not json' >"$WT1/e2e/reports/broken.json"
rc 1 "E2E pass with a FAIL verdict is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/fail.json
rc 1 "E2E pass with another ticket's evidence is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/other.json
rc 1 "E2E pass with broken JSON is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/broken.json
rc 1 "E2E pass with a missing file is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/nope.json
rc 1 "E2E pass with evidence outside the repo is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence "$ERR"
printf 'png' >"$WT1/e2e/reports/shot.png"
: >"$WT1/e2e/reports/empty.json"
printf '{}' >"$WT1/e2e/reports/emptyobj.json"
rc 1 "E2E pass with a screenshot as evidence is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/shot.png
expect "the screenshot refusal names the e2e-verify format" "grep -q 'not a .json file' '$ERR' && grep -q 'e2e-verify report' '$ERR'"
rc 1 "E2E pass with an empty JSON file is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/empty.json
expect "the empty-file refusal says it is empty" "grep -q 'empty.json is empty' '$ERR'"
rc 1 "E2E pass with an empty JSON object is refused" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/emptyobj.json
rm "$WT1/e2e/reports/shot.png" "$WT1/e2e/reports/empty.json" "$WT1/e2e/reports/emptyobj.json"
rc 0 "E2E pass with good evidence (id case-insensitive)" "$WT1/e2e" ac WEST-1 AC1 --tier e2e --result pass --evidence reports/good.json
expect "evidence is stored repo-relative" "grep -q '| E2E pass | evidence: e2e/reports/good.json$' '$F1'"
rc 1 "AC text with | is refused" "$WT1" ac WEST-1 AC2 --text "a | b"
rc 0 "add AC2" "$WT1" ac WEST-1 AC2 --text "Wrong password shows an error"
rc 0 "defer an item" "$WT1" defer WEST-1 --what "SSO login" --why "not in this sprint" --owner "PO"
expect "deferred line is written" "grep -q '^- SSO login - not in this sprint - owner: PO$' '$F1'"
rc 0 "check accepts the edited file" "$WT1" check WEST-1

echo "== merged gate and stale"
rc 0 "in-progress -> in-review" "$WT1" set WEST-1 in-review
rc 1 "merged with AC2 still todo is refused" "$WT1" set WEST-1 merged
rc 0 "AC2 UT pass" "$WT1" ac WEST-1 AC2 --tier ut --result pass
rc 0 "AC2 IT na" "$WT1" ac WEST-1 AC2 --tier it --result na
rc 0 "AC2 E2E na" "$WT1" ac WEST-1 AC2 --tier e2e --result na
rc 0 "ac --text with the same text keeps the tiers" "$WT1" ac WEST-1 AC2 --text "Wrong password shows an error"
expect "unchanged text kept AC2's tiers" "grep -q '^- AC2: Wrong password shows an error | UT pass | IT na | E2E na$' '$F1'"
rc 0 "ac --text that changes an AC's wording" "$WT1" ac WEST-1 AC2 --text "Wrong password shows an inline error"
expect "a changed AC has every tier reset to todo, na included" "grep -q '^- AC2: Wrong password shows an inline error | UT todo | IT todo | E2E todo$' '$F1'"
expect "the text change is noted" "grep -q 'AC2 text changed, all tiers reset to todo' '$F1'"
rc 0 "AC2 UT pass again" "$WT1" ac WEST-1 AC2 --tier ut --result pass
rc 0 "AC2 IT na again" "$WT1" ac WEST-1 AC2 --tier it --result na
rc 0 "AC2 E2E na again" "$WT1" ac WEST-1 AC2 --tier e2e --result na
rc 0 "stale AC1 after a spec change" "$WT1" stale WEST-1 --acs AC1 --note "spec v2"
expect "stale reopens in-review to in-progress" "grep -q '^state: in-progress' '$F1'"
expect "AC1 passed tiers became stale, na kept" "grep -q '^- AC1: User can log in | UT stale | IT na | E2E stale' '$F1'"
rc 1 "stale with an unknown AC is refused" "$WT1" stale WEST-1 --acs AC7

echo "== board"
git -C "$WT1" add -A
git -C "$WT1" commit -q -m "wip"
git -C "$WT1" push -q
rc 0 "board runs from another clone's main checkout" "$B" board
expect "board shows WEST-1 from its unmerged branch as in-progress" "grep -q '^| WEST-1 | Add login | in-progress | feat/WEST-1-add-login | 1/2 | 1 |' '$OUT'"
expect "board shows the claimed-but-unmerged WEST-2" "grep -q '^| WEST-2 | Race | picked |' '$OUT'"
expect "board shows WEST-4 from dev" "grep -q '^| WEST-4 |' '$OUT'"
rc 0 "board --live never fails on missing tools" "$B" board --live
rc 0 "board --out writes a file" "$B" board --out "$TMP/board.md"
expect "board --out file has the table" "grep -q '^| WEST-1 |' '$TMP/board.md'"
expect "board leaves the checkout clean" "[ -z \"\$(git -C '$B' status --porcelain)\" ]"
# A broken file must show up on the board, not vanish from it: on dev, on a claim, and not valid UTF-8.
DEV_SHA="$(git --git-dir="$ORIGIN" rev-parse refs/heads/dev)"
LONG="$(printf 'x%.0s' $(seq 1 250))"
{ sed 's/WEST-4/WEST-80/g' "$SEED/docs/status/WEST-4.md"; echo "- 2026-01-02 $LONG"; } >"$SEED/docs/status/WEST-80.md"
git -C "$SEED" add -A && git -C "$SEED" commit -q -m bad80 && git -C "$SEED" push -q origin HEAD:dev
git -C "$SEED" rm -q docs/status/WEST-80.md
sed 's/WEST-4/WEST-81/g' "$SEED/docs/status/WEST-4.md" >"$SEED/docs/status/WEST-81.md"
printf '\377\n' >>"$SEED/docs/status/WEST-81.md"
git -C "$SEED" add -A && git -C "$SEED" commit -q -m bad81 && git -C "$SEED" push -q origin HEAD:refs/heads/claim/WEST-81
rc 0 "board with invalid files still runs" "$B" board
expect "board shows the invalid file on dev as a row" "grep -q '^| WEST-80 | - | invalid |' '$OUT'"
expect "board says why the dev file is invalid" "grep -q 'WEST-80.md on origin/dev is invalid: line .*note longer than 200' '$OUT'"
expect "board shows a non-UTF-8 claim file as a row" "grep -q '^| WEST-81 | - | invalid |' '$OUT'"
expect "board says why the claim file is invalid" "grep -q 'WEST-81.md on claim/WEST-81 is invalid: .*not valid UTF-8' '$OUT'"
git -C "$SEED" push -q -f origin "$DEV_SHA:refs/heads/dev" :refs/heads/claim/WEST-81
git -C "$SEED" reset -q --hard "$DEV_SHA"
git -C "$B" fetch -q --prune origin

echo "== release"
rc 1 "release while in-progress is refused" "$WT1" release WEST-1
rc 0 "AC1 UT pass again" "$WT1" ac WEST-1 AC1 --tier ut --result pass
cp "$WT1/e2e/reports/good.json" "$WT1/e2e/reports/good2.json"
rc 0 "AC1 E2E pass again" "$WT1" ac WEST-1 AC1 --tier e2e --result pass --evidence e2e/reports/good2.json
rc 0 "in-progress -> in-review" "$WT1" set WEST-1 in-review --pr https://example.test/pr/1
rc 0 "in-review -> merged with every AC done" "$WT1" set WEST-1 merged
rc 0 "check accepts the merged file" "$WT1" check WEST-1
SUM="$(shasum "$F1")"
rc 1 "stale on a merged file is refused" "$WT1" stale WEST-1 --acs AC1 --note "spec v3"
expect "the stale refusal names the one path: release, pick --slug, stale in the new worktree" "grep -q 'status.py release WEST-1' '$ERR' && grep -q 'pick WEST-1 --slug <new-slug>' '$ERR' && grep -q 'stale WEST-1 --acs AC1. in the new worktree' '$ERR'"
rc 1 "merged -> in-progress is illegal" "$WT1" set WEST-1 in-progress
expect "the refused reopens left the merged file unchanged" "[ \"\$(shasum '$F1')\" = '$SUM' ]"
git -C "$WT1" add docs/status
git -C "$WT1" commit -q -m "status only"
rc 1 "check --ref HEAD refuses evidence that is not committed" "$WT1" check WEST-1 --ref HEAD
expect "check --ref names the uncommitted evidence" "grep -q 'good2.json is not committed at HEAD' '$OUT'"
rc 1 "release before the PR is merged into dev is refused" "$WT1" release WEST-1
expect "refusal says merged must be on origin/dev" "grep -q 'merged on origin/dev' '$ERR'"
git -C "$WT1" add -A
git -C "$WT1" commit -q -m "WEST-1 done"
git -C "$WT1" push -q
rc 0 "check --ref HEAD accepts the committed file and evidence" "$WT1" check WEST-1 --ref HEAD
rc 2 "check --ref and --base together is a usage error" "$WT1" check --ref HEAD --base origin/dev
git -C "$WT1" push -q origin HEAD:dev
rc 1 "the holder's pick of a stale (merged) claim is refused" "$A" pick WEST-1 --slug v2
expect "the stale-claim refusal suggests release and not --resume" "grep -q 'status.py release WEST-1' '$ERR' && ! grep -q -- '--resume' '$ERR'"
rc 0 "release --dry-run" "$WT1" release WEST-1 --dry-run
expect "release --dry-run keeps the claim" "git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-1 >/dev/null"
rc 0 "release after the merge into dev" "$WT1" release WEST-1
expect "claim/WEST-1 is gone from origin" "! git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-1 >/dev/null"
rc 1 "release with no claim is refused" "$WT1" release WEST-1
rc 1 "merged -> in-review is illegal" "$WT1" set WEST-1 in-review

echo "== re-pick after merge"
rc 1 "re-pick reusing the kept merged branch name is refused" "$B" pick WEST-1
expect "refusal asks for a new --slug" "grep -q 'pass --slug' '$ERR'"
git -C "$SEED" push -q origin HEAD:refs/heads/fix/WEST-1-someone-else
rc 1 "re-pick is refused while another branch for the ID exists" "$B" pick WEST-1 --slug v2
git -C "$SEED" push -q origin --delete fix/WEST-1-someone-else
rc 0 "re-pick of a merged feature succeeds while its merged branch is kept" "$B" pick WEST-1 --slug v2
WT1B="$(tail -n 1 "$OUT")"
expect "re-pick keeps the ACs and title, resets the state" "grep -q '^state: picked' '$WT1B/docs/status/WEST-1.md' && grep -q '^title: Add login' '$WT1B/docs/status/WEST-1.md' && grep -q '^- AC1: User can log in' '$WT1B/docs/status/WEST-1.md'"
expect "re-pick is noted" "grep -q 're-picked by b@t on feat/WEST-1-v2' '$WT1B/docs/status/WEST-1.md'"
CLAIM1="$(git --git-dir="$ORIGIN" rev-parse refs/heads/claim/WEST-1)"
rc 1 "release refuses the re-pick's live claim although the earlier pick is merged on dev" "$A" release WEST-1
expect "the refusal says the merged file is from an earlier pick" "grep -q 'earlier pick (feat/WEST-1-add-login)' '$ERR'"
expect "the re-pick's claim is kept" "[ \"\$(git --git-dir='$ORIGIN' rev-parse refs/heads/claim/WEST-1)\" = '$CLAIM1' ]"
rc 1 "the old merged worktree cannot reopen the feature" "$WT1" stale WEST-1 --acs AC1
expect "the reopen refusal points at release and a re-pick" "grep -q 'is merged' '$ERR' && grep -q 'pick WEST-1 --slug' '$ERR'"
rc 0 "board still runs after the refused release" "$B" board
expect "board shows the re-pick, not the old merged row" "grep -q '^| WEST-1 | Add login | picked | feat/WEST-1-v2 |' '$OUT'"
# A claim that changes between release's check and its delete is kept (the delete is leased).
rc 0 "drop the re-pick" "$WT1B" set WEST-1 dropped --note "not needed"
git -C "$WT1B" commit -q -am "drop" && git -C "$WT1B" push -q
cat >"$TMP/shim/git" <<EOF
#!/bin/sh
if [ "\$1" = push ]; then
  "$REALGIT" --git-dir="$ORIGIN" update-ref refs/heads/claim/WEST-1 "\$("$REALGIT" --git-dir="$ORIGIN" rev-parse refs/heads/dev)"
fi
exec "$REALGIT" "\$@"
EOF
PATH="$TMP/shim:$PATH" rc 1 "release whose claim moved after the check is refused" "$B" release WEST-1
expect "the moved claim was not deleted" "git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-1 >/dev/null"
git --git-dir="$ORIGIN" update-ref refs/heads/claim/WEST-1 "$CLAIM1"
rc 0 "release of the dropped re-pick" "$B" release WEST-1
expect "claim/WEST-1 is released" "! git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-1 >/dev/null"

echo "== defer the whole feature, release, re-pick"
rc 0 "pick WEST-42" "$A" pick WEST-42 --title "Cart total"
WT42="$(tail -n 1 "$OUT")"
rc 0 "WEST-42 in-progress" "$WT42" set WEST-42 in-progress
rc 0 "WEST-42 AC1" "$WT42" ac WEST-42 AC1 --text "Total is shown"
rc 0 "WEST-42 deferred" "$WT42" set WEST-42 deferred --note later
rc 1 "release refuses a deferral that is not pushed yet" "$A" release WEST-42
git -C "$WT42" commit -q -am "defer" && git -C "$WT42" push -q
rc 0 "release of the pushed deferral" "$A" release WEST-42
rc 1 "the released worktree cannot reopen the feature without a claim" "$WT42" set WEST-42 in-progress
expect "the refusal says the claim is gone and to pick again" "grep -q 'gone from origin' '$ERR' && grep -q 'pick WEST-42' '$ERR'"
expect "the refused reopen left the file deferred" "grep -q '^state: deferred' '$WT42/docs/status/WEST-42.md'"
rc 1 "re-pick reusing the deferred branch name asks for a new slug" "$B" pick WEST-42 --title "Cart total"
expect "refusal asks for a new --slug" "grep -q 'pass --slug' '$ERR'"
rc 0 "another clone re-picks the deferred feature" "$B" pick WEST-42 --slug v2 --no-worktree
expect "the re-pick keeps the deferred file's ACs" "git --git-dir='$ORIGIN' show refs/heads/claim/WEST-42:docs/status/WEST-42.md | grep -q '^- AC1: Total is shown'"
expect "the re-pick resets the state" "git --git-dir='$ORIGIN' show refs/heads/claim/WEST-42:docs/status/WEST-42.md | grep -q '^state: picked'"
rc 1 "the old worktree cannot reopen under the new claim" "$WT42" set WEST-42 in-progress
expect "the refusal names the new holder" "grep -q 'belongs to b@t on feat/WEST-42-v2' '$ERR'"
rc 1 "release refuses the re-pick although the old branch says deferred" "$A" release WEST-42
expect "the re-pick's claim is kept" "git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-42 >/dev/null"

echo "== merged in the UI while in-review, then the recovery"
rc 0 "pick WEST-44" "$A" pick WEST-44 --title "Recover me"
WT44="$(tail -n 1 "$OUT")"
rc 0 "WEST-44 in-progress" "$WT44" set WEST-44 in-progress
rc 0 "WEST-44 AC1" "$WT44" ac WEST-44 AC1 --text "Works" --tier ut --result pass
rc 0 "WEST-44 AC1 IT na" "$WT44" ac WEST-44 AC1 --tier it --result na
rc 0 "WEST-44 AC1 E2E na" "$WT44" ac WEST-44 AC1 --tier e2e --result na
rc 0 "WEST-44 in-review" "$WT44" set WEST-44 in-review
git -C "$WT44" commit -q -am "in review" && git -C "$WT44" push -q
# The user squash-merges in the UI and keeps the branch; nobody ran set merged.
git -C "$WT44" fetch -q origin
SQUASH="$(git -C "$WT44" commit-tree "$(git -C "$WT44" rev-parse 'HEAD^{tree}')" -p origin/dev -m "WEST-44 (squash)")"
git -C "$WT44" push -q origin "$SQUASH:refs/heads/dev"
rc 1 "release refuses while dev says in-review" "$A" release WEST-44
expect "the release refusal points at the recovery" "grep -q 'recovery' '$ERR'"
rc 1 "a re-pick is refused while the claim stands" "$B" pick WEST-44 --slug again
expect "the pick refusal explains the merged in-review claim" "grep -q 'merged while the file said in-review' '$ERR' && grep -q 'recovery' '$ERR'"
# The recovery runs in the existing feature worktree.
git -C "$WT44" fetch -q origin && git -C "$WT44" merge -q --no-edit origin/dev
rc 0 "recovery sets merged in the old worktree" "$WT44" set WEST-44 merged --pr https://example.test/pr/44
git -C "$WT44" commit -q -am "record merged"
expect "the recovery push fast-forwards the kept branch" "git -C '$WT44' push -q 2>/dev/null"
expect "the recovery PR merges into dev" "git -C '$WT44' push -q origin HEAD:dev 2>/dev/null"
rc 0 "release after the recovery" "$A" release WEST-44
expect "claim/WEST-44 is released" "! git --git-dir='$ORIGIN' rev-parse -q --verify refs/heads/claim/WEST-44 >/dev/null"

echo "== check"
D="$WT1/docs/status"
sed -e 's/^state: .*/state: merged/' -e 's/UT pass | IT na | E2E pass/UT stale | IT na | E2E pass/' "$F1" >"$D/WEST-1.md.tmp"
sed 's/WEST-1/WEST-90/g' "$D/WEST-1.md.tmp" | sed 's|evidence: e2e/reports/good2*.json|evidence: e2e/reports/good90.json|' >"$D/WEST-90.md"
printf '{"id":"WEST-90","verdict":"PASS"}\n' >"$WT1/e2e/reports/good90.json"
rm "$D/WEST-1.md.tmp"
rc 1 "check catches merged with a stale AC" "$WT1" check WEST-90
expect "check names the stale tier" "grep -q 'state merged but AC1 has UT stale' '$OUT'"
sed -e 's/WEST-1/WEST-91/g' -e 's/^state: .*/state: in-progress/' -e 's/| UT pass |/| UT done |/' "$F1" >"$D/WEST-91.md"
rc 1 "check catches an unknown token" "$WT1" check WEST-91
expect "check names the unknown token" "grep -q \"unknown UT result 'done'\" '$OUT'"
sed -e 's/WEST-1/WEST-92/g' -e 's|evidence: e2e/reports/good2*.json|evidence: e2e/reports/gone.json|' "$F1" >"$D/WEST-92.md"
rc 1 "check catches missing evidence" "$WT1" check WEST-92
expect "check names the missing file" "grep -q 'gone.json does not exist' '$OUT'"
sed -e 's/WEST-1/WEST-93/g' -e '/^spec:/d' "$F1" >"$D/WEST-93.md"
rc 1 "check catches a missing frontmatter key" "$WT1" check WEST-93
sed -e 's/WEST-1/WEST-94/g' -e 's|^branch: .*|branch: feat/other|' "$F1" >"$D/WEST-94.md"
rc 1 "check catches a branch without the ID" "$WT1" check WEST-94
sed -e 's/WEST-1/WEST-97/g' -e 's/| E2E pass | evidence: .*$/| E2E na/' "$F1" >"$D/WEST-97.md"
rc 0 "check accepts the branch <type>/<ID>-<slug>" "$WT1" check WEST-97
sed -i.bak 's|^branch: .*|branch: feat/WEST-970-other|' "$D/WEST-97.md" && rm "$D/WEST-97.md.bak"
rc 1 "check rejects a branch of another ID that starts with this one" "$WT1" check WEST-97
expect "check names the branch rule" "grep -q 'is not <type>/WEST-97 or <type>/WEST-97-<slug>' '$OUT'"
sed -e 's/WEST-1/WEST-95/g' -e 's/^state: .*/state: done/' "$F1" >"$D/WEST-95.md"
rc 1 "check catches an unknown state" "$WT1" check WEST-95
rc 1 "check with no IDs fails when any file is bad" "$WT1" check
expect "check reports one line per problem across files" "[ \"\$(grep -c 'docs/status/WEST-9' '$OUT')\" -ge 6 ]"
rc 1 "edits are refused on a file with unknown tokens" "$WT1" note WEST-91 "x"
expect "refusal says the file is invalid" "grep -q 'WEST-91.md is invalid' '$ERR'"
rc 1 "check --base catches a changed bad file" "$WT1" check --base origin/dev
expect "check --base reports the changed file" "grep -q 'WEST-91.md' '$OUT'"
rc 0 "check --base skips unchanged files" "$B" check --base origin/dev
rc 2 "check --base with an option-shaped value is a usage error" "$WT1" check --base=--output=pwned
expect "the option-shaped --base wrote no file" "[ -z \"\$(ls '$WT1' | grep pwned)\" ]"
rc 1 "check --base with a missing ref is refused" "$WT1" check --base no-such-ref
sed 's/WEST-1/WEST-96/g' "$F1" >"$D/WEST-96.md"
printf '\377\n' >>"$D/WEST-96.md"
rc 1 "check reports a non-UTF-8 file as a problem line" "$WT1" check WEST-96
expect "check names the encoding problem" "grep -q 'WEST-96.md: .*not valid UTF-8' '$OUT'"
rc 1 "edits refuse a non-UTF-8 file without crashing" "$WT1" note WEST-96 "x"
expect "the edit refusal names the encoding problem" "grep -q 'not valid UTF-8' '$ERR'"
git -C "$WT1" add "$D/WEST-96.md" && git -C "$WT1" commit -q -m bad -- "$D/WEST-96.md"
rc 1 "check --ref reports a committed non-UTF-8 file as a problem line" "$WT1" check WEST-96 --ref HEAD
expect "check --ref names the encoding problem" "grep -q 'not valid UTF-8' '$OUT'"
git -C "$WT1" reset -q --soft HEAD~1 && git -C "$WT1" reset -q -- "$D/WEST-96.md"
rm "$D"/WEST-9?.md
rc 0 "check passes once the bad files are gone" "$WT1" check
# A byte order mark from an editor is not a broken file, and the next script edit drops it.
{ printf '\357\273\277'; cat "$F1"; } >"$F1.tmp" && mv "$F1.tmp" "$F1"
rc 0 "check accepts a file with a UTF-8 byte order mark" "$WT1" check WEST-1
rc 0 "an edit works on a file with a byte order mark" "$WT1" note WEST-1 "bom"
expect "the edit removed the byte order mark" "[ \"\$(head -c 3 '$F1')\" = '---' ]"

if [ "$FAIL" = 0 ]; then echo "all status.py checks passed"; else echo "status.py checks FAILED"; exit 1; fi
