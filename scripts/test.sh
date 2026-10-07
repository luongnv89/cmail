#!/usr/bin/env bash
# Offline checks only; fixtures mock provider access and installers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TEST_BASH="${CMAIL_TEST_BASH:-bash}"
export PYTHONDONTWRITEBYTECODE=1
for tool in "$TEST_BASH" jq python3 node shellcheck; do
  command -v "$tool" >/dev/null || { printf 'Test dependency missing: %s\n' "$tool" >&2; exit 1; }
done
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
started=$SECONDS
count=0
run() {
  count=$((count + 1))
  if "$@" > "$TMP/log" 2>&1; then
    printf 'PASS %s\n' "$*"
    tail -n 1 "$TMP/log"
  else
    printf 'FAIL %s\n' "$*" >&2
    cat "$TMP/log" >&2
    exit 1
  fi
}
for file in cmail install.sh lib/*.sh scripts/*.sh; do "$TEST_BASH" -n "$file"; done
for suite in tests/*_test.sh; do run "$TEST_BASH" "$suite"; done
for suite in tests/pages_test.py tests/site_test.py tests/skill_setup_test.py; do run python3 "$suite"; done
run node --test tests/checklist_test.js
printf 'PASS: %s offline suites in %ss (%s)\n' "$count" "$((SECONDS - started))" "$TEST_BASH"
