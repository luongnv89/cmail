# ui.sh — logging, prompts, browser opening
# shellcheck shell=bash

if [ -t 1 ]; then
  C_BLUE=$'\033[1;34m'; C_GREEN=$'\033[1;32m'; C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_BLUE= C_GREEN= C_YELLOW= C_RED= C_DIM= C_OFF=
fi

log()   { printf '%s==>%s %s\n' "$C_BLUE" "$C_OFF" "$*"; }
ok()    { printf '%s ✓%s %s\n' "$C_GREEN" "$C_OFF" "$*"; }
warn()  { printf '%s !%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; }
die()   { printf '%sERROR:%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; exit 1; }
step()  { printf '\n%s── %s ──%s\n' "$C_BLUE" "$*" "$C_OFF"; }
note()  { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF"; }

confirm() { # confirm <question> — returns 0 on yes
  local ans
  printf '%s ?%s %s [y/N] ' "$C_YELLOW" "$C_OFF" "$1"
  read -r ans
  [ "${ans,,}" = "y" ] || [ "${ans,,}" = "yes" ]
}

open_url() { # open_url <url> — best-effort browser open, always prints
  local url="$1"
  note "open: $url"
  if [ -n "${BROWSER:-}" ]; then "$BROWSER" "$url" >/dev/null 2>&1 & return; fi
  case "$(uname -s)" in
    Darwin) open "$url" >/dev/null 2>&1 & ;;
    Linux)
      if command -v xdg-open >/dev/null; then xdg-open "$url" >/dev/null 2>&1 &
      elif command -v wslview >/dev/null; then wslview "$url" >/dev/null 2>&1 & fi ;;
  esac
  sleep 1
}

pause() { printf '%s… press Enter to continue%s ' "$C_DIM" "$C_OFF"; read -r; }
