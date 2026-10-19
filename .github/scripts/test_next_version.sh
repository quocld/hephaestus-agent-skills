#!/usr/bin/env bash
# Cases for next_version.py in a throwaway repo; exits 1 on any mismatch.
set -euo pipefail
N="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/next_version.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T"; git init -q -b main
c() { git -c user.email=t@t -c user.name=t commit -q --allow-empty "$@"; }
FAIL=0
want() { got="$(python3 "$N" | tr '\n' ' ')"; case "$got" in *"$1"*) echo "ok   $2 -> $1";; *) echo "FAIL $2: want $1, got $got"; FAIL=1;; esac; }
c -m "init";                                   want "version=v1.0.0" "first release"
git tag v1.0.0;                                want "release=false" "head already tagged"
c -m "fix: a";                                 want "version=v1.0.1" "fix"
c -m "feat(x): b";                             want "version=v1.1.0" "feat after fix"
c -m "feat(release): c" -m "a sentence about the rule: ! or BREAKING CHANGE major"
                                               want "version=v1.1.0" "BREAKING CHANGE in prose is not a footer"
c -m "refactor: d" -m "BREAKING CHANGE: the api moved"
                                               want "version=v2.0.0" "BREAKING CHANGE: footer"
git tag v2.0.0
c -m "feat!: e";                               want "version=v3.0.0" "bang after the type"
git tag v3.0.0
c -m "chore: f" -m "BREAKING-CHANGE: also a footer"; want "version=v4.0.0" "BREAKING-CHANGE: footer"
[ "$FAIL" = 0 ] && echo "all next_version checks passed" || { echo "next_version checks FAILED"; exit 1; }
