#!/usr/bin/env bash
# Offline account discovery, token and activation diagnostics.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/lib/ui.sh"
. "$ROOT/lib/cloudflare.sh"
TMP=$(mktemp -d)
cleanup() {
  local status=$?
  if [ "$status" != 0 ] && [ -f "$TMP/output" ]; then
    grep -vE 'sentinel-private-token|private-test-sentinel' "$TMP/output" >&2 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT
DOMAIN=example.com CLOUDFLARE_API_TOKEN=sentinel-private-token
ACCOUNT=0123456789abcdef0123456789abcdef
sleep() { :; }
open_url() { :; }
env_set() { :; }
curl() {
  local method=GET url='' body='' http=200
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --connect-timeout|--max-time) shift 2 ;;
      -sS) shift ;;
      -X) method="$2"; shift 2 ;;
      -H|-w|-d) shift 2 ;;
      https://*) url="$1"; shift ;;
      *) return 99 ;;
    esac
  done
  printf '%s %s\n' "$method" "$url" >>"$TMP/calls"
  case "$method $url" in
    "GET $CF_API/zones?name=$DOMAIN") body="$ZONES"; http="$ZONE_HTTP" ;;
    "GET $CF_API/accounts") body="$ACCOUNTS"; http="$ACCOUNT_HTTP" ;;
    "POST $CF_API/zones") body='{"success":true,"result":{"id":"test-zone"}}'; http="$CREATE_HTTP" ;;
    "GET $CF_API/zones/test-zone") body="$ZONE"; http="$DETAIL_HTTP" ;;
    "GET $CF_API/user/tokens/verify") body="$TOKEN"; http="$TOKEN_HTTP" ;;
    *) return 99 ;;
  esac
  if [ "$TRANSPORT" != 0 ]; then printf 'curl: DNS lookup failed\n' >&2; return "$TRANSPORT"; fi
  printf '%s\n%s' "$body" "$http"
}
reset() {
  ZONES='{"success":true,"result":[]}'
  ACCOUNTS="{\"success\":true,\"result\":[{\"id\":\"$ACCOUNT\",\"name\":\"Personal\"}]}"
  ZONE='{"success":true,"result":{"status":"active","name_servers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com"]}}'
  TOKEN='{"success":true,"result":{"status":"active"}}'
  ZONE_HTTP=200 ACCOUNT_HTTP=200 CREATE_HTTP=200 DETAIL_HTTP=200 TOKEN_HTTP=200 TRANSPORT=0
  CF_ACCOUNT_ID='' CF_NS=()
}
assert_absent() {
  if grep "$@"; then printf 'FAIL: unexpected content matched\n' >&2; exit 1; fi
}
run_case() {
  local name="$1" expected="$2" text="$3" action="${4:-zone}" rc
  : >"$TMP/calls"
  set +e
  (
    set -euo pipefail
    case "$action" in
      zone) cf_zone_ensure ;;
      token) cf_ensure_token ;;
      active) cf_zone_wait_active test-zone ;;
      manual) cf_manual_delegation test-zone ;;
    esac
    printf 'continued\n'
  ) >"$TMP/output" 2>&1
  rc=$?
  set -e
  if [ "$rc" != "$expected" ] || ! grep -qF "$text" "$TMP/output"; then
    printf 'FAIL: %s status=%s\n' "$name" "$rc" >&2
    command grep -vF "$CLOUDFLARE_API_TOKEN" "$TMP/output" >&2 || true
    exit 1
  fi
  assert_absent -qF "$CLOUDFLARE_API_TOKEN" "$TMP/output"
  if [ "$expected" != 0 ]; then assert_absent -qF continued "$TMP/output"; fi
  printf 'PASS: %s\n' "$name"
}
reset
ACCOUNTS='{"success":true,"result":[]}'
run_case 'empty accounts show unlock instructions' 1 'no Cloudflare account visible'
for text in 'https://dash.cloudflare.com/profile/api-tokens' 'Account Resources' 'Zone Resources' 'CF_ACCOUNT_ID=' 'does NOT grant' 'CLOUDFLARE_API_TOKEN in .env' './cmail setup' 'no zone created or nameservers changed'; do
  grep -qF "$text" "$TMP/output"
