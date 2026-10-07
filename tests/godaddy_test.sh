#!/usr/bin/env bash
# Offline regression tests; gddy and confirmation are mocked.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/ui.sh
. "$ROOT/lib/ui.sh"
# shellcheck source=../lib/godaddy.sh
. "$ROOT/lib/godaddy.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
DOMAIN=example.com
GDDY_ENV=prod

# Log calls so tests verify that no write or prompt occurs on a no-op/failure.
gddy() {
  printf '%s\n' "$*" >>"$TMP/calls"
  if [ "$1 $2" = "domain get" ]; then
    printf '%s\n' "$RESPONSE"
    return "$GET_STATUS"
  fi
  return "$SET_STATUS"
}
confirm() {
  printf 'confirm %s\n' "$*" >>"$TMP/calls"
  return "$CONFIRM_STATUS"
}

run_case() {
  local name="$1" expected_status="$2" expected_prompts="$3" expected_sets="$4" message="$5"
  local status prompts sets
  : >"$TMP/calls"
  set +e
  (set -euo pipefail; gddy_set_nameservers alice.ns.cloudflare.com bob.ns.cloudflare.com) >"$TMP/output" 2>&1
  status=$?
  set -e
  prompts=$(grep -c '^confirm ' "$TMP/calls" || true)
  sets=$(grep -c '^domain nameservers set ' "$TMP/calls" || true)
  if [ "$status" != "$expected_status" ] || [ "$prompts" != "$expected_prompts" ] \
     || [ "$sets" != "$expected_sets" ] || ! grep -qF "$message" "$TMP/output"; then
    printf 'FAIL: %s (status=%s prompts=%s sets=%s)\n' "$name" "$status" "$prompts" "$sets" >&2
    exit 1
  fi
  grep -qxF 'domain get example.com --env prod --json' "$TMP/calls"
  if [ "$expected_sets" = "1" ]; then
    local expected='domain nameservers set --nameserver alice.ns.cloudflare.com --nameserver bob.ns.cloudflare.com example.com --env prod'
    if [ "$DRY_RUN" = "1" ]; then expected+=' --dry-run'; fi
    grep -qxF "$expected" "$TMP/calls"
  fi
  printf 'PASS: %s\n' "$name"
}

GET_STATUS=0 SET_STATUS=0 CONFIRM_STATUS=0 DRY_RUN=0
RESPONSE='{"data":{"nameServers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com"]}}'
run_case 'already configured' 0 0 0 'skipping update'
RESPONSE='{"data":{"nameServers":["BOB.NS.CLOUDFLARE.COM.","Alice.NS.Cloudflare.Com"]}}'
run_case 'order, case and trailing dot are ignored' 0 0 0 'skipping update'
DRY_RUN=1
run_case 'already configured dry run' 0 0 0 'skipping update'

DRY_RUN=0
RESPONSE='{"data":{"nameServers":["ns01.domaincontrol.com","ns02.domaincontrol.com"]}}'
run_case 'different nameservers' 0 1 1 'nameservers set:'
DRY_RUN=1
run_case 'different nameservers dry run' 0 0 1 'GoDaddy:'
DRY_RUN=0
CONFIRM_STATUS=1
run_case 'declined confirmation' 1 1 0 'aborted before nameserver change'
CONFIRM_STATUS=0 SET_STATUS=1
run_case 'update failure remains fatal' 1 1 1 'nameserver update failed'
SET_STATUS=0
RESPONSE='{"data":{"nameServers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com","ns01.domaincontrol.com"]}}'
run_case 'extra current nameserver requires replacement' 0 1 1 'nameservers set:'
RESPONSE='{"data":{"nameServers":["alice.ns.cloudflare.com"]}}'
run_case 'partial match requires replacement' 0 1 1 'nameservers set:'

GET_STATUS=1
run_case 'lookup failure stops before mutation' 1 0 0 'could not verify current nameservers'
GET_STATUS=0
for RESPONSE in 'invalid json' '{"data":{}}' '{"data":{"nameServers":null}}' \
  '{"data":{"nameServers":[]}}' '{"data":{"nameServers":"alice.ns.cloudflare.com"}}' \
  '{"data":{"nameServers":[null]}}' '{"data":{"nameServers":[""]}}'; do
  run_case "invalid response: $RESPONSE" 1 0 0 'could not read current nameservers'
done
