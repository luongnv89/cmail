Current-runtime note: `0.2.0-dev` supports full read-only previews and requires
terminal stdin for guided setup. Follow the capability gate in
`autonomous-run.md` before choosing execution recipes below. A setup timer
measures configuration; independent delivery remains Gate 9 evidence.

# Verification matrix

Use the selected trusted launcher (installed, or source `./cmail`) and always pass
the selected config as `ENV_FILE`. The current installer pins legacy v0.1.0;
these gates support it and the reviewed current source, with different setup
completion evidence at gate 8. Record trusted offline help capabilities at gate 1.
**You run every check below** unless it is marked hands-on.
Hands-on evidence comes from the user as a sanitized observation (exact
domain/account, state, time), labelled user-reported. With no evidence, the gate
is BLOCKED. Do not call internal Bash helpers as a public API.

## Gate 1 — Installed CLI and dependencies

- Prerequisite: supported macOS/Linux shell on the target machine.
- Action: discovery and the pre-execution provenance check in SKILL.md (Bash
  `type -t cmail`, zsh `whence -w cmail`); only then trusted absolute-path help,
  or read-then-run `bash install.sh`. Read the trusted launcher's
  `default_config=` line as metadata for gate 2, never by executing it. Install
  missing curl/jq/gddy per SKILL.md.
- Verify: provenance and user-controlled path/runtime established before executing
  help (not just an alias/function or familiar output); help loads without missing
  libraries and lists setup/status/doctor/help. Bash is 3.2+; curl/jq/gddy/dig
  version/help succeeds.
- Failure: command missing differs from corrupt runtime or wrong binary.
- Repair/recheck: reinstall with the same user-owned paths or install the tool;
  repeat discovery/help and every missing-tool check.

## Gate 2 — Inputs and config

- Prerequisite: gate 1 and a selected config path.
- Action: create/complete the config per `configuration.md`; non-secret keys via
  `set_config.py`, the token by the user in their editor (hands-on).
- Verify: summary prints READY; checker exits 0; `bash -n` privately exits 0;
  config is not tracked by git. Secret presence is not credential validity.
- Failure: absent field, syntax error, insecure permissions or executable expansion.
- Repair/recheck: `set_config.py` for non-secret keys, `chmod 600` for mode, the
  user's editor for the token or complex lines; repeat summary and both checks.

## Gate 3 — Registrar authentication and domain ownership

- Current CLI manual mode (`REGISTRAR=manual`, default): no gddy or GoDaddy
  auth. Verify with the user's ownership statement for the exact domain
  (user-reported) and gate 4's zone read; never offer a purchase.
- Prerequisite: gates 1–2.
- Action: preflight auth status; background `gddy auth login --env <env>` when
  needed (hands-on browser approval); filtered `gddy domain get`.
  Values in angle brackets are data, not literal commands; validate and quote them.
- Verify: unexpired auth for the selected environment (or a PAT whose domain read
  succeeds); exact domain read succeeds and current nameservers are readable.
  An OTE sandbox does not prove production ownership; live setup stays BLOCKED
  until prod is selected and this gate is rechecked.
- Failure: authentication/lookup error, wrong environment/account or no ownership.
- Repair/recheck: renew login, correct account/environment, repeat the domain
  read. An unowned domain is a purchase stop (exact domain, price, prod). After a
  purchase timeout check orders/billing/ownership; never auto-repurchase.

## Gate 4 — Cloudflare token, account and zone

- Prerequisite: gates 1–3 and the token in config.
- Action: setup pass 1 checks the **actual configured token** (`/user/tokens/verify`),
  finds or creates the zone (`/zones?name=<domain>`, `/zones/<zone-id>`) and
  reads its nameservers. `cmail status` then reads `/zones/<zone-id>` and
  `/accounts/<owning-account-id>/email/routing/addresses`. cmail requires HTTP 2xx
  and API success for each request and redacts the token from errors.
- Verify: log shows `Cloudflare token verified` and `zone <id> — nameservers`
  (at least two); `status` succeeds for the exact zone and lists destinations of the
  owning account. Dashboard login/visibility and configured scopes do not prove
  token resource access; missing or failed reads mean BLOCKED.
  Read access does not prove write permission; later gates check each write.
  CF_ACCOUNT_ID bypasses discovery, not authorization.
- Failure: 401/403, no visible account, multiple accounts, invalid ID or wrong zone.
- Repair/recheck: multiple accounts → stop to choose, then `set_config.py
  CF_ACCOUNT_ID=<id>`; scope errors → the user edits the token's resources
  (hands-on; never "all accounts"); rerun pass 1. Never create a duplicate zone.

## Gate 5 — Delegation and active zone

- Prerequisite: gates 1–4; public DNS inventory; nameserver approval naming the
  domain and full replacement set (the stop in `autonomous-run.md`), unless the
  nameservers already match. No approval means BLOCKED.
- Action: pass 2 applies the approved change; setup then polls for Active.
  `DRY_RUN=1` is a nameserver preview only; it cannot satisfy this gate.
