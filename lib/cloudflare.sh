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
  local resp state
  while :; do
    if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
      resp=$(cf_routing_request GET '/user/tokens/verify') || return 1
      state=$(jq -er '.result.status | select(type == "string" and length > 0)' <<<"$resp") \
        || die "Cloudflare returned no token status — check https://www.cloudflarestatus.com/ before replacing credentials"
      [ "$state" != active ] || break
      warn "token is '$state' — create an active replacement token"
    fi
    cat >&2 <<EOF
Cloudflare has no self-service OAuth for scripts — a scoped API token is
needed once. Create it now (browser will open):

  1. "Create token" -> "Custom token" -> "Get started"
  2. Permissions (five rows):
       Zone  | Zone                 | Edit
       Zone  | Zone Settings        | Edit
       Zone  | DNS                  | Edit
       Zone  | Email Routing Rules  | Edit
       Account | Email Routing Addresses | Edit
  3. Zone Resources: Include -> All zones from an account -> <your account>
     (or "All zones" if you only have one account)
     Account Resources: Include -> <the account that owns your domain>
  4. Create token, copy it, paste below (input hidden).

EOF
    open_url "https://dash.cloudflare.com/profile/api-tokens"
    local tok
    printf '%s ?%s paste Cloudflare API token: ' "$C_YELLOW" "$C_OFF" >&2
    read -rs tok || die "no token input — run ./cmail setup in an interactive terminal or set CLOUDFLARE_API_TOKEN in .env"
    printf '\n' >&2
    [ -n "$tok" ] || die "token required — create a custom API token at https://dash.cloudflare.com/profile/api-tokens and rerun ./cmail setup"
    CLOUDFLARE_API_TOKEN="$tok"
  done
  env_set CLOUDFLARE_API_TOKEN "$CLOUDFLARE_API_TOKEN"
  ok "Cloudflare token verified and saved to .env"
  note "Token is active; account/zone permissions are checked by the following steps."
}

cf_zone_ensure() { # sets globals CF_ZONE_ID and CF_NS
  step "Cloudflare zone: $DOMAIN"
  local resp
  resp=$(cf_routing_request GET "/zones?name=$DOMAIN") || return 1
  jq -e '.result | type == "array"' >/dev/null <<<"$resp" \
    || die "Cloudflare returned an invalid zone list — no zone created or nameservers changed"
  CF_ZONE_ID=$(jq -r '.result[0].id // empty' <<<"$resp")
  if [ -z "$CF_ZONE_ID" ]; then
    local acct="${CF_ACCOUNT_ID:-}" count
    if [ -z "$acct" ]; then
      resp=$(cf_routing_request GET '/accounts') || return 1
      jq -e '.result | type == "array"' >/dev/null <<<"$resp" \
        || die "Cloudflare returned an invalid account list — no zone created or nameservers changed"
      count=$(jq '.result | length' <<<"$resp")
      if [ "$count" = 0 ]; then
        cf_account_recovery
        die "no Cloudflare account visible to token — no zone created or nameservers changed"
      elif [ "$count" -gt 1 ]; then
        warn "multiple Cloudflare accounts visible; refusing to choose one automatically" >&2
        jq -r '.result[] | "  \(.name): \(.id)"' <<<"$resp" >&2
        cf_account_recovery
        die "set CF_ACCOUNT_ID to the intended account — no zone created or nameservers changed"
      fi
      acct=$(jq -er '.result[0].id | select(type == "string" and length > 0)' <<<"$resp") \
        || die "Cloudflare account has no valid ID — no zone created or nameservers changed"
    fi
    [[ "$acct" =~ ^[[:xdigit:]]{32}$ ]] \
      || die "CF_ACCOUNT_ID must be the 32-character account ID from the Cloudflare dashboard, not the account name"
    log "creating zone $DOMAIN in account $acct"
    resp=$(cf_routing_request POST '/zones' \
      -d "$(jq -nc --arg name "$DOMAIN" --arg account "$acct" '{name:$name,account:{id:$account}}')") || return 1
    CF_ZONE_ID=$(jq -er '.result.id | select(type == "string" and length > 0)' <<<"$resp") \
      || die "Cloudflare did not confirm zone creation — check the dashboard before retrying"
  else
    ok "zone already exists"
  fi
  resp=$(cf_routing_request GET "/zones/$CF_ZONE_ID") || return 1
  local nameservers
  nameservers=$(jq -er '.result.name_servers | select(type == "array" and length >= 2 and all(.[]; type == "string" and length > 0)) | .[]' <<<"$resp") \
    || die "Cloudflare returned no valid nameservers — open the domain Overview in Cloudflare; no GoDaddy nameserver change applied"
  CF_NS=(); while IFS= read -r n; do CF_NS+=("$n"); done <<<"$nameservers"
  ok "zone $CF_ZONE_ID — nameservers: ${CF_NS[*]}"
}

