# cmail CLI guide (0.2.0-dev)

Set up custom-domain receiving, inspect forwarding, and diagnose problems. Incoming mail is forwarded by Cloudflare to an inbox you already own. Sending uses a separate optional manual guide.

## Install the reviewed checkout

```bash
bash install.sh --local
export PATH="$HOME/.local/bin:$PATH"
cmail --version
cmail config init
cmail setup
```

`--local` copies this checkout's runtime without downloads, provider access, or configuration replacement. Installed configuration defaults to `~/.config/cmail/.env`; direct `./cmail` execution defaults to checkout `.env`. `cmail config path` prints the selected path. The launcher path can be overridden at installation with `CMAIL_BIN_DIR`; use that directory in PATH instead when customized.

The unflagged installer retains the pinned v0.1.0 runtime. That older runtime has different commands and behavior. This development CLI is not a published release. Reinstall the reviewed checkout with `--local` to update it; existing configuration is preserved.

Runtime requirements: Bash 3.2+, curl, and jq on macOS/Linux. gddy is needed only for opt-in GoDaddy automation (`REGISTRAR=godaddy`). Setup checks tools and prints installation instructions. The optional Google sending guide requires browser/account eligibility and separate delivery checks.

## Commands

| Command | What it does |
|---|---|
| `cmail setup` | Guided receiving setup in a terminal |
| `cmail setup --dry-run` | Read-only provider inspection and plan with blockers |
| `cmail status` | Zone, routing, destinations, and rules report |
| `cmail doctor` | Read-only dependency/config/authentication checks |
| `cmail doctor --offline` | Local checks without provider requests |
| `cmail send-as` | Optional manual Gmail sending guide |
| `cmail config init` | Create mode-600 configuration; preserve existing files |
| `cmail config show` | Effective settings, with secrets redacted |
| `cmail config check` | Validate settings and report readiness |
| `cmail config set KEY VALUE` | Atomically update a public setting |
| `cmail config set KEY --stdin` | Read one setting from stdin; required for secrets |
| `cmail config path` | Print the resolved configuration path |
| `cmail completion bash\|zsh\|fish` | Print shell completions |
| `cmail help config set` | Help for any command path |

Every command accepts `--help`. `--version` reads this runtime's version. Invalid extra arguments and unknown flags are errors. Long options accept `--option=value` or `--option value`; `--` ends option parsing. Short flags are individual arguments, such as `-v -c /path/config`.

## Configure and inspect

```bash
cmail config set DOMAIN example.com
cmail config set DEST_EMAIL owner@example.net
cmail config set ADDRESSES hello,contact
cmail config check
cmail setup --domain example.com --destination owner@example.net --addresses hello,contact
```

## Registrar: manual (default) or GoDaddy (opt-in)

`REGISTRAR` (or `setup --registrar manual|godaddy`) selects how DNS delegation reaches Cloudflare. An explicit `--registrar` is saved like `--domain`.

- `manual` (default): bring a domain you already own at any registrar. Setup never runs gddy, never asks for GoDaddy authentication, and never buys a domain. It asks for DOMAIN if unset, verifies the Cloudflare token, and reuses or creates the zone. Then it runs the `Registrar nameservers` step:
  - Zone already **active** on Cloudflare: no registrar or nameserver change is needed, and setup continues.
  - Zone **pending**: setup prints the exact Cloudflare-assigned nameservers and the migration warnings: copy web, MX, TXT, and other records into Cloudflare, and turn off DNSSEC/DS records at the registrar before switching. It then polls activation (bounded by `--wait-timeout`) while you replace **all** nameservers at your registrar. If the wait ends first, rerun `cmail setup`; completed steps are skipped. cmail itself never changes delegation in this mode.
