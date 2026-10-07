# Changelog

## Unreleased

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
