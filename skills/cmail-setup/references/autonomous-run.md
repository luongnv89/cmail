# Running `cmail setup` autonomously

## Current CLI capability gate (0.2.0)

After Gate 1 provenance, check trusted help/version. If help advertises the full
`setup --dry-run` plan and `config` commands, use this section for the new runtime;
the closed/piped-stdin passes below apply only to the previous reviewed snapshot
and legacy v0.1.0. Never infer runtime behavior from the installer's location.

Install a reviewed new checkout with `bash install.sh --local`, then use the
same selected configuration for every command (`--config` or `ENV_FILE`). Run
`doctor --offline`, `config check`, and `setup --dry-run --format json` before
writes. Preview blockers need attention; a preview exit 0 alone is not readiness.
The preview's `data.registrar` is `manual` by default: no gddy, no GoDaddy
blocker, and its `nameservers` action is `ready` (zone active) or `manual` (set
the listed nameservers at the registrar). With `REGISTRAR=godaddy`, the GoDaddy
delegation read needs an existing PAT to prevent automatic OAuth; without one,
inspect delegation independently under the existing gate rules.
The full preview performs no provider/config writes, purchases, or authentication.

Actual setup requires terminal stdin. Use the tool's pseudo-terminal option,
run in the background, and relay prompts while monitoring output. Send a
nameserver/purchase confirmation only after the applicable evidence and user
approval are recorded. In manual mode, `Registrar nameservers` prints the
assigned set and DNS/DNSSEC warnings without prompting; relay them as the
nameserver stop. The user changes them at their registrar while setup polls;
if the wait ends, rerun setup after the change. Do not pipe blanket `y` or apply the historical closed-
stdin recipe to this runtime. Browser approval and destination verification
remain hands-on. Missing tools produce installation instructions; install them
under the existing skill authorization before rerunning. In GoDaddy mode,
`--no-browser` setup requires a PAT; guided setup supports OAuth.

The summary includes elapsed wall time and configured receiving addresses.
This includes user/provider waits, and does not replace Gate 9's delivery test.
Recovery still names the failed step; use its next action and rerun through a
terminal after repair. Use this capability gate for current-runtime recovery.

## Previous snapshot / legacy runtime recipes

Reviewed current-source `./cmail setup` runs these stages in order, saving
progress in config, and skips work already done: dependencies → configuration prompts (DEST_EMAIL, ADDRESSES)
→ GoDaddy auth → domain choice → Cloudflare token → zone create/reuse →
nameserver replacement (confirmation prompt) → wait for Active (polls ~20 min)
→ enable Email Routing → destination registration (polls ~10 min for the link
click) → forwarding rules → `Receiving is set up` summary, then exit 0. Setup
never runs the Gmail guide: sending is the separate, optional `cmail send-as`
command (waits for Enter), used only when the user asked to send from the
custom address. The default installer pins legacy v0.1.0 instead: after the
same receiving stages it runs the Gmail guide, which pauses without input.
Record trusted offline help at gate 1; never assume installation selects the
checkout's newer behavior. For receive-only use, ignore the legacy Gmail guide
and verify gate 8's exact post-receiving checkpoint and status rules.

Every prompt reads stdin. With stdin closed, a prompt fails and setup exits with
`Setup stopped at: <step>`, so a closed-stdin run never answers a question. When
nameservers already match, setup asks nothing and continues through routing,
destination and rules; the preflight decides whether that is acceptable.

## Inputs every run uses

```bash
cfg="<selected config>"             # from Gate 2; always pass it as ENV_FILE
launcher="<trusted absolute path>"  # installed launcher or checkout ./cmail
skill="<this skill's directory>"
log="$(mktemp "${TMPDIR:-/tmp}/cmail-setup.XXXXXX")"   # mode 600, new per pass
```

Always run as `DRY_RUN=0 ENV_FILE="$cfg" "$launcher" setup`: a checkout defaults
to its own `.env`, the installed launcher to its baked path, and an exported
`DRY_RUN` would otherwise leak in. The helpers, the checker and the run must touch
the same file.

## Preflight (read-only, before every pass)

1. `python3 "$skill/scripts/check_config.py" --summary "$cfg"` exits 0 and prints
   `READY:` (exit 3 means NOT READY: return to Gate 2; an empty value would make
   setup prompt). DRY_RUN must be absent or `0`: with `1`, setup previews, skips
   the confirmation and waits on a zone that cannot activate. Fix it with
   `set_config.py --replace "$cfg" DRY_RUN=0`.
2. Tools: `command -v curl jq gddy dig` all found (Gate 1), so setup's own
   installer path never runs.
3. GoDaddy auth (skip when the summary shows GDDY_PAT set: setup exports it, and
   its nameserver step performs the domain read):
   `gddy auth status --json 2>/dev/null | jq -c '[.data[]? | {env, expired}]'`.
   With no unexpired entry for GDDY_ENV, run `gddy auth login --env "$GDDY_ENV"`
   in the background, tell the user a browser window needs their approval, and
   poll the status line.
