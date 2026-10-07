# Verification matrix

Use the selected installed launcher or source `./cmail`, with the selected config
path. Do not assume `cmail help`'s adjacent-config or “doctor changes nothing” text
matches the installed launcher: the launcher sets ENV_FILE and doctor mutates files.
The current installer pins v0.1.0; these gates are compatible with that runtime.

All provider commands below are **user-local**, unrecorded and without tracing.
The user returns a sanitized observation, not credentials or raw output. Dashboard
evidence is valid when it states the exact domain/account, observed state and time;
label it user-reported. If no evidence is available, stop BLOCKED. Do not invent
step subcommands or use internal Bash helpers as a public API.

## Gate 1 — Installed CLI and dependencies

- Prerequisite: supported macOS/Linux and a terminal; install consent if needed.
- Action: discovery and pre-execution provenance check as described in SKILL.md
  (Bash `type -t cmail`, zsh `whence -w cmail`); only then trusted absolute-path
  help, or reviewed `bash install.sh` if needed. Read the trusted launcher's
  `default_config=` line as metadata for gate 2, never by executing it.
  Discover Bash/curl/jq/gddy and guide missing tools.
- Verify: executable provenance and user-controlled path/runtime established before
  executing help (not just an alias/function or familiar output); help loads without missing libraries
  and lists setup/status/doctor/help. Bash is 3.2+; curl/jq/gddy version/help succeeds.
- Failure: command missing is different from corrupt runtime or wrong binary.
- Repair/recheck: fix current-session PATH or reinstall with the same user-owned
  paths after permission; repeat discovery/help and every missing-tool check.

## Gate 2 — Inputs and config

- Prerequisite: gate 1, agreed path and permission to edit config.
- Action: local assignment-only config per `configuration.md`; gather non-secret
  domain, destination Gmail, local parts, prod/ote and intended account.
- Verify: selected file is user-owned, regular, non-symlink and mode 600; required
  fields are literal/nonempty, addresses valid and environment explicit. Offline
  checker exits 0; `bash -n` privately exits 0. Check user intent against values
  locally. Secret presence is not credential validity.
- Failure: absent field, syntax error, insecure permissions or executable expansion.
- Repair/recheck: edit locally or chmod 600 after permission; repeat both checks.
  Do not source a downloaded config to learn its values.

## Gate 3 — Registrar authentication and domain ownership

- Prerequisite: gates 1–2; consent to local browser authentication.
- Action: prefer `gddy auth login --env prod` (use ote only if explicitly chosen).
  Optional PAT acquisition is local. Inspect `gddy auth status --json` and
  `gddy domain get <validated-domain> --env <prod-or-ote> --json` locally.
  Values in angle brackets are data, not literal commands; validate and quote them.
- Verify: authentication for selected environment is not expired; exact domain
  lookup succeeds in the intended account and current nameservers are readable.
  PAT set, an auth message, or DOMAIN set alone proves none of this. With a PAT,
  the successful domain read is essential; OAuth status may not describe PAT state.
  An OTE sandbox does not prove production ownership; live setup remains BLOCKED
  until prod is selected and this gate is rechecked.
- Failure: authentication/lookup error, wrong environment/account or no ownership.
- Repair/recheck: correct account/environment, renew locally, repeat exact domain
  read. For an unowned domain, stop; only offer purchase after ownership/availability
  checks and explicit domain/price/prod consent. A purchase timeout requires checking
  orders/billing/ownership first; never auto-repurchase. Verify ownership afterward.

## Gate 4 — Cloudflare token, account and zone

- Prerequisite: gates 1–3 and local token acquisition.
- Action: inspect Cloudflare token settings and domain Overview locally. Use a trusted
  user-local API client with the **actual configured token** to make read-only GETs
  to `/user/tokens/verify`, `/zones/<zone-id>` and
  `/accounts/<owning-account-id>/email/routing/addresses`. Take IDs from the intended
  domain's Overview and validate them first. Keep token input in protected local
  input/storage, not shell argv, chat or captured tools; do not source config to probe.
  Return only sanitized result/identity/time, never headers or full responses.
  For a genuinely absent zone, first check the actual token's `/zones?name=<domain>`
  result plus intended account access/scopes and dashboard inventory. An empty list
  alone cannot authorize creation. Obtain consent, create locally, then perform the
  exact-zone read before marking this gate VERIFIED.
- Verify: authenticated reads using that token return HTTP 2xx **and** API success;
  token is active; exact-zone result matches DOMAIN, zone ID and intended owning
  account ID, with at least two assigned nameservers; account-scoped address list
  is readable. Dashboard login/visibility and configured scopes alone do not prove
  token resource access. Missing/403/malformed read evidence means BLOCKED, even if
  the browser can change the resource. Confirm the five operation permissions in
  `configuration.md`. Read access does not prove write permission: record granted
  scopes and separately verify each consented operation's post-state in later gates.
  CF_ACCOUNT_ID bypasses discovery, not authorization.
