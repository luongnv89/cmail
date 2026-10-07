#!/usr/bin/env bash
# Offline diagnostics tests: mocks only; config fixtures are private temporary files.
# Mocks are called indirectly by sourced workflow functions.
# shellcheck disable=SC2329
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMAIL_DIR="$ROOT"
. "$ROOT/lib/ui.sh"
. "$ROOT/lib/deps.sh"
. "$ROOT/lib/env.sh"
. "$ROOT/lib/godaddy.sh"
. "$ROOT/lib/gmail.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
CMAIL_DIR="$TMP"
ENV_FILE="$TMP/config"
GDDY_ENV=ote
DOMAIN=example.com
ADDRESSES=hello,contact
DEST_EMAIL=recipient@example.net
unset GDDY_PAT

run_expect() {
  local name="$1" expected="$2" fn="$3" status pattern
  shift 3
  : >"$TMP/calls"
  if (set -euo pipefail; "$fn") >"$TMP/output" 2>&1; then status=0; else status=$?; fi
  if [ "$status" != "$expected" ]; then
    printf 'FAIL: %s (status %s, expected %s)\n' "$name" "$status" "$expected" >&2
    cat "$TMP/output" >&2
    exit 1
  fi
  for pattern in "$@"; do
    if ! grep -qF "$pattern" "$TMP/output"; then
      printf 'FAIL: %s (missing %s)\n' "$name" "$pattern" >&2
      cat "$TMP/output" >&2
      exit 1
    fi
  done
  if grep -qF 'private-test-sentinel' "$TMP/output"; then
    printf 'FAIL: %s leaked a config/secret value\n' "$name" >&2
    exit 1
  fi
  printf 'PASS: %s\n' "$name"
}

missing_tool() {
  _pkg_install() { return 1; }
  ensure_tool cmail_nonexistent_test_tool test-package
}
run_expect 'package install recovery' 1 missing_tool 'permissions' 'network' 'manually' 'PATH' './cmail setup'

failed_gddy_install() {
  command() { if [ "$*" = '-v gddy' ]; then return 1; else builtin command "$@"; fi; }
  curl() { return 1; }
  ensure_gddy
}
run_expect 'gddy download recovery' 1 failed_gddy_install 'GitHub' 'permission' 'Install manually' 'PATH' './cmail setup'
missing_gddy_after_install() {
  command() { if [ "$*" = '-v gddy' ]; then return 1; else builtin command "$@"; fi; }
  curl() { printf ':\n'; }
  ensure_gddy
}
run_expect 'gddy PATH recovery' 1 missing_gddy_after_install 'unavailable after installer' 'export PATH=' 'command -v gddy'

failed_create() { cp() { return 1; }; env_init; }
run_expect 'config creation recovery' 1 failed_create 'could not create config' 'parent directory' './cmail setup'
printf 'GDDY_PAT=private-test-sentinel\n' >"$ENV_FILE"
failed_secure() { chmod() { return 1; }; env_init; }
run_expect 'config permissions recovery' 1 failed_secure 'could not secure config' 'chmod 600'
valid_config() { env_init; [ "$GDDY_PAT" = 'private-test-sentinel' ]; }
run_expect 'valid private config loads silently' 0 valid_config
printf 'GDDY_PAT="private-test-sentinel\n' >"$ENV_FILE"
run_expect 'config syntax recovery without value disclosure' 3 env_init 'could not load config' 'shell assignment syntax' './cmail setup'
printf 'printf "private-test-sentinel\\n"; false\n' >"$ENV_FILE"
run_expect 'config load recovery without value disclosure' 3 env_init 'could not load config' 'without sharing secrets'
printf 'GDDY_ENV = ote\nGDDY_PAT=private-test-sentinel\n' >"$ENV_FILE"
run_expect 'intermediate invalid assignment cannot retain production defaults silently' 3 env_init 'NAME=value' 'no spaces around' 'without sharing secrets'
printf 'false\nGDDY_PAT=private-test-sentinel\n' >"$ENV_FILE"
run_expect 'intermediate config failure is not masked by a final assignment' 3 env_init 'could not load config'
empty_input() { unset GDDY_PAT; env_require_prompt GDDY_PAT 'Test input' <<<''; }
run_expect 'empty input recovery' 1 empty_input 'GDDY_PAT is required' 'private config' './cmail setup'
eof_input() { unset GDDY_PAT; env_require_prompt GDDY_PAT 'Test input' --secret </dev/null; }
run_expect 'missing terminal input recovery' 1 eof_input 'input unavailable' 'interactive terminal'
existing_input() { GDDY_PAT=private-test-sentinel; env_require_prompt GDDY_PAT 'Test input' </dev/null; }
run_expect 'existing input does not prompt' 0 existing_input

# Config writes use a synthetic fixture, never a repository/user config.
printf 'GDDY_PAT=old\nGDDY_ENV=ote\n' >"$ENV_FILE"
save_input() { env_set GDDY_PAT private-test-sentinel; [ "$GDDY_PAT" = private-test-sentinel ]; }
run_expect 'config upsert' 0 save_input
grep -qxF 'GDDY_ENV=ote' "$ENV_FILE"
grep -qxF "GDDY_PAT='private-test-sentinel'" "$ENV_FILE"
save_quoted_input() {
  env_set GDDY_PAT 'hello, contact; $(do-not-run)'
  bash -n "$ENV_FILE"
  unset GDDY_PAT
  env_init
  [ "$GDDY_PAT" = 'hello, contact; $(do-not-run)' ]
}
run_expect 'config values with spaces/metacharacters remain assignments' 0 save_quoted_input
failed_save() { ENV_FILE="$TMP"; env_set GDDY_PAT private-test-sentinel; }
run_expect 'config write recovery' 3 failed_save 'could not save GDDY_PAT' 'permissions' 'cmail config'

