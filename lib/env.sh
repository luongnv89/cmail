# env.sh — .env load / save
# shellcheck shell=bash

ENV_FILE="${ENV_FILE:-$CMAIL_DIR/.env}"

env_init() {
  if [ ! -f "$ENV_FILE" ]; then
    cp "$CMAIL_DIR/.env.example" "$ENV_FILE" 2>/dev/null \
      || die "could not create config at $ENV_FILE — check the template exists and the parent directory is writable; create a private config from .env.example, then re-run ./cmail setup"
    log "created $ENV_FILE"
  fi
  chmod 600 "$ENV_FILE" 2>/dev/null \
    || die "could not secure config at $ENV_FILE — check file ownership/permissions, set chmod 600, then re-run ./cmail setup"
  if [ ! -r "$ENV_FILE" ] || ! bash -n "$ENV_FILE" >/dev/null 2>&1; then
    die "could not read or parse config at $ENV_FILE — check read permissions and shell assignment syntax (quote values with spaces); correct it locally without sharing secrets, then re-run ./cmail setup"
  fi
  local load_status=0 restore_errexit=0
  case "$-" in *e*) restore_errexit=1 ;; esac
  # Bash 3.2 may exit on a failing sourced command even inside an if condition.
  # Disable errexit explicitly so the contextual error can be shown privately.
  set +e
  set -a
  # shellcheck source=/dev/null
  . "$ENV_FILE" >/dev/null 2>&1 || load_status=$?
  set +a
  [ "$restore_errexit" = 0 ] || set -e
  [ "$load_status" = 0 ] \
    || die "could not load config at $ENV_FILE — check shell assignments locally without sharing secrets, then re-run ./cmail setup"
}

env_set() { # env_set KEY value — upsert into .env
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    # avoid leaking values into sed's argv on some platforms; use tmp file
    local tmp; tmp=$(mktemp) \
      || die "could not prepare config update — check temporary-directory permissions and disk space, then re-run ./cmail setup"
    if ! { { grep -v "^${key}=" "$ENV_FILE" || [ "$?" = 1 ]; } > "$tmp" \
      && printf '%s=%q\n' "$key" "$val" >> "$tmp" \
      && mv "$tmp" "$ENV_FILE"; }; then
      rm -f "$tmp"
      die "could not save $key in config — check file/directory permissions and disk space, then re-run ./cmail setup; do not share secret values"
    fi
  else
    printf '%s=%q\n' "$key" "$val" >> "$ENV_FILE" \
      || die "could not save $key in config — check file permissions and disk space, then re-run ./cmail setup; do not share secret values"
  fi
  chmod 600 "$ENV_FILE" 2>/dev/null \
    || die "could not secure saved config — check ownership and set chmod 600 before re-running ./cmail setup"
  printf -v "$key" '%s' "$val"
}

env_require_prompt() { # env_require_prompt KEY "prompt text" [--secret]
  local key="$1" prompt="$2" secret="${3:-}"
  local cur; cur="${!key:-}"
  [ -n "$cur" ] && return 0
  local val
  if [ "$secret" = "--secret" ]; then
    printf '%s ?%s %s: ' "$C_YELLOW" "$C_OFF" "$prompt" >&2
    read -rs val || { printf '\n' >&2; die "$key input unavailable — run ./cmail setup in an interactive terminal, or set $key in your private config first"; }
    printf '\n' >&2
  else
    printf '%s ?%s %s: ' "$C_YELLOW" "$C_OFF" "$prompt" >&2
    read -r val || die "$key input unavailable — run ./cmail setup in an interactive terminal, or set $key in your private config first"
  fi
  [ -n "$val" ] || die "$key is required — enter a non-empty value when re-running ./cmail setup, or set $key in your private config first; do not share secret values"
  env_set "$key" "$val"
}
