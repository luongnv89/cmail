#compdef cmail
# Save as _cmail in a directory on fpath before running compinit.
local cur="${words[CURRENT]}" prev='' word command='' sub='' skip=0 ended=0 i args=0
local -a choices flags
flags=(--help --version --config --format --verbose --quiet --no-color --no-browser --timeout -h -V -c -f -v -q)
(( CURRENT <= 1 )) || prev="${words[CURRENT-1]}"
case "$prev" in
  -c|--config) _files; return ;;
  -f|--format) choices=(text json); compadd -a choices; return ;;
  --registrar) choices=(manual godaddy); compadd -a choices; return ;;
  --domain|--destination|--addresses|--timeout|--wait-timeout) return ;;
esac
for ((i=2; i<CURRENT; i++)); do
  word="${words[i]}"
  if (( skip )); then skip=0; continue; fi
  if (( ! ended )); then
    case "$word" in
      --) ended=1; continue ;;
      -c|--config|-f|--format|--timeout|--domain|--destination|--addresses|--registrar|--wait-timeout) skip=1; continue ;;
      -*) continue ;;
    esac
  fi
  if [[ -z "$command" ]]; then command="$word"
  elif [[ "$command" == config && -z "$sub" ]]; then sub="$word"
  else (( args++ )); fi
 done
case "$command" in setup) flags+=(--domain --destination --addresses --registrar --dry-run --wait-timeout) ;; doctor) flags+=(--offline) ;; list) flags+=(--domain) ;; esac
[[ "$command $sub" != 'config set' ]] || flags+=(--stdin)
if [[ "$cur" == -* ]] && (( ! ended )); then
  compadd -a flags
else
  case "$command $sub" in
    ' '|'help ') choices=(setup status list doctor send-as config completion help) ;;
    'config ') choices=(init show check set path) ;;
    'config set') (( args )) || choices=(DOMAIN DEST_EMAIL ADDRESSES REGISTRAR GDDY_ENV CF_ZONE_ID CF_ACCOUNT_ID DRY_RUN CLOUDFLARE_API_TOKEN GDDY_PAT) ;;
    'completion ') (( args )) || choices=(bash zsh fish) ;;
  esac
  (( ${#choices} == 0 )) || compadd -a choices
fi
