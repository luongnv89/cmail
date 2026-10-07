# shellcheck shell=bash
# Variables are the public interface consumed by the orchestrator.
# shellcheck disable=SC2034
# Parse before configuration, dependency checks, or provider access.
cli_error() { printf 'cmail: %s\nTry: cmail %s --help\n' "$1" "${CLI_COMMAND:-}" >&2; exit 2; }

cli_help() {
  local topic="${1:-}"
  case "$topic" in
    '')
      cat <<'EOF'
cmail — free custom-domain email with Cloudflare Email Routing
Usage: cmail [options] COMMAND [options]

Commands:
  setup                 Configure receiving with a guided workflow
  status                Inspect zone, routing, destinations, and rules
  doctor                Check dependencies, configuration, and authentication
  send-as               Optional Gmail sending guide: ./cmail send-as
  config                Manage private configuration
  completion SHELL      Print bash, zsh, or fish completions
  help [COMMAND...]     Show command-specific help

Start here:
  cmail config init
  cmail doctor --offline
  cmail setup
EOF
      ;;
    setup)
      cat <<'EOF'
Usage: cmail setup [options]
Configure receiving. Run in a terminal; purchases and nameserver changes require confirmation.
  --domain DOMAIN          Domain name (default: DOMAIN setting)
  --destination EMAIL      Receiving inbox (default: DEST_EMAIL setting)
  --addresses LIST         Unique comma-separated local parts (default: ADDRESSES setting)
  --dry-run                Read-only plan; requires existing credentials, never writes
  --wait-timeout SECONDS   Limit each activation/verification wait (default: 1200)
Elapsed time includes user input, provider requests, and verification waits.
EOF
      ;;
    status) printf '%s\n' 'Usage: cmail status [options]' 'Read-only Cloudflare zone, routing, destination, and rule report.' 'Use --format json for scripts.' ;;
    doctor) printf '%s\n' 'Usage: cmail doctor [--offline] [options]' 'Read-only dependency/configuration/authentication checks. Never installs tools.' '  --offline    Check local tools and configuration without contacting providers' ;;
    send-as) printf '%s\n' 'Usage: cmail send-as [options]' 'Optional manual Gmail sending guide. Requires a terminal and configured receiving.' ;;
    config) printf '%s\n' 'Usage: cmail config COMMAND [options]' 'Commands: init, show, check, set KEY [VALUE], path' 'Use cmail config COMMAND --help for details.' ;;
    'config init') printf '%s\n' 'Usage: cmail config init [options]' 'Create a private mode-600 template; preserve an existing configuration.' ;;
    'config show') printf '%s\n' 'Usage: cmail config show [options]' 'Show effective public settings and secret presence, never secret values.' ;;
    'config check') printf '%s\n' 'Usage: cmail config check [options]' 'Check required settings and readiness; incomplete/invalid input exits 3.' ;;
    'config path') printf '%s\n' 'Usage: cmail config path [options]' 'Print the selected configuration path without creating it.' ;;
    'config set') printf '%s\n' 'Usage: cmail config set KEY [VALUE] [--stdin] [options]' 'Update one documented setting atomically. Secret keys require --stdin.' '  KEY        DOMAIN, DEST_EMAIL, ADDRESSES, GDDY_ENV, CF_ACCOUNT_ID, CF_ZONE_ID,' '             DRY_RUN, CLOUDFLARE_API_TOKEN, or GDDY_PAT' '  VALUE      Literal value; mutually exclusive with --stdin' '  --stdin    Read one value from standard input without echoing it' ;;
    completion) printf '%s\n' 'Usage: cmail completion SHELL' 'SHELL is required: bash, zsh, or fish. Prints a completion script.' ;;
    help) printf '%s\n' 'Usage: cmail help [COMMAND...]' 'Show help, e.g. cmail help config set.' ;;
    *) cli_error "unknown help topic '$topic'" ;;
  esac
  cat <<'EOF'