- Verify: fresh filtered `gddy domain get` shows exactly the assigned set
  (case/order/trailing-dot normalized); `status` shows zone status `active`;
  `dig +short NS` corroborates. In manual mode, the user changes nameservers at
  their registrar (hands-on), or the zone is already active. `status` `active`
  plus `dig +short NS` showing the assigned set verifies it. A submitted change is not active-zone evidence.
- Failure: failed read, uncertain write, mismatch, pending activation or broken DNSSEC.
- Repair/recheck: read registrar state before any retry; propagation can take
  24–48 hours — report PENDING and rerun pass 1 later, not the write. Never auto-roll back.

## Gate 6 — Email Routing active

- Prerequisite: gates 1–5; no unresolved non-Cloudflare MX (preflight stop).
- Action: setup enables routing, which adds and locks Cloudflare MX/TXT records.
- Verify: `status` email routing reports enabled/ready for the exact zone and
  `dig +short MX` returns Cloudflare's `route*.mx.cloudflare.net` hosts.
  `email routing: ?` or `status` exit 0 alone is not readiness.
- Failure: permission error, disabled/unknown status, DNS conflicts.
- Repair/recheck: Zone Settings permission (hands-on token edit) or a record
  migration plan (stop); never auto-delete MX/TXT. Rerun pass 1, repeat both checks.

## Gate 7 — Verified destination

- Prerequisite: gates 1–6 and access to DEST_EMAIL.
- Action: setup registers DEST_EMAIL (Cloudflare emails a link) or reuses it.
  Hands-on: the user clicks the link in that mailbox (any provider).
- Verify: `status` lists DEST_EMAIL with a `verified=<timestamp>`, not `verified=no`.
- Failure: wrong mailbox/account, missing/expired link, timeout or unverified state.
- Repair/recheck: Inbox/Spam in the correct account; resend from Cloudflare →
  Email Routing → Destination addresses (hands-on); rerun pass 1. Never duplicate.

## Gate 8 — Exact enabled forwarding rules

- Prerequisite: gates 1–7.
- Action: setup creates one rule per ADDRESSES local part and refuses to change a
  conflicting, disabled or duplicate rule.
- Verify: require **both** completion evidence and fresh exact-rule evidence:
  - Completion evidence is **either** a trusted current runtime whose setup
    printed `Receiving is set up` **and** exited 0, **or** a trusted legacy runtime
    whose offline help lacks `send-as`, with the exact checkpoint
    `Setup stopped at: Send FROM your custom address (manual, ~5 min)` **and**
    `Gmail guide paused without input` **after all receiving stages** in that
    same setup pass. The legacy pause exits nonzero; it is not a receiving failure.
  - In **both cases**, `ENV_FILE="$cfg" "$launcher" status` must succeed and list
    each requested `<local>@<domain> -> DEST_EMAIL [true]` exactly once, to the
    intended DEST_EMAIL. Inspect all entries for each requested alias: a duplicate
    with another target or disabled flag still fails. Unrelated aliases may exist.
- Failure: missing, incomplete, conflicting, disabled, duplicate or wrong-target
  rule; untrusted runtime, missing completion evidence, or any failure before
  the checkpoint is not success. A Gmail mention or missing `send-as` alone is
  insufficient; a current summary with nonzero exit is not completion.
- Repair/recheck: show the sanitized conflict and stop before correcting it;
  never overwrite unrelated rules. Rerun pass 1 and repeat both checks.

## Gate 9 — Inbound delivery, plus optional sending

- Prerequisite: gates 1–8, access to DEST_EMAIL and a different independent
  mailbox. Sending checks apply only when the user asked to send from the custom
  address; they also need DEST_EMAIL to be a Gmail/Google account.
- Action: hands-on. For every requested alias, the user sends a unique test from
  the independent mailbox to that alias. Only when sending was requested: run
  `cmail send-as` (see `autonomous-run.md`) and open Gmail Settings → Accounts and
  Import → Send mail as → Add another email address for the user. For every
  alias: SMTP smtp.gmail.com, port 587/TLS, full DEST_EMAIL username, Google App
  Password entered only in Gmail. The user completes the emailed confirmation.
- Verify: each alias's test arrives in DEST_EMAIL (check Spam). When sending was
  requested, also: each alias is confirmed in Gmail settings, and a message from
  Gmail with that custom From to the independent mailbox arrives with the exact
  From (check Spam, not just Sent). Record alias/direction/time, not message
  bodies or codes. These tests do not prove universal deliverability.
- Failure: inbound undelivered; when sending was requested, also unavailable App
  Password, SMTP rejection, unconfirmed alias or outbound undelivered. CLI exit or
  Enter does not verify any of these.
- Repair/recheck: inbound or confirmation missing → recheck gates 5–8. Outbound →
  SMTP host/port/TLS/username/App Password; enable 2-Step Verification if allowed;
  respect organization policy/Advanced Protection — an alternative provider is
  outside this skill, so stop BLOCKED for sending (receiving stays verified).
  Repeat every required test per alias. Never disable security controls.
