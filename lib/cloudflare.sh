# cloudflare.sh — Cloudflare REST API helpers (Email Routing)
# shellcheck shell=bash

CF_API="https://api.cloudflare.com/client/v4"

cf() {
  curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
       -H "Content-Type: application/json" "$@"
}

cf_ok() { jq -e '.success == true' >/dev/null 2>&1 <<<"$1"; }
cf_fail() { die "Cloudflare API error: $(jq -c '.errors // .' <<<"$1")"; }

cf_token_valid() {
  [ -n "${CLOUDFLARE_API_TOKEN:-}" ] || return 1
  curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    "$CF_API/user/tokens/verify" 2>/dev/null \
    | jq -e '.result.status == "active"' >/dev/null 2>&1
}

cf_ensure_token() {
  step "Cloudflare API token"
  while ! cf_token_valid; do
    cat >&2 <<EOF
Cloudflare has no self-service OAuth for scripts — a scoped API token is
needed once. Create it now (browser will open):

  1. "Create token" -> "Custom token" -> "Get started"
  2. Permissions (three rows):
       Zone  | Zone                 | Edit
       Zone  | DNS                  | Edit
       Zone  | Email Routing Rules  | Edit
  3. Zone Resources: Include -> All zones from an account -> <your account>
     (or "All zones" if you only have one account)
  4. Create token, copy it, paste below (input hidden).

EOF
    open_url "https://dash.cloudflare.com/profile/api-tokens"
    local tok
    printf '%s ?%s paste Cloudflare API token: ' "$C_YELLOW" "$C_OFF" >&2
    read -rs tok; printf '\n' >&2
    [ -n "$tok" ] || die "token required"
    CLOUDFLARE_API_TOKEN="$tok"
    cf_token_valid || warn "token rejected — check it and try again"
  done
  env_set CLOUDFLARE_API_TOKEN "$CLOUDFLARE_API_TOKEN"
  ok "Cloudflare token verified and saved to .env"
}

cf_zone_ensure() { # sets globals CF_ZONE_ID and CF_NS
  step "Cloudflare zone: $DOMAIN"
  local resp
  resp=$(cf "$CF_API/zones?name=$DOMAIN")
  cf_ok "$resp" || cf_fail "$resp"
  CF_ZONE_ID=$(jq -r '.result[0].id // empty' <<<"$resp")
  if [ -z "$CF_ZONE_ID" ]; then
    local acct
    acct=$(cf "$CF_API/accounts" | jq -r '.result[0].id // empty')
    [ -n "$acct" ] || die "no Cloudflare account visible to token — grant Account access"
    log "creating zone $DOMAIN"
    resp=$(cf -X POST "$CF_API/zones" \
      -d "{\"name\":\"$DOMAIN\",\"account\":{\"id\":\"$acct\"}}")
    cf_ok "$resp" || die "zone create failed (needs Account->Zone->Edit): $(jq -c '.errors' <<<"$resp")"
    CF_ZONE_ID=$(jq -r '.result.id' <<<"$resp")
  else
    ok "zone already exists"
  fi
  resp=$(cf "$CF_API/zones/$CF_ZONE_ID"); cf_ok "$resp" || cf_fail "$resp"
  CF_NS=(); while IFS= read -r n; do CF_NS+=("$n"); done \
    < <(jq -r '.result.name_servers[]' <<<"$resp")
  [ "${#CF_NS[@]}" -ge 2 ] || die "Cloudflare returned no nameservers"
  ok "zone $CF_ZONE_ID — nameservers: ${CF_NS[*]}"
}

cf_zone_wait_active() { # $1 = zone_id
  step "Waiting for zone activation (nameserver propagation)"
  local status=""
  for _ in $(seq 1 60); do
    status=$(cf "$CF_API/zones/$1" | jq -r '.result.status' 2>/dev/null || echo "?")
    [ "$status" = "active" ] && { ok "zone active"; return 0; }
    printf '  status: %s — retrying in 20s\n' "$status"
    sleep 20
  done
  die "zone still '$status' — check $DOMAIN nameservers at GoDaddy, then re-run"
}

