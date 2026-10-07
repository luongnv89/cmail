# ui.sh — logging, prompts, browser opening
# shellcheck shell=bash

if [ -t 1 ]; then
  C_BLUE=$'\033[1;34m'; C_GREEN=$'\033[1;32m'; C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_BLUE='' C_GREEN='' C_YELLOW='' C_RED='' C_DIM='' C_OFF=''
fi

log()   { printf '%s==>%s %s\n' "$C_BLUE" "$C_OFF" "$*"; }
ok()    { printf '%s ✓%s %s\n' "$C_GREEN" "$C_OFF" "$*"; }
warn()  { printf '%s !%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; }
die()   { printf '%sERROR:%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; exit 1; }
step()  { CMAIL_STEP="$*"; printf '\n%s── %s ──%s\n' "$C_BLUE" "$*" "$C_OFF"; }
note()  { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF"; }

confirm() { # confirm <question> — returns 0 on yes
  local ans
  printf '%s ?%s %s [y/N] ' "$C_YELLOW" "$C_OFF" "$1"
  read -r ans
  case "$ans" in [yY]|[yY][eE][sS]) return 0 ;; *) return 1 ;; esac
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

# Called once by setup's EXIT trap, including unexpected shell/tool failures.
# Never print the failed command: it may contain credentials.
setup_recovery() {
  printf '\nSetup stopped at: %s\n' "${CMAIL_STEP:-startup}" >&2
  case "${CMAIL_STEP:-}" in
    Dependencies*)
      note "Next: install the missing tool using your OS package manager; check network/sudo access and PATH." ;;
    Configuration*)
      note "Next: edit DEST_EMAIL and ADDRESSES in .env (local parts only, e.g. hello,contact). Keep this file private." ;;
    'GoDaddy authentication'*)
      note "Next: run gddy auth login --env ${GDDY_ENV:-prod} and complete browser consent; replace an expired GDDY_PAT in .env if using a PAT." ;;
    'Choose domain'*)
      note "Next: check the domain is in the correct GoDaddy account/environment. Check orders before retrying a purchase; set DOMAIN in .env once owned." ;;
    'Cloudflare API token'*)
      note "Next: open https://dash.cloudflare.com/profile/api-tokens. Replace an invalid/expired CLOUDFLARE_API_TOKEN in .env; for network/service errors, fix connectivity before changing the token." ;;
    'Cloudflare zone:'*)
      note "Next: check token Account Resources and Zone Resources at https://dash.cloudflare.com/profile/api-tokens. For account discovery problems, set CF_ACCOUNT_ID from the dashboard in .env; this does not grant permissions." ;;
    'GoDaddy: point'*)
      note "Next: open GoDaddy > domain > DNS > Nameservers and compare with Cloudflare > domain > Overview. If an update failed, verify its outcome before retrying." ;;
    'Waiting for zone activation'*)
      note "Next: compare GoDaddy delegation with the nameservers on Cloudflare Overview. Wait for propagation (up to 24–48 hours); an API/auth failure is not propagation." ;;
    'Enable Cloudflare Email Routing'*)
      note "Next: open Cloudflare > domain > Email > Email Routing. Check token Zone Settings:Edit and DNS conflicts; do not remove existing mail-provider records blindly." ;;
    'Destination address:'*)
      note "Next: check the destination Inbox/Spam and click Cloudflare's verification link. Resend missing/expired links from Email Routing > Destination addresses; token needs Account > Email Routing Addresses > Edit." ;;
    'Forwarding addresses'*)
      note "Next: open Cloudflare > domain > Email > Email Routing > Routing rules. Check enabled rules point to DEST_EMAIL and token has Zone > Email Routing Rules > Edit. Earlier rules may already exist." ;;
    'Send FROM'*)
      note "Next: finish Gmail Settings > Accounts and Import > Send mail as. Use a Google App Password with smtp.gmail.com:587 and verify the confirmation code." ;;
    *) note "Next: check the error above, configuration file permissions and required tools." ;;
  esac >&2
  if [ "${CMAIL_DNS_CHECKPOINT:-0}" = 1 ]; then
    note "Nameserver step was reached; delegation may already have changed. No rollback was attempted." >&2
  else
    note "This run has not attempted a nameserver update. Earlier resources/configuration may have been saved." >&2
  fi
  note "After fixing the cause, rerun ./cmail setup. Use ./cmail status to inspect saved Cloudflare state; never share .env or tokens." >&2
}
