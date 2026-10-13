#!/usr/bin/env bash
# ============================================================================
# cmail installer: user-local, no sudo. Never runs setup or changes DNS.
# Usage: curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash
# ============================================================================
set -euo pipefail
umask 022
# Bash parses this whole group before running any of it, so a download cut
# short during `curl ... | bash` fails to parse instead of running partially.
{
TOOL_NAME="cmail"
REPO_OWNER="luongnv89"
REPO_NAME="cmail"
REPO_URL="https://github.com/$REPO_OWNER/$REPO_NAME"
MARKER="free custom-domain email with Cloudflare Email Routing"
LEGACY_LAUNCHER="# cmail managed launcher v1"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RED=$'\033[0;31m' GREEN=$'\033[0;32m' YELLOW=$'\033[1;33m' BLUE=$'\033[0;34m' NC=$'\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi
info() { printf '%s[INFO]%s  %s\n' "$BLUE" "$NC" "$*"; }
ok()   { printf '%s[ OK ]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%s[WARN]%s  %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()  { printf '%s[ERR ]%s  %s\n' "$RED" "$NC" "$*" >&2; }
die()  { err "$@"; exit 1; }

usage() {
  cat <<'EOF'
Install the cmail command for the current user (no sudo).

Usage:
  curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash
  bash install.sh [--version vX.Y.Z] [--from-source]
  bash install.sh --local          # build and install this reviewed checkout (needs cargo)

Options:
  --version TAG   Install a specific release (default: latest; or CMAIL_VERSION)
  --from-source   Build the release with cargo instead of downloading a binary
  --local         Build the checkout containing this script with cargo
  -h, --help      Show this help

Environment:
  CMAIL_BIN_DIR   Install directory (default: ~/.local/bin)
  CMAIL_VERSION   Release tag, e.g. v0.4.0 (default: latest)

Downloads are verified against the release's SHA256SUMS before anything is
installed. Configuration (~/.config/cmail/.env) is never created or changed.
EOF
}

detect_os() {
  local os
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$os" in
    linux*) echo linux ;;
    darwin*) echo macos ;;
    mingw*|msys*|cygwin*) die "Windows is not supported; use WSL and run this installer inside it" ;;
    *) die "Unsupported operating system: $os" ;;
  esac
}

detect_arch() {
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) echo x86_64 ;;
    aarch64|arm64) echo aarch64 ;;
    *) echo "unsupported:$arch" ;;
  esac
}

# Release target triple, or empty when no prebuilt binary exists.
release_target() {
  local os="$1" arch="$2"
  # An x86_64 shell under Rosetta on Apple silicon should still get the native binary.
  if [ "$os" = macos ] && [ "$arch" = x86_64 ] \
    && [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = 1 ]; then
    arch=aarch64
  fi
  case "$os:$arch" in
    linux:x86_64) echo x86_64-unknown-linux-musl ;;
    linux:aarch64) echo aarch64-unknown-linux-musl ;;
    macos:x86_64) echo x86_64-apple-darwin ;;
    macos:aarch64) echo aarch64-apple-darwin ;;
    *) echo "" ;;
  esac
}

# HTTPS only; plain HTTP is accepted solely for a loopback test server.
check_url() {
  case "$1" in
    https://*|http://127.0.0.1:*|http://localhost:*) ;;
    *) die "refusing non-HTTPS download URL: $1" ;;
  esac
}

download() {
  local url="$1" out="$2"
  check_url "$url"
  if command -v curl >/dev/null 2>&1; then
    curl --fail --silent --show-error --location --proto '=https,http' --proto-redir '=https' \
      --connect-timeout 15 --max-time 300 --retry 2 -o "$out" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget --quiet --https-only --tries=3 --timeout=60 -O "$out" "$url" 2>/dev/null \
      || wget --quiet --tries=3 --timeout=60 -O "$out" "$url"
  else
    die "curl or wget is required to download cmail"
  fi
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d' ' -f1
  else
    die "sha256sum or shasum is required to verify the download"
  fi
}