cf_email_enable() {
  step "Enable Cloudflare Email Routing"
  local resp
  resp=$(cf -X POST "$CF_API/zones/$1/email/routing/enable" -d '{}' 2>/dev/null || true)
  if cf_ok "$resp"; then ok "email routing enabled (MX/SPF/DKIM/DMARC auto-created)"
  elif jq -e '.errors[0].message | test("already"; "i")' <<<"${resp:-{}}" >/dev/null 2>&1; then
    ok "email routing already enabled"
  else cf_fail "$resp"; fi
}

cf_dest_ensure() { # $1 = zone_id — waits for user to click verification email
  step "Destination address: $DEST_EMAIL"
  local verified
  verified=$(cf "$CF_API/zones/$1/email/routing/addresses" \
    | jq -r --arg e "$DEST_EMAIL" '.result[] | select(.email==$e) | .verified // empty')
  if [ -z "$verified" ]; then
    cf -X POST "$CF_API/zones/$1/email/routing/addresses" \
      -d "{\"email\":\"$DEST_EMAIL\"}" >/dev/null 2>&1 || true
    warn "verification email sent to $DEST_EMAIL — click the Cloudflare link"
    open_url "https://mail.google.com/"
    for _ in $(seq 1 40); do
      sleep 15
      verified=$(cf "$CF_API/zones/$1/email/routing/addresses" \
        | jq -r --arg e "$DEST_EMAIL" '.result[] | select(.email==$e) | .verified // empty')
      [ -n "$verified" ] && break
      printf '  still unverified — waiting (click the email link)…\n'
    done
    [ -n "$verified" ] || die "$DEST_EMAIL not verified — re-run setup after clicking the link"
  fi
  ok "$DEST_EMAIL verified"
}

cf_rules_ensure() { # $1 = zone_id — create forwarding rules for $ADDRESSES
  step "Forwarding addresses ($ADDRESSES -> $DEST_EMAIL)"
  local rules prio=0 a addr resp
  rules=$(cf "$CF_API/zones/$1/email/routing/rules"); cf_ok "$rules" || cf_fail "$rules"
  IFS=',' read -ra list <<<"$ADDRESSES"
  for a in "${list[@]}"; do
    a="${a// /}"; addr="$a@$DOMAIN"
    if jq -e --arg v "$addr" '.result[].matchers[]? | select(.value==$v)' \
        <<<"$rules" >/dev/null 2>&1; then
      ok "$addr already exists"; continue
    fi
    resp=$(cf -X POST "$CF_API/zones/$1/email/routing/rules" -d "$(jq -nc \
      --arg name "fwd $addr" --arg to "$addr" --arg dest "$DEST_EMAIL" \
      --argjson p "$prio" \
      '{name:$name, enabled:true, priority:$p,
        matchers:[{type:"literal", field:"to", value:$to}],
        actions:[{type:"forward", value:[$dest}]}')")
    cf_ok "$resp" || cf_fail "$resp"
    ok "$addr -> $DEST_EMAIL"
    prio=$((prio+1))
  done
}

cf_status() { # $1 = zone_id — print current routing state
  local resp
  resp=$(cf "$CF_API/zones/$1")
  printf 'zone status     : %s\n' "$(jq -r '.result.status' <<<"$resp")"
  resp=$(cf "$CF_API/zones/$1/email/routing")
  printf 'email routing   : %s\n' "$(jq -r '.result.status // "?"' <<<"$resp")"
  resp=$(cf "$CF_API/zones/$1/email/routing/addresses")
  printf 'destinations    :\n'; jq -r '.result[]? | "  - \(.email)  verified=\(.verified // "no")' <<<"$resp"
  resp=$(cf "$CF_API/zones/$1/email/routing/rules")
  printf 'rules           :\n'; jq -r '.result[]? | "  - \(.matchers[0].value) -> \(.actions[0].value[0])  [\(.enabled)]"' <<<"$resp"
}
