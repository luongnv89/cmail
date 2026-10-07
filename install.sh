#!/usr/bin/env bash
# User-local installation only: never run setup, doctor or a package manager.
set -euo pipefail
umask 077

fail() { printf 'cmail install: %s\n' "$*" >&2; exit 1; }
if [ "${1:-}" = --help ]; then
  printf '%s\n' 'Usage: bash install.sh' \
    'Overrides: CMAIL_REF (40-character commit), CMAIL_BIN_DIR, CMAIL_DATA_DIR, CMAIL_CONFIG_DIR' \
    'Defaults: pinned v0.1.0 runtime, ~/.local/bin, ~/.local/share/cmail, ~/.config/cmail'
  exit 0
fi
[ "$#" = 0 ] || fail 'unknown argument (see --help)'
[ -n "${HOME:-}" ] || fail 'HOME must be set'
ref="${CMAIL_REF:-eb45f9558ecc5874e6a21d6f1b93fe1379f46841}"
[ "${#ref}" = 40 ] || fail 'CMAIL_REF must be a full lowercase commit SHA'
case "$ref" in *[!0-9a-f]*) fail 'CMAIL_REF must be a full lowercase commit SHA' ;; esac
bin_dir="${CMAIL_BIN_DIR:-$HOME/.local/bin}"
data_dir="${CMAIL_DATA_DIR:-$HOME/.local/share/cmail}"
config_dir="${CMAIL_CONFIG_DIR:-$HOME/.config/cmail}"
for path in "$bin_dir" "$data_dir" "$config_dir"; do
  case "$path" in /*) ;; *) fail 'destination directories must be absolute paths' ;; esac
  [ ! -L "$path" ] || fail "refusing symlink directory: $path"
  [ ! -e "$path" ] || [ -d "$path" ] || fail "not a directory: $path"
done
launcher="$bin_dir/cmail"
launcher_marker='# cmail managed launcher v1'
check_launcher() {
  [ ! -L "$launcher" ] || fail "refusing symlink launcher: $launcher"
  if [ -e "$launcher" ]; then
    [ -f "$launcher" ] || fail "launcher is not a file: $launcher"
    local first second
    { IFS= read -r first; IFS= read -r second; } < "$launcher" \
      || fail "unmanaged launcher: $launcher"
    [ "$first" = '#!/usr/bin/env bash' ] && [ "$second" = "$launcher_marker" ] \
      || fail "unmanaged launcher: $launcher"
  fi
}
check_launcher
for tool in curl mktemp; do
  command -v "$tool" >/dev/null || fail "required tool missing: $tool"
done
# Never claim an existing directory, even an empty one, without our marker.
if [ ! -e "$data_dir" ]; then
  mkdir -p "$(dirname "$data_dir")"
  mkdir "$data_dir" || fail 'could not create runtime directory'
  printf '%s\n' 'cmail runtime store v1' > "$data_dir/.cmail-install"
fi
[ -f "$data_dir/.cmail-install" ] && [ ! -L "$data_dir/.cmail-install" ] \
  || fail "unmanaged runtime directory: $data_dir"
[ "$(< "$data_dir/.cmail-install")" = 'cmail runtime store v1' ] \
  || fail "invalid runtime marker: $data_dir"
lock="$data_dir/.install-lock"
mkdir "$lock" 2>/dev/null || fail "installation already locked: $lock (remove only if no installer is running)"
stage='' candidate='' activated=0
cleanup() {
  [ -z "$candidate" ] || rm -f "$candidate"
  if [ "$activated" = 0 ] && [ -n "$stage" ]; then rm -rf "$stage"; fi
  rmdir "$lock"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
stage=$(mktemp -d "$data_dir/runtime.XXXXXXXX")
mkdir "$stage/lib"
# Explicit destinations avoid archive traversal, links and extraction tools.
files=(cmail VERSION .env.example lib/ui.sh lib/env.sh lib/deps.sh lib/godaddy.sh lib/cloudflare.sh lib/gmail.sh)
for file in "${files[@]}"; do
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 120 \
    "https://raw.githubusercontent.com/luongnv89/cmail/$ref/$file" -o "$stage/$file" \
    || fail "download failed: $file (previous installation unchanged)"
  [ -s "$stage/$file" ] || fail "empty download: $file"
done
"$BASH" -n "$stage/cmail" || fail 'invalid cmail script'
for file in "$stage"/lib/*.sh "$stage/.env.example"; do
  "$BASH" -n "$file" || fail "invalid script: ${file##*/}"
done
chmod 700 "$stage/cmail"
# Help does not load config or contact providers. Do not use setup/doctor here.
ENV_FILE="$stage/unused-config" "$BASH" "$stage/cmail" help > "$stage/help.txt" \
  || fail 'runtime help verification failed'
grep -q 'cmail.*custom-domain email' "$stage/help.txt" || fail 'unexpected runtime help'
printf '%s\n' "$ref" > "$stage/COMMIT"
mkdir -p "$bin_dir" "$config_dir"
[ ! -L "$config_dir/.env" ] || fail 'refusing symlink configuration'
# No credentials or template are copied into existing configuration.
# env_init will create the file on the first explicit setup/status/doctor call.
candidate=$(mktemp "$bin_dir/.cmail-launcher.XXXXXXXX")
{
  printf '%s\n' '#!/usr/bin/env bash' "$launcher_marker"
  printf 'default_config=%q\n' "$config_dir/.env"
  # Expansion belongs to the generated launcher, not the installer.
  # shellcheck disable=SC2016
  printf 'export ENV_FILE="${ENV_FILE:-$default_config}"\n'
  printf 'exec bash %q "$@"\n' "$stage/cmail"
} > "$candidate"
chmod 700 "$candidate"
"$BASH" -n "$candidate"
"$BASH" "$candidate" help >/dev/null || fail 'launcher verification failed'
check_launcher
mv -f "$candidate" "$launcher"
activated=1
candidate=''
printf 'Installed cmail runtime %s\nLauncher: %s\nConfig: %s/.env\n' "$ref" "$launcher" "$config_dir"
# Print a command for the user's shell without expanding this process's PATH.
# shellcheck disable=SC2016
printf 'Verify: %q help\nPATH (if needed): export PATH=%q:"$PATH"\n' "$launcher" "$bin_dir"
printf '%s\n' 'Installation did not run setup or change DNS. Run cmail setup only when ready.'