# A binary we may replace: ours (it embeds the help tagline) or the 0.3 Bash launcher.
is_cmail() {
  local file="$1" second=''
  [ -f "$file" ] || return 1
  { IFS= read -r _ && IFS= read -r second; } < "$file" 2>/dev/null || true
  [ "$second" = "$LEGACY_LAUNCHER" ] && return 0
  grep -qF "$MARKER" "$file" 2>/dev/null
}

check_destination() {
  local target="$1"
  [ ! -L "$target" ] || die "$target is a symlink (another package manager?); remove it or set CMAIL_BIN_DIR"
  if [ -e "$target" ] && ! is_cmail "$target"; then
    die "$target exists and is not cmail; remove it or set CMAIL_BIN_DIR"
  fi
}

fetch_release() {
  local target="$1" work="$2" asset base expected actual
  asset="cmail-$target.tar.gz"
  if [ -n "${CMAIL_RELEASE_URL:-}" ]; then
    base="${CMAIL_RELEASE_URL%/}"
  elif [ -n "$VERSION" ]; then
    base="$REPO_URL/releases/download/$VERSION"
  else
    base="$REPO_URL/releases/latest/download"
  fi
  info "Downloading $asset (${VERSION:-latest release})"
  download "$base/$asset" "$work/$asset" || die "download failed: $base/$asset (nothing was installed)"
  download "$base/SHA256SUMS" "$work/SHA256SUMS" || die "checksum download failed (nothing was installed)"
  expected="$(awk -v name="$asset" '$2 == name || $2 == "*" name { print $1; exit }' "$work/SHA256SUMS")"
  [ -n "$expected" ] || die "SHA256SUMS has no entry for $asset (nothing was installed)"
  actual="$(sha256_of "$work/$asset")"
  [ "$actual" = "$expected" ] || die "checksum mismatch for $asset (expected $expected, got $actual); nothing was installed"
  ok "Checksum verified ($asset)"
  mkdir "$work/unpacked"
  tar -xzf "$work/$asset" -C "$work/unpacked" cmail 2>/dev/null \
    || die "release archive does not contain a cmail binary (nothing was installed)"
  if [ ! -f "$work/unpacked/cmail" ] || [ -L "$work/unpacked/cmail" ]; then
    die "release archive's cmail is not a regular file (nothing was installed)"
  fi
  BUILT="$work/unpacked/cmail"
}

build_source() {
  local work="$1" ref_args=()
  command -v cargo >/dev/null 2>&1 \
    || die "no prebuilt binary for this platform and cargo is missing; install Rust from https://rustup.rs and rerun"
  [ -z "$VERSION" ] || ref_args=(--tag "$VERSION")
  info "Building cmail from source with cargo (this can take a few minutes)"
  cargo install --git "$REPO_URL" ${ref_args[@]+"${ref_args[@]}"} --locked --root "$work/cargo" cmail \
    || die "cargo build failed (nothing was installed)"
  BUILT="$work/cargo/bin/cmail"
}

build_local() {
  local source_dir="$1"
  command -v cargo >/dev/null 2>&1 || die "--local needs cargo; install Rust from https://rustup.rs"
  [ -f "$source_dir/Cargo.toml" ] || die "--local must run from a cmail checkout (no Cargo.toml in $source_dir)"
  info "Building this checkout with cargo"
  cargo build --release --locked --manifest-path "$source_dir/Cargo.toml" \
    || die "cargo build failed (nothing was installed)"
  BUILT="$source_dir/target/release/cmail"
}

# Copy next to the destination, check it runs, then rename over the old one.
activate() {
  local built="$1" bin_dir="$2" target candidate version
  target="$bin_dir/$TOOL_NAME"
  version="$("$built" --version 2>/dev/null)" || die "the built binary does not run on this machine (nothing was installed)"
  case "$version" in "cmail "*) ;; *) die "unexpected binary (it printed '$version'); nothing was installed" ;; esac
  mkdir -p "$bin_dir"
  check_destination "$target"
  candidate="$bin_dir/.cmail.new.$$"
  cp "$built" "$candidate"
  chmod 755 "$candidate"
  "$candidate" --version >/dev/null 2>&1 || { rm -f "$candidate"; die "installed copy does not run (previous cmail unchanged)"; }
  mv -f "$candidate" "$target"
  ok "$version installed to $target"
}

