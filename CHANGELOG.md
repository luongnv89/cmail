# Changelog

## Unreleased

- Fix plain-text `cmail status` failing with "could not format routing state"
  when a rule has no forward destinations (drop, worker, catch-all, or no
  action). Rules now show `drop`, `worker NAME`, `no action`, and `catch-all`;
  JSON output is unchanged. Adds an offline regression.
- Add read-only `cmail list [--domain DOMAIN]`: every address on a domain, sorted,
  with its forward destinations (marked verified, unverified or unregistered),
  drop/worker actions, disabled rules, and the catch-all rule. Text and
  `--format json` output, completions, and offline regressions. `--domain` is now
  accepted by `setup` and `list` only.
- Make GoDaddy automation optional (#20). **Behavior change:** setup now defaults
  to `REGISTRAR=manual` and no longer requires `gddy` or GoDaddy authentication.
  It accepts an existing domain at any registrar. An already-active Cloudflare
  zone skips nameserver steps; a pending zone gets the exact assigned nameservers,
  DNS-record/DNSSEC migration warnings, and bounded activation polling. cmail
  never changes delegation in this mode. GoDaddy automation (domain picker,
  nameserver replacement, and the only path to a domain purchase) now requires
  `REGISTRAR=godaddy` or `cmail setup --registrar godaddy`. `doctor` checks gddy
  and GoDaddy authentication only in that mode, and `setup --dry-run` reports
  `registrar` and skips GoDaddy reads and blockers in manual mode. New
  `REGISTRAR` config key, `--registrar` option, completions, recovery guidance,
  and offline regressions.
- Add the `0.2.0-dev` CLI: strict arguments, command-level help/version, text/JSON
  reports, read-only doctor/status, full setup previews, literal configuration
  with environment precedence, private atomic config commands, secret stdin
  input, bash/zsh/fish completions, and complete local-checkout installation.
- Show actual elapsed setup time on success/failure and in preview JSON; include
  user input and provider verification waits. Bound provider requests/polling,
  require terminal stdin for guided commands, preserve provider confirmations,
  paginate rule inspection/reuse, and use GoDaddy's quote-token purchase flow
  with displayed prices, fees, and agreement titles/links before confirmation.
  Any charge requires the domain typed at an interactive terminal; piped input,
  flags, and environment variables can never approve a purchase.
- Add subprocess, configuration, terminal, timing, and installation regressions,
  `make test`/`make lint`, and macOS/Linux CLI CI. Document the current CLI and
  distinguish it from historical snapshot/legacy automation recipes. No release
  publication or live DNS/email verification is included.

- Fix the runtime mismatch in receive-only/optional-send quickstarts (#17).
  README, landing page and both setup guides now select the immutable reviewed
  development source snapshot `cda65f0554a870ed8079e93741a331918118acec`, check
  `./cmail help` for `send-as` before setup, and consistently use source `./cmail`
  and checkout `.env`. The unchanged installer still pins legacy v0.1.0, whose
  setup includes the Gmail guide and has no `send-as`. The mirrored setup skill
  accepts either current receiving summary + exit 0 or the trusted legacy
  post-receiving Gmail pause at gate 8; both require every requested rule enabled
  exactly once to the intended destination. Add offline prose-contract regressions;
  no new release, installer pin change or live verification is claimed.

- Receiving no longer requires Gmail or a Google account. `cmail setup` now
  forwards to any inbox you own and ends after the forwarding rules with a
  `Receiving is set up` summary (exit 0, no final Enter prompt). Gmail
  "Send mail as" moved to the optional `cmail send-as` command, which is not run
  by default. The DEST_EMAIL prompt, `.env.example`, destination-verification
  hints, README, site guides and the cmail-setup skill (2.1.0) now describe
  receiving as the default and sending as opt-in. The skill's pass 2 pipes only
  `y`, and it runs `send-as` only when the user asks to send. The README, landing
  page and setup guides lead with "custom-domain email in a few simple steps"
  (review source, `./cmail setup`, send a test), and the CLI help and setup banner
  state that sending is optional and only on request. The landing page adds a
  "Do I need Gmail or a Google account?" FAQ.

- cmail-setup skill 2.0.0 runs setup autonomously. The agent installs cmail and
  missing tools, writes non-secret config with a new `set_config.py` helper, reads
  config through `check_config.py --summary` (non-secret values only), runs a
  read-only preflight and then executes `cmail setup` itself with stdin closed.
  Stops are classified from setup's `Setup stopped at:` line and repaired from a
  step-keyed troubleshooting table. The agent asks only for missing values,
  hands-on steps (token entry, browser approvals, Gmail), nameserver replacement,
  existing MX/DNSSEC records, purchases, sudo or repeated failure; approval input
  is piped only for the nameserver confirmation after a closed-stdin pass.

- cmail-setup skill 1.1.0 opens with read-only context discovery (OS, source
  checkout, installed launcher, config presence, tools, request cues) instead of
  asking about setup mode, OS/access or installation status. Undetectable facts,
  such as browser access, stay unknown until a gate needs them. Discovery never
  executes cmail, reads `.env` or changes anything; consent and secret rules are
  unchanged.

- Add a framework-free cmail landing page and ordered first-time setup guides,
  with enabled native checkboxes, boolean-only browser progress, reset and
  resilient storage/no-JS handling. Document actual installer/skill paths,
  Cloudflare scopes, GoDaddy authentication/environment behavior, DNS safeguards,
  Gmail restrictions/confirmation and independent inbound/outbound checks.
  Flag Google's announced January 2027 third-party Send as removal. Include
  offline checklist/docs tests and optional real-browser regressions; no hosting,
  provider writes or live delivery verification is claimed.

- Add a portable cmail-setup agent skill with fail-closed verification gates,
  local-only credential guidance, consented staged provider setup and targeted
  failure/recheck instructions. Include a non-executing private config checker,
  offline tests and realistic evaluation cases; no live setup or skill publication.

- Add a user-local one-command installer for the complete pinned runtime with a
  generated launcher, private external config, staged validation and offline
  installer regressions. Installation does not run setup/doctor or provider calls.
- Document installation/verification/upgrades and the chosen upstream GitHub
  route, Homebrew prerequisites and actual distribution status. Installer release
  publication and Homebrew submission remain pending; no license is selected.

## v0.1.0 — 2026-10-07

First release of **cmail**, a Bash CLI for custom-domain email using Cloudflare Email Routing to receive mail in Gmail and guided Gmail “Send mail as” configuration for outbound mail.

### Features
- `./cmail setup`: guide dependency installation, GoDaddy browser OAuth or optional PAT authentication, domain selection or explicitly confirmed purchase, Cloudflare token and zone setup, confirmed nameserver replacement, zone activation, destination verification, and forwarding-rule creation. Save configuration for subsequent runs and finish with manual Gmail send-as instructions. @luongnv89
- `./cmail status`: report Cloudflare zone status, Email Routing state, destination verification, and forwarding rules using the saved zone ID or domain lookup. @luongnv89
- `./cmail doctor`: check required tools, GoDaddy auth status, and Cloudflare token activity; display configuration excluding lines containing `TOKEN`, `PAT`, or `SECRET`. This command can install missing dependencies and create or secure the local configuration file. @luongnv89

### Bug Fixes
The setup reliability and recovery repair is included once via squash commit `3064c8a` ([PR #1](https://github.com/luongnv89/cmail/pull/1), closing [issue #2](https://github.com/luongnv89/cmail/issues/2)). All fixes below are by @luongnv89.

- Read and normalize current GoDaddy nameservers, skip equivalent sets, require confirmation for real replacements, and stop on failed or malformed lookups.
- Correct Cloudflare Email Routing activation and forwarding-rule JSON; reuse enabled routing and reject disabled or conflicting rules rather than overwriting them or reporting them ready.
- Use the zone’s owning account for destination APIs, paginate destination lists, and reuse verified or pending destinations instead of registering duplicates.
- Support explicit `CF_ACCOUNT_ID` selection and refuse ambiguous account discovery; preserve HTTP/transport diagnostics and distinguish API failures from pending DNS propagation.
- Harden configuration permissions, loading, and saving; add step-specific recovery actions, uncertain-write warnings, and a reminder that DNS changes are not rolled back automatically.

### Documentation
- Document `CF_ZONE_ID` and `DRY_RUN`; the latter previews only the nameserver change, not the whole setup. @luongnv89
- Expand token permission/resource-scope instructions, stopped-setup recovery, DNS migration warnings, and Gmail App Password and manual mailbox verification guidance ([PR #1](https://github.com/luongnv89/cmail/pull/1)). @luongnv89

### Other Changes
- Rename the initial `s-mail` project and command to `cmail`. @luongnv89
- Add six offline regression suites with mocked GoDaddy and Cloudflare calls ([PR #1](https://github.com/luongnv89/cmail/pull/1)). @luongnv89

### New Contributors
- @luongnv89 authored the initial implementation and subsequent changes.

### Important Notes
- Domain registration costs money. Nameserver replacement can disrupt existing websites or mail; migrate DNS records first.
- Cloudflare forwards mail rather than providing a mailbox. Cloudflare destination verification and Gmail alias confirmation require user action; Gmail send-as and end-to-end delivery are not automatically verified.
- `status` can create or secure the local configuration file. Neither `status` nor `doctor` should be described as strictly read-only locally.

**First-release history**: https://github.com/luongnv89/cmail/commits/3064c8ad09f3f10dc3a67766a3c80e481e561366
