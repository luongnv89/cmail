#!/usr/bin/env bash
# Offline forwarding-rule tests exercise real jq payload generation.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/ui.sh
. "$ROOT/lib/ui.sh"
# shellcheck source=../lib/cloudflare.sh
. "$ROOT/lib/cloudflare.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
DOMAIN=example.com DEST_EMAIL='contact+test@gmail.com' CLOUDFLARE_API_TOKEN=test-token

jq() {
  if [ "$FAIL_PAYLOAD" = 1 ] && [ "$1" = -nc ]; then
    printf 'simulated jq payload failure\n' >&2; return 3
  fi
  command jq "$@"
}
curl() {
  local method=GET url='' data=''
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --connect-timeout|--max-time) shift 2 ;;
      -sS) shift ;;
      -X) method="$2"; shift 2 ;;
      -H|-w) shift 2 ;;
      -d) data="$2"; shift 2 ;;
      https://*) url="$1"; shift ;;
      *) printf 'unexpected curl argument\n' >&2; return 99 ;;
    esac
  done
  printf '%s %s\n' "$method" "$url" >>"$TMP/calls"
  if [ "$method" = GET ]; then
    [ "$url" = "$CF_API/zones/test-zone/email/routing/rules?per_page=50&page=1" ] || return 99
    printf '%s\n%s' "$GET_BODY" "$GET_HTTP"; return 0
  fi
  [ "$url" = "$CF_API/zones/test-zone/email/routing/rules" ] || return 99
  # Validate the exact payload shape, including the destination array.
  jq -e --arg dest "$DEST_EMAIL" '
    .enabled == true and (.priority | type == "number") and
    (.matchers | length == 1) and .matchers[0].type == "literal" and
    .matchers[0].field == "to" and (.matchers[0].value | endswith("@example.com")) and
    (.actions | length == 1) and .actions[0].type == "forward" and
    .actions[0].value == [$dest]
  ' >/dev/null <<<"$data" || return 99
  printf '%s\n' "$data" >>"$TMP/payloads"
  printf '%s\n%s' "$POST_BODY" "$POST_HTTP"
}
reset_responses() {
  GET_BODY='{"success":true,"result":[]}' GET_HTTP=200
  POST_BODY='{"success":true,"result":{"id":"new-rule"}}' POST_HTTP=200
  FAIL_PAYLOAD=0 ADDRESSES=contact
}
run_case() {
  local name="$1" expected_status="$2" expected_posts="$3" message="$4" status posts
  : >"$TMP/calls"; : >"$TMP/payloads"
  set +e
  (set -euo pipefail; cf_rules_ensure test-zone; printf 'setup continues\n') >"$TMP/output" 2>&1
  status=$?
  set -e
  posts=$(grep -c '^POST ' "$TMP/calls" || true)
  if [ "$status" != "$expected_status" ] || [ "$posts" != "$expected_posts" ] \
     || ! grep -qF "$message" "$TMP/output"; then
    printf 'FAIL: %s (status=%s posts=%s)\n' "$name" "$status" "$posts" >&2; exit 1
  fi
  if [ "$expected_status" != 0 ] && grep -qF 'setup continues' "$TMP/output"; then
    printf 'FAIL: continued after error\n' >&2; exit 1
  fi
  printf 'PASS: %s\n' "$name"
}

reset_responses
run_case 'contact rule has valid forward destination array' 0 1 "contact@$DOMAIN -> $DEST_EMAIL"
reset_responses
ADDRESSES='contact, hello'
run_case 'multiple addresses produce valid rules with increasing priority' 0 2 'setup continues'
jq -se 'map(.priority) == [0,1] and map(.matchers[0].value) == ["contact@example.com","hello@example.com"]' "$TMP/payloads" >/dev/null
reset_responses
GET_BODY='{"success":true,"result":[{"enabled":true,"matchers":[{"type":"literal","field":"to","value":"contact@example.com"}],"actions":[{"type":"forward","value":["contact+test@gmail.com"]}]}]}'
run_case 'correct enabled existing rule is skipped' 0 0 'already exists'
GET_BODY=$(jq -c '.result[0].enabled = false' <<<"$GET_BODY")
run_case 'disabled existing rule gives actionable recovery' 1 0 'enable/correct it'
GET_BODY=$(jq -c '.result[0].enabled = true | .result[0].actions[0].value = ["wrong@gmail.com"]' <<<"$GET_BODY")
run_case 'different destination is not reported as ready' 1 0 'Existing rules were not overwritten'
reset_responses
ADDRESSES='contact,contact'
run_case 'duplicate requested addresses create only one rule' 0 1 'already exists'
reset_responses
FAIL_PAYLOAD=1
run_case 'payload generation failure sends no POST' 1 0 'no request sent'
reset_responses
GET_HTTP=403 GET_BODY='{"success":false,"errors":[{"message":"Rules access denied"}]}'
run_case 'lookup failure prevents creation' 1 0 'Rules access denied'
grep -qF 'Zone > Email Routing Rules > Edit' "$TMP/output"
reset_responses
GET_BODY='{"success":true,"result":null}'
run_case 'malformed list prevents creation' 1 0 'invalid forwarding rules'
reset_responses
POST_HTTP=422 POST_BODY='{"success":false,"errors":[{"message":"Invalid rule"}]}'
run_case 'HTTP 422 includes Cloudflare error details' 1 1 'Invalid rule'
grep -qF 'HTTP 422' "$TMP/output"
