# cmail

Get a **free custom-domain email address** like `hello@your-domain` in **a few
simple steps**, delivered to **the inbox you already use** (Gmail, Outlook,
iCloud, Proton, a work address, …). Built on **Cloudflare Email Routing**; no
new mailbox and no Google account needed.

The receive-only workflow below uses a **reviewed development source snapshot**,
not v0.1.0, until a compatible release/installer ships. Fetch the pin explicitly;
it need not be advertised on the default branch:

```bash
git clone https://github.com/luongnv89/cmail
cd cmail
git fetch origin cda65f0554a870ed8079e93741a331918118acec
git checkout --detach cda65f0554a870ed8079e93741a331918118acec
# Review cmail and lib/ before execution.
./cmail help         # Must list send-as; stop if missing, before setup.
./cmail setup        # Approve in browser, paste a token, click one link.
                     # From another mailbox, email hello@your-domain — done.
```

Use this checkout's `./cmail`, not a PATH `cmail`; config defaults to checkout
`.env`. The [installer](#installation) still pins legacy v0.1.0: its setup
includes the Gmail guide and it has no `send-as` command.

> **Sending is optional, not the default** in this source workflow. `./cmail setup`
> only sets up receiving. If you also want to *send* as `hello@your-domain`, run
> `./cmail send-as` afterwards, only on request. It guides Gmail "Send mail as"
> and needs a Gmail/Google account. See
> [Optional: send from your custom address](#optional-send-from-your-custom-address).

Inspired by this [Tokifyi thread](https://x.com/tokifyi/status/2025741929997361371):
$0/month for email — you only pay for the domain itself.

Release: [v0.1.0](https://github.com/luongnv89/cmail/releases/tag/v0.1.0) · [Changelog](CHANGELOG.md).

## Start here

[cmail introduction](docs/index.html) → [ordered, checkable setup guide](docs/setup.html)
([Markdown fallback](docs/setup.md)). The configured Pages target is
[luongnv89.github.io/cmail](https://luongnv89.github.io/cmail/), available after
Pages is enabled and a deployment succeeds. The guide covers account/key acquisition,
private config, DNS migration, confirmation and independent delivery tests.
Checkmarks save only step IDs/booleans in this browser; they do not verify providers.
No credentials are collected by the site. See [local preview](docs/setup.md#local-preview-and-maintenance).

**Gmail sending policy:** [Google's current help](https://support.google.com/mail/answer/22370)
announces removal of third-party “Send as” starting **January 2027**. Check current
availability/account eligibility before relying on cmail's optional custom-domain
outbound path. Inbound Cloudflare forwarding is separate; alternative SMTP/Workspace setup
is outside this workflow. Public provider references were checked 7 October 2026,
not live authenticated setup or delivery.

## Installation

From a source checkout **containing `install.sh`**, install with one command:

```bash
bash install.sh
```

This installer is new and is **not in the v0.1.0 release**. A released remote
bootstrap command is pending separately authorized release/publication;
see the [distribution decision and recorded status](docs/distribution.md).
Do not assume the existing release contains the installer.

The installer downloads the complete v0.1.0 runtime at a pinned commit over
HTTPS. It requires Bash 3.2+, curl and standard macOS/Linux utilities, but not
git, jq, sudo, a package manager, authentication or provider access. It checks
syntax and offline help before activating a launcher. It never runs setup or
doctor, modifies shell startup files, or changes DNS/email settings.

Default destinations (use user-owned directories, including their parents):

| Item | Destination | Override |
|---|---|---|
| Launcher | `~/.local/bin/cmail` | `CMAIL_BIN_DIR` |
| Complete runtimes | `~/.local/share/cmail/runtime.*` | `CMAIL_DATA_DIR` |
| Private config | `~/.config/cmail/.env` | `CMAIL_CONFIG_DIR` at install; `ENV_FILE` at runtime |

Overrides must be absolute directories. Unmanaged runtime stores/executables
and direct symlink destinations are refused rather than overwritten. Existing
config is never replaced by installation or upgrades; the new config directory
is private and the file is created only on an explicit setup/status/doctor call.
The launcher honors an explicit `ENV_FILE` override. Source-checkout execution
still defaults to the adjacent `.env`.

Verify the installed CLI without authentication or network calls:

```bash
"$HOME/.local/bin/cmail" help
export PATH="$HOME/.local/bin:$PATH"   # only if this directory is not on PATH
cmail help
```

This default installed runtime is **legacy v0.1.0**: `cmail setup` still includes
the Gmail sending guide and has no `cmail send-as`. For receiving-only setup and
optional sending, use the reviewed source quickstart below instead. Only when
ready for the legacy guided, potentially live-changing workflow, run installed
`cmail setup`. Installation success proves CLI availability, not functioning
DNS, provider permissions or end-to-end email delivery.

Re-run `bash install.sh` to reinstall the pinned runtime. To upgrade after
reviewing an upstream revision, provide its full 40-character lowercase SHA:
`CMAIL_REF=<reviewed-commit-sha> bash install.sh`. Moving branches/tags are not
accepted. Each successful run activates a fresh runtime and retains old ones;
failed downloads/validation leave the old launcher working. Use the same paths
for subsequent installs, and never share a launcher across runtime stores.
To uninstall, remove the installed launcher and the managed cmail runtime
store; retain `~/.config/cmail` unless you explicitly want to delete your
configuration/credentials. No shell profile changes need undoing.

## Quickstart (reviewed current source)

Use this immutable feature-containing development snapshot, **not v0.1.0**, until
a compatible release/installer ships. Clone upstream and fetch the pin explicitly;
it need not be advertised on the default branch. Select the exact revision,
then review `cmail` and `lib/` before executing it:

```bash
git clone https://github.com/luongnv89/cmail
cd cmail
git fetch origin cda65f0554a870ed8079e93741a331918118acec
git checkout --detach cda65f0554a870ed8079e93741a331918118acec
./cmail help         # Must list send-as; stop if missing, before setup.
./cmail setup
```

All workflow commands below refer to this checkout's `./cmail`, not PATH `cmail`.
It defaults to checkout `.env`; to reuse private installed config, explicitly set
`ENV_FILE="$HOME/.config/cmail/.env"` for every `./cmail` invocation. Do not run
`bash install.sh` as part of this quickstart: its default pin selects legacy
v0.1.0, regardless of the checkout revision.

The script walks you through each step. Authentication is browser-based
(OAuth) wherever possible:

1. **Dependencies** — installs `gddy`, `jq`, `curl` if missing
2. **Configuration** — collect your destination inbox (any provider) and
   forwarding local parts
3. **GoDaddy authentication** — `gddy auth login` opens browser OAuth consent
4. **Domain** — pick one from your GoDaddy account (or register a new one
   via `gddy`, with an explicit price confirmation)
5. **Cloudflare token** — show required permissions, verify token activity,
   and save it to `.env`; activity alone does not prove resource access
6. **Cloudflare zone** — reuse/create the zone and fetch assigned nameservers;
   multiple visible accounts require an explicit `CF_ACCOUNT_ID`
7. **Nameservers** — check current GoDaddy nameservers. Matching servers are
   skipped; replacement requires confirmation. Migrate existing DNS records
   to Cloudflare first to avoid disrupting websites or existing mail.
8. **Zone activation** — wait up to about 20 minutes for propagation;
   failures explain how to check delegation and resume
9. **Email Routing** — skip enabled routing; otherwise Cloudflare adds and
   locks the required routing DNS records via its API
10. **Destination** — register/reuse your destination inbox; click the
    verification email while the script polls until confirmed
11. **Addresses** — create forwarding rules (`hello@`, `contact@`, …);
    conflicting or disabled existing rules require your attention

Setup ends here: receiving works. Test it by sending from a **different
mailbox** to your custom address (not automatically verified).

Re-runnable and idempotent — state lives in `.env`, existing resources
are detected and skipped.

### Optional: send from your custom address

Only if you also want to **send** as `hello@your-domain`, and your
`DEST_EMAIL` is a Gmail/Google account that can use App Passwords:

```bash
./cmail send-as
```

It guides the manual Gmail "Send mail as" setup with an App Password. Gmail's
confirmation code arrives through the forwarding that `setup` created, so run
`setup` first. Test outbound separately; pressing Enter does not verify it.

## Agent-assisted verified setup

The portable [cmail-setup skill](skills/cmail-setup/SKILL.md) guides installation,
dependency checks, private configuration, provider access and troubleshooting.
Copy the whole directory into your agent's skill location; see its
[installation and usage guide](skills/cmail-setup/docs/README.md). The runtime
installer does not install agent skills, and no tagged skill release is claimed.

Ask “Use cmail-setup to help me set up custom email” or `/cmail-setup` in an
agent supporting slash skills. The agent selects a trusted source or legacy
installed runtime and its tools, fills the non-secret config, runs a read-only
preflight and then runs that runtime's setup itself,
troubleshooting and rerunning on failure. It verifies each gate before advancing.
It asks only when a value is missing, a step needs you (Cloudflare token entry,
browser approvals, delivery tests, and Gmail send-as only if you ask for
sending), or a decision is important:
nameserver replacement, existing mail/DNSSEC records, purchases or sudo.
Credentials stay in your local browser/editor, never chat.

An optional Python 3 checker validates private literal config without sourcing or
printing it. Offline tests/evaluation cases do not prove a real user's setup,
provider access or delivery. Redistribution licensing remains a maintainer decision.

## Commands

These are the reviewed current-source commands; legacy v0.1.0 lacks `send-as`
and includes the Gmail guide in setup.

| Command | Description |
|---|---|
| `./cmail setup` | Guided receive setup (forwarding to any inbox) |
| `./cmail send-as` | Optional: guided Gmail "Send mail as" for sending from your custom address |
| `./cmail status` | Show zone, routing, destination, and rule state |
| `./cmail doctor` | Check tools + auth; may install missing dependencies |

`status` and `doctor` can create `.env` from the template or secure its permissions. They do not change live DNS or email-routing settings.

## Configuration

Copy `.env.example` to `.env` (the setup does this for you). `.env` is
git-ignored and `chmod 600`. It is trusted Bash assignment configuration
(`NAME=value`, no spaces around `=`); quote values containing spaces. Do not
put scripts/commands with side effects in it: setup evaluates it in an isolated
fail-fast validation shell before loading it, so assignments are evaluated twice.

| Var | Meaning |
|---|---|
| `DOMAIN` | Custom domain to use |
| `DEST_EMAIL` | Any email address you own that receives forwarded mail; must be a Gmail/Google account only for `send-as` |
| `ADDRESSES` | Comma-separated local parts, e.g. `hello,contact,me` |
| `CLOUDFLARE_API_TOKEN` | CF token: Zone permissions (Zone:Edit, Zone Settings:Edit, DNS:Edit, Email Routing Rules:Edit) plus Account permission (Email Routing Addresses:Edit) |
| `GDDY_ENV` | GoDaddy environment (default `prod`) |
| `GDDY_PAT` | Optional — PAT instead of OAuth for headless runs |
| `CF_ZONE_ID` | Auto-populated by `setup` — Cloudflare zone ID, used by `status` |
| `CF_ACCOUNT_ID` | Optional 32-character account ID from the Cloudflare dashboard; skips account discovery when creating a zone, and selects the intended account when several are visible. Does not grant API permissions. |
| `DRY_RUN` | `1` previews only nameserver replacement; setup can still perform other provider writes/purchases |

## What is NOT automated (and why)

- **Cloudflare API token** — Cloudflare has no self-service OAuth for
  arbitrary scripts; the script opens the token page, lists the five
  permissions to add, then verifies whatever you paste.
- **Destination verification** — Cloudflare emails a link to your
  destination inbox; you must click it (script waits and continues automatically).
- **Gmail "Send mail as"** (optional, `./cmail send-as`) — automating it
  needs the restricted `gmail.settings.*` OAuth scope, which requires a
  verified Google Cloud app — disproportionate for a personal setup.
  Guided manual instead.
- **Domain purchase** — supported via `gddy` but always asks before
  spending money.

## Recovering a stopped setup

Failures identify the step, give a **Next** action, and tell you to rerun
`./cmail setup` after fixing the cause. Earlier configuration/resources may
already be saved. Once the nameserver step is reached, DNS delegation may
already have changed; the script does not roll it back. For uncertain writes,
check the provider dashboard before retrying (especially domain purchases).
Do not share `.env`, API tokens, PATs, or app passwords.

### “No Cloudflare account visible to token”

A successful token verification means the token is **active**, not that it
can list accounts, read your domain, or create a zone. This failure happens
before this run creates a zone or attempts a GoDaddy nameserver change.

1. Open [Cloudflare API tokens](https://dash.cloudflare.com/profile/api-tokens)
   and edit the token. Under **Account Resources**, include the intended
   account; under **Zone Resources**, include its zones (or your existing
   domain). Zone creation needs **Zone → Zone → Edit**; destination
   registration needs **Account → Email Routing Addresses → Edit**.
2. If listing still exposes no account, open the
   [Cloudflare dashboard](https://dash.cloudflare.com/), select the account/domain,
   and copy its **Account ID** (not Zone ID). Add `CF_ACCOUNT_ID=<account ID>`
   to `.env`. This bypasses account discovery **only**; zone permissions and
   resource scope still apply. If your domain already exists but was not
   found, fix its token scope before trying to create it again.
3. If you create a replacement token, update `CLOUDFLARE_API_TOKEN` locally
   in `.env`, then rerun `./cmail setup`.

When multiple accounts are visible, setup lists them and asks you to select
one using `CF_ACCOUNT_ID` rather than silently choosing the first.

### Other steps

| Step / symptom | How to unblock |
|---|---|
| Dependency install fails | Check connectivity and package-manager/sudo access, install the named package manually, then check PATH. The GoDaddy installer places `gddy` in `~/.local/bin`. |
| Configuration cannot load / missing input | Check `.env` is writable by you, valid Bash assignments, and private (`chmod 600`). Set `DEST_EMAIL`, `ADDRESSES` (local parts only), and run setup interactively. |
| GoDaddy authentication/domain access | Use the correct account and `GDDY_ENV`; run `gddy auth login --env prod` (or `ote`), or replace an expired PAT locally. Check your domain/order history before repeating an uncertain purchase. |
| Nameserver lookup/update fails | Compare GoDaddy domain → DNS → Nameservers with Cloudflare domain → Overview. Verify a failed update's outcome before retrying; preserve/migrate existing DNS records first. |
| Zone stays pending | Verify both assigned nameservers at GoDaddy. Propagation can take 24–48 hours; rerun once Cloudflare shows Active. API/auth errors fail immediately instead of being treated as propagation. |
| HTTP 401/403 | Check token activity, operation-specific permission, and account/zone resource scope at the token settings URL. |
| Network / HTTP 429 / HTTP 5xx | Fix DNS/proxy/connectivity, wait after rate limiting, or check [Cloudflare status](https://www.cloudflarestatus.com/). Inspect the dashboard before retrying an uncertain write. |
| Email Routing activation fails | Check Email → Email Routing and conflicting MX/TXT records. Do not delete existing mail-provider records without planning migration. |
| Destination verification times out | Sign into the correct destination mailbox, check Inbox/Spam, click the Cloudflare link. Resend missing/expired links in Email Routing → Destination addresses; pending entries are kept. |
| Existing forwarding rule conflicts | In Email Routing → Routing rules, enable/correct the address's rule to forward to `DEST_EMAIL`. Setup will not overwrite it or report a wrong/disabled rule as ready. |
| Gmail send-as is blocked (`./cmail send-as`) | Enable 2-Step Verification and use a Google App Password, not the login password. Account policy may prohibit app passwords; use an approved SMTP provider instead. Check username, port 587/TLS, and the confirmation email. Receiving is unaffected. |

After setup, use a **different mailbox** to test inbound forwarding. If you ran
the optional `send-as` step, also send from the custom alias to that mailbox and
check the From address and delivery. Pressing Enter does not verify Gmail setup.

## Troubleshooting Email Routing

Email Routing activation uses `POST /zones/{zone_id}/email/routing/dns`
([Cloudflare API documentation](https://developers.cloudflare.com/api/resources/email_routing/subresources/dns/methods/create/))
and requires **Zone → Zone Settings → Edit**. If your token was created
using the earlier three-permission instructions, add this permission to
it in [Cloudflare's API token settings](https://dash.cloudflare.com/profile/api-tokens).
Ensure its zone resources include your domain, then rerun `./cmail setup`.
If you create a replacement token, update `CLOUDFLARE_API_TOKEN` in `.env`.

Destination addresses use the account-scoped endpoint
`/accounts/{account_id}/email/routing/addresses`
([Cloudflare API documentation](https://developers.cloudflare.com/api/resources/email_routing/subresources/addresses/methods/create/)).
Add **Account → Email Routing Addresses → Edit** to your token and include
the account that owns your domain under **Account Resources**. The script
reads that account ID from the selected zone; no manual account ID is needed.
Existing verified or pending destinations are reused rather than recreated.

Activation and destination failures include the HTTP status and Cloudflare
error body; network failures retain curl's diagnostic. Token verification only checks
that the token is active, not that it has every required permission.

## Tests

Run the offline regression tests (requires Bash and `jq`; the installer suite
itself only needs Bash and standard utilities):

```bash
bash tests/godaddy_test.sh
bash tests/cloudflare_test.sh
bash tests/cloudflare_dest_test.sh
bash tests/cloudflare_rules_test.sh
bash tests/cloudflare_setup_test.sh
bash tests/workflow_guidance_test.sh
bash tests/install_test.sh
python3 tests/skill_setup_test.py   # optional skill/config suite; needs Python 3
node --test tests/checklist_test.js # static checklist unit tests; Node 18+
python3 tests/site_test.py          # offline docs/link/contrast contract tests
```

GoDaddy, Cloudflare and installer downloads are mocked; the tests do not change
any live DNS settings. The installer suite verifies runnable help, complete
runtime downloads, private config/upgrade preservation and failure/conflict
handling, including paths with spaces and shell metacharacters.

The static site has no frontend build or production dependencies. Optional real
browser tests use an externally installed Playwright and Chromium/Chrome:

```bash
node --test tests/site_browser_test.cjs
```

If Playwright is outside the normal module search path, set `NODE_PATH` to its
containing `node_modules`. Set `CHROME_BIN` to a trusted browser executable to
use an existing Chrome instead of Playwright's bundled browser. Optional
`SCREENSHOT_DIR` stores review screenshots outside the source tree. The test
server is loopback-only; all external browser requests are blocked. The suite
checks keyboard controls, persistence/reset, malformed/blocked storage, no-JS,
and 375/768/1280px layouts; it never calls live providers.

## Website deployment

[GitHub Pages](https://luongnv89.github.io/cmail/) is the site destination.
The [Pages workflow](.github/workflows/pages.yml) validates the documentation,
checklist and staged artifact, then deploys updates after relevant changes land
on `main`. Pull requests validate without deploying. To redeploy, choose
**Actions → Deploy documentation to GitHub Pages → Run workflow → main**.
The `github-pages` environment shows the actual deployment URL/status.

Pages must be enabled with **Settings → Pages → Source: GitHub Actions**;
private repositories also require an eligible GitHub plan. Pages publishes the
website, not the repository: source/skill/installer links still require repository
access while private. No billing or repository visibility change is automated.

Only the six files allowlisted in [the staging script](scripts/build-pages.sh)
are published. Preview the exact artifact with `bash scripts/build-pages.sh`,
then `python3 -m http.server 8000 --bind 127.0.0.1 --directory _site`.
Use a fresh staging directory; the script refuses an existing `_site` rather
than overwriting it. Validate offline with `python3 tests/pages_test.py`
(no publication or provider calls).

## Requirements

Linux or macOS. Runtime tested on Arch Linux; the offline installer suite also
runs on macOS Bash 3.2. Setup/doctor install missing dependencies themselves
(`pacman`/`apt`/`brew` for `jq`/`curl`; official installer for `gddy`).

## Limitations

- Cloudflare only **forwards** mail — no mailbox/storage (your destination
  inbox's storage is used).
- Optional outbound via Gmail isn't DKIM-signed with your domain — fine for
  personal use; upgrade to Google Workspace if deliverability matters.
- Gmail sending limits and third-party send-as availability are Google/account
  dependent; see the January 2027 policy warning above. Neither CLI completion nor
  offline tests guarantee Gmail acceptance, DKIM alignment or delivery.
