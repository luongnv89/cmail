#!/usr/bin/env bash
# Offline account-scoped destination setup and status tests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/ui.sh
. "$ROOT/lib/ui.sh"
# shellcheck source=../lib/cloudflare.sh
. "$ROOT/lib/cloudflare.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
CLOUDFLARE_API_TOKEN=test-token
DEST_EMAIL='contact+test@gmail.com'

open_url() { printf 'open %s\n' "$*" >>"$TMP/calls"; }
sleep() { :; }
curl() {
  local method=GET url='' data='' formatted=0 body http=200 round
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -sS|-fsS) shift ;;
      -X) method="$2"; shift 2 ;;
      -H) shift 2 ;;
      -w) formatted=1; shift 2 ;;
      -d) data="$2"; shift 2 ;;
      https://*) url="$1"; shift ;;
      *) printf 'unexpected curl argument: %s\n' "$1" >&2; return 99 ;;
    esac
  done
  printf '%s %s data=%s\n' "$method" "$url" "$data" >>"$TMP/calls"
  case "$method $url" in
    "GET $CF_API/zones/test-zone") body="$ZONE_BODY"; http="$ZONE_HTTP" ;;
    "POST $CF_API/accounts/zone-owner/email/routing/addresses")
      body="$CREATE_BODY"; http="$CREATE_HTTP"
      if [ "$CREATE_EXIT" != 0 ]; then printf 'curl: Connection reset\n' >&2; return "$CREATE_EXIT"; fi ;;
    "GET $CF_API/accounts/zone-owner/email/routing/addresses?per_page=50&page=1")
      round=$(<"$TMP/round"); round=$((round + 1)); printf '%s' "$round" >"$TMP/round"
      if [ "$round" -lt "$VERIFIED_AFTER" ]; then body="$LIST_BEFORE"; http="$LIST_HTTP"
      else body="$LIST_AFTER"; http="$POLL_HTTP"; fi ;;
    "GET $CF_API/accounts/zone-owner/email/routing/addresses?per_page=50&page=2")
      body="$PAGE2_BODY"; http="$PAGE2_HTTP" ;;
    "GET $CF_API/zones/test-zone/email/routing") body='{"success":true,"result":{"status":"ready"}}' ;;
    "GET $CF_API/zones/test-zone/email/routing/rules") body='{"success":true,"result":[]}' ;;
    *) printf 'unexpected API endpoint: %s %s\n' "$method" "$url" >&2; return 99 ;;
  esac
  printf '%s' "$body"
  if [ "$formatted" = 1 ]; then printf '\n%s' "$http"; fi
}

reset_responses() {
  ZONE_BODY='{"success":true,"result":{"status":"active","account":{"id":"zone-owner"}}}'
  ZONE_HTTP=200 CREATE_HTTP=200 LIST_HTTP=200 POLL_HTTP=200 PAGE2_HTTP=200 CREATE_EXIT=0
  CREATE_BODY='{"success":true,"result":{"email":"contact+test@gmail.com","verified":null}}'
  LIST_BEFORE='{"success":true,"result":[]}'
  LIST_AFTER='{"success":true,"result":[{"email":"contact+test@gmail.com","verified":"2026-01-01T00:00:00Z"}]}'
  PAGE2_BODY="$LIST_AFTER"
  VERIFIED_AFTER=2 ACTION=setup
}
run_case() {
  local name="$1" expected_status="$2" expected_posts="$3" message="$4" status posts
  : >"$TMP/calls"; printf '0' >"$TMP/round"
  set +e
  (
    set -euo pipefail
    if [ "$ACTION" = status ]; then cf_status test-zone; else cf_dest_ensure test-zone; fi
    printf 'setup continues\n'
  ) >"$TMP/output" 2>&1
  status=$?
  set -e
  posts=$(grep -c '^POST ' "$TMP/calls" || true)
  if [ "$status" != "$expected_status" ] || [ "$posts" != "$expected_posts" ] \
     || ! grep -qF "$message" "$TMP/output"; then
    printf 'FAIL: %s (status=%s posts=%s)\n' "$name" "$status" "$posts" >&2; exit 1
  fi
  grep -qxF "GET $CF_API/zones/test-zone data=" "$TMP/calls"
  if [ "$expected_posts" = 1 ]; then
    grep -qxF "POST $CF_API/accounts/zone-owner/email/routing/addresses data={\"email\":\"contact+test@gmail.com\"}" "$TMP/calls"
  fi
  if [ "$expected_status" != 0 ] && grep -qF 'setup continues' "$TMP/output"; then
    printf 'FAIL: continued after error\n' >&2; exit 1
  fi
  if grep -qE '/zones/.*/email/routing/addresses|test-token' "$TMP/output" "$TMP/calls"; then
    printf 'FAIL: zone-scoped address endpoint or token leaked\n' >&2; exit 1
  fi
  printf 'PASS: %s\n' "$name"
}

