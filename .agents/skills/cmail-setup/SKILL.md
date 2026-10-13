---
name: "cmail-setup"
description: "Set up, resume or troubleshoot cmail custom-domain email (domain at any registrar → Cloudflare Email Routing → any inbox; optional GoDaddy automation and Gmail send-as): runs cmail setup itself, asking only for missing input, secrets or risky approvals. Don't use for mail migrations or campaigns."
compatibility: "macOS/Linux; the cmail 0.4.0+ binary (no bash/curl/jq needed at runtime); dig for verification; gddy (and jq to filter its output) only for opt-in GoDaddy automation or legacy runtimes; Python 3 for the bundled config helpers."
effort: "high"
metadata:
  version: "3.0.0"
  author: "Luong NGUYEN <luongnv89@gmail.com>"
---

# Autonomous cmail setup

Use this skill when the user asks to set up, resume or troubleshoot cmail
(a domain at any registrar → Cloudflare Email Routing → any inbox the user owns;
GoDaddy automation is optional); you run the commands. Receiving takes a few
simple steps and needs no Google account: `cmail setup` sets up receiving only.
Current cmail (0.4.0+) is a single Rust binary, always invoked as `cmail ...`
(never `./cmail`); it needs no bash, curl or jq. Install it with
`brew install luongnv89/tap/cmail`, the one-line installer, or `cargo install`
(Gate 1). Historical runtimes differ: the bash v0.2.0 CLI and the reviewed
snapshot shipped as a `cmail` script plus `lib/`, and a legacy v0.1.0 runtime's
setup still includes the Gmail guide and lacks `send-as`; its post-receiving
pause is accepted only by gate 8's exact checks.
Ignore that guide for receive-only requests. Sending from the custom address
(`cmail send-as`, Gmail only) is optional and never the default: include it only
when the user asks to send, and do not ask for DEST_EMAIL to be Gmail otherwise.
Run `cmail setup` as the primary path: prepare its inputs, run it,
troubleshoot any failure, then verify the result gate by gate. A setup request is
consent for every **auto** action below. Ask only at a **stop**.

Follow the capability gate in `references/autonomous-run.md`. Current cmail
requires terminal stdin for setup (`requires terminal`, exit 2 otherwise), has a
full read-only `setup --dry-run` preview, and prints elapsed setup time. Its
default `REGISTRAR=manual` works at any registrar without gddy or GoDaddy login:
an already-active Cloudflare zone needs no nameserver step; a pending zone prints
the assigned nameservers, which the user replaces at their registrar (a
nameserver stop) while setup polls for Active. Use `--registrar godaddy` /
`REGISTRAR=godaddy` only when the domain is at GoDaddy and the user wants
automation; only that mode can offer a purchase. The previous snapshot and
legacy v0.1.0 always use GoDaddy. Historical closed/piped-stdin recipes remain
scoped to those older runtimes. Delivery must still be verified independently.

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
with `scripts/set_config.py`. You may run `cmail setup`, `cmail status`,
`cmail doctor --offline`, `cmail config check` and `cmail config show`: they load
config internally and never print secret values. Never trace a legacy bash runtime
(`bash -x`), never `cat`, `grep`, `source` or print the config, never collect full
API responses. If
a secret is pasted, do not repeat it; advise rotation and local replacement.

`cmail setup` is interactive and does not stop at every gate: run the preflight
in `references/autonomous-run.md` first. Current cmail runs setup through a
pseudo-terminal; only legacy runtimes use the closed-stdin two-pass rule.
`setup --dry-run` (or `DRY_RUN=1`) is a full read-only preview on current cmail
and never writes. `doctor` is read-only on current cmail (it never installs tools);
legacy bash runtimes' `doctor` could install tools, so avoid it there. Piped
`status`/`list`/`doctor` text is tab-separated records; parse `--format json`.
`status` exit 0 alone is not a verdict.

## Gate 1 — Installation and tools

1. Confirm an `unknown` target machine; rerun stale/`unknown` probes; never ask
   what a target-shell probe answers.
