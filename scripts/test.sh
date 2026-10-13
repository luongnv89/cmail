#!/usr/bin/env bash
# Offline checks only: the Cloudflare API is a loopback fixture and gddy is faked.
set -euo pipefail
shopt -s nullglob
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
for tool in cargo python3 node; do
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
cargo build --quiet --locked
export CMAIL_BIN="$ROOT/target/debug/cmail"
for file in install.sh scripts/*.sh; do bash -n "$file"; done
run cargo test --quiet --locked
for suite in tests/*_test.sh; do run bash "$suite"; done
for suite in tests/cli_test.py tests/setup_flow_test.py tests/timing_test.py \
             tests/pages_test.py tests/site_test.py tests/skill_setup_test.py; do
  run python3 "$suite"
done
run node --test tests/checklist_test.js
run node --test tests/terminal_test.js
printf 'PASS: %s offline suites in %ss\n' "$count" "$((SECONDS - started))"