cf_zone_wait_active() { # $1 = zone_id
  step "Waiting for zone activation (nameserver propagation)"
  local status=""
  for _ in $(seq 1 60); do
    local resp
    resp=$(cf_routing_request GET "/zones/$1") || return 1
    status=$(jq -er '.result.status | select(type == "string" and length > 0)' <<<"$resp") \
      || die "Cloudflare returned no zone status — check the domain Overview in the dashboard"
    case "$status" in
      active|pending|initializing) ;;
      *) die "zone status '$status' needs attention — open the domain Overview in Cloudflare before retrying" ;;
    esac
    [ "$status" = "active" ] && { ok "zone active"; return 0; }
    printf '  status: %s — retrying in 20s\n' "$status"
    sleep 20
  done
  die "zone still '$status' after about 20 minutes — compare GoDaddy DNS > Nameservers with Cloudflare Overview nameservers (${CF_NS[*]:-see dashboard}). Propagation can take 24–48 hours; rerun ./cmail setup once Cloudflare shows Active. Nameservers may already have changed; no rollback was attempted"
}

cf_account_recovery() {
  cat >&2 <<EOF
To unlock account discovery:
  1. Open https://dash.cloudflare.com/profile/api-tokens and edit your token.
     An active token is not proof of account/zone access. Under Account Resources,
     include the account that owns $DOMAIN; under Zone Resources, include that
     account's zones (including $DOMAIN if it already exists).
     Zone creation needs Zone > Zone > Edit. Destination registration needs
     Account > Email Routing Addresses > Edit.
  2. Open https://dash.cloudflare.com/ and select the intended account/domain.
     Copy its Account ID (not Zone ID) from the dashboard and add this to .env:
       CF_ACCOUNT_ID=<32-character account ID>
     This skips account listing; it does NOT grant zone read/create permissions.
     If the domain already exists but was not found, fix its token scope first.
  3. If you create a replacement token, update CLOUDFLARE_API_TOKEN in .env
     locally (do not share it), then rerun ./cmail setup.
EOF
}

# Shared request diagnostics for zone, account, and routing operations.
cf_routing_request() { # method, API path, optional curl arguments
  local method="$1" path="$2" response status body detail code
  shift 2
  if response=$(curl -sS -X "$method" \
      -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
      -H "Content-Type: application/json" \
      -w $'\n%{http_code}' "$CF_API$path" "$@"); then
    status="${response##*$'\n'}"
    body="${response%$'\n'*}"
  else
    code=$?
    warn "check your connection, DNS, proxy and https://www.cloudflarestatus.com/; this is not evidence of an invalid token" >&2
    [ "$method" = GET ] || warn "the write outcome is unknown — inspect the Cloudflare dashboard before retrying" >&2
    die "Cloudflare request failed: $method $path (curl exit $code)"
  fi
  if [[ "$status" != 2[0-9][0-9] ]] || ! cf_ok "$body"; then
    detail=$(jq -ce '.errors // .' <<<"$body" 2>/dev/null) \
      || detail="non-JSON response: ${body:0:500}"
    [ -n "$body" ] || detail="empty response body"
    detail="${detail//"$CLOUDFLARE_API_TOKEN"/[redacted]}"
    detail="${detail:0:1000}"
    if [ "$status" = "401" ] || [ "$status" = "403" ]; then
      case "$path" in
        /accounts/*/email/routing/addresses*)
          warn "check token access to this account and grant Account > Email Routing Addresses > Edit" >&2 ;;
        /zones/*/email/routing/rules*)
          warn "check token access to this zone and grant Zone > Email Routing Rules > Edit" >&2 ;;
        /zones/*/email/routing*)
          warn "check token access to this zone and grant Zone > Zone Settings > Edit" >&2 ;;
        /accounts|/accounts\?*) cf_account_recovery ;;
        /zones|/zones\?*|/zones/*)
          warn "check Zone Resources includes ${DOMAIN:-your domain} (or its account's zones for creation); grant Zone > Zone > Edit" >&2 ;;
        /user/tokens/verify)
          warn "token rejected: replace CLOUDFLARE_API_TOKEN in .env with an active API token from https://dash.cloudflare.com/profile/api-tokens" >&2 ;;
        *) warn "check token resource access and permissions for $path" >&2 ;;
      esac
    fi
    case "$path" in
      /zones/*/email/routing/dns)
        warn "open Cloudflare > ${DOMAIN:-your domain} > Email > Email Routing; check conflicting MX/TXT records. Do not delete an existing mail provider's records without planning the migration" >&2 ;;
    esac
    if [ "$status" = "429" ]; then
      warn "Cloudflare rate limit reached — wait before rerunning ./cmail setup" >&2
    elif [[ "$status" = 5[0-9][0-9] ]]; then
      warn "Cloudflare service error — check https://www.cloudflarestatus.com/ and retry later; inspect the dashboard first if a write was attempted" >&2
    fi
    die "Cloudflare API error: $method $path (HTTP $status): $detail"
  fi
  printf '%s\n' "$body"
}