gddy() {
  printf '%s\n' "$*" >>"$TMP/calls"
  case "$1 $2" in
    'auth status') printf '%s\n' '{"data":[]}';;
    'auth login') return 1;;
    'domain list') printf '%s\n' "$LIST_RESPONSE"; return "$LIST_STATUS";;
    'domain get') return 1;;
    'domain available') return 0;;
    'domain quote') return "$QUOTE_STATUS";;
    'domain purchase') return 1;;
    *) return 1;;
  esac
}
run_expect 'GoDaddy auth recovery for selected environment' 1 gddy_ensure_auth 'gddy auth login --env ote' 'network/browser' 'renew/recreate' 'GDDY_PAT' './cmail setup'
grep -qxF 'auth login --env ote' "$TMP/calls"
pat_auth() { GDDY_PAT=private-test-sentinel; gddy_ensure_auth; }
run_expect 'PAT remains private' 0 pat_auth 'using PAT'
[ ! -s "$TMP/calls" ]
LIST_RESPONSE='' LIST_STATUS=1
list_domains() { unset DOMAIN; gddy_pick_domain </dev/null; }
run_expect 'domain list failure is explicit' 1 list_domains 'could not list GoDaddy domains' 'gddy domain list --env ote --json' 'GDDY_PAT' './cmail setup'
LIST_RESPONSE='not json' LIST_STATUS=0
run_expect 'invalid domain list recovery' 1 list_domains 'could not read GoDaddy domain list' 'response format'
LIST_RESPONSE='{"data":[]}'
run_expect 'empty domain list reaches domain prompt' 1 list_domains 'domain input unavailable' 'interactive terminal'
LIST_RESPONSE='{"data":[{"domain":"example.com"}]}'
select_owned() { unset DOMAIN; gddy_pick_domain <<<'example.com'; }
run_expect 'owned domain selection' 0 select_owned 'Your GoDaddy domains:'
if grep -qF 'domain purchase' "$TMP/calls"; then exit 1; fi
confirm() { printf 'confirm %s\n' "$*" >>"$TMP/calls"; return 0; }
QUOTE_STATUS=1
register_domain() { gddy_maybe_register example.com; }
run_expect 'quote failure recovery' 1 register_domain 'quote failed' 'GoDaddy orders' 'before retrying any purchase'
if grep -qF 'domain purchase' "$TMP/calls"; then exit 1; fi
QUOTE_STATUS=0
run_expect 'purchase ambiguity recovery' 1 register_domain 'outcome may be uncertain' 'BEFORE retrying purchase' 'duplicate charges' 'set DOMAIN' './cmail setup'
grep -qxF 'domain purchase example.com --env ote' "$TMP/calls"

# Verify migration guidance precedes confirmation and survives write failure.
nameserver_write_failure() {
  gddy() {
    if [ "$1 $2" = 'domain get' ]; then
      printf '%s\n' '{"data":{"nameServers":["ns01.domaincontrol.com","ns02.domaincontrol.com"]}}'
    else return 1; fi
  }
  confirm() { printf 'CONFIRM-MARKER\n'; return 0; }
  DRY_RUN=0
  gddy_set_nameservers alice.ns.cloudflare.com bob.ns.cloudflare.com
}
run_expect 'nameserver write ambiguity and DNS migration guidance' 1 nameserver_write_failure 'current nameservers:' 'desired nameservers:' 'copy existing DNS records' 'nameserver update failed' 'may still have applied' 'gddy domain get example.com --env ote --json' './cmail setup'
current_line=$(grep -nF 'current nameservers:' "$TMP/output" | head -1 | cut -d: -f1)
desired_line=$(grep -nF 'desired nameservers:' "$TMP/output" | head -1 | cut -d: -f1)
warning_line=$(grep -nF 'copy existing DNS records' "$TMP/output" | cut -d: -f1)
confirm_line=$(grep -nF 'CONFIRM-MARKER' "$TMP/output" | cut -d: -f1)
[ "$current_line" -lt "$confirm_line" ] && [ "$desired_line" -lt "$confirm_line" ] && [ "$warning_line" -lt "$confirm_line" ]
nameserver_read_failure() { DRY_RUN=0; gddy_set_nameservers alice.ns.cloudflare.com bob.ns.cloudflare.com; }
run_expect 'nameserver read recovery' 1 nameserver_read_failure 'no change applied' 'GoDaddy dashboard' 'gddy domain get example.com --env ote --json' './cmail setup'

gmail_guide() { open_url() { :; }; pause() { :; }; gmail_sendas_guide; }
run_expect 'manual Gmail troubleshooting and truthful completion' 0 gmail_guide 'optional' 'Receiving already' 'App passwords unavailable' '2-Step Verification' 'Work/school policy' 'SMTP rejected' 'Confirmation missing' 'DIFFERENT mailbox' 'Send from Gmail' 'not automatically verified'
if grep -qF 'setup complete' "$TMP/output"; then exit 1; fi
gmail_without_input() { open_url() { :; }; pause() { return 1; }; gmail_sendas_guide; }
run_expect 'Gmail guide resume without terminal input' 1 gmail_without_input 'Gmail guide paused without input' 'Gmail settings' './cmail send-as' 'not automatically verified'
