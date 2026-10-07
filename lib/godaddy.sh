# godaddy.sh — gddy auth + domain + nameserver helpers
# shellcheck shell=bash



gddy_ensure_auth() { # OAuth browser login if no valid credential for env
  step "GoDaddy authentication ($GDDY_ENV)"
  if [ -n "${GDDY_PAT:-}" ]; then ok "GDDY_PAT set — using PAT"; return 0; fi
  local expired
  expired=$(gddy auth status --json 2>/dev/null \
    | jq -r --arg e "$GDDY_ENV" '[.data[] | select(.env==$e and .expired==false)] | length' || echo 0)
  if ! [[ "$expired" =~ ^[1-9][0-9]*$ ]]; then
    log "no valid credential — starting OAuth (a browser window will open)"
    gddy auth login --env "$GDDY_ENV" || die "gddy auth login failed — check network/browser access and the correct GoDaddy account; retry gddy auth login --env $GDDY_ENV, then re-run ./cmail setup. If using a PAT, renew/recreate it for $GDDY_ENV and update GDDY_PAT privately (never paste it into logs)"
  fi
  ok "gddy authenticated"
}

gddy_pick_domain() { # sets DOMAIN (and saves to .env)
  step "Choose domain"
  if [ -n "${DOMAIN:-}" ]; then ok "DOMAIN=$DOMAIN (from .env)"; return 0; fi
  local domains
  domains=$(gddy domain list --env "$GDDY_ENV" --json 2>/dev/null) \
    || die "could not list GoDaddy domains — check network, account access and gddy auth login --env $GDDY_ENV; renew GDDY_PAT privately if used. Check domains in the GoDaddy dashboard or run gddy domain list --env $GDDY_ENV --json, then re-run ./cmail setup"
  domains=$(jq -er 'if (.data | type) == "array" then [.data[] | (.domain // .name // empty)] | sort | join("\n") else error("invalid domain list") end' <<<"$domains" 2>/dev/null) \
    || die "could not read GoDaddy domain list — check gddy domain list --env $GDDY_ENV --json and your GoDaddy dashboard; update gddy if its response format changed, then re-run ./cmail setup"
  if [ -n "$domains" ]; then
    printf 'Your GoDaddy domains:\n  - %s\n' "${domains//$'\n'/$'\n  - '}"
    echo "  - (type any other name to register a new one)"
  fi
  local val
  printf '%s ?%s domain to use: ' "$C_YELLOW" "$C_OFF"
  read -r val || die "domain input unavailable — run ./cmail setup in an interactive terminal, or set DOMAIN in your private config"
  [ -n "$val" ] || die "domain required — set DOMAIN in your private config or enter a domain when re-running ./cmail setup"
  if ! grep -qx "$val" <<<"$domains"; then gddy_maybe_register "$val"; fi
  env_set DOMAIN "$val"
}

gddy_maybe_register() { # offer to register the domain if not owned
  local d="$1"
  gddy domain get "$d" --env "$GDDY_ENV" >/dev/null 2>&1 && return 0
  warn "could not confirm $d in your GoDaddy account — check the dashboard, network and authentication before considering a purchase"
  gddy domain available "$d" --env "$GDDY_ENV" \
    || die "could not check availability for $d — check network, gddy auth login --env $GDDY_ENV and the GoDaddy dashboard, then re-run ./cmail setup; do not purchase until ownership/availability is clear"
  confirm "attempt registration via gddy now? (charges your GoDaddy account)" \
    || die "registration declined — check whether you already own $d in GoDaddy; register it if needed, then set DOMAIN and re-run ./cmail setup"
  gddy domain quote "$d" --env "$GDDY_ENV" \
    || die "quote failed — check network, authentication for $GDDY_ENV and domain availability. Check GoDaddy orders and domain ownership before retrying any purchase; once resolved, re-run ./cmail setup"
  confirm "confirm purchase of $d at the quoted price" \
    || die "purchase declined — no purchase requested; check GoDaddy orders/domain ownership, then re-run ./cmail setup when ready"
  gddy domain purchase "$d" --env "$GDDY_ENV" \
    || die "purchase failed — the outcome may be uncertain; check GoDaddy orders, billing and domain ownership BEFORE retrying purchase to avoid duplicate charges. Check network/authentication for $GDDY_ENV; if purchased, set DOMAIN and re-run ./cmail setup; otherwise resolve the order or contact GoDaddy support first"
  ok "registered $d"
}

gddy_set_nameservers() { # gddy_set_nameservers ns1 ns2 ...
  step "GoDaddy: point $DOMAIN nameservers at Cloudflare"
  local args=() n current desired
  for n in "$@"; do args+=(--nameserver "$n"); done

  current=$(gddy domain get "$DOMAIN" --env "$GDDY_ENV" --json) \
    || die "could not verify current nameservers — no change applied; check network, account access and gddy auth login --env $GDDY_ENV. Check GoDaddy dashboard > domain > DNS > Nameservers, or gddy domain get $DOMAIN --env $GDDY_ENV --json, then re-run ./cmail setup"
  current=$(jq -ce '
    .data.nameServers
    | if type == "array" and length > 0
         and all(.[]; type == "string" and length > 0)
      then map(ascii_downcase | sub("\\.$"; "")) | unique
      else error("missing or invalid nameservers") end
  ' <<<"$current" 2>/dev/null) || die "could not read current nameservers — no change applied; inspect GoDaddy dashboard > domain > DNS > Nameservers, or gddy domain get $DOMAIN --env $GDDY_ENV --json. Check/update gddy for response-format issues, then re-run ./cmail setup"
  desired=$(jq -cn --args '$ARGS.positional | map(ascii_downcase | sub("\\.$"; "")) | unique' "$@")
  if [ "$current" = "$desired" ]; then
    ok "nameservers already point at Cloudflare: $* — skipping update"
    return 0
  fi

  note "current nameservers: $current"
  note "desired nameservers: $desired"
  warn "this replaces ALL nameservers for $DOMAIN — copy existing DNS records (web, mail/MX, TXT and other services) to Cloudflare first or those services may break"
  if [ "${DRY_RUN:-0}" = "1" ]; then
    gddy domain nameservers set "${args[@]}" "$DOMAIN" --env "$GDDY_ENV" --dry-run \
      || die "nameserver preview failed — check account permissions, network and gddy auth login --env $GDDY_ENV; inspect GoDaddy dashboard > domain > DNS > Nameservers or gddy domain get $DOMAIN --env $GDDY_ENV --json, then re-run ./cmail setup with DRY_RUN=1"
    return
  fi
  confirm "apply nameserver change" \
    || die "aborted before nameserver change — migrate existing DNS records to Cloudflare, then re-run ./cmail setup when ready"
  gddy domain nameservers set "${args[@]}" "$DOMAIN" --env "$GDDY_ENV" \
    || die "nameserver update failed — it may still have applied; check GoDaddy dashboard > domain > DNS > Nameservers or gddy domain get $DOMAIN --env $GDDY_ENV --json against the desired nameservers above. Check network/authentication and domain permissions/locks; once resolved, re-run ./cmail setup (matching nameservers skip the write)"
  ok "nameservers set: $* (change submitted) — allow DNS propagation; verify in the GoDaddy dashboard or with gddy domain get $DOMAIN --env $GDDY_ENV --json"
}