2. Recheck `command -v cmail`, Bash `type -t cmail` (zsh `whence -w cmail`) and
   the expected install location. **Before executing help**,
   reject aliases/functions or an unexpected executable. Inspect the selected file
   locally without executing it: require a user-controlled file/parents and a
   known provenance: the Homebrew keg (`brew --prefix`, `brew list cmail`), the
   installer's `~/.local/bin/cmail` (or `CMAIL_BIN_DIR`), `~/.cargo/bin/cmail`
   from `cargo install`, or a reviewed checkout's `target/release/cmail`.
   A marker or familiar help text alone is not authentication.
   If provenance cannot be established, stop BLOCKED; never run an unknown PATH
   match to discover whether it is trusted.
   Only then use the quoted trusted absolute path with `--version` and `help`
   (`cmail --version` prints `cmail <version>`; a legacy/snapshot bash runtime
   lacks it, so fall back to its `help`). Confirm help lists
   setup/status/list/forward/doctor/send-as/config; record whether `send-as` is
   listed to distinguish current and legacy completion evidence. A different
   binary or failed help fails this gate.
3. Select deliberate installation when cmail is missing or untrusted (auto, no
   sudo). In order of preference:
   - Homebrew available: `brew install luongnv89/tap/cmail`.
   - Otherwise the one-line installer, read first, never piped unread: download
     `https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh` to a
     file, read it, then run it (the README's
     `curl -fsSL https://raw.githubusercontent.com/luongnv89/cmail/main/install.sh | bash`
     runs the same script). It downloads a prebuilt release binary, verifies its
     SHA256 and installs to `~/.local/bin` (override with absolute
     `CMAIL_BIN_DIR`); it sets up no provider.
   - Rust toolchain or unsupported platform:
     `cargo install --git https://github.com/luongnv89/cmail`, or
     `cargo install --path .` inside a reviewed checkout.
   Historical: v0.1.0 lacks an installer; the bash-era `bash install.sh` pinned a
   v0.2.0 script runtime with a launcher, and the reviewed snapshot was run as
   `./cmail` from a checkout. Do not use them for new setups.
4. Config default: `${XDG_CONFIG_HOME:-~/.config}/cmail/.env`, i.e. normally
   `~/.config/cmail/.env`. Precedence: `--config` > `CMAIL_CONFIG` > `ENV_FILE` >
   default; the trusted binary's `cmail config path` prints the selected path
   without creating or reading it. Call cmail by its trusted absolute path; report
   the PATH line for the user's profile instead of editing it.
5. Tools: the cmail binary needs none. Check `dig -v` for the verification
   gates. Only for GoDaddy mode or a legacy/snapshot runtime, also check
   `gddy --version`, `gddy auth --help` / `gddy domain --help` and `jq --version`
   (used to filter gddy output); legacy bash runtimes additionally need
   `command -v bash`, curl and jq. Install missing tools with brew or another
   no-sudo package manager (sudo is a stop). For gddy, download
   https://github.com/godaddy/cli/releases/latest/download/install.sh to a file,
   read it, run it. Recheck each tool.

## Gate 2 — Inputs and private configuration

Follow the instructions in `references/configuration.md`: select the config, create it from
the trusted template if absent, and run `scripts/check_config.py --summary`.
Fill missing or template-default keys from the request with `scripts/set_config.py`;
ask one batched question only for values still missing. If the token is empty,
stop: give the token recipe, open the file in the user's editor and wait for
"done". Then the checker, `cmail config check`, private `bash -n` (where bash
exists) and the not-tracked check must pass.
Checker success proves the file, not credentials or provider access.

## Gates 3–9 — Run `cmail setup`, then verify

Follow the steps in `references/autonomous-run.md`: preflight, pass 1 in the
background (through a pseudo-terminal on current cmail; stdin closed only on
legacy runtimes), classify the stop with its table (`Setup stopped at:`), the
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

- Registrar other than GoDaddy: use current cmail's default manual mode and
  relay its printed nameservers; legacy runtimes need GoDaddy, so stop there.
- Unsupported mail service: stop at the scope boundary.
- Other MX, SPF or DS records: stop before pass 1, even if nameservers match.
- `DRY_RUN=1` or an empty required value: fix config first; never pipe answers.

## Maintainer evaluation

Evaluate with `evals/evals.json` per `evals/README.md`, never with real
credentials, provider writes or mail sends; absent human feedback means
understanding is unconfirmed.
