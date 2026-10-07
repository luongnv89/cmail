# Recover without guessing

Start with the earliest failed gate. Use the gate the user named, the step in a
setup log's `Setup stopped at:` line, or find it by rerunning read-only checks in
gate order; do not open by asking which step failed. Read the `ERROR:` line for
the cause. For a hands-on check, ask only for its sanitized result and time; never
request full logs, `.env`, auth payloads, headers, codes, screenshots or secrets.

Each row: apply the repair yourself when marked **auto**, otherwise at a stop;
then rerun the original check (usually setup pass 1, which skips finished work).

| Stopped at / observation | Repair | Original check to repeat |
|---|---|---|
| cmail not on PATH | **auto:** call the trusted launcher by absolute path | `command -v cmail`, launcher `help` |
| Missing library / broken launcher | **auto:** rerun the reviewed installer with the same user-owned paths; config is preserved | Installed `help`, intended runtime |
| Installer HTTPS/download failure | **auto:** retry once; then stop with connection/proxy evidence. Never disable TLS or use HTTP | Installer, then launcher help |
| Unmanaged path/symlink refused | Stop: propose separate user-owned absolute dirs; never delete unrelated files | Installer plus launcher help |
| `Dependencies` | **auto:** brew install curl/jq or the read official gddy installer; sudo is a stop | Each tool's version/help |
| `Configuration` | **auto:** `set_config.py` for empty non-secret keys and `DRY_RUN=0`; token or complex lines are hands-on | Summary READY, checker, private `bash -n` |
| `GoDaddy authentication` | **auto:** background `gddy auth login --env <env>`; user approves; expired PAT is hands-on | Exact filtered domain read |
| `Choose domain` | DOMAIN was empty: fill it (auto from known input, else ask). Never purchase without the purchase stop | Summary shows DOMAIN; domain read |
| Purchase timed out | Stop: check orders, billing and ownership; never replay a purchase | Exact ownership read |
| `Cloudflare API token` | Hands-on: user creates or replaces the token in their editor; a network/5xx error is not a bad token | Pass 1 shows `token verified` |
| `Cloudflare zone:` 401/403 | Hands-on: user fixes the token's Account/Zone Resources; never widen to all accounts | Pass 1 zone line, then `status` |
| `Cloudflare zone:` multiple accounts | Stop: user picks the account from the listed names; **auto:** `set_config.py CF_ACCOUNT_ID=<id>` | Pass 1 zone line |
| Stale CF_ZONE_ID in `status` | Setup replaces it on its next pass; for `status` alone, stop to compare domain and owner, then **auto:** set the confirmed ID | `status` for the exact zone |
| `GoDaddy: point` with `aborted before nameserver change` | Not a failure: the nameserver approval stop in `autonomous-run.md` | Approved pass 2 |
| `GoDaddy: point` (write failed or uncertain) | **auto:** filtered `gddy domain get`; compare with the desired set before any retry | Fresh nameserver comparison |
| `Waiting for zone activation` | `zone still` after `nameservers set`: PENDING, wait and rerun pass 1 later. No `nameservers set` line: check DRY_RUN and registrar nameservers. `needs attention`: stop with the zone status | Zone `active` in `status` |
| `Enable Cloudflare Email Routing` | Permission → hands-on token edit; DNS conflict → stop with a migration plan; never delete records | Routing ready and Cloudflare MX |
| `Destination address:` | Hands-on: user clicks or resends the link in the correct destination mailbox; keep the pending entry | `status` shows `verified=<timestamp>` |
| `Forwarding addresses` | Stop: show the conflicting rule; correct only the intended rule after approval | Every alias `[true]` to DEST_EMAIL |
| Inbound missing | **auto:** recheck gates 5–8 with `status` and `dig`; the resend is hands-on | Inbound arrival |
| `cmail send-as` (sending requested) ends with `paused without input` | Not a failure: the guide printed; relay its steps | Gate 9 sending checks |
| `Send FROM` + `paused without input` (older runtime without `send-as`) | Not a failure: every receiving stage passed; Gmail steps apply only when sending was requested | Gates 3–8 checks, then Gate 9 |
| Gmail App Password unavailable (sending requested) | Respect policy/Advanced Protection; no bypass; receiving is unaffected | Gate 9 sending stays BLOCKED |
| Gmail confirmation missing (sending requested) | **auto:** recheck gates 5–8 with `status` and `dig`; resend is hands-on | Confirmed alias |
| Outbound rejected/not delivered (sending requested) | Hands-on: smtp.gmail.com, 587/TLS, full username, current App Password; recipient Spam | Recipient arrival with exact From |

HTTP 401/403 is not propagation. HTTP 429 requires waiting before rechecking; 5xx
or transport errors are unknown service outcomes, not invalid credentials. For
uncertain writes inspect provider post-state before retrying. Do not rerun setup
in a tight loop, use DRY_RUN as a safety switch or delete state to start over.

If the user pasted a credential, avoid quoting it back. Advise revocation/rotation
in the provider, local replacement, and recheck the affected gate and its
dependents. Chat deletion alone is not credential rotation.

After three targeted unsuccessful repairs, report BLOCKED with the evidence,
what remains unknown, the exact next check and any administrator/support action.
For delayed DNS report PENDING without dependent routing/DNS writes. Resume at the
failed gate after revalidating changed prerequisites. Never say “setup complete”
while inbound delivery is unverified, or, when sending was requested, while Gmail
confirmation or outbound delivery is unverified.
