#!/usr/bin/env bash
# shellcheck disable=SC2016  # fake uname/sysctl scripts expand their own $1
# Installer contracts against a loopback fake release; installs only into temp dirs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHELL_UNDER_TEST="${INSTALL_TEST_BASH:-bash}"
BIN="${CMAIL_BIN:-$ROOT/target/debug/cmail}"
[ -x "$BIN" ] || { printf 'build cmail first (cargo build)\n' >&2; exit 1; }
TMP="$(mktemp -d)"
SERVER_PID=''
cleanup() { [ -z "$SERVER_PID" ] || kill "$SERVER_PID" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

case "$(uname -s):$(uname -m)" in
  Linux:x86_64) NATIVE=x86_64-unknown-linux-musl ;;
  Linux:aarch64) NATIVE=aarch64-unknown-linux-musl ;;
  Darwin:x86_64) NATIVE=x86_64-apple-darwin ;;
  Darwin:arm64) NATIVE=aarch64-apple-darwin ;;
  *) printf 'SKIP: no release target for this machine\n'; exit 0 ;;
esac

# Fake release: tarballs for the native and a remapped target, plus SHA256SUMS.
RELEASE="$TMP/release"
mkdir -p "$RELEASE/stage"
cp "$BIN" "$RELEASE/stage/cmail"
sum() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
for target in "$NATIVE" aarch64-apple-darwin; do
  tar -czf "$RELEASE/cmail-$target.tar.gz" -C "$RELEASE/stage" cmail
done
: > "$RELEASE/SHA256SUMS"
for file in "$RELEASE"/*.tar.gz; do printf '%s  %s\n' "$(sum "$file")" "${file##*/}" >> "$RELEASE/SHA256SUMS"; done

PORT_FILE="$TMP/port"
# A plain socketserver skips HTTPServer.server_bind's getfqdn() reverse lookup,
# which can stall for many seconds on macOS runners; the port file is renamed in.
python3 - "$RELEASE" "$PORT_FILE" <<'EOF' &
import functools, http.server, os, socketserver, sys
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass
class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
handler = functools.partial(Quiet, directory=sys.argv[1])
server = Server(('127.0.0.1', 0), handler)
with open(sys.argv[2] + '.tmp', 'w') as port_file:
    port_file.write(str(server.server_address[1]))
os.replace(sys.argv[2] + '.tmp', sys.argv[2])
server.serve_forever()
EOF
SERVER_PID=$!
for _ in $(seq 300); do [ -s "$PORT_FILE" ] && break; sleep 0.1; done
[ -s "$PORT_FILE" ] || { printf 'FAIL: loopback release server did not start within 30s\n' >&2; exit 1; }
URL="http://127.0.0.1:$(cat "$PORT_FILE")"

passed=0
fail() { printf 'FAIL: %s\n' "$1" >&2; [ ! -f "$TMP/out" ] || cat "$TMP/out" >&2; exit 1; }
pass() { passed=$((passed + 1)); printf 'PASS: %s\n' "$1"; }

# Run the installer with a fresh HOME; extra VAR=value words go to env.
fresh() { rm -rf "${TMP:?}/home"; mkdir -p "$TMP/home"; }
run() {
  env -i PATH="${TEST_PATH:-$PATH}" HOME="$TMP/home" CMAIL_RELEASE_URL="$URL" "$@" > "$TMP/out" 2>&1
}
installed="$TMP/home/.local/bin/cmail"

fresh
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" || fail 'release install'
[ -x "$installed" ] || fail 'binary installed'
[ "$("$installed" --version)" = "$("$BIN" --version)" ] || fail 'installed version runs'
[ "$(tail -n 1 "$TMP/out")" = '[ OK ]  Installation complete!' ] || fail 'last line'
grep -q 'Checksum verified' "$TMP/out" || fail 'checksum reported'
grep -q 'is not on your PATH' "$TMP/out" || fail 'PATH hint'
[ ! -e "$TMP/home/.config/cmail" ] || fail 'config untouched'
pass 'release install verifies checksum, installs and reports'

run env PATH="$TMP/home/.local/bin:$PATH" "$SHELL_UNDER_TEST" "$ROOT/install.sh" || fail 'reinstall'
grep -q 'already on your PATH' "$TMP/out" || fail 'PATH detected'
pass 'reinstall over an existing cmail'

fresh
run "$SHELL_UNDER_TEST" -c "cat '$ROOT/install.sh' | $SHELL_UNDER_TEST" || fail 'piped install'
[ -x "$installed" ] || fail 'piped binary'
pass 'curl | bash style piped install'

fresh
run "$SHELL_UNDER_TEST" -c "head -c 2000 '$ROOT/install.sh' | $SHELL_UNDER_TEST" && fail 'truncated script must fail'
[ ! -e "$installed" ] || fail 'truncated script installed something'
pass 'truncated download runs nothing'

