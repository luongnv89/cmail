# shellcheck shell=bash
# Dependency inspection only. Installation is always an explicit user action.
ensure_tool() {
  local tool="$1" package="${2:-$1}"
  command -v "$tool" >/dev/null && { ok "$tool present"; return 0; }
  die "$tool missing — install '$package' manually with your package manager and check PATH (command -v $tool), then re-run ./cmail setup"
}
ensure_gddy() {
  command -v gddy >/dev/null && { ok 'gddy present'; return 0; }
  die 'gddy missing — Install manually: https://developer.godaddy.com/en/docs/api-users/cli/set-up; check GitHub/network access, add ~/.local/bin to PATH, then re-run ./cmail setup'
}
ensure_deps() { step 'Dependencies'; ensure_tool curl; ensure_tool jq; ensure_gddy; }
ensure_read_tools() { ensure_tool curl; ensure_tool jq; }