- `godaddy`: opt-in automation through the [GoDaddy CLI](https://developer.godaddy.com/en/docs/api-users/cli/set-up) (`gddy`). Setup requires gddy, authenticates (browser OAuth or `GDDY_PAT`), picks a GoDaddy domain, and compares the current nameservers. It replaces them only after confirmation. This is the only mode that can offer a domain registration, and any charge still requires the exact domain typed at a terminal.

`cmail doctor` checks gddy and GoDaddy authentication only when `REGISTRAR=godaddy`. Without it, a missing gddy never fails doctor.

```bash
cmail setup --domain example.com                 # any registrar, manual nameservers
cmail setup --registrar godaddy                  # opt in to GoDaddy automation
cmail config set REGISTRAR godaddy               # make the opt-in persistent
```

## Configuration files

Configuration contains documented literal `KEY=value` assignments. Single/double quotes and literal backslash escapes are supported; shell commands and expansions are rejected. Files must be user-owned regular files with mode 600. Read-only commands do not repair permissions or create missing files. Use `config init` to create one; fix an existing file's permissions locally when instructed.

Precedence: explicit command options → environment values → configuration file → defaults. An explicit empty environment value overrides a saved value. Operational environment names are `DOMAIN`, `DEST_EMAIL`, `ADDRESSES`, `REGISTRAR`, `GDDY_ENV`, `GDDY_PAT`, `CLOUDFLARE_API_TOKEN`, `CF_ACCOUNT_ID`, `CF_ZONE_ID`, and `DRY_RUN`.

Select a config with `--config PATH`; otherwise `CMAIL_CONFIG`, legacy `ENV_FILE`, and the checkout/installed default are tried in order. Global environment settings are `CMAIL_FORMAT`, `CMAIL_TIMEOUT`, `CMAIL_VERBOSE`, and `CMAIL_QUIET` (boolean settings use 0 or 1). Explicit global flags override those settings.

Explicit public setup options are saved after validation. Environment-only overrides remain temporary. Changing DOMAIN clears its saved CF_ZONE_ID so another domain's zone cannot be reused. IDs discovered by setup are saved for subsequent runs.

For secret input, use a private source without a value in the command arguments:

```bash
cmail config set CLOUDFLARE_API_TOKEN --stdin < /path/to/private/token
```

Stdin accepts one value, at most 4096 bytes, optionally followed by one newline. Multiline data and NUL are rejected. Empty values clear a setting. For hidden terminal token entry, use `cmail setup`. `config show` displays only secret presence and masks opaque values that may be misplaced credentials. The portable agent checker intentionally accepts a narrower literal subset.

## Preview and automation

```bash
cmail setup --dry-run --format json
cmail status --format json | jq '.data.rules'
cmail doctor --offline --format json
cmail --config ~/.config/cmail/work.env config check
```

Both `setup --dry-run` and legacy `DRY_RUN=1` preview the entire workflow in this version: no provider changes, purchases, configuration writes, browser launches, installations, or authentication flows. The preview needs valid existing Cloudflare credentials and reports the selected `registrar` in its JSON data. In manual mode it never runs gddy and has no GoDaddy blocker. Its `nameservers` action is `ready` when the zone is already active. It is `manual` and lists the assigned nameservers when the zone is pending, and `manual` with a note that setup prints them when no zone exists yet. With `REGISTRAR=godaddy` it uses a supplied `GDDY_PAT` for the GoDaddy delegation read. Without a PAT it reports that check as a blocker, since gddy can automatically start OAuth during a read. Guided setup supports browser OAuth. Read access does not establish every write permission.

A successfully generated preview exits 0 even when its `data.blockers` array is nonempty. Inspect blockers before setup. Actual setup and send-as require terminal stdin; running them with closed or piped stdin fails before writes. Agent runners must use a pseudo-terminal and relay prompts. GoDaddy nameserver replacement retains explicit confirmation. Any charge, such as a domain purchase (offered only with `REGISTRAR=godaddy`), always requires the exact domain name typed at an interactive terminal; no flag, environment variable, or piped input can approve it. Existing DNS/service records require migration review before delegation changes.

## Output and timing

Results go to stdout. Progress, prompts, warnings, and errors go to stderr. `--quiet` retains results and errors; `--verbose` adds redacted request context. They are mutually exclusive. Colors are used only on terminal diagnostics, and `NO_COLOR` (including an empty value) or `--no-color` disables them. `--no-browser` prints manual links; with `REGISTRAR=godaddy`, setup also requires an existing PAT in this mode to prevent automatic GoDaddy OAuth.

JSON is available for status, doctor, config show/check, and setup previews:

```json
{"schema_version":1,"command":"status","data":{"zone":{},"routing":{},"destinations":[],"rules":[]}}
```

Status emits a complete result after all reads succeed. Doctor/config checks also emit their diagnostic report when checks fail, alongside a nonzero exit code. Help, version, completions, guided setup, and the sending guide use text output.

A successful setup prints addresses and actual elapsed wall time:

```text
Receiving is set up
  hello@example.com -> owner@example.net
  contact@example.com -> owner@example.net

Elapsed time: 2m 14s (134 seconds)
```

This is an illustrative example, not a measured live setup. The timer starts when setup begins and includes user prompts, provider requests, DNS activation, and verification waits. Failed/interrupted setup prints elapsed time on stderr. Preview JSON includes `data.elapsed_seconds`. Timing measures configuration, not delivery: send from another mailbox and confirm receipt independently.

`--timeout SECONDS` defaults to 30 for provider commands/HTTP requests. `setup --wait-timeout SECONDS` defaults to 1200 for each activation or verification polling stage and the interactive OAuth command. Polls use the remaining deadline for requests/sleeps; user input itself has no automatic deadline. Failed writes report uncertain outcomes so users can inspect provider state before retrying.

| Exit code | Meaning |
|---|---|
| 0 | Success / report generated |
| 1 | Runtime or diagnostic check failure |
| 2 | Invalid invocation or unavailable required terminal |
| 3 | Invalid/incomplete input or configuration |
| 130 | Interrupted with Ctrl+C |

## Shell completions

Bash, for the current shell (save/source the file from your shell profile to persist):

```bash
cmail completion bash > ~/.cmail-completion.bash
source ~/.cmail-completion.bash
```

Zsh: create `~/.zfunc`, save `cmail completion zsh > ~/.zfunc/_cmail`, then put `fpath=(~/.zfunc $fpath)` before `autoload -Uz compinit; compinit` in `.zshrc`.

Fish: create `~/.config/fish/completions`, then run `cmail completion fish > ~/.config/fish/completions/cmail.fish`. Completions never read private configuration or credentials.

## Development checks

```bash
make test
CMAIL_TEST_BASH=/bin/bash make test
make lint
```

Offline tests use mocked providers, temporary configuration, and temporary installation paths. They require jq, Python 3, Node, Git, and Bash; lint requires ShellCheck. CI runs macOS/Linux checks. See [distribution status](distribution.md) for publication decisions and the [GoDaddy CLI reference](https://developer.godaddy.com/en/docs/api-users/cli/reference) for provider command behavior.
