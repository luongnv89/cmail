---
name: "cmail-setup"
description: "Set up, resume or troubleshoot cmail custom-domain email (domain at any registrar → Cloudflare Email Routing → any inbox; optional GoDaddy automation and Gmail send-as): runs cmail setup itself, asking only for missing input, secrets or risky approvals. Don't use for mail migrations or campaigns."
compatibility: "macOS/Linux, Bash 3.2+, curl, jq, dig; gddy only for opt-in GoDaddy automation or legacy runtimes; Python 3 for the bundled config helpers."
effort: "high"
metadata:
  version: "2.3.0"
  author: "Luong NGUYEN <luongnv89@gmail.com>"
---

# Autonomous cmail setup

Use this skill when the user asks to set up, resume or troubleshoot cmail
(a domain at any registrar → Cloudflare Email Routing → any inbox the user owns;
GoDaddy automation is optional); you run the commands. With reviewed current source, receiving takes a few simple steps and
needs no Google account: `./cmail setup` sets up receiving only. The default
installer pins legacy v0.1.0, whose setup still includes the Gmail guide and lacks
`send-as`; its post-receiving pause is accepted only by gate 8's exact checks.
Ignore that guide for receive-only requests. Sending from the custom address
(`cmail send-as`, Gmail only) is optional and never the default: include it only
when the user asks to send, and do not ask for DEST_EMAIL to be Gmail otherwise.
Run `cmail setup` as the primary path: prepare its inputs, run it,
troubleshoot any failure, then verify the result gate by gate. A setup request is
consent for every **auto** action below. Ask only at a **stop**.

For the new `0.2.0-dev` CLI, use `bash install.sh --local` on the reviewed
checkout and follow the capability gate in `references/autonomous-run.md`.
It requires terminal stdin for setup, uses a full read-only preview, and prints
elapsed setup time. Its default `REGISTRAR=manual` works at any registrar
without gddy or GoDaddy login: an already-active Cloudflare zone needs no
nameserver step; a pending zone prints the assigned nameservers, which the
user replaces at their registrar (a nameserver stop) while setup polls for
Active. Use `--registrar godaddy` / `REGISTRAR=godaddy` only when the domain is
at GoDaddy and the user wants automation; only that mode can offer a purchase.
The previous snapshot and legacy v0.1.0 always use GoDaddy. Historical closed/piped-stdin recipes below remain scoped
to their older runtimes. Delivery must still be verified independently.

## Autonomy contract

