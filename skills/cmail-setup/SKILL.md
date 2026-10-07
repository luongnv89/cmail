---
name: "cmail-setup"
description: "Analyze cmail setup and guide installation, configuration and troubleshooting with verified gates and local-only secrets. Use for cmail setup or recovery. Don't use for other registrars, mail migrations, or sending campaigns."
compatibility: "macOS/Linux, Bash 3.2+, curl; jq and gddy for setup; Python 3 for the optional offline config check."
effort: "high"
metadata:
  version: "1.0.2"
  author: "Luong NGUYEN <luongnv89@gmail.com>"
---

# Verified cmail setup

Help a user set up GoDaddy → Cloudflare Email Routing → Gmail. Treat installation,
provider readiness and mail delivery as separate outcomes. Use this skill on an
explicit setup request, or offer it for cmail troubleshooting. Consent to receive
help is not consent to install software, spend money or change DNS.

## Repo Sync Before Edits (mandatory)

Apply this section only when modifying a source checkout, including its `.env`.
Do not modify installed runtime files. Ask before syncing or stashing a checkout;
if the user declines, stop that edit. Protect untracked files as well:

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
Preserve the stash; inspect `git stash list` and `git stash show -p stash@{0}`
privately (it may contain secrets). Do not force or silently discard changes.
In unattended mode, report BLOCKED instead of waiting for an answer.

## Select the mode

- **New setup:** start at gate 1.
- **Resume/troubleshoot:** ask which gate failed and what changed. Read
  `references/troubleshooting.md`; recheck prerequisites and the failed gate.
  Never trust a previous success after its inputs, account, domain or config changed.
- **Advice-only/no terminal access:** give the next check for the user to run.
  Record evidence as user-reported, not agent-observed. Missing results block progress.

## Safety and gate contract

Read `references/verification.md` before taking setup actions. Keep a small,
secret-free gate ledger in the conversation: gate, status, observation/source,
timestamp, failure cause, next action and recheck result. Do not persist it unless
requested. States are VERIFIED, FAILED, BLOCKED or PENDING. Only VERIFIED unlocks
the next gate. A preview, empty response, timeout, HTTP error or missing human
confirmation is never VERIFIED. Keep independent diagnostics separate from setup.

For each gate: check prerequisites → explain the action/side effects → obtain any
required consent → act → verify the stated outcome. On failure, explain the
observed failure (not an invented cause), propose one targeted repair, and repeat
the **same verification check**. Stop after three unsuccessful repairs or when
access/consent/evidence is unavailable. DNS propagation remains PENDING; wait and
recheck without replaying writes. Recheck downstream gates after an upstream change.

Never ask for raw secrets in chat, logs, screenshots, tool calls or shell arguments.
Ask only whether local entry succeeded. Do not read `.env` into model context,
print it, source it as a diagnostic, run with tracing, or collect full API responses.
If a secret is pasted, do not repeat it; advise revocation/rotation and local replacement.
Use browser-local entry and a private, unrecorded terminal/editor. Run secret-bearing
CLI operations in the user's local terminal, not captured agent tools: current cmail
provider helpers pass tokens to curl headers via process arguments. This skill cannot
make that runtime secret transport safer. Report sanitized statuses only.

Obtain specific consent before dependency installs/config edits, browser login,
zone creation, **DNS writes**, routing/rule/destination changes, verification emails,
test messages or **domain purchase** (exact domain, price and environment). Inventory
existing DNS/MX/TXT and DNSSEC/DS with the user first; require a migration/DS plan
before replacing delegation. Do not delete existing records, widen token scopes to
all accounts, disable security controls or infer consent from silence.

`cmail setup` is monolithic: it cannot pause for this skill's external verification
after every stage. **Do not run it as a gate orchestrator.** Guide staged dashboard
changes using the matrix instead. If the user independently runs setup, explain its
side effects first and still verify every gate; its exit code does not prove readiness.
`doctor` may install tools/create config and print non-secret-key values; do not
capture it as a read-only or reliably redacted check. `status` loads trusted config,
may create/chmod it, and its summary is not a complete verification verdict.
`DRY_RUN=1` only previews GoDaddy nameservers: other setup writes remain live.

## Gate 1 — Installation and tools

1. Ask OS, terminal availability and whether this is installed or a source checkout.
2. Check `command -v cmail`; also check the expected launcher if PATH is missing.
   Use `cmail help` (or a quoted absolute path / `./cmail help`), not an unsupported
   `cmail --version`. Confirm it exposes setup/status/doctor/help and uses the expected
   launcher/runtime. A different binary or broken library load fails this gate.
