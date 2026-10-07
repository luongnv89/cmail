# deps.sh — ensure required CLI tools exist
# shellcheck shell=bash

_pkg_install() { # _pkg_install <pkg> — best-effort install across pkg managers
  local pkg="$1"
  if command -v pacman >/dev/null;   then sudo pacman -S --needed --noconfirm "$pkg"
  elif command -v apt-get >/dev/null; then sudo apt-get install -y "$pkg"
  elif command -v dnf >/dev/null;    then sudo dnf install -y "$pkg"
  elif command -v brew >/dev/null;   then brew install "$pkg"
  else return 1; fi
}

ensure_tool() { # ensure_tool <cmd> [pkg-name]
  local cmd="$1" pkg="${2:-$1}"
  command -v "$cmd" >/dev/null && { ok "$cmd present"; return 0; }
  warn "$cmd missing — installing ($pkg)"
  if ! _pkg_install "$pkg" || ! command -v "$cmd" >/dev/null; then die "could not install $cmd — check network access, package-manager availability and install permissions (sudo where required). Install '$pkg' manually, ensure '$cmd' is on PATH (command -v $cmd), then re-run ./cmail setup"; fi
  ok "$cmd installed"
}

ensure_gddy() {
  if command -v gddy >/dev/null; then ok "gddy present ($(gddy --version 2>/dev/null | head -1))"; return 0; fi
  warn "gddy missing — running official installer (installs to ~/.local/bin)"
  curl -fsSL https://github.com/godaddy/cli/releases/latest/download/install.sh | bash \
    || die "gddy install failed — check network access to GitHub and write permission for ~/.local/bin. Install manually: https://developer.godaddy.com/en/docs/api-users/cli/set-up; add ~/.local/bin to PATH, then re-run ./cmail setup"
  export PATH="$HOME/.local/bin:$PATH"
  command -v gddy >/dev/null || die "gddy unavailable after installer — check ~/.local/bin permissions and installer output; install manually: https://developer.godaddy.com/en/docs/api-users/cli/set-up. Run export PATH=\"\$HOME/.local/bin:\$PATH\", verify command -v gddy, then re-run ./cmail setup"
  ok "gddy installed"
}

ensure_deps() {
  step "Dependencies"
  ensure_tool curl curl
  ensure_tool jq jq
  ensure_gddy
}
