# cmail

Get a **free custom-domain email address** like `hello@your-domain` in **a few
simple steps**, delivered to **the inbox you already use** (Gmail, Outlook,
iCloud, Proton, a work address, …). Built on **Cloudflare Email Routing**; no
new mailbox and no Google account needed.

`cmail` is a single command-line program (written in Rust) with no runtime
dependencies: no Bash, curl or jq needed to run it.

## Install

One command, no clone, no sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash
```

The installer detects your OS and CPU (macOS or Linux, x86_64 or arm64),
downloads the matching prebuilt binary from the
[latest GitHub release](https://github.com/luongnv89/cmail/releases/latest),
verifies its SHA-256 checksum, and installs it as `~/.local/bin/cmail`
(override with `CMAIL_BIN_DIR`). It never runs setup or changes DNS. If
`~/.local/bin` is not on your `PATH`, it prints the line to add:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Homebrew** (macOS and Linux), which also installs shell completions:

```bash
brew install luongnv89/tap/cmail
```

**From a reviewed checkout** (needs [Rust](https://rustup.rs/)):

```bash
git clone https://github.com/luongnv89/cmail
cd cmail
bash install.sh --local      # builds this checkout and installs it to ~/.local/bin
# or: cargo install --path .
```

Then:

```bash
cmail --version
cmail config init
cmail setup
```

Upgrade by re-running the same install command (or `brew upgrade cmail`).
Uninstall by deleting the `cmail` binary (or `brew uninstall cmail`); your
private configuration in `~/.config/cmail` is kept unless you delete it.

**Proxies:** cmail does not use `HTTPS_PROXY` or `ALL_PROXY` yet. It connects
directly to `api.cloudflare.com` over HTTPS, so it needs direct internet access.
The installer's download does follow your proxy settings.

See [distribution](docs/distribution.md) for release and packaging details.

## Start here

Website: [luongnv89.github.io/cmail](https://luongnv89.github.io/cmail/), built from `docs/`:
[introduction](docs/index.html) → [8-step visual setup guide](docs/setup.html)
([Markdown version](docs/setup.md)) · [CLI docs](docs/docs.html) ·
[changelog](docs/changelog.html) · [privacy](docs/privacy.html).
Checkmarks save only step IDs/booleans in your browser; they do not verify
providers, and the site collects no credentials. See [local preview](docs/setup.md#local-preview).

**Any registrar, no GoDaddy required.** By default (`REGISTRAR=manual`) cmail
works with a domain you already own at any registrar. If the domain is already
active on Cloudflare, setup skips nameservers entirely. Otherwise it prints the
exact Cloudflare-assigned nameservers and migration warnings (copy existing DNS
records into Cloudflare and turn off DNSSEC first), then waits while you replace
the nameservers at your registrar. GoDaddy automation is opt-in:
`cmail setup --registrar godaddy` uses [`gddy`](https://developer.godaddy.com/en/docs/api-users/cli/set-up)
to pick a domain and apply the nameserver change after confirmation. Domain
purchase is offered only in that mode and needs the domain typed at a terminal.

**Gmail sending policy:** [Google's current help](https://support.google.com/mail/answer/22370)
announces removal of third-party “Send as” starting **January 2027**. Check current
availability before relying on cmail's optional outbound path. Inbound Cloudflare
forwarding is separate.

## What setup does

`cmail setup` runs in a terminal and walks through each step. Sending is optional
and not part of it.

1. **Configuration**: collect your destination inbox (any provider) and the
   addresses to create (`hello,contact,…`)
2. **Domain**: a domain you own at any registrar (or, with `--registrar godaddy`,
   pick or register one through `gddy`, with an explicit price confirmation)
3. **Cloudflare token**: show the four required permissions (no DNS permission), open the token page,
   and verify the token you paste (input hidden). Activity alone does not prove
   resource access; later steps check it.
4. **Cloudflare zone**: reuse the zone (or create it, if the token has Zone: Edit) and fetch its assigned nameservers.
   Several visible accounts require an explicit `CF_ACCOUNT_ID`.
5. **Nameservers**: print them for your registrar (or, with GoDaddy, compare and
   replace them after confirmation). Migrate existing DNS records first.
6. **Zone activation**: wait (default up to 20 minutes, `--wait-timeout`);
   failures explain how to check delegation and resume
7. **Email Routing**: skip if enabled; otherwise Cloudflare adds and locks the
   routing DNS records
8. **Destination**: register or reuse your inbox; click Cloudflare's verification
   email while cmail polls until it is confirmed
9. **Addresses**: create forwarding rules. Conflicting or disabled existing rules
   are reported, never overwritten.

Setup ends here: receiving works. Test it by sending from a **different mailbox**
to your custom address (delivery is not verified automatically). Setup is
re-runnable: state lives in your private config, and existing resources are
detected and skipped. `cmail setup --dry-run` prints the full plan without
changing anything.

### Optional: send from your custom address

Sending is optional. Only if you also want to **send** as `hello@your-domain`, and
your `DEST_EMAIL` is a Gmail/Google account that can use App Passwords:

```bash
cmail send-as
```

It guides the manual Gmail "Send mail as" setup with an App Password. Gmail's
confirmation code arrives through the forwarding that `setup` created, so run
`setup` first. Test outbound separately; pressing Enter does not verify it.

## Commands

| Command | Description |
|---|---|
| `cmail setup` | Guided receive setup (forwarding to any inbox); `--dry-run` previews it |
| `cmail status` | Show zone, routing, destination, and rule state |
| `cmail list [--domain DOMAIN]` | Every address on a domain, where it forwards, destination verification, and the catch-all |
| `cmail forward ADDRESS --destination EMAIL` | Change where an existing address forwards; asks before writing. The new inbox must be verified first (cmail offers to send the verification email, then you rerun) |
| `cmail doctor [--offline]` | Read-only configuration, registrar tool, and authentication checks |
| `cmail send-as` | Optional guided Gmail "Send mail as" |
| `cmail config init\|show\|check\|set\|path` | Manage the private configuration |
| `cmail completion bash\|zsh\|fish` | Print a shell completion script |

Every command has `--help`. Global options work before or after the command:
`-c/--config PATH`, `-f/--format text|json`, `-v/--verbose`, `-q/--quiet`,
`--no-color`, `--no-browser`, `--timeout SECONDS`.

**Output.** On a terminal, reports are drawn as boxes in a btop-inspired style.
When piped, `status`, `list`, `doctor` and `config show` print tab-separated
records (one per line, no header) for tools like `cut` and `awk`. For scripts,
prefer `--format json` (`{schema_version, command, data}`), which is stable.
`NO_COLOR` or `--no-color` turns color off; `FORCE_COLOR=1` forces styling.

```bash
cmail list --format json | jq -r '.data.addresses[].address'
cmail doctor --offline
cmail forward hello --destination new@outlook.com
```

**Exit codes:** `0` success, `1` provider or runtime failure, `2` invalid
arguments, `3` invalid configuration or input, `130` interrupted.

## Configuration

The private configuration lives at `~/.config/cmail/.env` (or
`$XDG_CONFIG_HOME/cmail/.env`). Select another file with `--config`,
`CMAIL_CONFIG` or `ENV_FILE`; `cmail config path` prints the one in use.
Environment variables override the file, and command-line options override both.

The file holds literal `NAME=value` lines. cmail parses it and never evaluates it:
expansions, commands and unquoted shell syntax are rejected. It must be a regular
file you own with mode `600`. `cmail config set KEY VALUE` updates one setting
atomically; secrets require `--stdin` so they never appear in shell history.

| Var | Meaning |
|---|---|
| `DOMAIN` | Custom domain to use |
| `DEST_EMAIL` | Any email address you own that receives forwarded mail; must be a Gmail/Google account only for `send-as` |
| `ADDRESSES` | Comma-separated local parts, e.g. `hello,contact,me` (default `hello`) |
| `CLOUDFLARE_API_TOKEN` | Zone:Read (Zone:Edit only if cmail adds the domain), Zone Settings:Edit, Email Routing Rules:Edit, Account Email Routing Addresses:Edit. Account Resources: only the account that owns the domain; Zone Resources: that domain (or all zones from that account when cmail adds it). Never All accounts. See [step 3 of the setup guide](docs/setup.md#3-create-a-cloudflare-api-token) |
| `REGISTRAR` | `manual` (default, any registrar) or `godaddy` (opt-in `gddy` automation) |
| `GDDY_ENV` | GoDaddy environment (default `prod`) |
| `GDDY_PAT` | Optional PAT instead of browser OAuth for headless GoDaddy runs |
| `CF_ZONE_ID` | Saved by `setup`; reused by `status`, `list` and `forward` |
| `CF_ACCOUNT_ID` | Optional 32-character account ID; selects the account when several are visible. Does not grant API permissions. |
| `DRY_RUN` | `1` makes `setup` run its read-only preview (same as `--dry-run`) |

Upgrading from 0.3 or earlier: a checkout's `./.env` is no longer read
automatically. Move it to `~/.config/cmail/.env` (keep `chmod 600`) or pass
`--config ./.env`.

## What is NOT automated (and why)

- **Cloudflare API token**: Cloudflare has no self-service OAuth for arbitrary
  programs; cmail opens the token page, lists the permissions to add, then
  verifies what you paste.
- **Destination verification**: Cloudflare emails a link to your destination
  inbox; you click it (cmail waits and continues automatically).
- **Gmail "Send mail as"** (optional, `cmail send-as`): automating it needs the
  restricted `gmail.settings.*` OAuth scope, which requires a verified Google
  Cloud app. Guided manual steps instead.
- **Domain purchase**: supported only via `gddy`, and always asks before spending money.

## Recovering a stopped setup

Failures name the step, give a **Next** action, and tell you to rerun
`cmail setup` after fixing the cause. Earlier configuration and resources may
already be saved. Once the GoDaddy nameserver step is reached, delegation may
already have changed; cmail never rolls it back. For uncertain writes, check
the provider dashboard before retrying (especially domain purchases). Never
share your config, API tokens, PATs or app passwords. `cmail status` shows the
saved Cloudflare state.

| Step / symptom | How to unblock |
|---|---|
| “No Cloudflare account visible to token” | Edit the token at [Cloudflare API tokens](https://dash.cloudflare.com/profile/api-tokens): include the account that owns your domain under **Account Resources** (not All accounts) and your domain under **Zone Resources** (all zones from that account only if cmail must add the domain). If listing still shows none, copy the **Account ID** (not Zone ID) from the dashboard and run `cmail config set CF_ACCOUNT_ID <id>`. |
| Several accounts visible | Setup lists them; select one with `CF_ACCOUNT_ID` rather than letting cmail guess. |
| HTTP 401/403 | Check token activity, the operation's permission (named in the error), and account/zone resource scope. |
| Network / HTTP 429 / 5xx | Fix connectivity, wait after rate limiting, or check [Cloudflare status](https://www.cloudflarestatus.com/). Inspect the dashboard before retrying an uncertain write. |
| Zone stays pending | Compare the nameservers at your registrar with Cloudflare Overview. Propagation can take 24–48 hours; rerun once Cloudflare shows Active. |
| Email Routing activation fails | Needs **Zone → Zone Settings → Edit**. Check conflicting MX/TXT records; do not delete an existing mail provider's records without planning a migration. |
| Destination verification times out | Check Inbox/Spam of the right mailbox and click the link. Resend from Email Routing → Destination addresses; the pending entry is kept. |
| Existing forwarding rule conflicts | Enable/correct it in Email Routing → Routing rules, or change its destination with `cmail forward`. Setup never overwrites it. |
| GoDaddy authentication/domain access | Use the right account and `GDDY_ENV`; run `gddy auth login --env prod` (or `ote`), or replace an expired PAT. |
| Gmail send-as blocked | Enable 2-Step Verification and use an App Password (smtp.gmail.com, port 587, TLS). Receiving is unaffected. |

## Agent-assisted verified setup

The portable [cmail-setup skill](skills/cmail-setup/SKILL.md) lets an AI agent
install cmail, fill the non-secret config, run a read-only preflight and then
run setup itself, verifying each gate and asking only when a step needs you
(token entry, browser approvals, delivery tests, nameserver or purchase
decisions). Credentials stay in your local browser or editor, never in chat. See
its [installation and usage guide](skills/cmail-setup/docs/README.md).

## Development

```bash
make build    # release binary in target/release/cmail
make test     # cargo tests + offline Python/Node contract suites
make lint     # cargo fmt --check, clippy -D warnings, shellcheck
```

The contract suites run the real binary against a loopback Cloudflare API
fixture (`tests/fixture_server.py`) and a fake `gddy`; they never contact live
providers or change DNS. Individual suites:

```bash
cargo test
python3 tests/cli_test.py           # command contracts, output formats, completions
python3 tests/setup_flow_test.py    # setup provider flows and recovery
python3 tests/timing_test.py        # elapsed time, interrupts, bounded waits
bash tests/install_test.sh          # installer against a local fake release
python3 tests/skill_setup_test.py   # cmail-setup skill and config helper
node --test tests/checklist_test.js # static checklist unit tests; Node 18+
python3 tests/site_test.py          # offline docs/link/contrast contract tests
```

Optional real-browser site tests use an externally installed Playwright:
`node --test tests/site_browser_test.cjs` (set `NODE_PATH`/`CHROME_BIN` as needed;
external requests are blocked).

### Website deployment

[GitHub Pages](https://luongnv89.github.io/cmail/) is built by the
[Pages workflow](.github/workflows/pages.yml) from the files allowlisted in
[the staging script](scripts/build-pages.sh). Preview with
`bash scripts/build-pages.sh` and
`python3 -m http.server 8000 --bind 127.0.0.1 --directory _site`; validate with
`python3 tests/pages_test.py`.

## Limitations

- Cloudflare only **forwards** mail: no mailbox or storage (your destination
  inbox's storage is used).
- Optional outbound via Gmail isn't DKIM-signed with your domain; fine for
  personal use, upgrade to Google Workspace if deliverability matters.
- Gmail sending limits and third-party send-as availability depend on Google and
  your account; see the January 2027 policy warning above.

## License

[MIT](LICENSE)