cf_email_enable() {
  step "Enable Cloudflare Email Routing"
  local resp enabled
  resp=$(cf_routing_request GET "/zones/$1/email/routing") || return 1
  enabled=$(jq -er '.result.enabled | select(type == "boolean") | tostring' <<<"$resp") \
    || die "Cloudflare Email Routing settings missing a valid enabled state — no change applied"
  if [ "$enabled" = "true" ]; then
    ok "email routing already enabled"
    return 0
  fi
  # https://developers.cloudflare.com/api/resources/email_routing/subresources/dns/methods/create/
  resp=$(cf_routing_request POST "/zones/$1/email/routing/dns" -d '{}') || return 1
  jq -e '.result.enabled == true' >/dev/null 2>&1 <<<"$resp" \
    || die "Cloudflare did not confirm Email Routing is enabled — check the zone in the dashboard"
  ok "email routing enabled (Cloudflare routing DNS records added and locked)"
}

cf_account_for_zone() { # $1 = zone_id; never assume the first account owns it
  local resp account
  resp=$(cf_routing_request GET "/zones/$1") || return 1
  account=$(jq -er '.result.account.id | select(type == "string" and length > 0)' <<<"$resp") \
    || die "Cloudflare zone is missing its account ID — no destination change applied"
  printf '%s\n' "$account"
}