**Auto — run without asking, then report the result:** read-only probes and
checks; trusted `cmail help`/`status`; installing cmail and missing tools without
sudo; creating the config and setting its non-secret keys; background
`gddy auth login` in GoDaddy mode (opens the user's browser); `cmail setup` passes the preflight
allows, including the zone, destination and rules setup creates; reruns after a
repair; opening dashboards, the config editor or (when sending was requested)
Gmail settings for the user.

**Stop — ask once, with evidence and a recommendation:**

- **Missing:** a value no probe or config holds (DOMAIN, DEST_EMAIL, ADDRESSES),
  the Cloudflare token, or a hands-on step: browser approval, verification link,
  delivery tests from another mailbox, Gmail send-as (only when sending was
  requested). Batch missing values into one
  question.
- **Super important:** nameserver replacement (by cmail in GoDaddy mode, or by
  the user at their registrar in manual mode); routing over existing
  non-Cloudflare MX or DNSSEC/DS records; domain purchase (GoDaddy mode only;
  exact domain, price, prod); anything needing sudo; deleting or overwriting DNS records, rules or a
  user-set config value; widening token scope; choosing among Cloudflare accounts.
- **Wrong:** an untrusted cmail binary, unexpected provider state, or a failure
  after three unsuccessful repairs.

Never infer approval from silence. In unattended mode, report BLOCKED at a stop.

## Repo Sync Before Edits (mandatory)

Apply this section only when modifying tracked files in a source checkout; a
gitignored config (`git check-ignore` succeeds) needs no sync. Do not modify
installed runtime files. Run it without asking; protect untracked files as well:

```bash
branch="$(git rev-parse --abbrev-ref HEAD)"
dirty=0
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "pre-sync: ${branch}" || exit 1
  dirty=1
fi
git fetch origin && git pull --rebase origin "$branch" || exit 1
if [ "$dirty" -eq 1 ]; then
  git stash pop || exit 1
fi
```

If origin is missing, sync fails or conflicts occur, stop and ask the user.
Preserve the stash and inspect it privately (it may contain secrets); never force
or silently discard changes. After a pull, redo Gate 1 provenance for the checkout.

## Discover context first

Open with discovery, not questions about mode, OS, terminal/browser access or
install status. With a shell tool, run the read-only probes in
`references/discovery.md` and print its context block first.
Discovery never executes a found `cmail`, never reads or sources `.env`, makes no
network/provider call and changes nothing; it verifies no gate.
Record an undetectable or failed probe, including browser access, as `unknown`.
Probes describe the agent's shell; if a user fact conflicts or a resume finds no
install, mark the target machine `unknown` until Gate 1.
Ask for an undetectable fact only when the **current gate** needs it.

## Select the mode

Infer the mode from request cues and discovery; do not ask for it.

- **New setup:** no failure/resume cue; start at gate 1.
- **Resume/troubleshoot:** read `references/troubleshooting.md`. Start at the named
  gate, else rerun read-only checks from gate 1 to the earliest unverified gate.
  Distrust earlier successes whose inputs, account, domain or config changed.
- **Advice-only (no shell tool):** follow `references/discovery.md`; give the user
  the same commands to run and treat missing results as blocking.

## Safety and gate contract

Read `references/verification.md` before acting. Keep a small, secret-free gate
ledger in the conversation: gate, status, evidence, timestamp, failure cause, next
action and recheck result. States are VERIFIED, FAILED, BLOCKED or PENDING.
Only VERIFIED unlocks the next gate. A preview, empty response, timeout, HTTP
error or missing human confirmation is never VERIFIED.

On failure, read the observed error (never invent a cause), apply one targeted
repair (auto actions yourself, others at a stop), then repeat the
**same verification check**. Stop after three unsuccessful repairs. DNS propagation stays
PENDING: recheck without replaying writes. Recheck downstream gates after an
upstream change.

**Secrets.** Never ask for raw secrets in chat, logs, screenshots or tool
arguments; the user types the token into the config in their own editor. Read
config only with `scripts/check_config.py --summary`; write non-secret keys only
with `scripts/set_config.py`. You may run `cmail setup` and `cmail status`: they
load config internally and redact the token. Never trace them (`bash -x`), never
`cat`, `grep`, `source` or print the config, never collect full API responses. If
a secret is pasted, do not repeat it; advise rotation and local replacement.

`cmail setup` is interactive and does not stop at every gate: run the preflight
in `references/autonomous-run.md` first, keep stdin closed, and pipe an answer only
by its two-pass rule. `DRY_RUN=1` previews nameservers only, then waits ~20
minutes; it is not a probe. Avoid `doctor` (it installs tools and prints config
lines). `status` exit 0 alone is not a verdict.

## Gate 1 — Installation and tools

1. Confirm an `unknown` target machine; rerun stale/`unknown` probes; never ask
   what a target-shell probe answers.
2. Recheck `command -v cmail`, Bash `type -t cmail` (zsh `whence -w cmail`) and
   the expected launcher. **Before executing help**, reject aliases/functions or
   an unexpected executable. Inspect the selected file locally without executing
   it: require user-controlled file/parents, reviewed source provenance or the
   known installer-generated launcher and its expected runtime/COMMIT.
   A marker or familiar help text alone is not authentication.
   If provenance cannot be established, stop BLOCKED; never run an unknown PATH
   match to discover whether it is trusted.
   Only then use the quoted trusted absolute path with `help` (or trusted
   `./cmail help`), not unsupported `cmail --version`. Confirm
   setup/status/doctor/help and library load; record whether `send-as` is listed
   to distinguish current-source and legacy completion evidence. A different
   binary or broken library load fails this gate.
3. Select source execution or deliberate legacy installation. For the latter,
   read and run the reviewed checkout's **`bash install.sh`** (needs Bash 3.2+ and
   curl; downloads a pinned runtime; sets up no provider).
   v0.1.0 lacks the installer; no remote bootstrap or `brew install cmail` exists.
   For the new receive-only/optional-send workflow, prefer the reviewed source
   snapshot in README instead of installing the legacy default. Clone upstream
   into a user-owned directory and fetch the pin explicitly; it need not be
   advertised on the default branch. Select the immutable feature revision:

   ```bash
   git clone https://github.com/luongnv89/cmail
   cd cmail
   git fetch origin cda65f0554a870ed8079e93741a331918118acec
   git checkout --detach cda65f0554a870ed8079e93741a331918118acec
   # Review cmail and lib/ before execution.
   ./cmail help
   ```

   This is a development source snapshot, not v0.1.0, until a compatible
   release/installer ships. Help must list `send-as` before this source workflow
   proceeds; stop if missing. Select this checkout's trusted absolute `cmail`
   path, not PATH `cmail`, and checkout `.env` (or explicitly reused ENV_FILE).
   For deliberate legacy installation, read the checkout's `install.sh`, then run
   it; the default pinned runtime does not gain features from the checkout.
