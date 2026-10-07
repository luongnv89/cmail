#!/usr/bin/env bash
# Offline Email Routing regression tests; curl is mocked.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/ui.sh
. "$ROOT/lib/ui.sh"
# shellcheck source=../lib/cloudflare.sh
. "$ROOT/lib/cloudflare.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
CLOUDFLARE_API_TOKEN=test-token

curl() {
  local method=GET url='' data='' header
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -sS) shift ;;
      -X) method="$2"; shift 2 ;;
      -H)
        header="$2"
        case "$header" in
          'Authorization: Bearer test-token'|'Content-Type: application/json') ;;
          *) printf 'unexpected header\n' >&2; return 99 ;;
        esac
        shift 2 ;;
      -w)
        [ "$2" = $'\n%{http_code}' ] || return 99
        shift 2 ;;
      -d) data="$2"; shift 2 ;;
      https://*) url="$1"; shift ;;
      *) printf 'unexpected curl argument: %s\n' "$1" >&2; return 99 ;;
    esac
  done
  printf '%s %s data=%s\n' "$method" "$url" "$data" >>"$TMP/calls"
  if [ "$method" = GET ]; then
    printf '%s\n%s' "$GET_BODY" "$GET_HTTP"
    if [ "$GET_EXIT" != 0 ]; then printf 'curl: Could not resolve host\n' >&2; fi
    return "$GET_EXIT"
  fi
  printf '%s\n%s' "$POST_BODY" "$POST_HTTP"
  if [ "$POST_EXIT" != 0 ]; then printf 'curl: Connection reset\n' >&2; fi
  return "$POST_EXIT"
}

reset_responses() {
  GET_BODY='{"success":true,"result":{"enabled":false,"status":"unconfigured"}}'
  POST_BODY='{"success":true,"result":{"enabled":true,"status":"ready"}}'
  GET_HTTP=200 POST_HTTP=200 GET_EXIT=0 POST_EXIT=0
}
run_case() {
  local name="$1" expected_status="$2" expected_posts="$3" message="$4" status posts
  : >"$TMP/calls"
  set +e
  (set -euo pipefail; cf_email_enable test-zone; printf 'setup continues\n') >"$TMP/output" 2>&1
  status=$?
  set -e
  posts=$(grep -c '^POST ' "$TMP/calls" || true)
  if [ "$status" != "$expected_status" ] || [ "$posts" != "$expected_posts" ] \
     || ! grep -qF "$message" "$TMP/output"; then
    printf 'FAIL: %s (status=%s posts=%s)\n' "$name" "$status" "$posts" >&2
    exit 1
  fi
  grep -qxF "GET $CF_API/zones/test-zone/email/routing data=" "$TMP/calls"
  if [ "$expected_posts" = 1 ]; then
    grep -qxF "POST $CF_API/zones/test-zone/email/routing/dns data={}" "$TMP/calls"
  fi
  if [ "$expected_status" != 0 ] && grep -qF 'setup continues' "$TMP/output"; then
    printf 'FAIL: setup continued after %s\n' "$name" >&2; exit 1
  fi
  if grep -qF "$CLOUDFLARE_API_TOKEN" "$TMP/output"; then
    printf 'FAIL: token leaked\n' >&2; exit 1
  fi
  printf 'PASS: %s\n' "$name"
}

reset_responses
run_case 'disabled routing uses DNS activation endpoint' 0 1 'setup continues'
GET_BODY='{"success":true,"result":{"enabled":true,"status":"ready"}}'
run_case 'enabled routing skips mutation' 0 0 'email routing already enabled'

for GET_HTTP in 400 403 404 500; do
  GET_BODY='{"success":false,"errors":[{"code":10000,"message":"Permission denied"}]}'
  run_case "HTTP $GET_HTTP lookup failure" 1 0 "HTTP $GET_HTTP"
  grep -qF 'Permission denied' "$TMP/output"
  if [ "$GET_HTTP" = 403 ]; then grep -qF 'Zone Settings > Edit' "$TMP/output"; fi
done
reset_responses
GET_EXIT=6
run_case 'lookup transport diagnostic retained' 1 0 'curl: Could not resolve host'
grep -qF 'curl exit 6' "$TMP/output"
reset_responses
GET_BODY='{"success":false,"errors":[{"code":1000,"message":"lookup rejected"}]}'
run_case 'HTTP 200 API lookup error' 1 0 'lookup rejected'
for GET_BODY in 'not json' '{"success":true}' '{"success":true,"result":{"enabled":"false"}}'; do
  run_case "invalid lookup response: $GET_BODY" 1 0 'ERROR:'
done

reset_responses
POST_HTTP=403
POST_BODY='{"success":false,"errors":[{"code":10000,"message":"Authentication error"}]}'
run_case 'activation permission failure shows API details' 1 1 'Authentication error'
grep -qF 'HTTP 403' "$TMP/output"
grep -qF 'Zone Settings > Edit' "$TMP/output"
POST_HTTP=400
POST_BODY='{"success":false,"errors":[{"code":1001,"message":"Conflicting MX records"}]}'
run_case 'activation DNS conflict remains fatal' 1 1 'Conflicting MX records'
POST_BODY=''
run_case 'empty HTTP error has a useful fallback' 1 1 'empty response body'
POST_HTTP=502 POST_BODY='<html>Bad Gateway</html>'
run_case 'non-JSON HTTP error is retained' 1 1 '<html>Bad Gateway</html>'
reset_responses
POST_EXIT=56
run_case 'activation transport error is not retried' 1 1 'curl: Connection reset'
grep -qF 'curl exit 56' "$TMP/output"
reset_responses
POST_BODY='{"success":false,"errors":[{"message":"activation rejected"}]}'
run_case 'HTTP 200 activation API error' 1 1 'activation rejected'
POST_BODY='invalid json'
run_case 'HTTP 200 malformed activation response' 1 1 'non-JSON response'
for POST_BODY in '{"success":true}' '{"success":true,"result":{"enabled":false}}'; do
  run_case "activation does not confirm enabled: $POST_BODY" 1 1 'did not confirm Email Routing is enabled'
done
