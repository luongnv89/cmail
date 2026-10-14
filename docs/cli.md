# cmail CLI guide (0.4.0)

Set up custom-domain receiving, inspect forwarding, and diagnose problems. Incoming mail is forwarded by Cloudflare to an inbox you already own. Sending uses a separate optional manual guide.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"   # only if the installer says it is not on PATH
cmail --version
cmail config init
cmail setup
```

The one-line command downloads the prebuilt cmail binary for your OS and architecture (macOS or Linux, x86_64 or arm64) from the GitHub release, verifies its SHA-256 checksum, and installs it to `~/.local/bin/cmail` without a clone or sudo. Set `CMAIL_BIN_DIR` to install elsewhere, and put that directory on PATH. The installer never runs setup, contacts no email provider, and does not edit shell profiles.

With Homebrew, which also installs shell completions:

```bash
brew install luongnv89/tap/cmail
```

To build a reviewed checkout instead (needs Rust and cargo), run this inside it:

```bash
bash install.sh --local      # or: cargo install --path .
```

`--local` builds this checkout and installs it to the same place, without provider access or configuration changes. Rerun the installer, `brew upgrade cmail`, or `--local` after pulling to update; existing configuration is preserved.

cmail does not use proxy settings (`HTTPS_PROXY`, `ALL_PROXY`) yet. It connects directly to `api.cloudflare.com` over HTTPS, so it needs direct internet access. The installer's download does follow your proxy settings.

Runtime requirements: none beyond the binary itself; cmail does not need Bash, curl or jq to run. gddy is needed only for opt-in GoDaddy automation (`REGISTRAR=godaddy`). The optional Google sending guide requires browser/account eligibility and separate delivery checks.

Configuration defaults to `~/.config/cmail/.env` (`$XDG_CONFIG_HOME/cmail/.env` when `XDG_CONFIG_HOME` is set); `cmail config path` prints the selected path. Earlier versions run from a checkout defaulted to the checkout's `.env`: pass `--config ./.env` or move that file to the default path.

## Commands

| Command | What it does |
|---|---|
| `cmail setup` | Guided receiving setup in a terminal |
| `cmail setup --dry-run` | Read-only provider inspection and plan with blockers |
| `cmail status` | Zone, routing, destinations, and rules report |
| `cmail list [--domain DOMAIN]` | Every address on a domain, where it forwards, and the catch-all rule |
| `cmail forward ADDRESS --destination EMAIL` | Change where an existing address forwards, in a terminal |
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

Every command accepts `--help`. `--version` prints the binary's version. Invalid extra arguments and unknown flags are errors. Long options accept `--option=value` or `--option value`; `--` ends option parsing. Short flags are individual arguments, such as `-v -c /path/config`.

## Configure and inspect

```bash
cmail config set DOMAIN example.com
cmail config set DEST_EMAIL owner@example.net
cmail config set ADDRESSES hello,contact
cmail config check
cmail setup --domain example.com --destination owner@example.net --addresses hello,contact
```

## Change where an address forwards

`cmail forward` moves an existing address to a new inbox. The address and its Cloudflare rule stay; only the destination changes. Run it in a terminal:

```bash
cmail forward hello --destination new@example.org
cmail forward hello@example.org --destination new@example.org --domain example.org
```

ADDRESS is a local part (`hello`) or `LOCAL@DOMAIN`. The domain is `DOMAIN` from the configuration unless you pass `--domain`. cmail reads the address's rule, shows `hello@example.com: old@example.net -> new@example.org` and asks before writing. It then updates the rule in place, keeping its name, matcher, priority and enabled state, and reads it back. After that, mail to the address goes to the new inbox and no longer to the old one. Test it from a different mailbox than the new destination.

Cloudflare forwards only to verified destination addresses, so the new inbox must be verified first. Nothing about the address changes until it is:

- **New inbox not registered yet:** cmail offers to register it, which sends Cloudflare's verification email, then stops. Click the link in that inbox (check Spam), then rerun the same `cmail forward` command. Until then the address keeps forwarding to the old inbox.
- **Registered but not verified:** cmail stops with the same next step and sends nothing. A missing or expired link can be resent from Cloudflare > Email > Email Routing > Destination addresses.

`DEST_EMAIL` in the configuration is updated only when the change is on the configured domain and every address in `ADDRESSES` then forwards to the new inbox. Otherwise cmail keeps `DEST_EMAIL` and names the addresses that still forward elsewhere. `cmail setup` checks every address against one `DEST_EMAIL`, so it reports those addresses as conflicting until they all forward to one inbox. Move each of them with `cmail forward`.

cmail refuses, without changing anything, when the address has no rule (create it with `cmail setup`). It also refuses when the address has more than one rule, a custom matcher, a Worker-managed rule, or an action other than a single forward. Change those in Cloudflare > Email > Email Routing > Routing rules. A disabled rule stays disabled, with a warning. If the address already forwards to the new inbox, nothing is written. `forward` has no `--dry-run` or JSON output; `cmail list` shows the current destinations.

## Registrar: manual (default) or GoDaddy (opt-in)

`REGISTRAR` (or `setup --registrar manual|godaddy`) selects how DNS delegation reaches Cloudflare. An explicit `--registrar` is saved like `--domain`.

- `manual` (default): bring a domain you already own at any registrar. Setup never runs gddy, never asks for GoDaddy authentication, and never buys a domain. It asks for DOMAIN if unset, verifies the Cloudflare token, and reuses the zone or creates it (zone creation needs Zone: Edit on the account's zones). Then it runs the `Registrar nameservers` step:
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

Select a config with `--config PATH`; otherwise `CMAIL_CONFIG`, legacy `ENV_FILE`, and `${XDG_CONFIG_HOME:-~/.config}/cmail/.env` are tried in order. Global environment settings are `CMAIL_FORMAT`, `CMAIL_TIMEOUT`, `CMAIL_VERBOSE`, and `CMAIL_QUIET` (boolean settings use 0 or 1). Explicit global flags override those settings.

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

A successfully generated preview exits 0 even when its `data.blockers` array is nonempty. Inspect blockers before setup. Actual setup, forward and send-as require terminal stdin; running them with closed or piped stdin fails before writes. Agent runners must use a pseudo-terminal and relay prompts. GoDaddy nameserver replacement retains explicit confirmation. Any charge, such as a domain purchase (offered only with `REGISTRAR=godaddy`), always requires the exact domain name typed at an interactive terminal; no flag, environment variable, or piped input can approve it. Existing DNS/service records require migration review before delegation changes.

## Output and timing

Results go to stdout. Progress, prompts, warnings, and errors go to stderr. `--quiet` retains results and errors; `--verbose` adds redacted request context. They are mutually exclusive. On a terminal, status, list, doctor, config show/check and setup previews draw boxes with status marks (`●` ok, `▲` attention, `✗` failed). When stdout is piped, they print plain tab-separated records, one per line with no header, so they work with `cut`, `grep` and `awk`. `--format json` remains the stable scripting contract. A non-empty `NO_COLOR` or `--no-color` disables color; `FORCE_COLOR=1` styles output that is not a terminal (never JSON). Outside a UTF-8 locale, boxes use ASCII characters. `--no-browser` prints manual links; with `REGISTRAR=godaddy`, setup also requires an existing PAT in this mode to prevent automatic GoDaddy OAuth.

JSON is available for status, list, doctor, config show/check, and setup previews:

```json
{"schema_version":1,"command":"status","data":{"zone":{},"routing":{},"destinations":[],"rules":[]}}
```

`cmail list` answers "which addresses exist and where does each one forward?" for the configured domain, or for any other zone the token can read with `--domain`. Each forward destination is marked `verified`, `unverified` (Cloudflare will not deliver until the verification link is clicked) or `unregistered`. Each rule is shown as enabled or disabled, and the catch-all rule is listed separately:

```text
╭─┐example.com addresses┌──────────────────────────────────────────╮
│ contact@example.com  →  owner@example.net (verified)  ✗ disabled │
│ hello@example.com    →  owner@example.net (verified)  ● enabled  │
├──────────────────────────────────────────────────────────────────┤
│ catch-all → drop  ✗ disabled                                     │
╰─┘2 addresses└────────────────────────────────────────────────────╯
```

Piped, the same command prints one record per address (address, destinations, state) and a final `catch-all` record:

```text
contact@example.com	owner@example.net (verified)	disabled
hello@example.com	owner@example.net (verified)	enabled
catch-all	drop	disabled
```

With `--format json`, `data.addresses[]` holds `address`, `rule_id`, `name`, `enabled`, `priority`, `matchers` and `actions`; forward actions also carry `destinations[]` with `email` and `state`. `data.catch_all` is `null` when the zone has no catch-all rule.

Status and list emit a complete result after all reads succeed. Doctor/config checks also emit their diagnostic report when checks fail, alongside a nonzero exit code. Help, version, completions, guided setup, and the sending guide use text output.

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
| 143 | Terminated (SIGTERM) |

## Shell completions

Homebrew installs completions automatically. The scripts are generated from the command tree, so they always match the installed version.

Bash, for the current shell (save/source the file from your shell profile to persist):

```bash
cmail completion bash > ~/.cmail-completion.bash
source ~/.cmail-completion.bash
```

Zsh: create `~/.zfunc`, save `cmail completion zsh > ~/.zfunc/_cmail`, then put `fpath=(~/.zfunc $fpath)` before `autoload -Uz compinit; compinit` in `.zshrc`.

Fish: create `~/.config/fish/completions`, then run `cmail completion fish > ~/.config/fish/completions/cmail.fish`. Completions never read private configuration or credentials.

## Development checks

```bash
make test    # cargo test, then the Python/Node suites against the built binary
make lint    # cargo fmt --check, cargo clippy -D warnings, shellcheck install.sh scripts/*.sh
make build   # release binary in target/release/cmail
```

Offline tests use a loopback Cloudflare API fixture, a fake gddy, temporary configuration, and temporary installation paths; they never contact providers. They require Rust/cargo, Python 3 and Node; lint also requires ShellCheck. CI runs macOS/Linux checks. See [distribution status](distribution.md) for publication decisions and the [GoDaddy CLI reference](https://developer.godaddy.com/en/docs/api-users/cli/reference) for provider command behavior.
