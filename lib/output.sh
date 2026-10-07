# shellcheck shell=bash
# Result rendering is separate from UI diagnostics.
output_require_json() { command -v jq >/dev/null || die 'jq is required for JSON output; install jq and check PATH'; }
output_envelope() { output_require_json; jq -nc --arg command "$1" --argjson data "$2" '{schema_version:1,command:$command,data:$data}'; }
output_checks_start() { CHECK_NAMES=() CHECK_STATES=() CHECK_MESSAGES=() CHECK_NEXT=(); }
output_check() { CHECK_NAMES+=("$1"); CHECK_STATES+=("$2"); CHECK_MESSAGES+=("$3"); CHECK_NEXT+=("${4:-}"); }
output_checks() {
  local command="$1" i checks='[]' state
  if [ "$CMAIL_FORMAT" = json ]; then
    output_require_json
    for ((i=0; i<${#CHECK_NAMES[@]}; i++)); do
      checks=$(jq -nc --argjson checks "$checks" --arg name "${CHECK_NAMES[i]}" --arg state "${CHECK_STATES[i]}" \
        --arg message "${CHECK_MESSAGES[i]}" --arg next "${CHECK_NEXT[i]}" \
        '$checks + [{name:$name,state:$state,message:$message,next:$next}]')
    done
    output_envelope "$command" "$(jq -nc --argjson checks "$checks" '{checks:$checks}')"
  else
    for ((i=0; i<${#CHECK_NAMES[@]}; i++)); do
      state="${CHECK_STATES[i]}"
      printf '%-5s %s\n' "$(printf '%s' "$state" | tr '[:lower:]' '[:upper:]')" "${CHECK_MESSAGES[i]}"
      [ -z "${CHECK_NEXT[i]}" ] || printf '      Next: %s\n' "${CHECK_NEXT[i]}"
    done
  fi
}
output_elapsed() {
  local seconds="$1"
  local unit=seconds
  [ "$seconds" != 1 ] || unit=second
  printf '%sm %ss (%s %s)' "$((seconds / 60))" "$((seconds % 60))" "$seconds" "$unit"
}
