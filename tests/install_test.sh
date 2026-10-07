#!/usr/bin/env bash
# Offline installer regressions: every download is served from local fixtures.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export CMAIL_BIN_DIR="$TMP/bin space '\$;" \
  CMAIL_DATA_DIR="$TMP/data space '\$;" CMAIL_CONFIG_DIR="$TMP/config space '\$;"
export FIXTURE="$TMP/fixture" CURL_LOG="$TMP/curl.log" FAIL_FILE='' MODE='' FAIL_SWITCH=0
REAL_MV="$(command -v mv)"
export REAL_MV
file_mode() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys
print(format(Path(sys.argv[1]).stat().st_mode & 0o777, 'o'))
PY
}
mkdir -p "$TMP/mock" "$FIXTURE/lib" "$FIXTURE/completions"
cp "$ROOT/cmail" "$ROOT/VERSION" "$ROOT/.env.example" "$FIXTURE/"
cp "$ROOT"/lib/*.sh "$FIXTURE/lib/"
cp "$ROOT"/completions/* "$FIXTURE/completions/"
cat > "$TMP/mock/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$CURL_LOG"
url='' output=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
file="${url#https://raw.githubusercontent.com/luongnv89/cmail/}"
file="${file#*/}"
[ "$file" != "${FAIL_FILE:-}" ] || exit 22
cp "$FIXTURE/$file" "$output"
if [ "${MODE:-}" = empty ] && [ "$file" = VERSION ]; then : > "$output"; fi
if [ "${MODE:-}" = syntax ] && [ "$file" = lib/env.sh ]; then printf '\nif\n' >> "$output"; fi
if [ "${MODE:-}" = smoke ] && [ "$file" = cmail ]; then printf '\nexit 42\n' > "$output"; fi
MOCK
cat > "$TMP/mock/mv" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
if [ "${FAIL_SWITCH:-0}" = 1 ]; then exit 1; fi
"$REAL_MV" "$@"
# Simulate interruption immediately after publication but before success output.
if [ "${FAIL_SWITCH:-0}" = signal ]; then kill -TERM "$PPID"; fi
MOCK
chmod +x "$TMP/mock/curl" "$TMP/mock/mv"
export PATH="$TMP/mock:$PATH"
passed=0
pass() { passed=$((passed + 1)); printf 'ok %s - %s\n' "$passed" "$1"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
install() { "$BASH" "$ROOT/install.sh" > "$TMP/output" 2> "$TMP/error"; }
expect_failure() {
  if install; then fail "$1 unexpectedly succeeded"; fi
  grep -q "$2" "$TMP/error" || fail "$1 wrong diagnostic"
  pass "$1"
}
install || { printf 'fresh install failed: %s\n' "$(< "$TMP/error")" >&2; exit 1; }
[ -x "$CMAIL_BIN_DIR/cmail" ] || fail 'no executable launcher'
"$CMAIL_BIN_DIR/cmail" help > "$TMP/help"
grep -q 'custom-domain email' "$TMP/help" || fail 'installed help'
[ ! -e "$CMAIL_CONFIG_DIR/.env" ] || fail 'install created config'
pass 'fresh install is runnable with shell-metacharacter paths and no setup'
[ "$(wc -l < "$CURL_LOG" | tr -d ' ')" = 15 ] || fail 'incomplete runtime download'
grep -q -- '--proto =https --proto-redir =https' "$CURL_LOG" || fail 'unsafe transport'
grep -q 'eb45f9558ecc5874e6a21d6f1b93fe1379f46841' "$CURL_LOG" || fail 'unpinned source'
pass 'complete runtime including CLI parser from pinned HTTPS source'
[ "$(file_mode "$CMAIL_CONFIG_DIR")" = 700 ] || fail 'config directory not private'
pass 'new config directory is private'
printf 'DOMAIN=example.com\n' > "$CMAIL_CONFIG_DIR/.env"
cp "$CMAIL_CONFIG_DIR/.env" "$TMP/saved-config"
install
cmp "$CMAIL_CONFIG_DIR/.env" "$TMP/saved-config" || fail 'reinstall replaced config'
pass 'reinstall preserves external configuration'
cp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher"
export CMAIL_REF=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
install
cmp -s "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher" && fail 'upgrade did not switch runtime'
cmp "$CMAIL_CONFIG_DIR/.env" "$TMP/saved-config" || fail 'upgrade changed config'
pass 'explicit pinned upgrade switches runtime and preserves config'
cp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher"
for failure in lib/cli.sh lib/output.sh lib/plan.sh completions/cmail.bash completions/cmail.zsh completions/cmail.fish cmail lib/ui.sh lib/env.sh lib/deps.sh lib/godaddy.sh lib/cloudflare.sh lib/gmail.sh VERSION .env.example; do
  export FAIL_FILE="$failure"
  expect_failure "failed download $failure" 'download failed'
  cmp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher" || fail 'download failure broke active launcher'
  "$CMAIL_BIN_DIR/cmail" help >/dev/null
  [ ! -e "$CMAIL_DATA_DIR/.install-lock" ] || fail 'lock leaked'
done
export FAIL_FILE=''
for mode in empty syntax smoke; do
  export MODE="$mode"
  expect_failure "$mode validation failure" 'empty download\|invalid script\|runtime help verification failed'
  cmp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher" || fail 'validation failure broke installation'
done
export MODE=''
export FAIL_SWITCH=1
expect_failure 'late launcher rename failure' 'launcher activation failed'
cmp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher" || fail 'late failure replaced launcher'
"$CMAIL_BIN_DIR/cmail" help >/dev/null
cmp "$CMAIL_CONFIG_DIR/.env" "$TMP/saved-config" || fail 'late failure changed config'
[ ! -e "$CMAIL_DATA_DIR/.install-lock" ] || fail 'late failure leaked lock'
pass 'late activation failure preserves runnable installation and config'
export FAIL_SWITCH=signal
if install; then fail 'simulated signal should stop installer'; fi
"$CMAIL_BIN_DIR/cmail" help >/dev/null || fail 'signal deleted active runtime'
[ ! -e "$CMAIL_DATA_DIR/.install-lock" ] || fail 'signal leaked lock'
pass 'interruption after rename retains active runtime'
export FAIL_SWITCH=0
printf 'touch %q\nexit 42\n' "$TMP/config-loaded" > "$TMP/override-config"
ENV_FILE="$TMP/override-config" install
[ ! -e "$TMP/config-loaded" ] || fail 'installer evaluated inherited config'
pass 'installer validation never evaluates inherited ENV_FILE'
ENV_FILE="$TMP/override-config" "$CMAIL_BIN_DIR/cmail" help >/dev/null
[ ! -e "$TMP/config-loaded" ] || fail 'help sourced config'
pass 'help never evaluates user config'
printf 'DOMAIN=override.example\n' > "$TMP/override-config"
chmod 600 "$TMP/override-config"
if ENV_FILE="$TMP/override-config" "$CMAIL_BIN_DIR/cmail" status > "$TMP/status" 2>&1; then fail 'status should lack token'; fi
[ "$(file_mode "$TMP/override-config")" = 600 ] || fail 'override not used by env_init'
cmp "$CMAIL_CONFIG_DIR/.env" "$TMP/saved-config" || fail 'explicit override ignored'
pass 'launcher respects explicit ENV_FILE override'
cp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher"
cp "$CURL_LOG" "$TMP/saved-curl-log"
mv "$CMAIL_CONFIG_DIR/.env" "$TMP/regular-config"
mkdir "$CMAIL_CONFIG_DIR/.env"
printf '%s\n' preserved > "$CMAIL_CONFIG_DIR/.env/sentinel"
chmod 755 "$CMAIL_CONFIG_DIR/.env"
expect_failure 'directory configuration rejected before installation' 'configuration is not a regular file'
[ "$(file_mode "$CMAIL_CONFIG_DIR/.env")" = 755 ] || fail 'changed config directory mode'
[ ! -e "$CMAIL_CONFIG_DIR/.env/.env.example" ] || fail 'copied template into config directory'
grep -q '^preserved$' "$CMAIL_CONFIG_DIR/.env/sentinel" || fail 'changed directory configuration'
rm "$CMAIL_CONFIG_DIR/.env/sentinel"
rmdir "$CMAIL_CONFIG_DIR/.env"
mkfifo "$CMAIL_CONFIG_DIR/.env"
chmod 640 "$CMAIL_CONFIG_DIR/.env"
expect_failure 'FIFO configuration rejected without opening it' 'configuration is not a regular file'
[ -p "$CMAIL_CONFIG_DIR/.env" ] || fail 'replaced config FIFO'
[ "$(file_mode "$CMAIL_CONFIG_DIR/.env")" = 640 ] || fail 'changed config FIFO mode'
rm "$CMAIL_CONFIG_DIR/.env"
ln -s "$TMP/regular-config" "$CMAIL_CONFIG_DIR/.env"
expect_failure 'symlink configuration rejected before installation' 'symlink configuration'
[ -L "$CMAIL_CONFIG_DIR/.env" ] || fail 'replaced config symlink'
cmp "$TMP/regular-config" "$TMP/saved-config" || fail 'changed config symlink target'
rm "$CMAIL_CONFIG_DIR/.env"
mv "$TMP/regular-config" "$CMAIL_CONFIG_DIR/.env"
cmp "$CURL_LOG" "$TMP/saved-curl-log" || fail 'config preflight performed downloads'
cmp "$CMAIL_BIN_DIR/cmail" "$TMP/old-launcher" || fail 'config conflict replaced launcher'
"$CMAIL_BIN_DIR/cmail" help >/dev/null
[ ! -e "$CMAIL_DATA_DIR/.install-lock" ] || fail 'config conflict leaked lock'
pass 'configuration conflicts preserve installation and perform no downloads'
export CMAIL_REF=main
expect_failure 'reject moving ref' 'full lowercase commit SHA'
export CMAIL_REF=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
mkdir "$CMAIL_DATA_DIR/.install-lock"
expect_failure 'concurrent install rejected' 'already locked'
rmdir "$CMAIL_DATA_DIR/.install-lock"
mv "$CMAIL_BIN_DIR/cmail" "$TMP/managed-launcher"
printf '%s\n' 'unrelated executable' > "$CMAIL_BIN_DIR/cmail"
expect_failure 'unmanaged launcher preserved' 'unmanaged launcher'
grep -q unrelated "$CMAIL_BIN_DIR/cmail" || fail 'clobbered conflict'
rm "$CMAIL_BIN_DIR/cmail"
ln -s "$TMP/managed-launcher" "$CMAIL_BIN_DIR/cmail"
expect_failure 'symlink launcher rejected' 'symlink launcher'
rm "$CMAIL_BIN_DIR/cmail"
mv "$TMP/managed-launcher" "$CMAIL_BIN_DIR/cmail"
original_data="$CMAIL_DATA_DIR"
export CMAIL_DATA_DIR="$TMP/unmanaged"
mkdir "$CMAIL_DATA_DIR"
expect_failure 'unmanaged runtime rejected' 'unmanaged runtime'
printf '%s\n' wrong > "$CMAIL_DATA_DIR/.cmail-install"
expect_failure 'malformed runtime marker rejected' 'invalid runtime marker'
export CMAIL_DATA_DIR="$TMP/data-link"
ln -s "$original_data" "$CMAIL_DATA_DIR"
expect_failure 'symlink runtime rejected' 'symlink directory'
export CMAIL_DATA_DIR="$original_data" CMAIL_BIN_DIR=relative
expect_failure 'relative directory rejected' 'absolute paths'
# Install the reviewed local checkout with network access forbidden by the mock.
unset CMAIL_REF
export CMAIL_BIN_DIR="$TMP/bin space '\$;"
export FAIL_FILE=cmail
before_downloads=$(wc -l < "$CURL_LOG")
"$BASH" "$ROOT/install.sh" --local > "$TMP/local-output" 2> "$TMP/error"
[ "$(wc -l < "$CURL_LOG")" = "$before_downloads" ] || fail 'local mode downloaded files'
"$CMAIL_BIN_DIR/cmail" --version > "$TMP/version"
grep -q "$(cat "$ROOT/VERSION")" "$TMP/version" || fail 'local version mismatch'
for shell in bash zsh fish; do
  "$CMAIL_BIN_DIR/cmail" completion "$shell" > "$TMP/completion"
  cmp "$TMP/completion" "$ROOT/completions/cmail.$shell" || fail 'installed completion mismatch'
done
cmp "$CMAIL_CONFIG_DIR/.env" "$TMP/saved-config" || fail 'local install replaced config'
pass 'local installation has no downloads, preserves config, includes completions and version'
printf '%s installer cases passed (offline)\n' "$passed"
