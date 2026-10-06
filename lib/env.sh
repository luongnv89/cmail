# env.sh — .env load / save
# shellcheck shell=bash

ENV_FILE="${ENV_FILE:-$SMAIL_DIR/.env}"

env_init() {
  if [ ! -f "$ENV_FILE" ]; then
    cp "$SMAIL_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log "created $ENV_FILE (chmod 600)"
  fi
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  set -a; . "$ENV_FILE"; set +a
}

env_set() { # env_set KEY value — upsert into .env
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    # avoid leaking values into sed's argv on some platforms; use tmp file
    local tmp; tmp=$(mktemp)
    grep -v "^${key}=" "$ENV_FILE" > "$tmp"
    printf '%s=%s\n' "$key" "$val" >> "$tmp"
    mv "$tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
  printf -v "$key" '%s' "$val"
}

env_require_prompt() { # env_require_prompt KEY "prompt text" [--secret]
  local key="$1" prompt="$2" secret="${3:-}"
  local cur; cur="${!key:-}"
  [ -n "$cur" ] && return 0
  local val
  if [ "$secret" = "--secret" ]; then
    printf '%s ?%s %s: ' "$C_YELLOW" "$C_OFF" "$prompt" >&2
    read -rs val; printf '\n' >&2
  else
    printf '%s ?%s %s: ' "$C_YELLOW" "$C_OFF" "$prompt" >&2
    read -r val
  fi
  [ -n "$val" ] || die "$key is required"
  env_set "$key" "$val"
}