reset_responses
run_case 'absent address created in zone owner account and verified' 0 1 "$DEST_EMAIL verified"
reset_responses
VERIFIED_AFTER=1
run_case 'existing verified address needs no POST or browser' 0 0 "$DEST_EMAIL verified"
if grep -q '^open ' "$TMP/calls"; then printf 'FAIL: browser opened for verified address\n' >&2; exit 1; fi
reset_responses
LIST_BEFORE='{"success":true,"result":[{"email":"contact+test@gmail.com","verified":null}]}'
run_case 'pending destination is not recreated' 0 0 'already registered but unverified'
reset_responses
LIST_BEFORE='{"success":true,"result":[{"email":"other@gmail.com","verified":null}],"result_info":{"total_pages":2}}'
run_case 'existing destination on second page is found' 0 0 "$DEST_EMAIL verified"
grep -qF 'page=2' "$TMP/calls"
PAGE2_HTTP=403 PAGE2_BODY='{"success":false,"errors":[{"message":"Permission denied"}]}'
run_case 'failed second page cannot trigger creation' 1 0 'Permission denied'
grep -qF 'Account > Email Routing Addresses > Edit' "$TMP/output"

reset_responses
LIST_BEFORE=$(jq -nc '{success:true,result:[range(0;50) | {email:("other" + tostring + "@gmail.com"),verified:null}]}')
run_case 'full page without metadata continues to next page' 0 0 "$DEST_EMAIL verified"
grep -qF 'page=2' "$TMP/calls"
reset_responses
CREATE_BODY='{"success":true,"result":{"email":"contact+test@gmail.com","verified":"2026-01-01T00:00:00Z"}}'
run_case 'verified create response needs no polling' 0 1 "$DEST_EMAIL verified"
[ "$(<"$TMP/round")" = 1 ]

reset_responses
ZONE_HTTP=403 ZONE_BODY='{"success":false,"errors":[{"message":"Zone denied"}]}'
run_case 'zone lookup failure stops before address access' 1 0 'Zone denied'
for ZONE_BODY in '{"success":true,"result":{}}' '{"success":true,"result":{"account":{"id":null}}}' \
  '{"success":true,"result":{"account":{"id":123}}}'; do
  ZONE_HTTP=200
  run_case "invalid zone account: $ZONE_BODY" 1 0 'missing its account ID'
done
reset_responses
LIST_HTTP=403 LIST_BEFORE='{"success":false,"errors":[{"message":"Address access denied"}]}'
run_case 'account permission failure does not create destination' 1 0 'Address access denied'
grep -qF 'Account > Email Routing Addresses > Edit' "$TMP/output"
for LIST_BEFORE in '{"success":true,"result":null}' \
  '{"success":true,"result":[{"email":"contact+test@gmail.com","verified":false}]}' \
  '{"success":true,"result":[],"result_info":{"total_pages":"2"}}' \
  '{"success":true,"result":[],"result_info":{"total_pages":false}}'; do
  LIST_HTTP=200
  run_case "malformed destination list: $LIST_BEFORE" 1 0 'ERROR:'
done
reset_responses
CREATE_HTTP=400 CREATE_BODY='{"success":false,"errors":[{"message":"Address creation rejected"}]}'
run_case 'creation failure never claims email sent' 1 1 'Address creation rejected'
if grep -qF 'verification email sent' "$TMP/output"; then printf 'FAIL: claimed email sent after creation failed\n' >&2; exit 1; fi
reset_responses
CREATE_EXIT=56
run_case 'ambiguous create transport failure is not retried' 1 1 'curl exit 56'
reset_responses
CREATE_BODY='{"success":true,"result":{}}'
run_case 'invalid create result stops polling' 1 1 'did not confirm destination registration'
reset_responses
LIST_BEFORE='{"success":true,"result":[{"email":"contact+test@gmail.com","verified":null}]}'
POLL_HTTP=403 LIST_AFTER='{"success":false,"errors":[{"message":"Polling denied"}]}'
run_case 'poll failure is surfaced without recreating' 1 0 'Polling denied'
reset_responses
VERIFIED_AFTER=100 LIST_BEFORE='{"success":true,"result":[{"email":"contact+test@gmail.com","verified":null}]}'
run_case 'verification timeout is fatal and does not recreate' 1 0 'not verified'
[ "$(<"$TMP/round")" = 41 ]
reset_responses
ACTION=status VERIFIED_AFTER=1
run_case 'status lists account addresses and remains read-only' 0 0 "$DEST_EMAIL"
