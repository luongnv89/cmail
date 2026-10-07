# shellcheck shell=bash
# Literal configuration. Never source or evaluate user content.
# shellcheck disable=SC2034
ENV_FILE="${CLI_CONFIG:-${CMAIL_CONFIG:-${ENV_FILE:-$CMAIL_DIR/.env}}}"
case "$ENV_FILE" in /*) ;; *) ENV_FILE="$PWD/$ENV_FILE" ;; esac
CMAIL_CONFIG_KEYS=(DOMAIN DEST_EMAIL ADDRESSES CLOUDFLARE_API_TOKEN GDDY_ENV GDDY_PAT CF_ZONE_ID CF_ACCOUNT_ID DRY_RUN)
CONFIG_KEYS=() CONFIG_VALUES=()

config_key_valid() {
  case "$1" in DOMAIN|DEST_EMAIL|ADDRESSES|CLOUDFLARE_API_TOKEN|GDDY_ENV|GDDY_PAT|CF_ZONE_ID|CF_ACCOUNT_ID|DRY_RUN) return 0 ;; *) return 1 ;; esac
}
config_secret() { case "$1" in CLOUDFLARE_API_TOKEN|GDDY_PAT) return 0 ;; *) return 1 ;; esac; }
config_error() { printf 'cmail: %s; correct the private config locally (cmail config --help).\n' "$*" >&2; return 3; }

config_literal() { # raw assignment word -> CONFIG_LITERAL (no evaluation)
  local raw="$1" number="$2" state='' char next i=0 result='' LC_ALL=C
  while [ "$i" -lt "${#raw}" ]; do
    char="${raw:i:1}"; i=$((i + 1))
    [[ "$char" = [[:print:]] || "$char" = $'\t' ]] || { config_error "line $number: unsupported character"; return 3; }
    if [ "$state" = single ]; then
      if [ "$char" = "'" ]; then state=''; else result="$result$char"; fi
      continue
    fi
    case "$char" in
      "\\")
        [ "$i" -lt "${#raw}" ] || { config_error "line $number: dangling escape"; return 3; }
        next="${raw:i:1}"; i=$((i + 1))
        [[ "$next" = [[:print:]] || "$next" = $'\t' ]] || { config_error "line $number: unsupported character"; return 3; }
        if [ "$state" = double ]; then
          case "$next" in "\\"|'"'|'$'|'`') ;; *) result="$result\\" ;; esac
        fi
        result="$result$next" ;;
      '"') if [ "$state" = double ]; then state=''; else state=double; fi ;;
      "'") if [ "$state" = double ]; then result="$result$char"; else state=single; fi ;;
      '$'|'`') config_error "line $number: expansions/commands are not allowed; use literal KEY=value assignments"; return 3 ;;
      *)
        if [ -z "$state" ]; then
          case "$char" in ' '|$'\t'|';'|'&'|'|'|'<'|'>'|'('|')'|'~'|'*'|'?'|'['|']'|'{'|'}')
            config_error "line $number: quote spaces and remove shell syntax; use literal KEY=value assignments"; return 3 ;;
          esac
        fi
        result="$result$char" ;;
    esac
  done
  [ -z "$state" ] || { config_error "line $number: invalid quoting; check shell assignment syntax"; return 3; }
  CONFIG_LITERAL="$result"
}

config_read() {
  CONFIG_KEYS=() CONFIG_VALUES=()
  if ! { [ ! -L "$ENV_FILE" ] && [ -f "$ENV_FILE" ] && [ -O "$ENV_FILE" ] && [ -r "$ENV_FILE" ]; }; then
    config_error 'selected config must be a readable user-owned regular file, not a symlink'; return 3
  fi
  local mode size clean line key raw number=0 seen='|' LC_ALL=C
  mode=$(stat -f %Lp "$ENV_FILE" 2>/dev/null) || mode=$(stat -c %a "$ENV_FILE")
  [ "$mode" = 600 ] || { config_error 'selected config must have mode 600 (chmod 600 on the selected file)'; return 3; }
  size=$(wc -c < "$ENV_FILE")
  [ "$size" -le 65536 ] || { config_error 'selected config exceeds 64 KiB'; return 3; }
  clean=$(tr -d '\000' < "$ENV_FILE" | wc -c)
  [ "$size" = "$clean" ] || { config_error 'selected config contains unsupported controls'; return 3; }
  while IFS= read -r line || [ -n "$line" ]; do
    number=$((number + 1))
    [[ "${line//$'\t'/}" != *[[:cntrl:]]* ]] || { config_error "line $number: unsupported controls"; return 3; }
    # Trim only ASCII spaces/tabs, including around comments and assignments.
    line="${line#"${line%%[!$' \t']*}"}"
    line="${line%"${line##*[!$' \t']}"}"
    case "$line" in ''|'#'*) continue ;; esac
    [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]] || { config_error "line $number: use NAME=value, no spaces around '='"; return 3; }
    key="${BASH_REMATCH[1]}" raw="${BASH_REMATCH[2]}"
    config_key_valid "$key" || { config_error "line $number: unsupported key"; return 3; }
    case "$seen" in *"|$key|"*) config_error "line $number: duplicate $key assignment"; return 3 ;; esac
    config_literal "$raw" "$number" || return 3
    seen="$seen$key|"
    CONFIG_KEYS+=("$key"); CONFIG_VALUES+=("$CONFIG_LITERAL")
  done < "$ENV_FILE"
}

config_domain_valid() {
  local value="$1" label rest="$1" LC_ALL=C
  [ "${#value}" -le 253 ] && [[ "$value" = *.* ]] && [[ "$value" != *. ]] || return 1
  while [ -n "$rest" ]; do
    label="${rest%%.*}"
    [[ "$label" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]] && [ "${#label}" -le 63 ] || return 1
    [ "$label" != "$rest" ] || break
    rest="${rest#*.}"
  done
  [[ "$label" =~ ^[A-Za-z]{2,63}$ ]]
}
config_local_valid() { local LC_ALL=C; [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$ ]]; }
config_field_valid() {
  local key="$1" value="$2" item list=() seen='|' LC_ALL=C
  case "$key" in
    DOMAIN) config_domain_valid "$value" ;;
    DEST_EMAIL) [[ "$value" = *@* ]] && config_local_valid "${value%%@*}" && config_domain_valid "${value#*@}" ;;
    ADDRESSES)
      [[ "$value" != ,* && "$value" != *, && "$value" != *,,* ]] || return 1
      IFS=',' read -ra list <<< "$value"
      [ "${#list[@]}" -gt 0 ] || return 1
      for item in "${list[@]}"; do
        item="${item#"${item%%[! ]*}"}"; item="${item%"${item##*[! ]}"}"
        config_local_valid "$item" || return 1
        case "$seen" in *"|$item|"*) return 1 ;; esac
        seen="$seen$item|"
      done ;;
    GDDY_ENV) [ "$value" = prod ] || [ "$value" = ote ] ;;
    CF_ACCOUNT_ID|CF_ZONE_ID) [[ "$value" =~ ^[[:xdigit:]]{32}$ ]] ;;
    DRY_RUN) [ "$value" = 0 ] || [ "$value" = 1 ] ;;
    CLOUDFLARE_API_TOKEN|GDDY_PAT) [[ "$value" != *[![:print:]]* ]] ;;
    *) return 1 ;;
  esac
}
config_validate() { # allow empty fields while setup collects input
  local key value
  for key in "${CMAIL_CONFIG_KEYS[@]}"; do
    value="${!key:-}"
    if [ -n "$value" ] && ! config_field_valid "$key" "$value"; then
      config_error "$key has an invalid value"; return 3
    fi
  done
}
config_ready() {
  local key
  config_validate || return 3
  for key in DOMAIN DEST_EMAIL ADDRESSES CLOUDFLARE_API_TOKEN GDDY_ENV; do
    [ -n "${!key:-}" ] || { config_error "$key is required"; return 3; }
  done
}
config_load() { # preserve environment over file, even explicit empty overrides
  local i key file_domain=''
  if [ -e "$ENV_FILE" ] || [ -L "$ENV_FILE" ]; then
    config_read || return 3
    for ((i=0; i<${#CONFIG_KEYS[@]}; i++)); do
      key="${CONFIG_KEYS[i]}"
      [ "$key" != DOMAIN ] || file_domain="${CONFIG_VALUES[i]}"
      if [ -z "${!key+x}" ]; then printf -v "$key" '%s' "${CONFIG_VALUES[i]}"; fi
    done
  fi
  GDDY_ENV="${GDDY_ENV-prod}" ADDRESSES="${ADDRESSES-hello}" DRY_RUN="${DRY_RUN-0}"
  [ -z "${CLI_DOMAIN:-}" ] || DOMAIN="$CLI_DOMAIN"
  [ -z "${CLI_DESTINATION:-}" ] || DEST_EMAIL="$CLI_DESTINATION"
  [ -z "${CLI_ADDRESSES:-}" ] || ADDRESSES="$CLI_ADDRESSES"
  # A domain override must never reuse a zone ID belonging to the saved domain.
  if [ -n "${DOMAIN:-}" ]; then DOMAIN=$(printf '%s' "$DOMAIN" | tr '[:upper:]' '[:lower:]'); fi
  file_domain=$(printf '%s' "$file_domain" | tr '[:upper:]' '[:lower:]')
  if [ -n "$file_domain" ] && [ "${DOMAIN:-}" != "$file_domain" ]; then CF_ZONE_ID=''; fi
  config_validate || return 3
  export GDDY_ENV
  [ -z "${GDDY_PAT:-}" ] || export GDDY_PAT
}

env_init() { # setup-only creation and permission repair
  if [ ! -e "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ]; then
    (umask 077; set -o noclobber; cat "$CMAIL_DIR/.env.example" > "$ENV_FILE") 2>/dev/null \
      || die "could not create config at $ENV_FILE — check the template exists and the parent directory is writable; create a private config from .env.example, then re-run ./cmail setup"
    log "created $ENV_FILE"
  fi
  if ! { [ ! -L "$ENV_FILE" ] && [ -f "$ENV_FILE" ] && [ -O "$ENV_FILE" ]; }; then
    die 'config must be a user-owned regular file, not a symlink'
  fi
  chmod 600 "$ENV_FILE" 2>/dev/null \
    || die "could not secure config at $ENV_FILE — check file ownership/permissions, set chmod 600, then re-run ./cmail setup"
  config_load || { printf 'cmail: could not load config; use literal NAME=value assignments and valid shell assignment syntax, without sharing secrets; re-run ./cmail setup.\n' >&2; return 3; }
}

env_set() { # atomic same-directory update, never print values
  local key="$1" value="$2" tmp quoted='' line char j
  if ! config_key_valid "$key" || { [ -n "$value" ] && ! config_field_valid "$key" "$value"; }; then config_error 'invalid configuration update'; return 3; fi
  if [ "$key" = DOMAIN ] && [ "${DOMAIN:-}" != "$value" ]; then
    env_set CF_ZONE_ID '' || return 3
  fi
  config_read || { config_error "could not save $key; check file permissions"; return 3; }
  tmp=$(mktemp "${ENV_FILE%/*}/.cmail-config.XXXXXXXX") || die 'could not prepare config update; check directory permissions and disk space'
  for ((j=0; j<${#value}; j++)); do
    char="${value:j:1}"
    if [ "$char" = "'" ]; then quoted="$quoted'\\''"; else quoted="$quoted$char"; fi
  done
  if ! {
    # Keep comments and unchanged settings, replacing only the selected key.
    while IFS= read -r line || [ -n "$line" ]; do
      [[ "$line" =~ ^[[:blank:]]*$key= ]] || printf '%s\n' "$line"
    done < "$ENV_FILE"
    printf "%s='%s'\n" "$key" "$quoted"
  } > "$tmp" || ! chmod 600 "$tmp" || ! mv -f "$tmp" "$ENV_FILE"; then
    rm -f "$tmp"
    die "could not save $key in config — check file/directory permissions and disk space, then re-run ./cmail setup; do not share secret values"
  fi
  printf -v "$key" '%s' "$value"
}

env_require_prompt() {
  local key="$1" prompt="$2" secret="${3:-}" val
  [ -z "${!key:-}" ] || return 0
  printf '%s ?%s %s: ' "$C_YELLOW" "$C_OFF" "$prompt" >&2
  if [ "$secret" = --secret ]; then
    read -rs val || { printf '\n' >&2; die "$key input unavailable — run ./cmail setup in an interactive terminal, or set $key in your private config first"; }
    printf '\n' >&2
  else
    read -r val || die "$key input unavailable — run ./cmail setup in an interactive terminal, or set $key in your private config first"
  fi
  [ -n "$val" ] || die "$key is required — enter a non-empty value when re-running ./cmail setup, or set $key in your private config first; do not share secret values"
  env_set "$key" "$val"
}

config_init() {
  if [ -e "$ENV_FILE" ] || [ -L "$ENV_FILE" ]; then
    config_read || return 3
    printf 'Configuration already exists: %s\n' "$ENV_FILE"
    return 0
  fi
  local parent="${ENV_FILE%/*}"
  [ ! -L "$parent" ] || { config_error 'configuration parent must not be a symlink'; return 3; }
  (umask 077; mkdir -p "$parent") || die 'could not create configuration directory; check permissions'
  (umask 077; set -o noclobber; cat "$CMAIL_DIR/.env.example" > "$ENV_FILE") 2>/dev/null \
    || die 'could not create configuration; check the selected path and directory permissions'
  printf 'Created private configuration: %s\nNext: cmail setup\n' "$ENV_FILE"
}

config_public_value() {
  local key="$1" value="${!1:-}" token
  # Long opaque aliases may be misplaced tokens; display only their state.
  if [ "$key" = ADDRESSES ] && [[ "$value" =~ [A-Za-z0-9_+-]{32,} ]]; then value='<redacted>'; fi
  for token in "${CLOUDFLARE_API_TOKEN:-}" "${GDDY_PAT:-}"; do
    if [ -n "$token" ] && [[ "$value" = *"$token"* ]]; then value='<redacted>'; fi
  done
  CONFIG_PUBLIC_VALUE="$value"
}
config_show() {
  config_load || return 3
  local key state settings='{}' secrets='{}'
  [ "$CMAIL_FORMAT" != json ] || output_require_json
  [ "$CMAIL_FORMAT" != text ] || printf 'Config: %s\n' "$ENV_FILE"
  for key in "${CMAIL_CONFIG_KEYS[@]}"; do
    if config_secret "$key"; then
      if [ -n "${!key:-}" ]; then state='set'; else state=empty; fi
      if [ "$CMAIL_FORMAT" = json ]; then secrets=$(jq -nc --argjson current "$secrets" --arg key "$key" --arg state "$state" '$current+{($key):$state}')
      else printf '%-22s %s\n' "$key" "$state"; fi
    else
      config_public_value "$key"
      if [ "$CMAIL_FORMAT" = json ]; then settings=$(jq -nc --argjson current "$settings" --arg key "$key" --arg value "$CONFIG_PUBLIC_VALUE" '$current+{($key):$value}')
      else printf '%-22s %s\n' "$key" "$CONFIG_PUBLIC_VALUE"; fi
    fi
  done
  if [ "$CMAIL_FORMAT" = json ]; then
    output_envelope 'config show' "$(jq -nc --arg path "$ENV_FILE" --argjson settings "$settings" --argjson secrets "$secrets" '{path:$path,settings:$settings,secrets:$secrets}')"
  fi
}
config_check() {
  local code=0
  output_checks_start
  if config_load && config_ready; then
    output_check config pass 'configuration ready' 'Use cmail setup --dry-run to inspect provider state.'
  else
    output_check config fail 'configuration invalid or incomplete' 'Correct the fields reported on stderr, then rerun cmail config check.'
    code=3
  fi
  output_checks 'config check'
  return "$code"
}
config_set_command() {
  local key="${CLI_ARGS[0]}" value='' read_status=0 LC_ALL=C
  config_key_valid "$key" || cli_error 'unknown setting; see cmail config set --help'
  if config_secret "$key" && [ "$CLI_STDIN" = 0 ]; then cli_error 'secret settings require --stdin; pipe from a private source, never pass a token as an argument'; fi
  if [ "$CLI_STDIN" = 1 ]; then
    [ ! -t 0 ] || cli_error '--stdin needs piped input or a private file; use setup for hidden terminal token entry'
    # Read to EOF, a NUL, or the size cap. Unlike command substitution this
    # detects NUL without silently discarding it. Only one trailing LF is allowed.
    IFS= read -r -d '' -n 4098 value || read_status=$?
    if [ "$read_status" = 0 ] || [ "${#value}" -ge 4098 ]; then
      config_error 'stdin must contain one value, without NUL, at most 4096 bytes'; return 3
    fi
    value="${value%$'\n'}"
  else value="${CLI_ARGS[1]}"; fi
  [ "${#value}" -le 4096 ] || { config_error 'value exceeds 4096 bytes'; return 3; }
  if [ -n "$value" ] && ! config_field_valid "$key" "$value"; then config_error "$key has invalid input"; return 3; fi
  env_set "$key" "$value" || return 3
  printf 'Updated %s (value hidden).\n' "$key"
}
cmd_config() {
  case "$CLI_SUBCOMMAND" in
    init) config_init ;; show) config_show ;; check) config_check ;;
    set) config_set_command ;; path) printf '%s\n' "$ENV_FILE" ;;
  esac
}
