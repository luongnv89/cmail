# cmail: first-time setup

[Introduction](index.html) · [Interactive checklist](setup.html) · [Runtime README](https://github.com/luongnv89/cmail/blob/main/README.md) · [Agent skill](https://github.com/luongnv89/cmail/blob/main/skills/cmail-setup/SKILL.md)

This sequence is Cloudflare incoming forwarding to any inbox you own (Gmail,
Outlook, iCloud, Proton, …) plus an **optional** manual Gmail send-as step for
sending, not mailbox hosting or Google Workspace provisioning. If you only need
to receive mail, skip step 13. The HTML guide has enabled, keyboard-operable
checkboxes, saved progress and reset. GitHub Markdown checkboxes
are a reading/printing fallback, not persistent interactive controls.

**The short version: a few simple steps.** Check prerequisites (step 1), install
cmail (step 2), run `cmail setup`, then send yourself a test (step 14).
`cmail setup` carries out steps 3–12 for you and pauses only for browser approvals, the Cloudflare token,
the nameserver confirmation and one verification click; read those steps to
review or troubleshoot. **Sending is optional and only on request:** step 13
(`cmail send-as`) is not part of the default setup.

**Before choosing Gmail for (optional) sending:** [Google’s current Send as help](https://support.google.com/mail/answer/22370)
announces removal of third-party Send as starting **January 2027**. Inbound
forwarding is separate and needs no Google account. Check the current policy and
account eligibility; an alternative SMTP service/Workspace migration is outside
this guide.

Public authoritative references were fetched 7 October 2026. Dashboard labels and
policies may change. No logged-in provider actions, DNS writes, purchases or live
mail delivery were tested. Never give this page, browser storage, chat, captured
agent tools or screenshots your tokens, passwords, config or confirmation codes.
The checklist stores only allowlisted step IDs and booleans, local to the browser
profile/site origin; it is your review record, not live verification.

## Ordered checklist

### 1. Prerequisites

- [ ] Verify prerequisites and migration impact.

Use macOS/Linux with a trusted terminal, Bash 3.2+, curl and standard utilities.
Git is needed only to clone source; Python 3 is optional for the checker. Have an
owned GoDaddy domain, a Cloudflare account, a receiving inbox (any provider; a
Gmail/Google account only if you also want to send) and a **different mailbox**
for tests. Choose DOMAIN (bare domain), DEST_EMAIL (full receiving address),
ADDRESSES (comma-separated local parts, e.g. `hello,contact`) and whether any
aliases need sending. Inventory existing web/mail/MX/TXT/subdomain DNS and
DNSSEC/DS records. Plan migration before changing anything. Only if sending: check
Google policy and whether App Passwords are permitted. Missing access is not a
purchase signal.

### 2. Install from reviewed source

- [ ] Verify the trusted CLI and select the actual config path.

Obtain/review the [upstream default-branch source](https://github.com/luongnv89/cmail)
(clone, or unpack its source archive). A clone route after review:

```bash
git clone https://github.com/luongnv89/cmail
cd cmail
bash install.sh
"$HOME/.local/bin/cmail" help
export PATH="$HOME/.local/bin:$PATH"
cmail help
```

Installer bootstrap requires Bash/curl/standard utilities, not jq/gddy/sudo/provider
access. It downloads the pinned v0.1.0 runtime, does not run setup or edit profiles.
v0.1.0 itself has neither installer nor newer skill/checker. Keep the checkout for
the checker. No released remote bootstrap or Homebrew package is promised.
[Distribution contract](distribution.md): paths, upgrades, limitations and status.

Defaults: launcher `~/.local/bin/cmail`, runtimes `~/.local/share/cmail/runtime.*`,
config `~/.config/cmail/.env`. Absolute install overrides: CMAIL_BIN_DIR,
CMAIL_DATA_DIR, CMAIL_CONFIG_DIR. All paths/parents must be user-controlled and
non-symlink; existing config is preserved. Runtime ENV_FILE overrides config;
source `./cmail` defaults to checkout `.env`. Do not edit retained runtime config.
Help must load setup/status/doctor/help offline; this proves no provider readiness.

### 3. Prepare runtime tools

- [ ] Verify Bash, curl, jq, gddy and command compatibility.

Privately check `bash --version`, `curl --version`, `jq --version`, `gddy --version`
and `gddy --help`. Install missing curl/jq with your existing package manager;
review [gddy’s official installer](https://developer.godaddy.com/en/docs/api-users/cli/set-up)
before execution. Its `~/.local/bin` needs PATH. Compare `gddy tree`/help against
cmail’s domain/nameserver commands. Newer purchase syntax may differ from pinned
cmail; stop on incompatibility and use staged dashboard actions instead.
`cmail setup`/`doctor` may install missing tools; `status`/`doctor` can create/secure
local config. Doctor can print non-secret config and is not the safe checker.

### 4. GoDaddy authentication and existing domain

- [ ] Verify exact-domain access, production ownership and current nameservers.

Prefer local browser OAuth: `gddy auth login --env prod`, sign in to the intended
account and review consent. Privately inspect `gddy auth status --json` for expiry
and `gddy domain get 'example.com' --env prod --json` (replace example.com with your
owned domain). Compare GoDaddy domain portfolio → exact domain → DNS → Nameservers.
Set GDDY_ENV=prod for real resources; ote is a sandbox, not production evidence.

For optional headless PAT, sign in to [Personal Access Tokens](https://developer.godaddy.com/personal-access-token)
→ + Generate Token → descriptive name, expiration, scopes. Expand Domains & DNS:
`domains.domain:read` for reads; `domains.nameserver:update` only for approved
nameserver replacement; `domains.domain:create` only for separately approved
registration. Generate and copy the one-time secret to a password manager/private
local GDDY_PAT config. OAuth needs no PAT.

[Current auth docs](https://developer.godaddy.com/en/docs/api-users/auth) use
`Authorization: Bearer <PAT>` for Domains v3 at `https://api.godaddy.com`; legacy
v1/v2 classic credentials use `Authorization: sso-key <key>:<secret>`. cmail has no
classic key/secret fields. The [inspected CLI environment defaults](https://github.com/godaddy/cli/blob/c6d47e1432849e6cef8811d262c8773147a55131/rust/src/environments/mod.rs)
map prod to api.godaddy.com and ote to api.ote-godaddy.com; config can override URLs.
Its [Domains client](https://github.com/godaddy/cli/blob/c6d47e1432849e6cef8811d262c8773147a55131/rust/domains-client/src/lib.rs)
sets Authorization/x-request-id, **not an environment-selector header**. cmail
passes `--env` to gddy, not raw headers. Verify your installed CLI’s endpoints;
never assume an OTE header/credential makes a production URL safe. Auth status,
PAT presence and new v3 docs do not prove pinned-runtime compatibility/access.

If unowned, stop and register deliberately through GoDaddy after reviewing exact
domain, price, renewal, term, contacts and billing, then repeat ownership read.
cmail’s blank-DOMAIN picker can offer registration and asks before attempt/quoted
purchase; prefilled DOMAIN skips the picker. An access error is not proof of
non-ownership. A purchase timeout requires orders/billing/ownership inspection
before any retry, not automatic repurchase.

### 5. Cloudflare account, zone and IDs

- [ ] Identify the owning account, exact zone and assigned nameservers.

Sign in to [Cloudflare](https://dash.cloudflare.com/), choose account and find the
domain under Domains (older layouts: Websites). Reuse it; if genuinely absent,
approve adding/onboarding the domain and plan, review DNS imports, finish onboarding
but do not change registrar nameservers yet. Never create a duplicate because a
token cannot see an existing zone.

Domain Overview → API section → copy Account ID and Zone ID separately; Account ID
also through dashboard Search → “Copy account ID”. These are 32 hex characters
identifying different resources. Record assigned nameservers, not examples.
CF_ACCOUNT_ID selects creation account/bypasses discovery only, no authorization;
set when zero/multiple accounts are visible. CF_ZONE_ID identifies this domain,
saved by setup and used by status. Destination calls use the zone’s owning account.
[Official ID instructions](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/).

### 6. Cloudflare user token

- [ ] Create/save the scoped token privately.

[My Profile → API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create
Token → Custom token / Get started. Use a user API token, not Global API Key.
Add exactly the five required operation permissions:

| Scope | Permission | Access |
|---|---|---|
| Zone | Zone | Edit |
| Zone | Zone Settings | Edit |
| Zone | DNS | Edit |
| Zone | Email Routing Rules | Edit |
| Account | Email Routing Addresses | Edit |

Zone Resources → Include specific existing domain, or intended account’s zones for
zone creation. Account Resources → Include the same owning account. Never grant
all accounts as an automatic fix. Review expiration/client IP restrictions,
Continue to summary → Create Token. Copy the one-time secret to secure local
storage and private CLOUDFLARE_API_TOKEN config (or CLI hidden prompt), never this
page/chat/screenshots. [Official token steps](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/).
Token active status is not proof of resource access or successful writes.

### 7. Private literal config and optional checker

- [ ] Check the selected config without sourcing or exposing it.

Pick installed default `~/.config/cmail/.env`, install-time CMAIL_CONFIG_DIR,
runtime ENV_FILE, or source `.env`. Preserve existing data. For a new default only,
from the reviewed checkout, after verifying user-owned non-symlink parents:

```bash
(umask 077; mkdir -p "$HOME/.config/cmail";
  cp -n .env.example "$HOME/.config/cmail/.env")
chmod 700 "$HOME/.config/cmail"
chmod 600 "$HOME/.config/cmail/.env"
```

Edit privately using `KEY='literal value'`, no duplicate/unknown keys or spaces
around `=`. Fill DOMAIN, DEST_EMAIL, ADDRESSES, CLOUDFLARE_API_TOKEN; explicitly set
GDDY_ENV=prod. GDDY_PAT is optional for OAuth; CF_ACCOUNT_ID/CF_ZONE_ID must match
resources if set. Optional DRY_RUN=0/1 previews nameservers only. **No Google App
Password in .env.** Runtime evaluates Bash config twice: forbid commands, `$()`,
backticks, expansions, scripts and multiline values; do not source to validate.

The newer source checkout, not the runtime installer, contains the checker:

```bash
python3 skills/cmail-setup/scripts/check_config.py "$HOME/.config/cmail/.env"
bash -n "$HOME/.config/cmail/.env" >/dev/null 2>&1
```

Use your selected path. Require both exits 0 and matching intent. The checker
never prints/sources values and checks user ownership, regular/non-symlink mode
600 file, known fields and conservative LF-only literal grammar. With no Python,
review these properties locally, do not claim checker PASS. In source checkout,
`git check-ignore .env` must pass and `git ls-files --error-unmatch .env` must fail.
Never commit config; rotate leaks. [Exact contract](https://github.com/luongnv89/cmail/blob/main/skills/cmail-setup/references/configuration.md).

### 8. Actual-token resource access

- [ ] Verify token activity plus exact zone/owning account access.

In a trusted unrecorded local API client using the actual configured token, read
GET `/user/tokens/verify`, `/zones/<zone-id>` and
`/accounts/<owning-account-id>/email/routing/addresses` under
`https://api.cloudflare.com/client/v4`. Protected local token input only, no shell
history, captured tools or shared headers/full responses. Follow
[the skill’s gate 4](https://github.com/luongnv89/cmail/blob/main/skills/cmail-setup/references/verification.md#gate-4--cloudflare-token-account-and-zone).

Require HTTP 2xx + API success for all reads, active token, exact domain/zone/owning
account match, assigned nameservers and readable destinations. Reads do not prove
write permissions; review grants and later resulting states. On 401/403 fix precise
permission/resource scope. Zero/multiple accounts may need correct CF_ACCOUNT_ID;
it bypasses discovery only. Empty zone listing does not prove absence: confirm
inventory before creating. Dashboard visibility alone is not token authorization.

### 9. Migrate DNS and delegate

- [ ] Verify complete nameservers and Active zone after migration.

Copy/review all existing web/mail/TXT/service DNS in Cloudflare; import may be
incomplete. Plan DNSSEC/DS transition so old DS does not invalidate delegation.
Compare GoDaddy DNS → Nameservers with Cloudflare’s complete assigned set. Matching
set needs no write. Otherwise approve exact domain/full replacement set and migrate
before changing through registrar dashboard/reviewed compatible CLI. This replaces
ALL nameservers and can disrupt sites/mail. Fresh registrar read must match and
Cloudflare must show Active; a submitted change is not activation. Public DNS NS
lookup is extra corroboration. Polling lasts about 20 minutes; allow 24–48 hours
propagation, wait/recheck rather than repeatedly writing. Inspect uncertain writes
before retrying; no automatic rollback.

**DRY_RUN is not globally safe:** `DRY_RUN=1 cmail setup` previews only nameserver
replacement. It can still create zones, enable routing/DNS, register destinations,
create rules and offer purchases. Monolithic setup does not enforce this staged
guide’s external gates. Prefer staged dashboards or the separate setup skill;
review every pending action before choosing the CLI.

### 10. Enable routing after mail migration review

- [ ] Verify fresh routing-enabled state and DNS requirements.

Current dashboard: Compute → Email Service → Email Routing → select/onboard domain
(older: domain → Email → Email Routing). Review proposed MX/TXT/SPF/DKIM and existing
mail conflicts before approving. Never auto-delete existing mail records or create
competing SPF records. cmail’s `POST /zones/{zone_id}/email/routing/dns` adds/locks
routing DNS, requires Zone Settings:Edit and reuses enabled routing. HTTP success
or status exit 0 is not readiness; inspect fresh state. Routing authentication is
not Gmail outbound domain DKIM alignment.
[Current routing guide](https://developers.cloudflare.com/email-service/get-started/route-emails/).

### 11. Verify destination

- [ ] Verify exact destination in zone’s owning account.

Email Routing → Destination Addresses, account-scoped: reuse verified/pending
DEST_EMAIL. If absent approve add/verification email. Open the correct mailbox
Inbox/Spam and click Cloudflare Verify email address yourself. Refresh until exact
entry has verified state/timestamp. For absent/expired link deliberately resend;
keep pending entries, do not duplicate. A click alone is not proof.

### 12. Exact forwarding rules

- [ ] Inspect one intended enabled rule for every alias.

Email Routing → domain → Routing Rules → Create routing rule. For each ADDRESSES
local part choose intended domain, Send to an email, verified DEST_EMAIL, review
and save. Inspect full details: correct enabled literal “to” matcher forwarding
to exactly destination; no conflicting duplicate, disabled rule or wrong action.
Catch-all not needed. Do not silently overwrite unrelated rules; approve correction
and inspect fresh state. Create success/truncated status does not prove correctness.

### 13. Optional: manual Gmail aliases for sending

- [ ] Confirm every eligible requested outbound alias, or skip sending.

**Skip this step if you only need to receive mail.** It applies only when you
want to send from the custom address and DEST_EMAIL is a Gmail/Google account.
`cmail send-as` prints the same guidance; `cmail setup` does not run it.

Recheck [January 2027 policy and alias instructions](https://support.google.com/mail/answer/22370).
If unavailable/prohibited, stop outbound and use an approved alternative outside
this guide. Google Account → Security → 2-Step Verification (if permitted), then
[App Passwords](https://myaccount.google.com/apppasswords) → descriptive Mail/cmail
name → create one-time password. [Restrictions](https://support.google.com/accounts/answer/185833):
security-key-only 2-Step Verification, work/school accounts or Advanced Protection
may not offer it. Never disable protections or use normal login password.
Changing Google password revokes App Passwords; revoke unused/leaked passwords.

Desktop Gmail → Settings → See all settings → Accounts and Import (or Accounts)
→ Send mail as → Add another email address. Enter your name and exact owned alias;
keep Treat as an alias for same-person aliases if shown. If SMTP is requested,
existing cmail path: smtp.gmail.com, 587, TLS, full DEST_EMAIL username, its App
Password entered directly in Gmail dialog **not .env, page, localStorage or chat**.
Never choose unsecured connection. Availability/acceptance remains Google-dependent.
Add Account / Send verification, receive via working forwarding rule and complete
link/code privately. Repeat each alias; inspect confirmed Gmail settings. Select
custom From when composing, intentionally choose default From/reply-to if desired.
Enter/CLI success/password creation/Sent entry is not delivery. Recipients may see
Gmail “on behalf of”; domain DKIM alignment is not guaranteed.

### 14. Independent delivery tests

- [ ] Observe inbound (and, if requested, outbound) receipt for every alias.

Send a unique benign test from a different mailbox to each alias; confirm in
DEST_EMAIL including Spam (same-account tests can be suppressed). Only if you set
up sending in step 13: compose from the exact custom From to independent mailbox; confirm recipient arrival, actual
From/reply-to, not just Sent. Reply back as extra check. Inbound failure: recheck
zone/routing DNS/destination/rule. Outbound failure: current policy, SMTP/TLS,
username/password/confirmation. Repair then repeat the affected tests. Record only sanitized
alias/direction/time/result privately, never bodies/secrets/codes. If sending was
requested and only inbound works, outbound is blocked, not completed. No universal delivery/compliance claim.
[Targeted troubleshooting](https://github.com/luongnv89/cmail/blob/main/skills/cmail-setup/references/troubleshooting.md).

## Local preview and maintenance

No frontend build or framework is required. From repository root run
`python3 -m http.server 8000 --bind 127.0.0.1`, then open
`http://127.0.0.1:8000/docs/` and `http://127.0.0.1:8000/docs/setup.html`.
Stop the server when done. Direct file opening works for reading/checking, but
browser file-origin persistence varies; use local HTTP to test reload progress.
Once Pages is enabled with **Source: GitHub Actions** on an eligible GitHub plan,
GitHub Actions validates and deploys the site when site files or the deployment
workflow change on `main`; manual runs on `main` are also supported
([workflow](https://github.com/luongnv89/cmail/blob/main/.github/workflows/pages.yml)).
Pull requests run validation without deploying. Only the explicitly listed site
files are uploaded, never private config, runtime or skill scripts
([staging script](https://github.com/luongnv89/cmail/blob/main/scripts/build-pages.sh)).
The Pages URL is shown in the deployment's `github-pages` environment.
GitHub source/skill links require repository access while the repository is private;
public website access does not grant access to the source or installer.

Browser progress uses only `cmail:setup-progress:v1`; reset removes that key alone.
Blocked storage/corruption shows a notice and leaves session checkboxes usable.
Reset failure can allow older saved progress to return after reload; the notice
explains that. Without JavaScript checkboxes work for this visit only, with no
misleading progress/reset controls. All details remain expanded when checked.

The optional skill is separate, not installed by the runtime installer; offline
evaluation cases are not a certified/measured live behavioral benchmark. No
repository license grants redistribution rights. Read the
[skill installation guide](https://github.com/luongnv89/cmail/blob/main/skills/cmail-setup/docs/README.md) before copying it.

Further official references: [GoDaddy PAT creation](https://developer.godaddy.com/en/docs/api-users/auth/how-to),
[production quickstart](https://developer.godaddy.com/en/docs/api-users/quickstart).
Keep the HTML and Markdown ordered steps/claims aligned when updating provider
instructions. Recheck authoritative links; never replace an access failure with
unconsented purchases or DNS changes.