cf_addresses_list() { # $1 = account_id; returns an array across all pages
  local resp records='[]' page=1 pages count batch
  while :; do
    [ "$page" -le 1000 ] || die "destination listing exceeded 1000 pages — no complete result available"
    resp=$(cf_routing_request GET "/accounts/$1/email/routing/addresses?per_page=50&page=$page") || return 1
    batch=$(jq -ce '
      .result | if type == "array" and all(.[];
        (.email | type == "string" and length > 0) and
        (.verified == null or (.verified | type == "string" and length > 0)))
      then . else error("invalid destination addresses") end
    ' <<<"$resp") || die "Cloudflare returned invalid destination addresses"
    records=$(jq -cn --argjson a "$records" --argjson b "$batch" '$a + $b') || return 1
    count=$(jq 'length' <<<"$batch")
    # If pagination metadata is omitted, keep reading full pages.
    pages=$(jq -er --argjson page "$page" --argjson count "$count" '
      .result_info.total_pages as $total
      | (if $total == null then (if $count == 50 then $page + 1 else $page end) else $total end)
      | select(type == "number" and . >= 0 and . == floor)
    ' <<<"$resp") || die "Cloudflare returned invalid destination pagination"
    [ "$page" -lt "$pages" ] || break
    page=$((page + 1))
  done
  printf '%s\n' "$records"
}

cf_dest_ensure() { # $1 = zone_id — waits for user to click verification email
  step "Destination address: $DEST_EMAIL"
  local account destinations destination resp verified
  account=$(cf_account_for_zone "$1") || return 1
  destinations=$(cf_addresses_list "$account") || return 1
  destination=$(jq -c --arg e "$DEST_EMAIL" '[.[] | select(.email == $e)][0] // empty' <<<"$destinations")
  if [ -z "$destination" ]; then
    resp=$(cf_routing_request POST "/accounts/$account/email/routing/addresses" \
      -d "$(jq -nc --arg e "$DEST_EMAIL" '{email:$e}')") || return 1
    destination=$(jq -ce --arg e "$DEST_EMAIL" '
      .result | select(.email == $e and
        (.verified == null or (.verified | type == "string" and length > 0)))
    ' <<<"$resp") || die "Cloudflare did not confirm destination registration"
    warn "verification email sent to $DEST_EMAIL — click the Cloudflare link"
  elif ! jq -e '.verified != null' >/dev/null <<<"$destination"; then
    warn "$DEST_EMAIL already registered but unverified — click the existing Cloudflare verification email"
  fi
  verified=$(jq -r '.verified // empty' <<<"$destination")
  if [ -z "$verified" ]; then
    note "Sign into $DEST_EMAIL in Gmail and check Inbox and Spam for Cloudflare's verification link."
    note "Missing or expired link? Open Cloudflare > ${DOMAIN:-your domain} > Email > Email Routing > Destination addresses and resend verification."
    open_url "https://mail.google.com/"
    for _ in $(seq 1 40); do
      sleep 15
      destinations=$(cf_addresses_list "$account") || return 1
      verified=$(jq -r --arg e "$DEST_EMAIL" '.[] | select(.email == $e) | .verified // empty' <<<"$destinations")
      [ -n "$verified" ] && break
      printf '  still unverified — waiting (click the email link)…\n'
    done
    [ -n "$verified" ] || die "$DEST_EMAIL not verified after about 10 minutes — check Inbox/Spam in the correct Gmail account, resend an expired/missing link from Cloudflare Email Routing > Destination addresses, then rerun ./cmail setup after clicking it. The pending destination is kept"
  fi
  ok "$DEST_EMAIL verified"
}

cf_rules_ensure() { # $1 = zone_id — create forwarding rules for $ADDRESSES
  step "Forwarding addresses ($ADDRESSES -> $DEST_EMAIL)"
  local rules prio=0 a addr payload list=()
  rules=$(cf_routing_request GET "/zones/$1/email/routing/rules") || return 1
  jq -e '.result | type == "array"' >/dev/null 2>&1 <<<"$rules" \
    || die "Cloudflare returned invalid forwarding rules — no change applied"
  IFS=',' read -ra list <<<"$ADDRESSES"
  for a in "${list[@]}"; do
    a="${a// /}"; addr="$a@$DOMAIN"
    if jq -e --arg v "$addr" '.result[].matchers[]? | select(.value==$v)' \
        <<<"$rules" >/dev/null 2>&1; then
      if ! jq -e --arg v "$addr" --arg dest "$DEST_EMAIL" '
        [.result[] | select(any(.matchers[]?; .value == $v))] as $matches
        | ($matches | length) == 1 and ($matches[0] |
          .enabled == true and .matchers == [{type:"literal",field:"to",value:$v}]
          and .actions == [{type:"forward",value:[$dest]}])
      ' <<<"$rules" >/dev/null 2>&1; then
        die "$addr has an existing disabled, conflicting, or different forwarding rule — open Cloudflare > $DOMAIN > Email > Email Routing > Routing rules and enable/correct it to forward to $DEST_EMAIL, then rerun ./cmail setup. Existing rules were not overwritten"
      fi
      ok "$addr already exists"; continue
    fi
    payload=$(jq -nc \
      --arg name "fwd $addr" --arg to "$addr" --arg dest "$DEST_EMAIL" \
      --argjson p "$prio" \
      '{name:$name, enabled:true, priority:$p,
        matchers:[{type:"literal", field:"to", value:$to}],
        actions:[{type:"forward", value:[$dest]}]}') \
      || die "could not build forwarding rule for $addr — no request sent"
    cf_routing_request POST "/zones/$1/email/routing/rules" -d "$payload" >/dev/null || return 1
    rules=$(jq -c --argjson rule "$payload" '.result += [$rule]' <<<"$rules") || return 1
    ok "$addr -> $DEST_EMAIL"
    prio=$((prio+1))
  done
}

cf_status() { # $1 = zone_id — print current routing state
  local resp account
  account=$(cf_account_for_zone "$1") || return 1
  resp=$(cf_routing_request GET "/zones/$1") || return 1
  printf 'zone status     : %s\n' "$(jq -r '.result.status' <<<"$resp")"
  resp=$(cf_routing_request GET "/zones/$1/email/routing") || return 1
  printf 'email routing   : %s\n' "$(jq -r '.result.status // "?"' <<<"$resp")"
  resp=$(cf_addresses_list "$account") || return 1
  printf 'destinations    :\n'; jq -r '.[] | "  - \(.email)  verified=\(.verified // "no")"' <<<"$resp"
  resp=$(cf_routing_request GET "/zones/$1/email/routing/rules") || return 1
  printf 'rules           :\n'; jq -r '.result[]? | "  - \(.matchers[0].value) -> \(.actions[0].value[0])  [\(.enabled)]"' <<<"$resp"
}
