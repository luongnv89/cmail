#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export CMAIL_DIR="$ROOT" ENV_FILE="$TMP/config"
. "$ROOT/lib/ui.sh"
. "$ROOT/lib/env.sh"
passed=0
check() {
  local name="$1" expected="$2" code
  shift 2
  if (set -euo pipefail; "$@") > "$TMP/out" 2> "$TMP/err"; then code=0; else code=$?; fi
  if [ "$code" != "$expected" ]; then printf 'FAIL: %s (%s, expected %s)\n' "$name" "$code" "$expected"; cat "$TMP/err"; exit 1; fi
  passed=$((passed + 1)); printf 'PASS: %s\n' "$name"
}
fixture() { printf '%s\n' "$1" > "$ENV_FILE"; chmod 600 "$ENV_FILE"; }
fixture "DOMAIN='example.com'
DEST_EMAIL=user@example.net
ADDRESSES='hello, contact'
GDDY_ENV=ote
CLOUDFLARE_API_TOKEN='synthetic-token'"
check 'literal config parses and validates' 0 config_load
check 'literal config is ready' 0 bash -c '. "$CMAIL_DIR/lib/env.sh"; config_load && config_ready'
precedence() { DOMAIN=override.example; config_load; [ "$DOMAIN" = override.example ]; [ "$GDDY_ENV" = ote ]; }
check 'environment overrides file' 0 precedence
fixture 'DOMAIN=$(touch must-not-exist)'
check 'command substitution rejected' 3 config_load
fixture 'DOMAIN=example.com;false'
check 'commands rejected' 3 config_load
fixture 'DOMAIN=example.com
DOMAIN=other.example'
check 'duplicate settings rejected' 3 config_load
fixture 'UNSUPPORTED=value'
check 'unknown setting rejected' 3 config_load
fixture 'DOMAIN=bad/domain'
check 'domain validation' 3 config_load
fixture 'ADDRESSES=hello,hello'
check 'duplicate aliases rejected' 3 config_load
fixture 'GDDY_PAT="opaque\$literal\\backslash"'
quoted() { config_load; [ "$GDDY_PAT" = 'opaque$literal\backslash' ]; }
check 'quoted escaped dollar stays literal' 0 quoted
fixture "GDDY_PAT='opaque with spaces and '\\''quote'"
check 'single quote concatenation' 0 config_load
fixture 'DOMAIN=example.com'
chmod 644 "$ENV_FILE"
check 'read-only load refuses insecure file without chmod' 3 config_load
[ "$(stat -f %Lp "$ENV_FILE" 2>/dev/null || stat -c %a "$ENV_FILE")" = 644 ]
chmod 600 "$ENV_FILE"
ln -s "$ENV_FILE" "$TMP/link"
symlink() { ENV_FILE="$TMP/link"; config_load; }
check 'symlink refused' 3 symlink
mkfifo "$TMP/fifo"
fifo() { ENV_FILE="$TMP/fifo"; config_load; }
check 'FIFO refused without blocking' 3 fifo
fixture 'DOMAIN=example.com
CF_ZONE_ID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
domain_change() { DOMAIN=other.example; config_load; [ -z "$CF_ZONE_ID" ]; }
check 'domain override drops saved zone ID' 0 domain_change
fixture 'DOMAIN=example.com'
atomic() {
  local i
  env_set DOMAIN other.example; config_read
  for ((i=0; i<${#CONFIG_KEYS[@]}; i++)); do
    if [ "${CONFIG_KEYS[i]}" = DOMAIN ]; then [ "${CONFIG_VALUES[i]}" = other.example ]; return; fi
  done
  return 1
}
check 'atomic public update' 0 atomic
fixture 'GDDY_PAT=old'
secret_roundtrip() { env_set GDDY_PAT "opaque '\$literal"; unset GDDY_PAT; config_load; [ "$GDDY_PAT" = "opaque '\$literal" ]; }
check 'opaque secret roundtrip without evaluation' 0 secret_roundtrip
printf 'GDDY_PAT=bad\000value\n' > "$ENV_FILE"
check 'NUL refused' 3 config_load
printf '%s config cases passed\n' "$passed"