done
assert_absent -q '^POST ' "$TMP/calls"
CF_ACCOUNT_ID="$ACCOUNT"
run_case 'explicit account bypasses inaccessible listing' 0 'zone test-zone'
assert_absent -q '/accounts' "$TMP/calls"
reset
ACCOUNTS="$(jq -c '.result += [{id:"ffffffffffffffffffffffffffffffff",name:"Work"}]' <<<"$ACCOUNTS")"
run_case 'multiple accounts require selection' 1 'refusing to choose one automatically'
assert_absent -q '^POST ' "$TMP/calls"
reset
ZONES='{"success":true,"result":[{"id":"test-zone"}]}'
run_case 'existing zone needs no account enumeration' 0 'zone already exists'
assert_absent -q '/accounts' "$TMP/calls"
reset
ACCOUNT_HTTP=403 ACCOUNTS='{"success":false,"errors":[{"message":"Account denied"}]}'
run_case 'account denial includes HTTP and recovery' 1 'HTTP 403'
grep -qF CF_ACCOUNT_ID "$TMP/output"
assert_absent -q '^POST ' "$TMP/calls"
reset
ZONE_HTTP=403 ZONES='{"success":false,"errors":[{"message":"Zone denied"}]}' CF_ACCOUNT_ID="$ACCOUNT"
run_case 'account ID cannot bypass denied zone access' 1 'Zone > Zone > Edit'
assert_absent -q '^POST ' "$TMP/calls"
reset
ZONE_HTTP=500 ZONES='{"success":false,"errors":[{"message":"Service unavailable"}]}'
run_case 'service outage is not called missing account' 1 'Cloudflare service error'
reset
TRANSPORT=6
run_case 'transport failure explains connectivity' 1 'not evidence of an invalid token'
assert_absent -q '^POST ' "$TMP/calls"
for ZONES in 'not JSON' '{"success":true}' '{"success":true,"result":{}}'; do
  TRANSPORT=0
  run_case 'malformed zone list stops before writes' 1 'ERROR:'
  assert_absent -q '^POST ' "$TMP/calls"
done
reset
ACCOUNTS='{"success":false,"errors":[{"message":"Account API rejected request"}]}'
run_case 'HTTP 200 account rejection retains details' 1 'Account API rejected request'
reset
ACCOUNT_HTTP=403 ACCOUNTS="$(jq -nc --arg secret "$CLOUDFLARE_API_TOKEN" '{success:false,errors:[{message:$secret}]}')"
run_case 'API error details redact the token' 1 '[redacted]'
reset
CF_ACCOUNT_ID=wrong
run_case 'invalid explicit account explains required ID' 1 '32-character account ID'
assert_absent -q '^POST ' "$TMP/calls"
reset
ZONES='{"success":true,"result":[{"id":"test-zone"}]}' ZONE='{"success":true,"result":{"name_servers":[]}}'
run_case 'missing nameservers give dashboard recovery' 1 'no nameserver change applied'
assert_absent -qF 'GoDaddy' "$TMP/output"
reset
run_case 'token validation explains permission boundary' 0 'permissions are checked' token
TOKEN_HTTP=401 TOKEN='{"success":false,"errors":[{"message":"Invalid token"}]}'
run_case 'invalid token shows replacement path' 1 'replace CLOUDFLARE_API_TOKEN in .env' token
reset
TRANSPORT=6
run_case 'token transport failure is not misdiagnosed' 1 'not evidence of an invalid token' token
reset
run_case 'active zone proceeds' 0 'zone active' active
ZONE='{"success":true,"result":{"status":"pending"}}'
run_case 'pending activation explains propagation and delegation' 1 '24–48 hours' active
grep -qF 'no rollback' "$TMP/output"
grep -qF 'your domain registrar' "$TMP/output"
assert_absent -qF 'GoDaddy' "$TMP/output"
DETAIL_HTTP=403 ZONE='{"success":false,"errors":[{"message":"Denied during poll"}]}'
run_case 'activation API denial fails immediately' 1 'Denied during poll' active
[ "$(grep -c '^GET ' "$TMP/calls")" = 1 ]

# Manual registrar mode: instructions only, never a registrar write.
reset
run_case 'manual delegation skips an active zone' 0 'no registrar changes needed' manual
assert_absent -qF 'replace ALL nameservers' "$TMP/output"
[ "$(cat "$TMP/calls")" = "GET $CF_API/zones/test-zone" ]
ZONE='{"success":true,"result":{"status":"pending","name_servers":["alice.ns.cloudflare.com","bob.ns.cloudflare.com"]}}'
run_case 'manual delegation prints exact nameservers for a pending zone' 0 'replace ALL nameservers' manual
for text in '  alice.ns.cloudflare.com' '  bob.ns.cloudflare.com' 'domain registrar' 'DNSSEC' 'DS records' 'MX' 'Copy every DNS record' 'continued'; do
  grep -qF -- "$text" "$TMP/output"
done
assert_absent -qF 'GoDaddy' "$TMP/output"
assert_absent -q '^POST ' "$TMP/calls"
(CMAIL_QUIET=1; cf_manual_delegation test-zone) >"$TMP/output" 2>&1
grep -qF 'alice.ns.cloudflare.com' "$TMP/output"
printf 'PASS: manual delegation instructions survive --quiet\n'
ZONE='{"success":true,"result":{"status":"pending","name_servers":[]}}'
run_case 'manual delegation refuses missing nameservers' 1 'no nameserver change applied' manual
ZONE='{"success":true,"result":{}}'
run_case 'manual delegation requires zone status' 1 'no zone status' manual

