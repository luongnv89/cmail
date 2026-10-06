# cmail

Interactive setup for a **free custom-domain email address** using
**Cloudflare Email Routing** (receive) + **Gmail "Send mail as"** (send).

Inspired by this [Tokifyi thread](https://x.com/tokifyi/status/2025741929997361371):
$0/month for email — you only pay for the domain itself.

## Quickstart

```bash
git clone https://github.com/luongnv89/cmail && cd cmail
./cmail setup
```

The script walks you through each step. Authentication is browser-based
(OAuth) wherever possible:

1. **Dependencies** — installs `gddy`, `jq`, `curl` if missing
2. **Configuration** — collect your destination Gmail and forwarding local parts
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
10. **Destination** — register/reuse your Gmail; click the verification
    email while the script polls until confirmed
11. **Addresses** — create forwarding rules (`hello@`, `contact@`, …);
    conflicting or disabled existing rules require your attention
12. **Send-as** — guided manual Gmail setup with an app password;
    test inbound and outbound separately (not automatically verified)

Re-runnable and idempotent — state lives in `.env`, existing resources
are detected and skipped.

## Commands

| Command | Description |
|---|---|
| `./cmail setup` | Full guided setup |
| `./cmail status` | Show zone, routing, destination, and rule state |
| `./cmail doctor` | Check tools + auth without changing anything |

## Configuration

Copy `.env.example` to `.env` (the setup does this for you). `.env` is
git-ignored and `chmod 600`.

| Var | Meaning |
|---|---|
| `DOMAIN` | Custom domain to use |
| `DEST_EMAIL` | Gmail address that receives forwarded mail |
| `ADDRESSES` | Comma-separated local parts, e.g. `hello,contact,me` |
| `CLOUDFLARE_API_TOKEN` | CF token: Zone permissions (Zone:Edit, Zone Settings:Edit, DNS:Edit, Email Routing Rules:Edit) plus Account permission (Email Routing Addresses:Edit) |
| `GDDY_ENV` | GoDaddy environment (default `prod`) |
| `GDDY_PAT` | Optional — PAT instead of OAuth for headless runs |
| `CF_ZONE_ID` | Auto-populated by `setup` — Cloudflare zone ID, used by `status` |
| `CF_ACCOUNT_ID` | Optional 32-character account ID from the Cloudflare dashboard; skips account discovery when creating a zone, and selects the intended account when several are visible. Does not grant API permissions. |
| `DRY_RUN` | `1` previews the nameserver change without applying it |

## What is NOT automated (and why)

- **Cloudflare API token** — Cloudflare has no self-service OAuth for
  arbitrary scripts; the script opens the token page, lists the five
  permissions to add, then verifies whatever you paste.
- **Destination verification** — Cloudflare emails a link to your Gmail;
  you must click it (script waits and continues automatically).
- **Gmail "Send mail as"** — automating it needs the restricted
  `gmail.settings.*` OAuth scope, which requires a verified Google Cloud
  app — disproportionate for a personal setup. Guided manual instead.
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
| Destination verification times out | Sign into the correct Gmail account, check Inbox/Spam, click the Cloudflare link. Resend missing/expired links in Email Routing → Destination addresses; pending entries are kept. |
| Existing forwarding rule conflicts | In Email Routing → Routing rules, enable/correct the address's rule to forward to `DEST_EMAIL`. Setup will not overwrite it or report a wrong/disabled rule as ready. |
| Gmail send-as is blocked | Enable 2-Step Verification and use a Google App Password, not the login password. Account policy may prohibit app passwords; use an approved SMTP provider instead. Check username, port 587/TLS, and the confirmation email. |

After the manual Gmail step, use a **different mailbox** to test inbound
forwarding, then send from the custom alias to that mailbox and check the
From address and delivery. Pressing Enter does not verify Gmail setup.

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

Run the offline regression tests (requires Bash and `jq`):

```bash
bash tests/godaddy_test.sh
bash tests/cloudflare_test.sh
bash tests/cloudflare_dest_test.sh
bash tests/cloudflare_rules_test.sh
bash tests/cloudflare_setup_test.sh
bash tests/workflow_guidance_test.sh
```

GoDaddy and Cloudflare calls are mocked; the tests do not change any live
DNS settings.

## Requirements

Linux or macOS. Tested on Arch Linux. Installs missing deps itself
(`pacman`/`apt`/`brew` for `jq`/`curl`; official installer for `gddy`).

## Limitations

- Cloudflare only **forwards** mail — no mailbox/storage (Gmail's storage
  is used).
- Outbound via Gmail isn't DKIM-signed with your domain — fine for
  personal use; upgrade to Google Workspace if deliverability matters.
- Gmail cap: ~500 sends/day.