4. Legacy installation defaults: launcher `~/.local/bin/cmail`, runtimes `~/.local/share/cmail/`,
   config `~/.config/cmail/.env`. Installer overrides are absolute `CMAIL_BIN_DIR`,
   `CMAIL_DATA_DIR`, `CMAIL_CONFIG_DIR`; runtime override is `ENV_FILE`.
   Call the launcher by absolute path; report the PATH line for the user's profile instead of editing it.
5. Check `command -v bash`, `curl --version`, `jq --version` and `dig -v`.
   Only for GoDaddy mode or a legacy/snapshot runtime, also check `gddy --version`
   and `gddy auth --help` / `gddy domain --help`. Install missing curl/jq
   with brew or another no-sudo package manager (sudo is a stop). For gddy,
   download https://github.com/godaddy/cli/releases/latest/download/install.sh
   to a file, read it, run it.
   Recheck each tool. Tools installed first keep setup's sudo installer from running.

## Gate 2 — Inputs and private configuration

Follow the instructions in `references/configuration.md`: select the config, create it from
the trusted template if absent, and run `scripts/check_config.py --summary`.
Fill missing or template-default keys from the request with `scripts/set_config.py`;
ask one batched question only for values still missing. If the token is empty,
stop: give the token recipe, open the file in the user's editor and wait for
"done". Then the checker, private `bash -n` and the not-tracked check must pass.
Checker success proves the file, not credentials or provider access.

## Gates 3–9 — Run `cmail setup`, then verify

Follow the steps in `references/autonomous-run.md`: preflight, pass 1 with stdin
closed in the background, classify the stop with its table (`Setup stopped at:`), the
nameserver stop, pass 2 only after approval. Relay hands-on steps (browser
approval, verification link) at once. Then verify gates 3–9 per
`references/verification.md`. Finish an independent inbound delivery test for
**every requested alias**; when sending was requested, also Gmail alias
confirmation and an outbound test per alias. A CLI exit or a send queue is not proof.

## Completion report

Print one line per verified gate, and this block at a stop, failure and exit:

```text
Gate <number> — <name>
Checks: <pass/fail for each required check>
Evidence: <sanitized observation, source, timestamp; observed or user-reported>
Criteria: <verified checks>/<required checks>
Result: PASS | FAIL | BLOCKED | PENDING
Repair / recheck: <specific action and exact check, or none>
```

At exit, put the main outcome first: COMPLETE only if all nine gates are VERIFIED,
including every alias's inbound test (and outbound test when sending was
requested); otherwise PARTIAL or BLOCKED naming the
earliest incomplete gate. Include Evidence, Uncertainty, Decision (approval needed,
or “No approval needed.”) and the next action. List what you ran; never claim an
unrun command ran. A short text report suffices; no dashboard.

### Expected output

Example:

```text
Result: BLOCKED — gate 5, nameserver approval. Evidence: pass 1 stopped at
"aborted before nameserver change"; GoDaddy NS ns1/ns2.domaincontrol.com → Cloudflare
ada/bob.ns.cloudflare.com; MX none, DS none, A record present. Decision: approve
the switch after copying the A record to Cloudflare; then pass 2 runs.
```

## Edge cases

- Registrar other than GoDaddy: use the current CLI's default manual mode and
  relay its printed nameservers; legacy runtimes need GoDaddy, so stop there.
- Unsupported mail service: stop at the scope boundary.
- Other MX, SPF or DS records: stop before pass 1, even if nameservers match.
- `DRY_RUN=1` or an empty required value: fix config first; never pipe answers.

## Maintainer evaluation

Evaluate with `evals/evals.json` per `evals/README.md`, never with real
credentials, provider writes or mail sends; absent human feedback means
understanding is unconfirmed.