# All steps have next actions; guidance does not disclose credentials.
for CMAIL_STEP in 'Dependencies' 'Configuration' 'GoDaddy authentication (prod)' 'Choose domain' 'Cloudflare API token' 'Cloudflare zone: example.com' 'Registrar nameservers: example.com' 'GoDaddy: point example.com nameservers at Cloudflare' 'Waiting for zone activation' 'Enable Cloudflare Email Routing' 'Destination address: user@example.net' 'Forwarding addresses'; do
  CMAIL_DNS_CHECKPOINT=0 setup_recovery >"$TMP/output" 2>&1
  grep -qF 'Next:' "$TMP/output"
  grep -qF './cmail setup' "$TMP/output"
  grep -qF 'has not attempted a nameserver update' "$TMP/output"
  assert_absent -qF "$CLOUDFLARE_API_TOKEN" "$TMP/output"
done
CMAIL_DNS_CHECKPOINT=1 setup_recovery >"$TMP/output" 2>&1
grep -qF 'delegation may already have changed' "$TMP/output"
CMAIL_STEP='Registrar nameservers: example.com' CMAIL_DNS_CHECKPOINT=2 setup_recovery >"$TMP/output" 2>&1
grep -qF 'cmail never changes nameservers in manual registrar mode' "$TMP/output"
grep -qF 'replace ALL nameservers' "$TMP/output"
assert_absent -qF 'delegation may already have changed' "$TMP/output"
assert_absent -qF 'GoDaddy' "$TMP/output"
CMAIL_STEP='Waiting for zone activation' CMAIL_DNS_CHECKPOINT=2 setup_recovery >"$TMP/output" 2>&1
assert_absent -qF 'GoDaddy' "$TMP/output"
printf 'PASS: recovery guidance covers all setup steps and DNS checkpoint\n'

# Exercise the actual orchestrator and EXIT trap with isolated fixture helpers.
mkdir -p "$TMP/cli/lib"
cp "$ROOT/cmail" "$TMP/cli/cmail"
cp "$ROOT/VERSION" "$TMP/cli/VERSION"
cp "$ROOT/lib/cli.sh" "$TMP/cli/lib/cli.sh"
cp "$ROOT/lib/output.sh" "$TMP/cli/lib/output.sh"
cp "$ROOT/lib/env.sh" "$TMP/cli/lib/env.real.sh"
cp "$ROOT/lib/plan.sh" "$TMP/cli/lib/plan.sh"
cp "$ROOT/lib/ui.sh" "$TMP/cli/lib/ui.sh"
for module in env deps godaddy cloudflare gmail; do : >"$TMP/cli/lib/$module.sh"; done
printf '%s\n' 'ensure_deps() { step "Dependencies"; }' >"$TMP/cli/lib/deps.sh"
printf '%s\n' 'config_error() { printf "%s\n" "$*" >&2; return 3; }' 'config_load() { :; }' 'env_init() { :; }' 'env_require_prompt() { :; }' 'env_set() { :; }' >"$TMP/cli/lib/env.sh"
printf '%s\n' 'gddy_ensure_auth() { step "GoDaddy authentication (prod)"; echo GDDY-STUB-RAN >&2; }' 'gddy_pick_domain() { DOMAIN=example.com; }' 'gddy_set_nameservers() { step "GoDaddy: point example.com nameservers at Cloudflare"; echo GDDY-STUB-RAN >&2; }' >"$TMP/cli/lib/godaddy.sh"
printf '%s\n' 'cf_ensure_token() { step "Cloudflare API token"; }' 'cf_zone_ensure() { step "Cloudflare zone: example.com"; if [ "$FAIL_AT" = zone ]; then die "no account"; fi; CF_ZONE_ID=test-zone; CF_NS=(alice bob); }' 'cf_manual_delegation() { step "Registrar nameservers: example.com"; echo MANUAL-DELEGATION-RAN >&2; }' 'cf_zone_wait_active() { step "Waiting for zone activation"; return 7; }' >"$TMP/cli/lib/cloudflare.sh"
for registrar in godaddy manual; do
  for FAIL_AT in zone activation; do
    set +e
    REGISTRAR="$registrar" FAIL_AT="$FAIL_AT" python3 "$ROOT/tests/run_tty.py" "$BASH" "$TMP/cli/cmail" setup >"$TMP/output" 2>&1
    rc=$?
    set -e
    [ "$rc" != 0 ]
    [ "$(grep -c 'Setup stopped at:' "$TMP/output")" = 1 ]
    grep -qF 'Next:' "$TMP/output"
    if [ "$FAIL_AT" = zone ]; then
      [ "$rc" = 1 ]; grep -qF 'has not attempted a nameserver update' "$TMP/output"
    elif [ "$registrar" = godaddy ]; then
      [ "$rc" = 1 ]; grep -qF 'delegation may already have changed' "$TMP/output"
      assert_absent -qF 'MANUAL-DELEGATION-RAN' "$TMP/output"
    else
      [ "$rc" = 1 ]; grep -qF 'cmail never changes nameservers in manual registrar mode' "$TMP/output"
      grep -qF 'MANUAL-DELEGATION-RAN' "$TMP/output"
      assert_absent -qF 'delegation may already have changed' "$TMP/output"
    fi
    if [ "$registrar" = manual ]; then
      assert_absent -qF 'GDDY-STUB-RAN' "$TMP/output"
      assert_absent -qF 'GoDaddy' "$TMP/output"
    else
      grep -qF 'GDDY-STUB-RAN' "$TMP/output"
    fi
  done
