# godaddy.sh — gddy auth + domain + nameserver helpers
# shellcheck shell=bash

GDDY_ENV="${GDDY_ENV:-prod}"

gddy_ensure_auth() { # OAuth browser login if no valid credential for env
  step "GoDaddy authentication ($GDDY_ENV)"
  if [ -n "${GDDY_PAT:-}" ]; then ok "GDDY_PAT set — using PAT"; return 0; fi
  local expired
  expired=$(gddy auth status --json 2>/dev/null \
    | jq -r --arg e "$GDDY_ENV" '[.data[] | select(.env==$e and .expired==false)] | length' || echo 0)
  if [ "$expired" = "0" ]; then
    log "no valid credential — starting OAuth (a browser window will open)"
    gddy auth login --env "$GDDY_ENV" || die "gddy auth login failed"
  fi
  ok "gddy authenticated"
}

gddy_pick_domain() { # sets DOMAIN (and saves to .env)
  step "Choose domain"
  if [ -n "${DOMAIN:-}" ]; then ok "DOMAIN=$DOMAIN (from .env)"; return 0; fi
  local domains
  domains=$(gddy domain list --env "$GDDY_ENV" --json 2>/dev/null \
    | jq -r '.data[]? | (.domain // .name // empty)' | sort)
  if [ -n "$domains" ]; then
    echo "Your GoDaddy domains:"; echo "$domains" | sed 's/^/  - /'
    echo "  - (type any other name to register a new one)"
  fi
  local val
  printf '%s ?%s domain to use: ' "$C_YELLOW" "$C_OFF"; read -r val
  [ -n "$val" ] || die "domain required"
  if ! grep -qx "$val" <<<"$domains"; then gddy_maybe_register "$val"; fi
  env_set DOMAIN "$val"
}

gddy_maybe_register() { # offer to register the domain if not owned
  local d="$1"
  gddy domain get "$d" --env "$GDDY_ENV" >/dev/null 2>&1 && return 0
  warn "$d not in your GoDaddy account"
  gddy domain available "$d" --env "$GDDY_ENV" || true
  confirm "attempt registration via gddy now? (charges your GoDaddy account)" \
    || die "register $d first, then re-run setup"
  gddy domain quote "$d" --env "$GDDY_ENV" || die "quote failed"
  confirm "confirm purchase of $d at the quoted price" || die "aborted"
  gddy domain purchase "$d" --env "$GDDY_ENV" || die "purchase failed"
  ok "registered $d"
}

gddy_set_nameservers() { # gddy_set_nameservers ns1 ns2 ...
  step "GoDaddy: point $DOMAIN nameservers at Cloudflare"
  local args=() n
  for n in "$@"; do args+=(--nameserver "$n"); done
  if [ "${DRY_RUN:-0}" = "1" ]; then
    gddy domain nameservers set "${args[@]}" "$DOMAIN" --env "$GDDY_ENV" --dry-run; return
  fi
  warn "this replaces ALL nameservers for $DOMAIN"
  confirm "apply nameserver change" || die "aborted before nameserver change"
  gddy domain nameservers set "${args[@]}" "$DOMAIN" --env "$GDDY_ENV" \
    || die "nameserver update failed"
  ok "nameservers set: $*"
}