3. If missing, guide the reviewed checkout's **`bash install.sh`** after consent.
   Installer bootstrap needs Bash 3.2+, curl and standard utilities, not jq/gddy/git.
   It downloads a pinned runtime; it does not set up providers. v0.1.0 lacks the
   installer; no released remote bootstrap or `brew install cmail` is promised.
   Without a checkout, guide obtaining the upstream default-branch source from
   https://github.com/luongnv89/cmail, reviewing it, then entering its directory.
4. Explain default launcher `~/.local/bin/cmail`, runtimes `~/.local/share/cmail/`,
   config `~/.config/cmail/.env`. Installer overrides are absolute `CMAIL_BIN_DIR`,
   `CMAIL_DATA_DIR`, `CMAIL_CONFIG_DIR`; runtime override is `ENV_FILE`.
   Source execution defaults to checkout `.env`. Recheck resolved launcher/help;
   add `~/.local/bin` to the current PATH only with permission.
5. Check `command -v bash`, `curl --version`, `jq --version`, `gddy --version`
   and `gddy auth --help` / `gddy domain --help`. Help must support the needed
   domain/auth commands. List missing tools; guide the OS's existing brew/apt-get/
   pacman/dnf package manager for curl/jq after consent. Do not auto-install a
   package manager or grant sudo. For gddy use the official instructions at
   https://developer.godaddy.com/en/docs/api-users/cli/set-up and review its installer
   before local execution. Recheck each missing tool's discovery and help/version.

## Gate 2 — Inputs and private configuration

Read `references/configuration.md` now. Ask for non-secret DOMAIN, DEST_EMAIL,
ADDRESSES, intended Cloudflare account and GDDY_ENV (prod or ote), preferred config
path and existing-service impact. Ask whether the domain is owned; never turn an
access failure into a purchase. Explain forwarding vs mailbox and Gmail send limits.
Guide local config creation/editing and secret acquisition using that reference.
Verify config existence, ownership, permissions, literal assignments and required
fields with `scripts/check_config.py` (or local manual checks if Python is unavailable).
Its success proves file readiness only, not credentials or provider permissions.

## Gates 3–9 — Provider and mailbox verification

Follow gates 3–9 in `references/verification.md` in order. Each has its own
prerequisites, safe action, verification, failure repair and recheck. Guide local
OAuth/token checks, confirm domain/account access, then zone/delegation, active
routing, verified destination and exact enabled rules. For uncertain writes,
inspect current state before proposing a retry. No dependent writes during PENDING.
Finish manual Gmail alias confirmation and independent inbound/outbound delivery
for **every requested alias**. Pressing Enter or seeing a send queue is not proof.

## Completion report

After **each** gate (including failures), print this compact report:

```text
Gate <number> — <name>
Checks: <pass/fail for each required check>
Evidence: <sanitized observation, source, timestamp; observed or user-reported>
Criteria: <verified checks>/<required checks>
Result: PASS | FAIL | BLOCKED | PENDING
Repair / recheck: <specific action and exact check, or none>
```

At exit, put the main outcome first. Use COMPLETE only if all nine gates are
VERIFIED, including every alias's two delivery tests. Otherwise use PARTIAL or
BLOCKED and name the earliest incomplete gate. Include Evidence, Uncertainty and
Decision (specific approval needed, or “No approval needed.”) plus the next action.
Do not claim that suggested commands ran or a hypothetical setup succeeded.
A short text report is sufficient; no interactive dashboard is needed for one setup.

### Expected output

Example: `Result: BLOCKED — gate 4, zone access. Evidence: user-reported HTTP 403
at zone lookup. Uncertainty: write access and mail delivery untested. Decision:
No approval needed for read-only recheck. Next: verify intended Zone Resources
locally, then repeat the same lookup; do not create a duplicate zone.`

## Edge cases

- Unsupported registrar/mail service: stop at the scope boundary; do not improvise migration.
- No terminal, browser access or consent: give one next check and report BLOCKED.
- Pending/uncertain write: inspect post-state; do not replay writes or advance.
- Complex shell config or runtime-control keys: reject, simplify locally and recheck.

## Maintainer evaluation

Use `evals/evals.json` for offline scenario evaluations. Never use real credentials,
provider writes or mail sends for evaluation. Run the config/contract tests with
`python3 tests/skill_setup_test.py` from the source repository; they do not prove
live setup or agent adherence. Keep behavioral evals and human-understanding review
separate from these tests. Grade actual outputs for main result findability,
fact/assumption separation, claim-to-evidence traceability and clear next decision.
Ask human reviewers the same four questions; absent feedback means understanding
is unconfirmed, not passed. Provider steps need user interaction and cannot be
safely delegated away from that consent/evidence boundary. All references and
scripts travel with this directory;
no other skill or future documentation issue is required.