done
printf 'PASS: real setup trap preserves failure status and reports recovery once\n'
cp "$ROOT/lib/env.sh" "$TMP/cli/lib/env.sh"
printf 'GDDY_ENV = ote\nDOMAIN=example.com\nDEST_EMAIL=private-test-sentinel\nADDRESSES=hello\n' >"$TMP/cli/.env"
set +e
ENV_FILE="$TMP/cli/.env" python3 "$ROOT/tests/run_tty.py" "$BASH" "$TMP/cli/cmail" setup >"$TMP/output" 2>&1
rc=$?
set -e
[ "$rc" = 3 ]
grep -qF 'could not load config' "$TMP/output"
grep -qF 'Setup stopped at: Configuration' "$TMP/output"
assert_absent -qF 'GoDaddy authentication' "$TMP/output"
assert_absent -qF 'Cloudflare API token' "$TMP/output"
assert_absent -qF 'private-test-sentinel' "$TMP/output"
printf 'PASS: malformed configuration blocks all provider steps\n'

# Setup is receive-only by default; Gmail send-as runs only via its own command.
printf '%s\n' 'config_error() { printf "%s\n" "$*" >&2; return 3; }' 'config_load() { :; }' 'env_init() { :; }' 'env_require_prompt() { :; }' 'env_set() { :; }' >"$TMP/cli/lib/env.sh"
printf '%s\n' 'cf_ensure_token() { :; }' 'cf_zone_ensure() { CF_ZONE_ID=test-zone; CF_NS=(alice bob); }' 'cf_manual_delegation() { :; }' 'cf_zone_wait_active() { :; }' 'cf_email_enable() { :; }' 'cf_dest_ensure() { :; }' 'cf_rules_ensure() { :; }' >"$TMP/cli/lib/cloudflare.sh"
printf '%s\n' 'gmail_sendas_guide() { echo GMAIL-GUIDE-RAN; }' >"$TMP/cli/lib/gmail.sh"
DOMAIN=example.com DEST_EMAIL=user@example.net ADDRESSES='hello, contact' python3 "$ROOT/tests/run_tty.py" "$BASH" "$TMP/cli/cmail" setup </dev/null >"$TMP/output" 2>&1
grep -qF 'Receiving is set up' "$TMP/output"
grep -qF 'hello@example.com -> user@example.net' "$TMP/output"
grep -qF 'contact@example.com -> user@example.net' "$TMP/output"
grep -qF 'DIFFERENT mailbox' "$TMP/output"
grep -qF './cmail send-as' "$TMP/output"
assert_absent -qF 'GMAIL-GUIDE-RAN' "$TMP/output"
assert_absent -qF 'Setup stopped at:' "$TMP/output"
DOMAIN=example.com DEST_EMAIL=user@gmail.com ADDRESSES=hello python3 "$ROOT/tests/run_tty.py" "$BASH" "$TMP/cli/cmail" send-as >"$TMP/output" 2>&1
grep -qF 'GMAIL-GUIDE-RAN' "$TMP/output"
set +e
DOMAIN=example.com DEST_EMAIL='' ADDRESSES=hello python3 "$ROOT/tests/run_tty.py" "$BASH" "$TMP/cli/cmail" send-as >"$TMP/output" 2>&1
rc=$?
set -e
[ "$rc" = 3 ]
grep -qF 'no DEST_EMAIL in config' "$TMP/output"
grep -qF './cmail setup first' "$TMP/output"
assert_absent -qF 'GMAIL-GUIDE-RAN' "$TMP/output"
bash "$TMP/cli/cmail" help | grep -F './cmail send-as' >/dev/null
printf 'PASS: setup is receive-only; send-as is a separate optional command\n'
