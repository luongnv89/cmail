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
2. **GoDaddy** — `gddy auth login` opens a browser OAuth consent screen
3. **Cloudflare** — opens the API-token page with the exact permission
   list to pick; the token is verified automatically and stored in `.env`
4. **Domain** — pick one from your GoDaddy account (or register a new one
   via `gddy`, with an explicit price confirmation)
5. **Nameservers** — Cloudflare zone is created and GoDaddy nameservers
   are pointed at it automatically
6. **Email Routing** — enabled via the Cloudflare API (MX/SPF/DKIM/DMARC
   records are auto-created)
7. **Destination** — your Gmail is registered; you click the verification
   email while the script polls until it's confirmed
8. **Addresses** — unlimited forwarding rules (`hello@`, `contact@`, …)
   created via API
9. **Send-as** — Gmail outbound needs an app password, so this last step
   is guided manually (script deep-links the right settings page)

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
| `CLOUDFLARE_API_TOKEN` | CF token (Zone:Edit, DNS:Edit, Email Routing Rules:Edit) |
| `GDDY_ENV` | GoDaddy environment (default `prod`) |
| `GDDY_PAT` | Optional — PAT instead of OAuth for headless runs |
| `CF_ZONE_ID` | Auto-populated by `setup` — Cloudflare zone ID, used by `status` |
| `DRY_RUN` | `1` previews the nameserver change without applying it |

## What is NOT automated (and why)

- **Cloudflare API token** — Cloudflare has no self-service OAuth for
  arbitrary scripts; the script opens the token page, lists the three
  permissions to add, then verifies whatever you paste.
- **Destination verification** — Cloudflare emails a link to your Gmail;
  you must click it (script waits and continues automatically).
- **Gmail "Send mail as"** — automating it needs the restricted
  `gmail.settings.*` OAuth scope, which requires a verified Google Cloud
  app — disproportionate for a personal setup. Guided manual instead.
- **Domain purchase** — supported via `gddy` but always asks before
  spending money.

## Requirements

Linux or macOS. Tested on Arch Linux. Installs missing deps itself
(`pacman`/`apt`/`brew` for `jq`/`curl`; official installer for `gddy`).

## Limitations

- Cloudflare only **forwards** mail — no mailbox/storage (Gmail's storage
  is used).
- Outbound via Gmail isn't DKIM-signed with your domain — fine for
  personal use; upgrade to Google Workspace if deliverability matters.
- Gmail cap: ~500 sends/day.