main() {
  local mode=release arg bin_dir os arch target script_path source_dir
  VERSION="${CMAIL_VERSION:-}"
  while [ "$#" -gt 0 ]; do
    arg="$1"; shift
    case "$arg" in
      -h|--help) usage; exit 0 ;;
      --local) mode=local ;;
      --from-source) mode=source ;;
      --version)
        [ "$#" -gt 0 ] || die "--version needs a release tag such as v0.4.0"
        VERSION="$1"; shift ;;
      --version=*) VERSION="${arg#*=}" ;;
      *) die "unknown argument: $arg (see --help)" ;;
    esac
  done
  if [ -n "$VERSION" ]; then
    case "$VERSION" in v*) ;; *) VERSION="v$VERSION" ;; esac
    printf '%s\n' "$VERSION" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$' \
      || die "invalid release tag: $VERSION (expected vX.Y.Z)"
  fi
  [ -n "${HOME:-}" ] || die "HOME must be set"
  bin_dir="${CMAIL_BIN_DIR:-$HOME/.local/bin}"
  case "$bin_dir" in /*) ;; *) die "CMAIL_BIN_DIR must be an absolute path" ;; esac
  [ ! -L "$bin_dir" ] || die "refusing symlinked install directory: $bin_dir"
  [ ! -e "$bin_dir" ] || [ -d "$bin_dir" ] || die "not a directory: $bin_dir"
  check_destination "$bin_dir/$TOOL_NAME"

  info "Installing $TOOL_NAME"
  os="$(detect_os)"
  arch="$(detect_arch)"
  target="$(release_target "$os" "$arch")"
  info "OS: $os | Arch: ${arch#unsupported:} | Target: ${target:-none (build from source)}"

  WORK="$(mktemp -d)"
  trap 'rm -rf "${WORK:-}"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  BUILT=''
  if [ "$mode" = local ]; then
    [ -z "$VERSION" ] || die "--version applies to release installs; omit it with --local"
    # A piped script has no file path, so there is no checkout to build.
    script_path="${BASH_SOURCE[0]:-}"
    if [ -z "$script_path" ] || [ ! -f "$script_path" ]; then
      die "--local needs a cloned checkout: run bash install.sh --local inside it"
    fi
    source_dir="$(cd "$(dirname "$script_path")" && pwd)"
    build_local "$source_dir"
  elif [ "$mode" = source ] || [ -z "$target" ]; then
    [ -n "$target" ] || warn "No prebuilt binary for $os/${arch#unsupported:}; building from source"
    build_source "$WORK"
  else
    for tool in tar awk; do
      command -v "$tool" >/dev/null 2>&1 || die "$tool is required to install cmail"
    done
    fetch_release "$target" "$WORK"
  fi
  activate "$BUILT" "$bin_dir"

  if [ -d "$HOME/.local/share/cmail" ] && [ -f "$HOME/.local/share/cmail/.cmail-install" ]; then
    info "The old 0.3 runtime store $HOME/.local/share/cmail is no longer used; you may delete it"
  fi
  case ":${PATH:-}:" in
    *":$bin_dir:"*)
      found="$(command -v cmail 2>/dev/null || true)"
      if [ -n "$found" ] && [ "$found" != "$bin_dir/cmail" ]; then
        warn "another cmail comes first on PATH: $found"
      fi
      info "PATH: $bin_dir is already on your PATH; run: cmail --version" ;;
    *)
      warn "$bin_dir is not on your PATH. Add this to ~/.zshrc or ~/.bashrc:"
      # Print a command for the user's shell without expanding this process's PATH.
      # shellcheck disable=SC2016
      printf '  export PATH=%q:"$PATH"\n' "$bin_dir" ;;
  esac
  proxy_note="Proxy: cmail does not use HTTPS_PROXY or ALL_PROXY yet; it needs direct HTTPS access to api.cloudflare.com"
  if [ -n "${HTTPS_PROXY:-}${https_proxy:-}${ALL_PROXY:-}${all_proxy:-}" ]; then
    warn "$proxy_note"
  else
    info "$proxy_note"
  fi
  info "Installation did not run setup or change DNS. Next: cmail config init, then cmail setup"
  ok "Installation complete!"
}

main "$@"
exit
}