- Failure: 401/403, no visible account, multiple accounts, invalid ID or wrong zone.
- Repair/recheck: select intended account; correct only the necessary resource scope
  or permission locally; repeat the same actual-token status and exact-zone/account
  authenticated reads. Do not
  use all accounts as an automatic workaround or create a duplicate zone.

## Gate 5 — Delegation and active zone

- Prerequisite: gates 1–4; inventory web/mail/TXT/other DNS and DNSSEC/DS; user has
  confirmed migration to Cloudflare and the DNSSEC transition plan. Specific consent
  names the domain and full replacement nameserver set. No consent means BLOCKED.
- Action: compare GoDaddy DNS → Nameservers with Cloudflare Overview. If different,
  guide the approved registrar update locally. If matching, no write is needed.
  `DRY_RUN=1` is a nameserver preview only; it cannot satisfy this gate.
- Verify: fresh registrar read/dashboard shows exactly the assigned nameserver set
  (case/order/trailing-dot normalized); Cloudflare exact domain shows Active.
  If available, a public DNS NS lookup independently corroborates delegation.
  A submitted nameserver change is not active-zone evidence.
- Failure: failed read, uncertain write, mismatch, pending activation or broken DNSSEC.
- Repair/recheck: inspect current registrar state before retrying a write; compare
  both dashboards and the DS plan. Pending propagation can take 24–48 hours; wait
  and repeat the same registrar/zone checks, not the write. Never auto-roll back.

## Gate 6 — Email Routing active

- Prerequisite: gates 1–5, planned existing-mail migration, explicit DNS/routing consent.
- Action: Cloudflare → domain → Email → Email Routing; enable only after user reviews
  conflicting MX/TXT. Activation adds/locks routing DNS records; it is a DNS write.
- Verify: exact domain routing is enabled and dashboard DNS requirements are satisfied;
  after any API activation, obtain a fresh read/dashboard state (not just HTTP 2xx).
  `cmail status` exit 0 or `email routing: ?` is not a readiness check.
- Failure: permission error, disabled/unknown status, DNS conflicts.
- Repair/recheck: correct Zone Settings permission/resource scope, plan record
  migration; do not auto-delete MX/TXT. Repeat fresh routing and DNS-requirements check.

## Gate 7 — Verified destination

- Prerequisite: gates 1–6 and access to DEST_EMAIL in the correct Gmail account.
- Action: Cloudflare Email Routing → Destination addresses; reuse existing entry.
  Register/resend only with consent to email; user clicks the verification link.
- Verify: exact destination in the zone's **owning account** has a verified timestamp
  / verified state in a fresh dashboard/list read. Pending entry or click alone fails.
- Failure: wrong Gmail/account, missing/expired link, timeout or unverified state.
- Repair/recheck: Inbox/Spam in the correct account; consented resend for expired link;
  repeat destination state check. Keep the pending entry; do not create duplicates.

## Gate 8 — Exact enabled forwarding rules

- Prerequisite: gates 1–7 and consent to create/correct rules.
- Action: Cloudflare Routing rules; inspect **every** ADDRESSES local part.
- Verify: for each `<local>@<domain>`, exactly one intended enabled literal `to`
  matcher forwards to exactly DEST_EMAIL; no disabled/conflicting duplicate or other
  action. Use full dashboard rule details, not a truncated status summary.
  After creation obtain a fresh read; a successful POST alone is insufficient.
- Failure: missing, conflicting, disabled, duplicate or wrong-target rule.
- Repair/recheck: show sanitized conflict to the user; correct only after consent,
  do not overwrite unrelated rules. Repeat full rule inspection for every alias.

## Gate 9 — Gmail confirmation and two delivery directions

- Prerequisite: gates 1–8, manual Gmail access and a different independent mailbox.
- Action: Gmail Settings → See all settings → Accounts and Import → Send mail as
  → Add another email address. For every requested alias: SMTP smtp.gmail.com,
  port 587/TLS, full DEST_EMAIL username, Google App Password entered only in Gmail.
  Complete emailed alias confirmation. Obtain consent for test messages.
- Verify: each exact alias is confirmed in Gmail settings. From the independent
  mailbox send a unique benign test to that alias; user confirms arrival in DEST_EMAIL.
  Then choose that custom From address in Gmail and send to the independent mailbox;
  confirm recipient arrival and exact From address (check Spam, not just Sent).
  Record alias/direction/time and user-reported delivery, not message bodies/codes.
  A reply back to the alias is a useful extra check. These tests do not prove universal
  deliverability, domain DKIM or compliance with Gmail sending limits.
- Failure: unavailable App Password, SMTP rejection, unconfirmed alias or either
  direction undelivered. CLI Enter/pause/exit success does not verify any of these.
- Repair/recheck: enable 2-Step Verification if allowed; respect organization policy/
  Advanced Protection. Use an approved alternative if App Passwords are prohibited,
  but that alternative is outside this skill; stop BLOCKED, not “Gmail complete”.
  For missing confirmation/inbound, recheck routing/destination/rules; for outbound,
  check SMTP username/port/TLS and current local password. Retry confirmation and
  **both** delivery tests after repair, per alias. Never disable security controls.