4. Ownership and delegation:
   `gddy domain get "$DOMAIN" --env "$GDDY_ENV" --json | jq -c '{status: .data.status, nameServers: .data.nameServers}'`.
   Never print the unfiltered response (it holds contact data). Status must be
   active. If the read fails, run
   `gddy domain list --env "$GDDY_ENV" --json | jq -r '.data[] | .domain // .name'`:
   list fails or shows the domain → auth/account trouble (Gate 3); list succeeds
   without it → wrong account or unowned. Unowned is a stop: run `gddy domain available` and
   `gddy domain quote`, then ask with the exact price; buy only on explicit approval.
   The purchase prompt requires the exact domain typed at the terminal; type it only
   after the user approves that domain and price in this conversation.
5. Public DNS inventory:

   ```bash
   for t in NS MX TXT DS A AAAA; do printf '%s: ' "$t"; dig +short "$t" "$DOMAIN" | tr '\n' ' '; echo; done
   dig +short CNAME "www.$DOMAIN"
   ```

**Stop before pass 1** when the inventory shows MX records that are not
`route*.mx.cloudflare.net`, an SPF TXT (`v=spf1`) that does not include
`_spf.mx.cloudflare.net`, or DS records: routing would conflict with existing mail,
and delegation needs a DNSSEC plan. Show the records and recommend a plan. On
approval, record those exact records and the decision in the gate ledger; later
preflights treat the same records as approved and stop again only for new or
changed records. Existing records stay visible until delegation changes, so
re-asking about them is a defect.

## Running a pass

Run every pass in the background — pass 2 includes the ~20-minute activation and
~10-minute destination polls, and a foreground timeout would kill it before its
recovery message. While it runs, read the log tail and relay hands-on steps at
once: `verification email sent`, `still unverified`, browser approval. Never run
two setup passes at the same time.

**Pass 1 — stdin closed:**

```bash
DRY_RUN=0 ENV_FILE="$cfg" "$launcher" setup </dev/null >"$log" 2>&1; echo "exit=$?" >>"$log"
```

Pass 1 may create the Cloudflare zone and save CF_ZONE_ID before it stops.

## Classify the stop

Check rows in order; the first match wins.

| Log evidence | Meaning | Next |
|---|---|---|
| `aborted before nameserver change` | Nameservers differ; setup reached the confirmation | Stop: nameserver approval |
| `Receiving is set up` and `exit=0` | Every API stage succeeded | Verify gates 3–8, then Gate 9 |
| Exact `Setup stopped at: Send FROM your custom address (manual, ~5 min)` with `Gmail guide paused without input` after all receiving stages in the same pass | Trusted legacy runtime whose offline `help` lacks `send-as`: receiving API stages succeeded, then it showed the Gmail guide; nonzero exit is expected at this pause, not before it | Verify gates 3–8, then Gate 9; Gmail steps still apply only when sending was requested |
| `zone still` and the log shows `nameservers set` or `already point at Cloudflare` | Delegation PENDING | Wait; rerun pass 1 later (matching nameservers skip the write) |
| `zone status` … `needs attention` | Zone moved, deleted or blocked | Stop (wrong): show the status |
| `not verified after about 10 minutes` | Destination link not clicked | Stop (hands-on): user clicks the link; rerun pass 1 |
| Any other `Setup stopped at: <step>` | Failure at that step | `troubleshooting.md` row for the step |

Report only the step, the `ERROR:` line and sanitized values; never paste the log.

## Nameserver stop and pass 2

Ask with: current GoDaddy nameservers, the Cloudflare set from the log's
`desired nameservers` line, the log's `creating zone … in account <id>` line when
pass 1 created the zone (so the user can confirm the account), the public DNS
inventory, which records must exist in
Cloudflare first so web or other services keep working, and a recommendation. On
approval of that exact set, run pass 2 in the background with a new log:

```bash
printf 'y\n' | DRY_RUN=0 ENV_FILE="$cfg" "$launcher" setup >"$log" 2>&1; echo "exit=$?" >>"$log"
```

Two-pass rule: pipe this input only when pass 1 ended at
`aborted before nameserver change`, the preflight still passes, and the approval
is recent. Then the `y` answers the nameserver confirmation, the only prompt left.
Never pipe `yes` or answers to any other prompt:
an unexpected prompt (token, domain, registration) would take the `y` as its
value. After pass 2, confirm the log's `desired nameservers` line still matches
the approved set and that it shows `nameservers set`; report any mismatch. Classify
pass 2 with the same table.

## After the automated stages

Run `ENV_FILE="$cfg" "$launcher" status` and the checks in `verification.md` for
gates 3–8. Put that exact `status` command in the final report: with a per-domain
config, a plain `cmail status` reads a different file. Then drive Gate 9: the
inbound test for every alias.

Only when the user asked to **send** from the custom address (and DEST_EMAIL is a
Gmail/Google account), print the guide with
`ENV_FILE="$cfg" "$launcher" send-as </dev/null`. It ends with
`Gmail guide paused without input`, which is expected, not a failure. Relay its
steps, open `https://mail.google.com/mail/u/0/#settings/accounts` and
`https://myaccount.google.com/apppasswords` for the user, and add the sending
checks to Gate 9. On an older runtime whose `help` does not list `send-as`, relay
the Gate 9 sending steps from `verification.md` instead. Without that request, do
not mention App Passwords or run `send-as`.
