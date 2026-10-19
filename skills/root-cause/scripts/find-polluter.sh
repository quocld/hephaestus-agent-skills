#!/usr/bin/env bash
# Find the test file that creates unwanted state (a stray file or folder).
# Runs each matching test file alone, in order, and stops at the first one after which <path> exists.
# Usage: bash find-polluter.sh <path> <test-glob> <test-command>
#   <test-command> must run exactly one file, given as its last argument.
# Example: bash find-polluter.sh tmp-uploads 'apps/**/*.test.ts' 'pnpm vitest run'
# Exit codes: 1 = polluter found, 0 = none found, 2 = usage error or the runs could not be trusted.
# Output of every run goes to a log file whose path is printed at the start.
set -u

if [ $# -ne 3 ]; then
  echo "Usage: bash find-polluter.sh <path> <test-glob> <test-command>" >&2
  exit 2
fi

POLLUTION="$1"
PATTERN="${2#./}"
TEST_CMD="$3"
LOG="$(mktemp -t find-polluter.XXXXXX)"

if [ -e "$POLLUTION" ]; then
  echo "$POLLUTION already exists; remove it first so the run starts clean." >&2
  exit 2
fi

# Skip dependency and build folders at any depth.
# find -path cannot match '**/' against zero directories, so also try the pattern with '**/' removed.
FILES=()
while IFS= read -r f; do FILES+=("$f"); done < <(
  find . \( -name node_modules -o -name .git -o -name dist -o -name build -o -name .next -o -name coverage \) -prune -o \
    -type f \( -path "./$PATTERN" -o -path "./${PATTERN//\*\*\//}" \) -print | sort -u
)
TOTAL=${#FILES[@]}
if [ "$TOTAL" -eq 0 ]; then
  echo "No test files match: $2" >&2
  exit 2
fi
echo "Checking $TOTAL test files for: $POLLUTION (log: $LOG)"

FAILED=0
COUNT=0
for FILE in "${FILES[@]}"; do
  COUNT=$((COUNT + 1))
  echo "[$COUNT/$TOTAL] $FILE"
  echo "=== $FILE" >>"$LOG"
  bash -c "$TEST_CMD \"\$1\"" _ "$FILE" >>"$LOG" 2>&1 || FAILED=$((FAILED + 1))
  if [ -e "$POLLUTION" ]; then
    echo "Polluter: $FILE created $POLLUTION"
    ls -la "$POLLUTION"
    exit 1
  fi
done

if [ "$FAILED" -eq "$TOTAL" ]; then
  echo "Every run failed, so the test command is probably wrong; nothing was proven. See $LOG" >&2
  exit 2
fi
echo "No polluter found ($FAILED of $TOTAL runs failed; see $LOG)."
exit 0
