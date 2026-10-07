# shellcheck shell=bash
# Read-only setup planning. No authentication, writes, prompts, or browser calls.
plan_action() {
  PLAN_ACTIONS=$(jq -nc --argjson actions "$PLAN_ACTIONS" --arg name "$1" --arg state "$2" \
    --arg message "$3" --arg next "${4:-}" '$actions+[{name:$name,state:$state,message:$message,next:$next}]')
}
plan_account() {
  local resp count
  if [ -n "${CF_ACCOUNT_ID:-}" ]; then PLAN_ACCOUNT="$CF_ACCOUNT_ID"; return 0; fi
  resp=$(cf_routing_request GET /accounts) || return 1
  count=$(jq -er '.result | select(type=="array") | length' <<< "$resp") || die 'Cloudflare returned invalid accounts'
  if [ "$count" != 1 ]; then
    plan_action account blocked 'Select the intended Cloudflare account.' 'Set CF_ACCOUNT_ID from the dashboard; token resource access still applies.'
    return 0
  fi
  PLAN_ACCOUNT=$(jq -er '.result[0].id | select(type=="string" and length>0)' <<< "$resp") || die 'Cloudflare account ID missing'
}
cmd_setup_plan() {
  ensure_read_tools
  config_ready || return 3
  PLAN_ACTIONS='[]' PLAN_ACCOUNT=''
  local resp zone zone_id='' zone_state='' desired='[]' current='[]' destinations='[]' rules='[]' enabled=false
  local addr alias_list=() matches verified data token_state
  plan_action config planned 'Setup will save explicit settings and discovered resource IDs in private configuration.'
  resp=$(cf_routing_request GET /user/tokens/verify) || return 1
  token_state=$(jq -er '.result.status | select(type=="string")' <<< "$resp") || die 'Cloudflare token status missing'
  [ "$token_state" = active ] || die 'Cloudflare token is not active; replace it locally before setup'
  plan_action cloudflare ready 'Cloudflare token active; read access is checked below.'
  # gddy can automatically start OAuth even during reads when scopes are missing.
  # A supplied PAT prevents that flow. Otherwise report the delegation check as
  # blocked rather than invoking a command that could launch a browser or save tokens.
  if [ -n "${GDDY_PAT:-}" ]; then
    type -P gddy >/dev/null || die 'gddy missing; install it before checking GoDaddy domain access'
    if resp=$(gddy domain get "$DOMAIN" --env "$GDDY_ENV" --json 2>/dev/null); then
      current=$(jq -ce '.data.nameServers | select(type=="array" and length>0 and all(.[]; type=="string" and length>0)) | map(ascii_downcase | sub("\\.$";"")) | unique | sort' <<< "$resp") \
        || die 'GoDaddy returned invalid nameservers; check domain access'
      plan_action godaddy ready 'GoDaddy domain ownership and nameservers readable.'
    else
      plan_action godaddy blocked 'GoDaddy domain ownership could not be verified.' 'Check the account, domain ownership, PAT, and connectivity; preview never purchases domains.'
    fi
  else
    plan_action godaddy blocked 'GoDaddy delegation check requires an existing PAT for a guaranteed read-only preview.' 'Set GDDY_PAT privately, or check current nameservers in the dashboard. Guided setup supports browser OAuth.'
  fi
  resp=$(cf_routing_request GET "/zones?name=$DOMAIN") || return 1
  zone=$(jq -ce --arg domain "$DOMAIN" '.result | if type=="array" then [.[] | select(.name==$domain)] else error("invalid zone list") end | if length<=1 then .[0] // {} else error("ambiguous zones") end' <<< "$resp") \
    || die 'Cloudflare returned an invalid or ambiguous zone list'
  zone_id=$(jq -r '.id // empty' <<< "$zone")
  if [ -n "$zone_id" ]; then
    resp=$(cf_routing_request GET "/zones/$zone_id") || return 1
    zone=$(jq -ce --arg domain "$DOMAIN" '.result | select(.name==$domain and (.status|type=="string") and (.account.id|type=="string" and length>0))' <<< "$resp") \
      || die 'Cloudflare zone does not match DOMAIN or returned malformed data'
    PLAN_ACCOUNT=$(jq -r '.account.id' <<< "$zone")
    desired=$(jq -ce '.name_servers | select(type=="array" and length>=2 and all(.[]; type=="string" and length>0)) | map(ascii_downcase | sub("\\.$";"")) | unique | sort' <<< "$zone") \
      || die 'Cloudflare assigned nameservers missing'
    zone_state=$(jq -r '.status' <<< "$zone")
    plan_action zone ready 'Reuse the existing Cloudflare zone.'
    resp=$(cf_routing_request GET "/zones/$zone_id/email/routing") || return 1
    enabled=$(jq -er '.result.enabled | select(type=="boolean") | tostring' <<< "$resp") || die 'Cloudflare returned invalid Email Routing state'
    rules=$(cf_rules_list "$zone_id") || return 1
  else
    plan_account || return 1
    plan_action zone planned 'Create a Cloudflare zone and fetch its assigned nameservers.'
  fi
  if [ "$desired" != '[]' ] && [ "$current" = "$desired" ]; then
    plan_action nameservers ready 'Delegation already matches Cloudflare; skip the update.'
  else
    plan_action nameservers confirmation 'Review existing DNS records, then confirm the full nameserver replacement if needed.' 'Migrate web, MX, TXT, DNSSEC, and other service records before changing delegation.'
  fi
  if [ "$zone_state" = active ]; then plan_action activation ready 'Zone currently active; setup rechecks activation after delegation.'
  else plan_action activation wait 'Wait for Cloudflare zone activation after delegation.'; fi
  if [ "$enabled" = true ]; then plan_action routing ready 'Email Routing enabled; skip activation.'
  else plan_action routing planned 'Enable Email Routing after reviewing existing mail DNS records.'; fi
  if [ -n "$PLAN_ACCOUNT" ]; then
    destinations=$(cf_addresses_list "$PLAN_ACCOUNT") || return 1
    verified=$(jq -r --arg email "$DEST_EMAIL" '[.[] | select(.email==$email)][0].verified // empty' <<< "$destinations")
    if [ -n "$verified" ]; then plan_action destination ready 'Destination already verified.'
    elif jq -e --arg email "$DEST_EMAIL" 'any(.[]; .email==$email)' >/dev/null <<< "$destinations"; then
      plan_action destination manual 'Reuse the pending destination; wait for its verification link.' 'Click the Cloudflare link in the receiving inbox.'
    else plan_action destination manual 'Register the destination; wait for its verification link.' 'Click the Cloudflare link in the receiving inbox.'; fi
  else
    plan_action destination blocked 'Destination registration cannot be inspected until the account is selected.' 'Set CF_ACCOUNT_ID and rerun the preview.'
  fi
  IFS=',' read -ra alias_list <<< "$ADDRESSES"
  for addr in "${alias_list[@]}"; do
    addr="${addr// /}@$DOMAIN"
    matches=$(jq -c --arg addr "$addr" '[.[] | select(any(.matchers[]?; .value==$addr))]' <<< "$rules")
    if [ "$matches" = '[]' ]; then
      plan_action "$addr" planned "Create forwarding to $DEST_EMAIL."
    elif jq -e --arg addr "$addr" --arg dest "$DEST_EMAIL" 'length==1 and (.[0] | .enabled==true and .matchers==[{type:"literal",field:"to",value:$addr}] and .actions==[{type:"forward",value:[$dest]}])' >/dev/null <<< "$matches"; then
      plan_action "$addr" ready 'Existing enabled forwarding rule matches; skip creation.'
    else
      plan_action "$addr" blocked 'An existing disabled or conflicting rule requires attention.' 'Enable/correct the rule in Cloudflare; setup never overwrites conflicting rules.'
    fi
  done
  plan_action delivery manual 'Send from a different mailbox to verify receiving after setup.'
  data=$(jq -nc --arg domain "$DOMAIN" --arg destination "$DEST_EMAIL" --argjson actions "$PLAN_ACTIONS" \
    --argjson elapsed "$((SECONDS - CMAIL_SETUP_STARTED))" '{dry_run:true,domain:$domain,destination:$destination,actions:$actions,
    blockers:[$actions[] | select(.state=="blocked") | .message],elapsed_seconds:$elapsed}')
  if [ "$CMAIL_FORMAT" = json ]; then output_envelope setup "$data"
  else
    printf 'Read-only setup plan for %s\n' "$DOMAIN"
    jq -r '.actions[] | "  [\(.state)] \(.name): \(.message)" + (if .next=="" then "" else "\n    Next: "+.next end)' <<< "$data"
    printf '\nElapsed time: '; output_elapsed "$((SECONDS - CMAIL_SETUP_STARTED))"; printf '\n'
  fi
}