Options (before or after the command):
  -h, --help              Show this help and exit
  -V, --version           Print version and exit
  -c, --config PATH       Select private configuration (CMAIL_CONFIG, ENV_FILE, then default)
  -f, --format text|json  Report format (default: CMAIL_FORMAT or text)
  -v, --verbose           Additional redacted diagnostics
  -q, --quiet             Suppress routine progress; retain results and errors
  --no-color             Disable color (also respects NO_COLOR)
  --no-browser           Print links for manual opening
  --timeout SECONDS      HTTP request timeout (default: CMAIL_TIMEOUT or 30)
Use -- to end option parsing. Invalid arguments exit 2; invalid input exits 3.
EOF
}

cli_parse() {
  CLI_COMMAND='' CLI_SUBCOMMAND='' CLI_ARGS=()
  CMAIL_FORMAT="${CMAIL_FORMAT:-text}"
  CMAIL_TIMEOUT="${CMAIL_TIMEOUT:-30}"
  CMAIL_VERBOSE="${CMAIL_VERBOSE:-0}" CMAIL_QUIET="${CMAIL_QUIET:-0}"
  CMAIL_NO_COLOR=0 CMAIL_NO_BROWSER=0 CMAIL_OFFLINE=0 CMAIL_DRY_RUN=0
  CMAIL_WAIT_TIMEOUT=1200 CLI_CONFIG='' CLI_DOMAIN='' CLI_DESTINATION='' CLI_ADDRESSES=''
  CLI_STDIN=0 CLI_HELP=0 CLI_VERSION=0 CLI_SETUP_OPTIONS=0
  local arg option value end=0 positionals=()
  while [ "$#" -gt 0 ]; do
    arg="$1"; shift
    if [ "$end" = 1 ]; then positionals+=("$arg"); continue; fi
    option="${arg%%=*}"
    case "$option" in --domain|--destination|--addresses|--wait-timeout) CLI_SETUP_OPTIONS=1 ;; esac
    case "$option" in
      --) [ "$arg" = -- ] || cli_error "unknown option '$arg'"; end=1 ;;
      -h|--help|-V|--version|-v|--verbose|-q|--quiet|--no-color|--no-browser|--offline|--dry-run|--stdin)
        [ "$arg" = "$option" ] || cli_error "$option does not accept a value"
        case "$option" in
          -h|--help) CLI_HELP=1 ;; -V|--version) CLI_VERSION=1 ;;
          -v|--verbose) CMAIL_VERBOSE=1 ;; -q|--quiet) CMAIL_QUIET=1 ;;
          --no-color) CMAIL_NO_COLOR=1 ;; --no-browser) CMAIL_NO_BROWSER=1 ;;
          --offline) CMAIL_OFFLINE=1 ;; --dry-run) CMAIL_DRY_RUN=1 ;; --stdin) CLI_STDIN=1 ;;
        esac ;;
      -c|--config|-f|--format|--timeout|--wait-timeout|--domain|--destination|--addresses)
        if [ "$arg" != "$option" ]; then value="${arg#*=}"
        else [ "$#" -gt 0 ] || cli_error "$option needs a value"; value="$1"; shift; fi
        [ -n "$value" ] || cli_error "$option needs a non-empty value"
        case "$option" in
          -c|--config) CLI_CONFIG="$value" ;; -f|--format) CMAIL_FORMAT="$value" ;;
          --timeout) CMAIL_TIMEOUT="$value" ;; --wait-timeout) CMAIL_WAIT_TIMEOUT="$value" ;;
          --domain) CLI_DOMAIN="$value" ;; --destination) CLI_DESTINATION="$value" ;; --addresses) CLI_ADDRESSES="$value" ;;
        esac ;;
      -*) cli_error "unknown option '$arg'" ;;
      *) positionals+=("$arg") ;;
    esac
  done
  [ "${#positionals[@]}" = 0 ] || CLI_COMMAND="${positionals[0]}"
  case "$CLI_COMMAND" in
    ''|setup|status|doctor|send-as|config|completion|help) ;;
    *) cli_error "unknown command '$CLI_COMMAND'" ;;
  esac
  if [ "$CLI_COMMAND" = config ]; then
    CLI_SUBCOMMAND="${positionals[1]:-}"
    case "$CLI_SUBCOMMAND" in ''|init|show|check|set|path) ;; *) cli_error "unknown config command '$CLI_SUBCOMMAND'" ;; esac
    [ "${#positionals[@]}" -le 2 ] || CLI_ARGS=("${positionals[@]:2}")
  else
    [ "${#positionals[@]}" -le 1 ] || CLI_ARGS=("${positionals[@]:1}")
  fi
  case "$CMAIL_FORMAT" in text|json) ;; *) cli_error '--format must be text or json' ;; esac
  [[ "$CMAIL_TIMEOUT" =~ ^[1-9][0-9]{0,5}$ ]] || cli_error '--timeout must be a positive integer (at most 999999 seconds)'
  [[ "$CMAIL_WAIT_TIMEOUT" =~ ^[1-9][0-9]{0,5}$ ]] || cli_error '--wait-timeout must be a positive integer (at most 999999 seconds)'
  case "$CMAIL_VERBOSE:$CMAIL_QUIET" in 0:0|0:1|1:0) ;; *) cli_error '--verbose and --quiet are mutually exclusive boolean settings' ;; esac
  [ "$CLI_VERSION" = 0 ] || { printf 'cmail %s\n' "$(cat "$CMAIL_DIR/VERSION")"; exit 0; }
  if [ "$CLI_COMMAND" = help ]; then cli_help "${CLI_ARGS[*]:-}"; exit 0; fi
  if [ "$CLI_HELP" = 1 ] || [ -z "$CLI_COMMAND" ] || { [ "$CLI_COMMAND" = config ] && [ -z "$CLI_SUBCOMMAND" ]; }; then
    cli_help "${CLI_COMMAND}${CLI_SUBCOMMAND:+ $CLI_SUBCOMMAND}"; exit 0
  fi
  [ "$CMAIL_OFFLINE" = 0 ] || [ "$CLI_COMMAND" = doctor ] || cli_error '--offline is only available for doctor'
  [ "$CMAIL_DRY_RUN" = 0 ] || [ "$CLI_COMMAND" = setup ] || cli_error '--dry-run is only available for setup'
  if [ "$CLI_SETUP_OPTIONS" = 1 ]; then
    [ "$CLI_COMMAND" = setup ] || cli_error 'setup options are only available for setup'
  fi
  [ "$CLI_STDIN" = 0 ] || [ "$CLI_COMMAND $CLI_SUBCOMMAND" = 'config set' ] || cli_error '--stdin is only available for config set'
  case "$CLI_COMMAND $CLI_SUBCOMMAND" in
    'config set')
      if [ "$CLI_STDIN" = 1 ]; then [ "${#CLI_ARGS[@]}" = 1 ] || cli_error 'config set --stdin needs exactly one KEY'
      else [ "${#CLI_ARGS[@]}" = 2 ] || cli_error 'config set needs KEY and VALUE, or KEY --stdin'; fi ;;
    'completion ')
      [ "${#CLI_ARGS[@]}" = 1 ] || cli_error 'completion needs one shell: bash, zsh, or fish'
      case "${CLI_ARGS[0]}" in bash|zsh|fish) ;; *) cli_error 'completion shell must be bash, zsh, or fish' ;; esac ;;
    *) [ "${#CLI_ARGS[@]}" = 0 ] || cli_error 'unexpected positional argument' ;;
  esac
  if [ "$CMAIL_FORMAT" = json ]; then
    case "$CLI_COMMAND $CLI_SUBCOMMAND" in
      'status '|'doctor '|'config show'|'config check') ;;
      'setup ') ;; # legacy DRY_RUN is resolved after reading configuration
      *) cli_error 'JSON is available for status, doctor, config show/check, and setup --dry-run' ;;
    esac
  fi
}