fresh
cp "$RELEASE/SHA256SUMS" "$TMP/sums"
# Change each hash's first digit (0 becomes 1, anything else 0) so it always differs.
sed -e 's/^0/1/' -e t -e 's/^[0-9a-f]/0/' "$TMP/sums" > "$RELEASE/SHA256SUMS"
if cmp -s "$TMP/sums" "$RELEASE/SHA256SUMS"; then fail 'checksums corrupted'; fi
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'checksum mismatch must fail'
cp "$TMP/sums" "$RELEASE/SHA256SUMS"
grep -q 'checksum mismatch' "$TMP/out" || fail 'mismatch message'
[ ! -e "$installed" ] || fail 'mismatch installed something'
pass 'checksum mismatch installs nothing'

fresh
run env CMAIL_RELEASE_URL="$URL/missing" "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'missing asset must fail'
grep -q 'download failed' "$TMP/out" || fail 'download failure message'
pass 'missing release asset fails cleanly'

fresh
run env CMAIL_RELEASE_URL="http://example.com/release" "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'plain http must fail'
grep -q 'refusing non-HTTPS' "$TMP/out" || fail 'https message'
pass 'non-HTTPS release URL refused'

fresh
mkdir -p "$TMP/home/.local/bin"
printf '#!/bin/sh\necho other tool\n' > "$installed"; chmod 755 "$installed"
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'unmanaged file must be kept'
grep -q 'is not cmail' "$TMP/out" || fail 'unmanaged message'
grep -q 'other tool' "$installed" || fail 'unmanaged file changed'
rm -f "$installed"; ln -s /bin/sh "$installed"
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'symlink must be kept'
grep -q 'symlink' "$TMP/out" || fail 'symlink message'
pass 'unmanaged files and symlinks are never replaced'

fresh
mkdir -p "$TMP/home/.local/bin" "$TMP/home/.local/share/cmail"
printf '#!/usr/bin/env bash\n# cmail managed launcher v1\nexec bash /old/cmail "$@"\n' > "$installed"
touch "$TMP/home/.local/share/cmail/.cmail-install"
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" || fail 'legacy upgrade'
"$installed" --version >/dev/null || fail 'legacy replaced by binary'
grep -q 'no longer used' "$TMP/out" || fail 'legacy store note'
pass 'upgrade replaces the 0.3 Bash launcher'

fresh
run env CMAIL_BIN_DIR="$TMP/custom bin" "$SHELL_UNDER_TEST" "$ROOT/install.sh" --version 0.4.0 || fail 'custom dir + version'
[ -x "$TMP/custom bin/cmail" ] || fail 'custom dir install'
run env CMAIL_BIN_DIR=relative "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'relative dir must fail'
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" --version latest && fail 'bad tag must fail'
grep -q 'invalid release tag' "$TMP/out" || fail 'bad tag message'
pass 'CMAIL_BIN_DIR, --version and validation'

# Platform mapping: a macOS arm64 machine downloads the aarch64-apple-darwin asset.
fresh
mkdir -p "$TMP/fake"
printf '#!/bin/sh\ncase "$1" in -s) echo Darwin ;; -m) echo arm64 ;; esac\n' > "$TMP/fake/uname"
printf '#!/bin/sh\necho 0\n' > "$TMP/fake/sysctl"
chmod 755 "$TMP/fake/uname" "$TMP/fake/sysctl"
TEST_PATH="$TMP/fake:$PATH" run "$SHELL_UNDER_TEST" "$ROOT/install.sh" || fail 'macos arm64 mapping'
grep -q 'cmail-aarch64-apple-darwin.tar.gz' "$TMP/out" || fail 'aarch64-apple-darwin asset'
printf '#!/bin/sh\ncase "$1" in -s) echo Linux ;; -m) echo riscv64 ;; esac\n' > "$TMP/fake/uname"
mkdir -p "$TMP/nocargo"
for tool in bash sh env cat tr cut awk grep mktemp rm mkdir dirname tail head; do
  ln -sf "$(command -v "$tool")" "$TMP/nocargo/$tool"
done
TEST_PATH="$TMP/fake:$TMP/nocargo" run "$SHELL_UNDER_TEST" "$ROOT/install.sh" && fail 'unsupported arch without cargo'
grep -q 'no prebuilt binary for this platform and cargo is missing' "$TMP/out" || fail 'unsupported arch message'
pass 'platform detection and unsupported-platform guidance'

fresh
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" --help || fail 'help'
grep -q 'bash install.sh --local' "$TMP/out" || fail 'help mentions --local'
run "$SHELL_UNDER_TEST" "$ROOT/install.sh" --bogus && fail 'unknown argument'
run "$SHELL_UNDER_TEST" -c "cat '$ROOT/install.sh' | $SHELL_UNDER_TEST -s -- --local" && fail 'piped --local must fail'
grep -q 'needs a cloned checkout' "$TMP/out" || fail 'piped --local message'
pass 'help, argument errors and piped --local'

if [ "${INSTALL_TEST_LOCAL:-1}" = 1 ] && command -v cargo >/dev/null; then
  fresh
  run env PATH="$PATH" CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}" RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}" \
    "$SHELL_UNDER_TEST" "$ROOT/install.sh" --local || fail 'local build install'
  "$installed" --version >/dev/null || fail 'local binary runs'
  pass '--local builds and installs the checkout'
fi

printf 'PASS: %s installer checks (%s)\n' "$passed" "$SHELL_UNDER_TEST"
