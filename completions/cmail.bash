# cmail bash completion. Source this file; it never reads configuration.
# shellcheck shell=bash disable=SC2034
_cmail_complete() {
  local cur="${COMP_WORDS[COMP_CWORD]}" prev='' word command='' sub='' skip=0 ended=0 i candidate choices=''
  local args=0 flags='--help --version --config --format --verbose --quiet --no-color --no-browser --timeout -h -V -c -f -v -q'
  COMPREPLY=()
  [ "$COMP_CWORD" = 0 ] || prev="${COMP_WORDS[COMP_CWORD-1]}"
  case "$prev" in
    -c|--config) while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -f -- "$cur"); return 0 ;;
    -f|--format) choices='text json' ;;
    --registrar) choices='manual godaddy' ;;
    --domain|--destination|--addresses|--timeout|--wait-timeout) return 0 ;;
  esac
  if [ -z "$choices" ]; then
    for ((i=1; i<COMP_CWORD; i++)); do
      word="${COMP_WORDS[i]}"
      if [ "$skip" = 1 ]; then skip=0; continue; fi
      if [ "$ended" = 0 ]; then
        case "$word" in
          --) ended=1; continue ;;
          -c|--config|-f|--format|--timeout|--domain|--destination|--addresses|--registrar|--wait-timeout) skip=1; continue ;;
          -*) continue ;;
        esac
      fi
      if [ -z "$command" ]; then command="$word"
      elif [ "$command" = config ] && [ -z "$sub" ]; then sub="$word"
      else args=$((args + 1)); fi
    done
    case "$command" in setup) flags="$flags --domain --destination --addresses --registrar --dry-run --wait-timeout" ;; doctor) flags="$flags --offline" ;; esac
    [ "$command $sub" != 'config set' ] || flags="$flags --stdin"
    if [[ "$cur" = -* ]] && [ "$ended" = 0 ]; then choices="$flags"
    else
      case "$command $sub" in
        ' '|'help ') choices='setup status doctor send-as config completion help' ;;
        'config ') choices='init show check set path' ;;
        'config set') [ "$args" != 0 ] || choices='DOMAIN DEST_EMAIL ADDRESSES REGISTRAR GDDY_ENV CF_ZONE_ID CF_ACCOUNT_ID DRY_RUN CLOUDFLARE_API_TOKEN GDDY_PAT' ;;
        'completion ') [ "$args" != 0 ] || choices='bash zsh fish' ;;
      esac
    fi
  fi
  while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -W "$choices" -- "$cur")
  return 0
}
complete -F _cmail_complete cmail
